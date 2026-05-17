"""Core business logic for Devpost CLI and MCP server."""

import asyncio
import json
import os
import random
import re
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .cache import (
    CacheManager,
    make_hackathon_key,
    make_list_key,
    make_project_key,
    make_projects_key,
    make_rules_key,
    make_scrape_key,
    make_evaluate_key,
    make_search_projects_key,
    make_popular_projects_key,
    make_built_with_key,
    make_featured_projects_key,
    make_participants_key,
    make_resources_key,
    make_updates_key,
    make_discussions_key,
    parse_days_left,
    parse_prize_amount,
)
from .logging_config import get_logger
from .session import (
    clear_session,
    get_credentials,
    load_session,
    save_credentials,
    save_session,
)

logger = get_logger("core")

BASE_URL = "https://devpost.com"
API_BASE = "https://devpost.com/api"

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0
RETRY_STATUS_CODES = {429, 502, 503, 504}

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", re.IGNORECASE)
_DEVPOST_URL_RE = re.compile(r"^https://([a-z0-9-]+\.)?devpost\.com/", re.IGNORECASE)


class DevpostError(Exception):
    """User-friendly error with code and message."""

    def __init__(self, message: str, code: str = "ERROR", status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def validate_slug(slug: str) -> str:
    """Validate and return a hackathon slug."""
    if not slug or not _SLUG_RE.match(slug):
        raise DevpostError(
            f"Invalid hackathon slug: '{slug}'. Must contain only letters, numbers, and hyphens.",
            code="VALIDATION_ERROR",
        )
    return slug


def validate_devpost_url(url: str) -> str:
    """Validate and return a Devpost URL."""
    if not url or not _DEVPOST_URL_RE.match(url):
        raise DevpostError(
            f"Invalid Devpost URL: '{url}'. Must be a https://*.devpost.com/ URL.",
            code="VALIDATION_ERROR",
        )
    return url


def clean_html(text: str) -> str:
    """Strip HTML tags from text."""
    if not text:
        return text
    return re.sub(r"<[^>]+>", "", text)


def _extract_section(
    soup: BeautifulSoup,
    result: dict,
    field: str,
    heading_patterns: list[str],
) -> None:
    """Extract list items following headings matching any pattern into result[field]."""
    items = []
    for heading in soup.find_all(re.compile(r'^h[1-6]$', re.I)):
        text = heading.get_text(strip=True).lower()
        if any(re.search(p, text) for p in heading_patterns):
            sibling = heading.find_next_sibling()
            while sibling and sibling.name not in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                if sibling.name in ('ul', 'ol'):
                    for li in sibling.find_all('li'):
                        li_text = li.get_text(strip=True)
                        if li_text and len(li_text) < 500:
                            items.append(li_text)
                elif sibling.name == 'p':
                    p_text = sibling.get_text(strip=True)
                    if p_text and len(p_text) < 500:
                        items.append(p_text)
                elif sibling.name == 'table':
                    for row in sibling.find_all('tr'):
                        row_text = row.get_text(strip=True)
                        if row_text and len(row_text) < 500:
                            items.append(row_text)
                sibling = sibling.find_next_sibling()
    result[field] = list(dict.fromkeys(items))[:30]


def _signal_time_pressure(days_left: Optional[float], status: str) -> dict:
    if status == "ended":
        return {"level": "closed", "days_left": None, "detail": "Submission period has ended"}
    if days_left is None:
        return {"level": "unknown", "days_left": None, "detail": "Deadline unknown"}
    if days_left <= 1:
        return {"level": "critical", "days_left": days_left, "detail": f"Closing in {days_left:.0f} day(s)"}
    if days_left <= 5:
        return {"level": "high", "days_left": days_left, "detail": f"{days_left:.0f} days left"}
    if days_left <= 14:
        return {"level": "medium", "days_left": days_left, "detail": f"{days_left:.0f} days left"}
    return {"level": "low", "days_left": days_left, "detail": f"{days_left:.0f} days left"}


def _signal_prize_density(prize_per_project: float) -> dict:
    if prize_per_project >= 5000:
        return {"level": "high", "per_project": prize_per_project, "detail": f"${prize_per_project:,.0f} per project — very high"}
    if prize_per_project >= 1000:
        return {"level": "medium", "per_project": prize_per_project, "detail": f"${prize_per_project:,.0f} per project"}
    if prize_per_project > 0:
        return {"level": "low", "per_project": prize_per_project, "detail": f"${prize_per_project:,.0f} per project — low"}
    return {"level": "none", "per_project": 0, "detail": "No cash prize"}


def _signal_competition_density(registrants_per_prize: float) -> dict:
    if registrants_per_prize >= 500:
        return {"level": "high", "registrants_per_prize": registrants_per_prize, "detail": f"{registrants_per_prize:.0f} registrants per prize — very competitive"}
    if registrants_per_prize >= 100:
        return {"level": "medium", "registrants_per_prize": registrants_per_prize, "detail": f"{registrants_per_prize:.0f} registrants per prize"}
    return {"level": "low", "registrants_per_prize": registrants_per_prize, "detail": f"{registrants_per_prize:.0f} registrants per prize — less crowded"}


def _signal_submission_gap(registrants: int, submissions: int, status: str) -> dict:
    if status == "ended":
        return {"level": "closed", "detail": f"{submissions} submissions from {registrants} registrants"}
    if registrants > 100 and submissions == 0:
        return {"level": "wide_open", "detail": f"{registrants} registrants, 0 submissions yet — wide open"}
    if registrants > 0 and submissions > 0:
        ratio = submissions / registrants
        if ratio < 0.1:
            return {"level": "wide_open", "detail": f"Only {submissions} submissions from {registrants} registrants ({ratio:.0%})"}
        if ratio < 0.3:
            return {"level": "moderate", "detail": f"{submissions} submissions from {registrants} registrants ({ratio:.0%})"}
        return {"level": "filling", "detail": f"{submissions} submissions from {registrants} registrants ({ratio:.0%})"}
    return {"level": "unknown", "detail": f"{registrants} registrants, {submissions} submissions"}


def _signal_theme_fit(skills: Optional[list[str]], sponsor_apis: list[str], themes: list[str]) -> dict:
    if not skills:
        return {"level": "unknown", "detail": "No skills provided (use --skills to get theme-fit signal)"}
    skills_lower = {s.lower().strip() for s in skills}

    matched = set()
    all_tech = sponsor_apis + themes
    for tech in all_tech:
        tech_lower = tech.lower()
        for skill in skills_lower:
            if skill in tech_lower or tech_lower in skill:
                matched.add(skill)

    if matched:
        return {"level": "high", "matched_skills": sorted(matched), "detail": f"Your skills match: {', '.join(sorted(matched))}"}
    return {"level": "low", "matched_skills": [], "detail": "No direct skill match with themes/sponsor APIs"}


def _compute_verdict(signals: dict, status: str) -> tuple[str, str]:
    if status == "ended":
        return "Skip", "Submission period has ended"

    scores = {"enter": 0, "skip": 0}
    reasons = []

    tp = signals.get("time_pressure", {})
    if tp.get("level") == "critical":
        scores["skip"] += 2
        reasons.append("deadline is critical")
    elif tp.get("level") == "high":
        scores["skip"] += 1
        reasons.append("deadline is tight")

    pd = signals.get("prize_density", {})
    if pd.get("level") == "high":
        scores["enter"] += 2
        reasons.append("high prize density")
    elif pd.get("level") == "medium":
        scores["enter"] += 1
    elif pd.get("level") in ("low", "none"):
        scores["skip"] += 1
        reasons.append("low/no prize")

    cd = signals.get("competition_density", {})
    if cd.get("level") == "low":
        scores["enter"] += 1
        reasons.append("low competition")
    elif cd.get("level") == "high":
        scores["skip"] += 1

    sg = signals.get("submission_gap", {})
    if sg.get("level") == "wide_open":
        scores["enter"] += 2
        reasons.append("submission gap — wide open")
    elif sg.get("level") == "filling":
        scores["skip"] += 1

    tf = signals.get("theme_fit", {})
    if tf.get("level") == "high":
        scores["enter"] += 1
        reasons.append("good skill/theme fit")
    elif tf.get("level") == "low" and tf.get("detail", "") != "No skills provided (use --skills to get theme-fit signal)":
        scores["skip"] += 1

    if scores["enter"] > scores["skip"] + 1:
        return "Enter", f"Favorable: {', '.join(reasons[:3])}"
    if scores["skip"] > scores["enter"] + 1:
        return "Skip", f"Unfavorable: {', '.join(reasons[:3])}"
    return "Maybe", f"Mixed signals: {', '.join(reasons[:3])}"


class DevpostClient:
    """HTTP client for Devpost API and scraping."""

    def __init__(self, headed: bool = False, use_cache: bool = True) -> None:
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/html",
            },
            timeout=30.0,
            follow_redirects=True,
        )
        self.headed = headed
        self.use_cache = use_cache
        self._cache = CacheManager() if use_cache else None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False

    async def close(self) -> None:
        await self.client.aclose()

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with exponential backoff retry on transient errors."""
        last_exc: Optional[Exception] = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await self.client.request(method, url, **kwargs)
                if resp.status_code in RETRY_STATUS_CODES:
                    if attempt < MAX_RETRIES:
                        delay = RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                        if resp.status_code == 429:
                            retry_after = resp.headers.get("Retry-After")
                            if retry_after:
                                try:
                                    delay = float(retry_after)
                                except ValueError:
                                    pass
                        logger.debug("HTTP %d, retrying in %.1fs (attempt %d/%d)", resp.status_code, delay, attempt + 1, MAX_RETRIES)
                        await asyncio.sleep(delay)
                        continue
                    status = resp.status_code
                    if status == 429:
                        raise DevpostError("Rate limited by Devpost (HTTP 429). Try again later.", code="RATE_LIMITED", status_code=status)
                    if status == 404:
                        raise DevpostError(f"Resource not found (HTTP 404): {url}", code="NOT_FOUND", status_code=status)
                    if status in (502, 503, 504):
                        raise DevpostError(f"Devpost is temporarily unavailable (HTTP {status}). Try again later.", code="SERVER_ERROR", status_code=status)
                    resp.raise_for_status()
                if resp.status_code == 404:
                    raise DevpostError(f"Resource not found (HTTP 404): {url}", code="NOT_FOUND", status_code=404)
                if resp.status_code == 403:
                    raise DevpostError(f"Access denied (HTTP 403): {url}", code="ACCESS_DENIED", status_code=403)
                if resp.status_code >= 500:
                    raise DevpostError(f"Server error (HTTP {resp.status_code}): {url}", code="SERVER_ERROR", status_code=resp.status_code)
                if resp.status_code >= 400:
                    raise DevpostError(f"HTTP {resp.status_code} error for {url}", code="HTTP_ERROR", status_code=resp.status_code)
                return resp
            except httpx.TimeoutException as e:
                last_exc = e
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.debug("Request timeout, retrying in %.1fs (attempt %d/%d)", delay, attempt + 1, MAX_RETRIES)
                    await asyncio.sleep(delay)
                    continue
                raise DevpostError(f"Request timed out after {MAX_RETRIES} retries: {url}", code="TIMEOUT") from e
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in RETRY_STATUS_CODES and attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.debug("HTTP %d, retrying in %.1fs (attempt %d/%d)", status, delay, attempt + 1, MAX_RETRIES)
                    await asyncio.sleep(delay)
                    continue
                if status == 404:
                    raise DevpostError(f"Resource not found (HTTP 404): {url}", code="NOT_FOUND", status_code=status) from e
                if status == 429:
                    raise DevpostError("Rate limited by Devpost (HTTP 429). Try again later.", code="RATE_LIMITED", status_code=status) from e
                raise DevpostError(f"HTTP {status} error for {url}: {e.response.text[:200]}", code="HTTP_ERROR", status_code=status) from e
            except httpx.ConnectError as e:
                last_exc = e
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.debug("Connection error, retrying in %.1fs (attempt %d/%d)", delay, attempt + 1, MAX_RETRIES)
                    await asyncio.sleep(delay)
                    continue
                raise DevpostError(f"Could not connect to Devpost: {url}", code="NETWORK_ERROR") from e
        raise DevpostError(f"Request failed after {MAX_RETRIES} retries: {url}", code="NETWORK_ERROR")

    async def list_hackathons(
        self,
        limit: int = 20,
        open_state: Optional[str] = None,
        sort_by: str = "recently-added",
        query: Optional[str] = None,
    ) -> list[dict]:
        """List hackathons via API.

        Note: The API open_state filter is broken for non-open states.
        When requesting 'ended' (closed) hackathons, we page through
        results and filter client-side.
        """
        api_state = open_state
        if api_state == "closed":
            api_state = "ended"

        if api_state in ("ended", "closed"):
            return await self._list_ended_hackathons(limit=limit, query=query)

        cache_key = make_list_key(state=open_state, sort_by=sort_by, query=query, limit=limit)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        params: dict = {"limit": limit, "sort_by": sort_by}
        if open_state:
            params["open_state"] = open_state
        if query:
            params["q"] = query

        resp = await self._request_with_retry(
            "GET",
            f"{API_BASE}/hackathons",
            params=params,
            headers={"Accept": "application/json"},
        )
        data = resp.json()
        hackathons = data.get("hackathons", [])

        for h in hackathons:
            if h.get("prize_amount"):
                h["prize_amount"] = clean_html(h["prize_amount"])
            h["ends_at"] = h.get("time_left_to_submission") or h.get("submission_period_dates")

        if self._cache:
            self._cache.set(cache_key, hackathons)

        return hackathons

    async def _list_ended_hackathons(
        self,
        limit: int = 20,
        query: Optional[str] = None,
    ) -> list[dict]:
        """List ended (closed) hackathons by paging through the API.

        The Devpost API does not support filtering by open_state=ended,
        so we page through results starting from later pages where
        ended hackathons typically appear.
        """
        cache_key = make_list_key(state="ended", sort_by="recently-added", query=query, limit=limit)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        ended = []

        for start_page in [18, 15, 20, 25, 30, 35, 40, 1, 5, 10]:
            if len(ended) >= limit:
                break
            try:
                resp = await self._request_with_retry(
                    "GET",
                    f"{API_BASE}/hackathons",
                    params={"page": start_page, "limit": 9, "sort_by": "recently-added"},
                    headers={"Accept": "application/json"},
                )
                data = resp.json()
                hackathons = data.get("hackathons", [])
                if not hackathons:
                    continue
                for h in hackathons:
                    if h.get("open_state") == "ended":
                        if h.get("prize_amount"):
                            h["prize_amount"] = clean_html(h["prize_amount"])
                        h["ends_at"] = h.get("time_left_to_submission") or h.get("submission_period_dates")
                        if query:
                            q = query.lower()
                            title = (h.get("title") or "").lower()
                            tagline = (h.get("tagline") or "").lower()
                            if q not in title and q not in tagline:
                                continue
                        ended.append(h)
            except DevpostError:
                continue

        page = 19
        max_scan = 60
        while len(ended) < limit and page <= max_scan:
            try:
                resp = await self._request_with_retry(
                    "GET",
                    f"{API_BASE}/hackathons",
                    params={"page": page, "limit": 9, "sort_by": "recently-added"},
                    headers={"Accept": "application/json"},
                )
                data = resp.json()
                hackathons = data.get("hackathons", [])
                if not hackathons:
                    break
                has_ended = False
                for h in hackathons:
                    if h.get("open_state") == "ended":
                        has_ended = True
                        if h.get("prize_amount"):
                            h["prize_amount"] = clean_html(h["prize_amount"])
                        h["ends_at"] = h.get("time_left_to_submission") or h.get("submission_period_dates")
                        if query:
                            q = query.lower()
                            title = (h.get("title") or "").lower()
                            tagline = (h.get("tagline") or "").lower()
                            if q not in title and q not in tagline:
                                continue
                        ended.append(h)
                if not has_ended:
                    break
            except DevpostError:
                break
            page += 1

        ended = ended[:limit]

        seen_urls = set()
        deduped = []
        for h in ended:
            url = h.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                deduped.append(h)

        if self._cache:
            self._cache.set(cache_key, deduped, ttl=1800)

        return deduped

    async def get_hackathon_by_slug(self, slug: str) -> Optional[dict]:
        """Get hackathon by URL slug."""
        validate_slug(slug)
        cache_key = make_hackathon_key(slug)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        resp = await self._request_with_retry(
            "GET",
            f"{API_BASE}/hackathons",
            params={"url": slug, "limit": 1},
            headers={"Accept": "application/json"},
        )
        data = resp.json()
        hackathons = data.get("hackathons", [])
        if not hackathons:
            return None

        h = hackathons[0]
        if h.get("prize_amount"):
            h["prize_amount"] = clean_html(h["prize_amount"])
        h["ends_at"] = h.get("time_left_to_submission") or h.get("submission_period_dates")

        if self._cache:
            self._cache.set(cache_key, h)

        return h

    async def get_hackathon_details(self, hackathon_url: str) -> dict[str, Any]:
        """Scrape detailed hackathon info from its page."""
        validate_devpost_url(hackathon_url)
        resp = await self._request_with_retry("GET", hackathon_url)

        soup = BeautifulSoup(resp.text, "html.parser")

        title = self._get_meta(soup, "og:title") or self._get_meta(soup, "twitter:title")
        description = (
            self._get_meta(soup, "og:description")
            or self._get_meta(soup, "description")
            or self._get_meta(soup, "twitter:description")
        )
        image = self._get_meta(soup, "og:image")

        rules_url = f"{hackathon_url.rstrip('/')}/rules" if not hackathon_url.endswith("/rules") else hackathon_url

        return {
            "title": title,
            "description": description,
            "image_url": image,
            "url": hackathon_url,
            "rules_url": rules_url,
        }

    async def scrape_hackathon_page(self, url: str) -> dict[str, Any]:
        """Deep scrape a hackathon page to extract all available info."""
        validate_devpost_url(url)
        cache_key = make_scrape_key(url)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        result = {"success": False, "url": url, "steps": [], "data": {}}

        try:
            result["steps"].append(f"Fetching {url}")
            resp = await self._request_with_retry("GET", url)

            soup = BeautifulSoup(resp.text, "html.parser")
            data = {}

            scripts = soup.find_all("script")
            for script in scripts:
                text = script.string or ""
                if "__INITIAL_STATE__" in text or "window.__DATA__" in text:
                    try:
                        json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', text, re.DOTALL)
                        if json_match:
                            data["initial_state"] = json.loads(json_match.group(1))
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.debug("Could not parse initial state JSON: %s", e)

            data["title"] = (
                self._get_meta(soup, "og:title")
                or self._get_meta(soup, "twitter:title")
                or (soup.find("h1").get_text(strip=True) if soup.find("h1") else None)
            )
            data["description"] = (
                self._get_meta(soup, "og:description")
                or self._get_meta(soup, "description")
                or self._get_meta(soup, "twitter:description")
            )
            data["image"] = self._get_meta(soup, "og:image")

            date_patterns = [
                r'(\w+\s+\d{1,2},?\s+\d{4})',
                r'(\d{1,2}/\d{1,2}/\d{2,4})',
                r'(\w+\s+\d{1,2}\s+-\s+\w+\s+\d{1,2},?\s+\d{4})',
            ]
            text_content = soup.get_text()
            dates_found = []
            for pattern in date_patterns:
                matches = re.findall(pattern, text_content)
                dates_found.extend(matches)
            if dates_found:
                data["dates_mentioned"] = list(set(dates_found))[:5]

            prize_elems = soup.find_all(string=re.compile(r'\$[\d,]+', re.I))
            for elem in prize_elems:
                parent = elem.parent
                if parent and parent.name not in ['script', 'style', 'noscript']:
                    text = parent.get_text(strip=True)
                    if len(text) < 200 and '$' in text:
                        data["prize_text"] = text
                        break

            stats = {}
            for pattern in [r'(\d+)\s+submissions?', r'(\d+)\s+participants?', r'(\d+)\s+registrations?']:
                match = re.search(pattern, text_content, re.I)
                if match:
                    key = pattern.split()[-1].replace('?', '').replace('s', '')
                    stats[key] = int(match.group(1))
            if stats:
                data["stats"] = stats

            if "winner" in text_content.lower() or "winners" in text_content.lower():
                data["winners_announced"] = True
                winner_section = soup.find(string=re.compile(r'winners?', re.I))
                if winner_section:
                    data["has_winners_section"] = True

            rules_link = soup.find("a", href=re.compile(r'rules|guidelines', re.I))
            if rules_link:
                rules_href = rules_link.get("href", "")
                data["rules_url"] = rules_href if rules_href.startswith("http") else f"{url.rstrip('/')}/{rules_href.lstrip('/')}"

            gallery_link = soup.find("a", href=re.compile(r'project-gallery|submissions', re.I))
            if gallery_link:
                data["gallery_url"] = gallery_link.get("href")

            themes = []
            for tag in soup.find_all(class_=re.compile(r'theme|tag|category', re.I)):
                text = tag.get_text(strip=True)
                if text and len(text) < 50:
                    themes.append(text)
            if themes:
                data["themes"] = list(set(themes))[:10]

            result["data"] = data
            result["success"] = True
            result["is_closed"] = data.get("winners_announced", False) or "submission period ended" in text_content.lower()

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            result["steps"].append(f"Failed to fetch: {e.message}")
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        if result["success"] and self._cache:
            self._cache.set(cache_key, result, ttl=1800)

        return result

    async def list_hackathon_projects(
        self,
        hackathon_url: str,
        limit: int = 50,
        winners_only: bool = False,
        fetch_all_pages: bool = True,
    ) -> dict[str, Any]:
        """List all projects from a hackathon's project gallery."""
        validate_devpost_url(hackathon_url)
        cache_key = make_projects_key(hackathon_url)
        if self._cache and not winners_only:
            cached = self._cache.get(cache_key)
            if cached is not None:
                if winners_only:
                    cached["projects"] = [p for p in cached.get("projects", []) if p.get("is_winner")]
                return cached

        result = {
            "success": False,
            "hackathon_url": hackathon_url,
            "steps": [],
            "projects": [],
        }

        base_gallery_url = f"{hackathon_url.rstrip('/')}/project-gallery"
        result["steps"].append(f"Fetching gallery: {base_gallery_url}")

        try:
            all_projects = []
            seen_urls = set()
            page = 1
            max_pages = 10 if fetch_all_pages else 1

            while page <= max_pages:
                gallery_url = f"{base_gallery_url}?page={page}" if page > 1 else base_gallery_url
                result["steps"].append(f"Fetching page {page}: {gallery_url}")

                try:
                    resp = await self._request_with_retry("GET", gallery_url)

                    soup = BeautifulSoup(resp.text, "html.parser")

                    if page == 1:
                        title_elem = soup.find("h1") or soup.find("title")
                        if title_elem:
                            result["hackathon_title"] = title_elem.get_text(strip=True)

                        date_elem = soup.find(class_=re.compile(r'date|time|period', re.I))
                        if date_elem:
                            result["hackathon_date_info"] = date_elem.get_text(strip=True)

                    page_projects = []
                    project_cards = soup.find_all(class_=re.compile(r'software-entry|project-item|gallery-item|submission', re.I))

                    if not project_cards:
                        project_cards = soup.find_all("article")

                    if not project_cards:
                        project_links = soup.find_all("a", href=re.compile(r'/software/'))
                        for link in project_links:
                            href = link.get("href", "")
                            if href in seen_urls or not href:
                                continue

                            seen_urls.add(href)
                            card = link.find_parent(class_=re.compile(r'entry|card|item', re.I)) or link.parent

                            proj = await _extract_project_from_card(card, link, self)
                            if proj:
                                if winners_only and not proj.get("is_winner"):
                                    continue
                                page_projects.append(proj)
                    else:
                        for card in project_cards:
                            try:
                                link = card.find("a", href=re.compile(r'/software/'))
                                if not link:
                                    continue

                                href = link.get("href", "")
                                if href in seen_urls or not href:
                                    continue
                                seen_urls.add(href)

                                proj = await _extract_project_from_card(card, link, self)
                                if proj:
                                    if winners_only and not proj.get("is_winner"):
                                        continue
                                    page_projects.append(proj)

                            except Exception as e:
                                logger.debug("Error parsing project card: %s", e)
                                result["steps"].append(f"Error parsing card: {e}")

                    if not page_projects:
                        result["steps"].append(f"No projects found on page {page}, stopping")
                        break

                    all_projects.extend(page_projects)
                    result["steps"].append(f"Found {len(page_projects)} projects on page {page}")

                    if limit > 0 and len(all_projects) >= limit:
                        all_projects = all_projects[:limit]
                        result["steps"].append(f"Reached limit of {limit} projects")
                        break

                    next_link = soup.find("a", href=re.compile(r'page=\d+'))
                    if not next_link or f"page={page+1}" not in str(next_link):
                        pagination = soup.find(class_=re.compile(r'pagination', re.I))
                        if pagination:
                            next_page_link = pagination.find("a", href=re.compile(rf'page={page+1}'))
                            if not next_page_link:
                                result["steps"].append("No more pages found")
                                break
                        else:
                            result["steps"].append("No pagination found, assuming last page")
                            break

                    page += 1

                except DevpostError as e:
                    if e.status_code == 404:
                        result["steps"].append(f"Page {page} not found (404), stopping")
                        break
                    raise

            result["projects"] = all_projects
            result["count"] = len(all_projects)
            result["pages_fetched"] = page
            result["success"] = True

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        if result["success"] and self._cache:
            self._cache.set(cache_key, result, ttl=1800)

        if winners_only and result.get("success"):
            result["projects"] = [p for p in result.get("projects", []) if p.get("is_winner")]
            result["count"] = len(result["projects"])

        return result

    async def get_project_details(self, project_url: str) -> dict[str, Any]:
        """Get detailed info about a specific project using browser automation."""
        validate_devpost_url(project_url)
        cache_key = make_project_key(project_url)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return {
                "error": "Playwright not installed. Install with: pip install playwright && playwright install chromium",
                "code": "DEPENDENCY_MISSING",
            }

        result = {"success": False, "url": project_url, "steps": [], "data": {}}

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not self.headed)
            page = await browser.new_page()

            try:
                result["steps"].append(f"Loading {project_url}")
                await page.goto(project_url, timeout=30000)
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(1)

                data = {}

                try:
                    title = await page.wait_for_selector("h1#app-title, h1", timeout=5000)
                    data["title"] = await title.text_content()
                except Exception:
                    logger.debug("Could not extract project title from %s", project_url)

                try:
                    tagline = await page.query_selector("p.tagline, .elevator-pitch, #app-tagline")
                    data["tagline"] = await tagline.text_content() if tagline else None
                except Exception:
                    logger.debug("Could not extract tagline from %s", project_url)

                try:
                    desc = await page.query_selector("#app-details, .description, .software-description")
                    if desc:
                        data["description"] = await desc.text_content()
                        data["description_html"] = await desc.inner_html()
                except Exception as e:
                    logger.debug("Description extraction error: %s", e)
                    result["steps"].append(f"Description error: {e}")

                try:
                    built = await page.query_selector("#built-with, .built-with")
                    if built:
                        text = await built.text_content()
                        techs = [t.strip() for t in text.replace("Built With", "").split() if t.strip()]
                        data["built_with"] = techs
                except Exception:
                    logger.debug("Could not extract built-with from %s", project_url)

                links = {}
                try:
                    github = await page.query_selector("a[href*='github.com']")
                    if github:
                        links["github"] = await github.get_attribute("href")
                except Exception:
                    logger.debug("Could not extract GitHub link from %s", project_url)
                try:
                    demo = await page.query_selector("a[href*='try-it-out'], a.demo-link, a[title*='demo' i]")
                    if demo:
                        href = await demo.get_attribute("href")
                        if href:
                            links["demo"] = href
                except Exception:
                    logger.debug("Could not extract demo link from %s", project_url)
                try:
                    video = await page.query_selector("a[href*='youtube.com'], a[href*='vimeo.com'], a[href*='youtu.be']")
                    if video:
                        links["video"] = await video.get_attribute("href")
                except Exception:
                    logger.debug("Could not extract video link from %s", project_url)
                try:
                    website = await page.query_selector("a[rel*='external'], a.website-link")
                    if website:
                        href = await website.get_attribute("href")
                        if href and "devpost.com" not in href:
                            links["website"] = href
                except Exception:
                    logger.debug("Could not extract website link from %s", project_url)
                if links:
                    data["links"] = links

                team = []
                try:
                    team_section = await page.query_selector("#app-team, .team-members, .collaborators")
                    if team_section:
                        members = await team_section.query_selector_all("a[href*='/users/']")
                        seen = set()
                        for member in members:
                            try:
                                username = await member.get_attribute("href")
                                name = await member.text_content()
                                if username:
                                    username_clean = username.replace("/users/", "").strip("/")
                                    if username_clean not in seen:
                                        seen.add(username_clean)
                                        team.append({
                                            "username": username_clean,
                                            "name": name.strip() if name else username_clean,
                                        })
                            except Exception:
                                logger.debug("Could not extract team member info")
                except Exception as e:
                    logger.debug("Team extraction error: %s", e)
                    result["steps"].append(f"Team error: {e}")
                if team:
                    data["team"] = team

                screenshots = []
                try:
                    gallery = await page.query_selector("#gallery, .gallery, .screenshots")
                    if gallery:
                        imgs = await gallery.query_selector_all("img")
                        for img in imgs:
                            try:
                                src = await img.get_attribute("src")
                                if src and "placeholder" not in src:
                                    screenshots.append(src)
                            except Exception:
                                logger.debug("Could not extract screenshot src")
                except Exception:
                    logger.debug("Could not extract screenshots from %s", project_url)
                if screenshots:
                    data["screenshots"] = screenshots

                try:
                    hackathon = await page.query_selector("a[href*='devpost.com/'][href$='/']")
                    if hackathon:
                        hack_name = await hackathon.text_content()
                        hack_url = await hackathon.get_attribute("href")
                        data["hackathon"] = {
                            "name": hack_name.strip() if hack_name else None,
                            "url": hack_url,
                        }
                except Exception:
                    logger.debug("Could not extract hackathon link from project page")

                try:
                    winner_badge = await page.query_selector(".winner, .winner-badge, .prize-winner")
                    if winner_badge:
                        data["is_winner"] = True
                        prize_text = await winner_badge.text_content()
                        data["prize"] = prize_text.strip() if prize_text else "Winner"
                except Exception:
                    logger.debug("Could not extract winner badge from project page")

                result["data"] = data
                result["success"] = True
                result["steps"].append("Successfully extracted project details")

            except Exception as e:
                result["error"] = str(e)
                result["steps"].append(f"Error: {e}")
            finally:
                await browser.close()

        if result["success"] and self._cache:
            self._cache.set(cache_key, result, ttl=1800)

        return result

    async def parse_rules_page(self, slug: str) -> dict[str, Any]:
        """Parse a hackathon's rules page into structured sections."""
        validate_slug(slug)
        cache_key = make_rules_key(slug)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        rules_url = f"https://{slug}.devpost.com/rules"
        result = {
            "success": False,
            "slug": slug,
            "url": rules_url,
            "eligibility": [],
            "requirements": [],
            "judging_criteria": [],
            "prize_categories": [],
            "key_dates": [],
            "sponsor_apis": [],
        }

        try:
            resp = await self._request_with_retry("GET", rules_url)
            soup = BeautifulSoup(resp.text, "html.parser")
            raw_text = soup.get_text()
            result["raw_text_length"] = len(raw_text)

            _extract_section(soup, result, "eligibility", [r"eligib", r"who\s+can", r"participa", r"enter\s+this"])
            _extract_section(soup, result, "requirements", [r"requirement", r"what\s+to\s+submit", r"submission\s+req", r"must\s+submit", r"deliverable"])
            _extract_section(soup, result, "judging_criteria", [r"judg", r"criteria", r"how\s+will\s+", r"evaluat", r"scor"])
            _extract_section(soup, result, "sponsor_apis", [r"sponsor\s+api", r"must\s+use", r"required\s+tech", r"platform", r"api\s+access", r"technology\s+req"])

            prize_items = []
            for elem in soup.find_all(string=re.compile(r'\$[\d,]+', re.I)):
                parent = elem.parent
                if parent and parent.name not in ('script', 'style', 'noscript'):
                    row = parent.find_parent('tr') or parent.find_parent('li') or parent
                    text = row.get_text(strip=True)
                    if len(text) < 300 and '$' in text:
                        prize_items.append(text)
            result["prize_categories"] = list(dict.fromkeys(prize_items))[:20]

            date_items = []
            for elem in soup.find_all(string=re.compile(
                r'(deadline|submis|start|end|close|open|due|register).*?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w+\s+\d{1,2},?\s+\d{4})',
                re.I,
            )):
                parent = elem.parent
                if parent and parent.name not in ('script', 'style', 'noscript'):
                    text = parent.get_text(strip=True)
                    if len(text) < 300:
                        date_items.append(text)
            for elem in soup.find_all(string=re.compile(
                r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w+\s+\d{1,2},?\s+\d{4}).*?(deadline|submis|start|end|close|open|due|register)',
                re.I,
            )):
                parent = elem.parent
                if parent and parent.name not in ('script', 'style', 'noscript'):
                    text = parent.get_text(strip=True)
                    if len(text) < 300:
                        date_items.append(text)
            result["key_dates"] = list(dict.fromkeys(date_items))[:10]

            has_content = any([
                result["eligibility"],
                result["requirements"],
                result["judging_criteria"],
                result["prize_categories"],
                result["key_dates"],
                result["sponsor_apis"],
            ])
            result["success"] = True
            if not has_content:
                result["message"] = "Page fetched but no structured rules sections found"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)

        if result["success"] and self._cache:
            self._cache.set(cache_key, result, ttl=300)

        return result

    async def get_winners(self, slug: str) -> dict[str, Any]:
        """Get winning projects from a hackathon."""
        validate_slug(slug)
        hackathon_url = f"https://{slug}.devpost.com/"

        result = {
            "success": False,
            "slug": slug,
            "winners": [],
            "count": 0,
        }

        try:
            gallery_data = await self.list_hackathon_projects(
                hackathon_url=hackathon_url,
                limit=500,
                winners_only=True,
            )
            winners = gallery_data.get("projects", [])
            if winners:
                result["winners"] = winners
                result["count"] = len(winners)
                result["success"] = True
                return result

            winners_url = f"https://{slug}.devpost.com/winners"
            try:
                resp = await self._request_with_retry("GET", winners_url)
                soup = BeautifulSoup(resp.text, "html.parser")

                project_links = soup.find_all("a", href=re.compile(r"/software/"))
                seen = set()
                for link in project_links:
                    href = link.get("href", "")
                    if not href or href in seen:
                        continue
                    seen.add(href)

                    card = link.find_parent(class_=re.compile(r"entry|card|item|winner", re.I)) or link
                    title_elem = card.find(["h2", "h3", "h4", "h5"]) or link
                    title = title_elem.get_text(strip=True) if title_elem else "Unknown"

                    prize_elem = card.find(class_=re.compile(r"prize|winner|1st|2nd|3rd|finalist", re.I))
                    prize = prize_elem.get_text(strip=True) if prize_elem else None

                    url = f"https://devpost.com{href}" if href.startswith("/") else href

                    tagline_elem = card.find(class_=re.compile(r"tagline|description|summary", re.I))
                    tagline = tagline_elem.get_text(strip=True) if tagline_elem else None

                    winners.append({
                        "title": title,
                        "url": url,
                        "prize": prize,
                        "tagline": tagline,
                        "is_winner": True,
                    })

                if winners:
                    result["winners"] = winners
                    result["count"] = len(winners)
                    result["success"] = True
                    return result
            except DevpostError as e:
                logger.debug("Could not fetch /winners page: %s", e.message)
            except Exception as e:
                logger.debug("Error scraping /winners: %s", e)

            if not winners:
                result["success"] = True
                result["message"] = "No winners found (may not be announced yet, or page blocked by Cloudflare)"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)

        return result

    async def evaluate_hackathon(self, slug: str, skills: Optional[list[str]] = None) -> dict[str, Any]:
        """Evaluate a hackathon and produce a decision report.

        Orchestrates info, scrape, rules, and projects to answer:
        'Should I enter? What's the angle?'
        """
        validate_slug(slug)
        cache_key = make_evaluate_key(slug)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        result = {
            "success": False,
            "slug": slug,
            "verdict": "Maybe",
            "verdict_reason": "",
            "basics": {},
            "competition": {},
            "eligibility": [],
            "requirements": [],
            "judging_criteria": [],
            "prize_categories": [],
            "key_dates": [],
            "sponsor_apis": [],
            "signals": {},
            "errors": [],
        }

        try:
            info = await self.get_hackathon_by_slug(slug)
            if info is None:
                raise DevpostError(f"Hackathon '{slug}' not found", code="NOT_FOUND")

            hackathon_url = info.get("url", f"https://{slug}.devpost.com/")
            prize_raw = info.get("prize_amount") or "0"
            prize_amount = parse_prize_amount(prize_raw) or 0
            days_left = parse_days_left(info.get("ends_at"))
            registrations = info.get("registrations_count", 0)
            submissions_count = info.get("submissions_count")
            status = info.get("open_state", "unknown")

            result["basics"] = {
                "title": info.get("title", "Unknown"),
                "prize": prize_raw,
                "prize_amount": prize_amount,
                "status": status,
                "dates": info.get("submission_period_dates", ""),
                "url": hackathon_url,
                "organization": info.get("organization_name", ""),
                "featured": info.get("featured", False),
                "themes": [t.get("name", "") for t in info.get("themes", [])],
            }

            scrape_data = None
            try:
                scrape_data = await self.scrape_hackathon_page(hackathon_url)
            except DevpostError as e:
                result["errors"].append(f"Scrape failed: {e.message}")

            if scrape_data and scrape_data.get("success"):
                data = scrape_data.get("data", {})
                if data.get("stats"):
                    if submissions_count is None:
                        submissions_count = data["stats"].get("submission")

            rules_data = None
            try:
                rules_data = await self.parse_rules_page(slug)
                if rules_data.get("success"):
                    result["eligibility"] = rules_data.get("eligibility", [])
                    result["requirements"] = rules_data.get("requirements", [])
                    result["judging_criteria"] = rules_data.get("judging_criteria", [])
                    result["prize_categories"] = rules_data.get("prize_categories", [])
                    result["key_dates"] = rules_data.get("key_dates", [])
                    result["sponsor_apis"] = rules_data.get("sponsor_apis", [])
                else:
                    err = rules_data.get("error", "Unknown rules error")
                    result["errors"].append(f"Rules parse failed: {err}")
            except DevpostError as e:
                result["errors"].append(f"Rules parse failed: {e.message}")

            projects_data = None
            try:
                projects_data = await self.list_hackathon_projects(
                    hackathon_url=hackathon_url, limit=500,
                )
            except DevpostError as e:
                result["errors"].append(f"Projects fetch failed: {e.message}")

            project_count = 0
            if projects_data and projects_data.get("success"):
                project_count = projects_data.get("count", len(projects_data.get("projects", [])))
                if submissions_count is None or submissions_count == 0:
                    submissions_count = project_count

            if submissions_count is None:
                submissions_count = 0

            prizes_count = info.get("prizes_counts", {}).get("cash", 1) or 1
            prize_per_project = prize_amount / max(1, submissions_count) if prize_amount else 0
            registrants_per_prize = registrations / max(1, prizes_count)

            time_pressure = _signal_time_pressure(days_left, status)
            prize_density = _signal_prize_density(prize_per_project)
            competition_density = _signal_competition_density(registrants_per_prize)
            submission_gap = _signal_submission_gap(registrations, submissions_count, status)
            theme_fit = _signal_theme_fit(skills, result.get("sponsor_apis", []), result["basics"].get("themes", []))

            result["competition"] = {
                "registrants": registrations,
                "submissions": submissions_count,
                "prize_per_project": round(prize_per_project, 2),
                "registrants_per_prize": round(registrants_per_prize, 1),
                "prize_categories": prizes_count,
            }

            result["signals"] = {
                "time_pressure": time_pressure,
                "prize_density": prize_density,
                "competition_density": competition_density,
                "submission_gap": submission_gap,
                "theme_fit": theme_fit,
            }

            verdict, reason = _compute_verdict(result["signals"], status)
            result["verdict"] = verdict
            result["verdict_reason"] = reason
            result["success"] = True

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)

        if result["success"] and self._cache:
            self._cache.set(cache_key, result, ttl=300)

        return result

    async def search_in_hackathon(
        self,
        hackathon_slug_or_url: str,
        query: str,
        winners_only: bool = False,
        tech_only: bool = False,
        include_rules: bool = False,
    ) -> dict[str, Any]:
        """Search within a specific hackathon's projects and optionally its description/rules."""
        slug = hackathon_slug_or_url
        if "://" in hackathon_slug_or_url:
            parsed = urlparse(hackathon_slug_or_url)
            host = parsed.hostname or ""
            if host.endswith(".devpost.com"):
                slug = host.replace(".devpost.com", "")
            else:
                slug = hackathon_slug_or_url.rstrip("/").rsplit("/", maxsplit=1)[-1]
        validate_slug(slug)

        result = {
            "success": False,
            "hackathon_slug": slug,
            "query": query,
            "matches": {"projects": [], "description": [], "rules": []},
        }

        try:
            hackathon_url = f"https://{slug}.devpost.com/"
            projects_data = await self.list_hackathon_projects(
                hackathon_url=hackathon_url,
                limit=500,
                winners_only=winners_only,
            )

            q = query.lower()
            for proj in projects_data.get("projects", []):
                matched = False
                match_reasons = []

                if not tech_only:
                    title = (proj.get("title") or "").lower()
                    tagline = (proj.get("tagline") or "").lower()
                    if q in title or q in tagline:
                        matched = True
                        if q in title:
                            match_reasons.append("title")
                        if q in tagline:
                            match_reasons.append("tagline")

                tech_text = ", ".join(proj.get("built_with", []) if isinstance(proj.get("built_with"), list) else []).lower()
                if q in tech_text:
                    matched = True
                    match_reasons.append("tech_stack")

                if winners_only and not proj.get("is_winner"):
                    matched = False

                if matched:
                    result["matches"]["projects"].append({
                        "title": proj.get("title", "Unknown"),
                        "url": proj.get("url", ""),
                        "tagline": proj.get("tagline"),
                        "is_winner": proj.get("is_winner", False),
                        "prize": proj.get("prize"),
                        "matched_in": match_reasons,
                    })

            if include_rules:
                scrape_data = await self.scrape_hackathon_page(hackathon_url)
                if scrape_data.get("success"):
                    data = scrape_data.get("data", {})
                    desc = (data.get("description") or "").lower()
                    if q in desc:
                        idx = desc.find(q)
                        start = max(0, idx - 80)
                        end = min(len(desc), idx + len(q) + 80)
                        snippet = data.get("description", "")[start:end]
                        result["matches"]["description"].append({
                            "field": "description",
                            "snippet": snippet,
                        })

                rules_data = await self.parse_rules_page(slug)
                if rules_data.get("success"):
                    for section_name in ("eligibility", "requirements", "judging_criteria", "sponsor_apis"):
                        for item in rules_data.get(section_name, []):
                            if q in item.lower():
                                result["matches"]["rules"].append({
                                    "field": section_name,
                                    "snippet": item[:200],
                                })
                    for cat in rules_data.get("prize_categories", []):
                        if q in cat.lower():
                            result["matches"]["rules"].append({
                                "field": "prize_category",
                                "snippet": cat[:200],
                            })
                    for date_item in rules_data.get("key_dates", []):
                        if q in date_item.lower():
                            result["matches"]["rules"].append({
                                "field": "key_date",
                                "snippet": date_item[:200],
                            })

            result["success"] = True
            result["total_matches"] = (
                len(result["matches"]["projects"])
                + len(result["matches"]["description"])
                + len(result["matches"]["rules"])
            )

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)

        return result

    async def search_projects(
        self,
        query: str,
        limit: int = 20,
    ) -> list[dict]:
        """Search projects via /software/search."""
        cache_key = make_search_projects_key(query, limit)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        projects = []
        page = 1
        max_pages = (limit + 11) // 12

        while page <= max_pages and len(projects) < limit:
            try:
                resp = await self._request_with_retry(
                    "GET",
                    f"{BASE_URL}/software/search",
                    params={"q": query, "page": page},
                )
                soup = BeautifulSoup(resp.text, "html.parser")
                project_cards = soup.find_all(class_=re.compile(r'software-entry|project-item|gallery-item', re.I))
                if not project_cards:
                    project_cards = soup.find_all("article")
                if not project_cards:
                    project_links = soup.find_all("a", href=re.compile(r'/software/'))
                    seen = set()
                    for link in project_links:
                        href = link.get("href", "")
                        if href in seen or not href:
                            continue
                        seen.add(href)
                        card = link.find_parent(class_=re.compile(r'entry|card|item', re.I)) or link.parent
                        proj = await _extract_project_from_card(card, link, self)
                        if proj and proj not in projects:
                            projects.append(proj)
                else:
                    for card in project_cards:
                        try:
                            link = card.find("a", href=re.compile(r'/software/'))
                            if not link:
                                continue
                            href = link.get("href", "")
                            if not href:
                                continue
                            proj = await _extract_project_from_card(card, link, self)
                            if proj and proj not in projects:
                                projects.append(proj)
                        except Exception:
                            continue
            except DevpostError:
                break
            page += 1

        projects = projects[:limit]
        if self._cache:
            self._cache.set(cache_key, projects)
        return projects

    async def get_popular_projects(self, limit: int = 20) -> list[dict]:
        """Get popular projects from /software/popular."""
        cache_key = make_popular_projects_key(limit)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        projects = []
        page = 1
        max_pages = (limit + 11) // 12

        while page <= max_pages and len(projects) < limit:
            try:
                resp = await self._request_with_retry(
                    "GET",
                    f"{BASE_URL}/software/popular",
                    params={"page": page},
                )
                soup = BeautifulSoup(resp.text, "html.parser")
                project_cards = soup.find_all(class_=re.compile(r'software-entry|project-item', re.I))
                if not project_cards:
                    project_cards = soup.find_all("article")
                for card in project_cards:
                    try:
                        link = card.find("a", href=re.compile(r'/software/'))
                        if not link:
                            continue
                        href = link.get("href", "")
                        if not href:
                            continue
                        proj = await _extract_project_from_card(card, link, self)
                        if proj and proj not in projects:
                            projects.append(proj)
                    except Exception:
                        continue
            except DevpostError:
                break
            page += 1

        projects = projects[:limit]
        if self._cache:
            self._cache.set(cache_key, projects)
        return projects

    async def get_built_with_projects(
        self,
        tech: str,
        limit: int = 20,
    ) -> list[dict]:
        """Get projects built with a specific technology from /software/built-with/<tech>."""
        cache_key = make_built_with_key(tech, limit)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        tech_slug = tech.lower().replace(" ", "-").replace("+", "plus")
        projects = []
        page = 1
        max_pages = (limit + 11) // 12

        while page <= max_pages and len(projects) < limit:
            try:
                resp = await self._request_with_retry(
                    "GET",
                    f"{BASE_URL}/software/built-with/{tech_slug}",
                    params={"page": page},
                )
                soup = BeautifulSoup(resp.text, "html.parser")
                project_cards = soup.find_all(class_=re.compile(r'software-entry|project-item', re.I))
                if not project_cards:
                    project_cards = soup.find_all("article")
                for card in project_cards:
                    try:
                        link = card.find("a", href=re.compile(r'/software/'))
                        if not link:
                            continue
                        href = link.get("href", "")
                        if not href:
                            continue
                        proj = await _extract_project_from_card(card, link, self)
                        if proj:
                            proj["built_with"] = proj.get("built_with", [])
                            if tech.lower() not in [t.lower() for t in proj.get("built_with", [])]:
                                proj["built_with"].append(tech)
                            if proj not in projects:
                                projects.append(proj)
                    except Exception:
                        continue
            except DevpostError:
                break
            page += 1

        projects = projects[:limit]
        if self._cache:
            self._cache.set(cache_key, projects)
        return projects

    async def get_featured_projects(self, limit: int = 20) -> list[dict]:
        """Get staff picks/featured projects from /software."""
        cache_key = make_featured_projects_key(limit)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        projects = []
        page = 1
        max_pages = (limit + 11) // 12

        while page <= max_pages and len(projects) < limit:
            try:
                resp = await self._request_with_retry(
                    "GET",
                    f"{BASE_URL}/software",
                    params={"page": page},
                )
                soup = BeautifulSoup(resp.text, "html.parser")
                project_cards = soup.find_all(class_=re.compile(r'software-entry|project-item|featured', re.I))
                if not project_cards:
                    project_cards = soup.find_all("article")
                for card in project_cards:
                    try:
                        link = card.find("a", href=re.compile(r'/software/'))
                        if not link:
                            continue
                        href = link.get("href", "")
                        if not href:
                            continue
                        proj = await _extract_project_from_card(card, link, self)
                        if proj:
                            featured_badge = card.find(class_=re.compile(r'staff-pick|featured|pick', re.I))
                            if featured_badge:
                                proj["is_featured"] = True
                            if proj not in projects:
                                projects.append(proj)
                    except Exception:
                        continue
            except DevpostError:
                break
            page += 1

        projects = projects[:limit]
        if self._cache:
            self._cache.set(cache_key, projects)
        return projects

    async def get_participants(self, slug: str, limit: int = 50) -> dict[str, Any]:
        """Get participants from /{slug}/participants."""
        validate_slug(slug)
        cache_key = make_participants_key(slug, limit)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        participants_url = f"https://{slug}.devpost.com/participants"
        result = {
            "success": False,
            "slug": slug,
            "participants": [],
            "count": 0,
        }

        try:
            resp = await self._request_with_retry("GET", participants_url)
            soup = BeautifulSoup(resp.text, "html.parser")

            participant_cards = soup.find_all(class_=re.compile(r'participant|user-card|team-member', re.I))
            if not participant_cards:
                participant_cards = soup.find_all("a", href=re.compile(r'/users/'))

            seen = set()
            for card in participant_cards:
                if len(seen) >= limit:
                    break
                try:
                    if card.name == "a":
                        href = card.get("href", "")
                        username = href.replace("/users/", "").strip("/")
                        if not username or username in seen:
                            continue
                        seen.add(username)
                        name = card.get_text(strip=True)
                        result["participants"].append({
                            "username": username,
                            "name": name if name else username,
                            "url": f"{BASE_URL}/users/{username}",
                        })
                    else:
                        link = card.find("a", href=re.compile(r'/users/'))
                        if link:
                            href = link.get("href", "")
                            username = href.replace("/users/", "").strip("/")
                            if not username or username in seen:
                                continue
                            seen.add(username)
                            name = link.get_text(strip=True)
                            result["participants"].append({
                                "username": username,
                                "name": name if name else username,
                                "url": f"{BASE_URL}/users/{username}",
                            })
                except Exception:
                    continue

            result["count"] = len(result["participants"])
            result["success"] = True

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)

        if result["success"] and self._cache:
            self._cache.set(cache_key, result)

        return result

    async def get_resources(self, slug: str) -> dict[str, Any]:
        """Get resources from /{slug}/resources."""
        validate_slug(slug)
        cache_key = make_resources_key(slug)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        resources_url = f"https://{slug}.devpost.com/resources"
        result = {
            "success": False,
            "slug": slug,
            "resources": [],
        }

        try:
            resp = await self._request_with_retry("GET", resources_url)
            soup = BeautifulSoup(resp.text, "html.parser")

            resource_items = soup.find_all(class_=re.compile(r'resource|link-item|list-item', re.I))
            if not resource_items:
                resource_items = soup.find_all("li")
            if not resource_items:
                resource_links = soup.find_all("a", href=re.compile(r'^http'))

            for item in resource_items:
                try:
                    if item.name == "a":
                        title = item.get_text(strip=True)
                        href = item.get("href", "")
                        if title and href:
                            result["resources"].append({
                                "title": title,
                                "url": href if href.startswith("http") else f"{BASE_URL}{href}",
                            })
                    else:
                        link = item.find("a")
                        if link:
                            title = link.get_text(strip=True)
                            href = link.get("href", "")
                            if title and href:
                                result["resources"].append({
                                    "title": title,
                                    "url": href if href.startswith("http") else f"{BASE_URL}{href}",
                                })
                except Exception:
                    continue

            result["success"] = True

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)

        if result["success"] and self._cache:
            self._cache.set(cache_key, result)

        return result

    async def get_updates(self, slug: str, limit: int = 20) -> dict[str, Any]:
        """Get updates from /{slug}/updates."""
        validate_slug(slug)
        cache_key = make_updates_key(slug, limit)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        updates_url = f"https://{slug}.devpost.com/updates"
        result = {
            "success": False,
            "slug": slug,
            "updates": [],
            "count": 0,
        }

        try:
            resp = await self._request_with_retry("GET", updates_url)
            soup = BeautifulSoup(resp.text, "html.parser")

            update_cards = soup.find_all(class_=re.compile(r'update|post|news-item', re.I))
            if not update_cards:
                update_cards = soup.find_all("article")

            for card in update_cards:
                if len(result["updates"]) >= limit:
                    break
                try:
                    title_elem = card.find(["h2", "h3", "h4"]) or card.find(class_=re.compile(r'title|heading', re.I))
                    title = title_elem.get_text(strip=True) if title_elem else "Untitled"

                    date_elem = card.find(class_=re.compile(r'date|time|published', re.I))
                    date = date_elem.get_text(strip=True) if date_elem else None

                    content_elem = card.find(class_=re.compile(r'content|body|description|excerpt', re.I))
                    content = content_elem.get_text(strip=True) if content_elem else None

                    link_elem = card.find("a", href=re.compile(r'/updates/'))
                    url = link_elem.get("href", "") if link_elem else None
                    if url and not url.startswith("http"):
                        url = f"{BASE_URL}{url}"

                    result["updates"].append({
                        "title": title,
                        "date": date,
                        "content": content,
                        "url": url,
                    })
                except Exception:
                    continue

            result["count"] = len(result["updates"])
            result["success"] = True

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)

        if result["success"] and self._cache:
            self._cache.set(cache_key, result)

        return result

    async def get_discussions(self, slug: str, limit: int = 20) -> dict[str, Any]:
        """Get discussions/forum topics from /{slug}/forum_topics."""
        validate_slug(slug)
        cache_key = make_discussions_key(slug, limit)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        discussions_url = f"https://{slug}.devpost.com/forum_topics"
        result = {
            "success": False,
            "slug": slug,
            "discussions": [],
            "count": 0,
        }

        try:
            resp = await self._request_with_retry("GET", discussions_url)
            soup = BeautifulSoup(resp.text, "html.parser")

            topic_rows = soup.find_all(class_=re.compile(r'topic|forum-item|discussion', re.I))
            if not topic_rows:
                topic_rows = soup.find_all("tr", class_=re.compile(r'topic', re.I))
            if not topic_rows:
                topic_links = soup.find_all("a", href=re.compile(r'/forum_topics/'))

            for row in topic_rows:
                if len(result["discussions"]) >= limit:
                    break
                try:
                    if row.name == "a":
                        title = row.get_text(strip=True)
                        href = row.get("href", "")
                        if title and href:
                            result["discussions"].append({
                                "title": title,
                                "url": href if href.startswith("http") else f"{BASE_URL}{href}",
                            })
                    else:
                        link = row.find("a", href=re.compile(r'/forum_topics/'))
                        if link:
                            title = link.get_text(strip=True)
                            href = link.get("href", "")
                            if not title or not href:
                                continue

                            author_elem = row.find(class_=re.compile(r'author|user', re.I))
                            author = author_elem.get_text(strip=True) if author_elem else None

                            replies_elem = row.find(class_=re.compile(r'replies|comments|responses', re.I))
                            replies = replies_elem.get_text(strip=True) if replies_elem else None

                            date_elem = row.find(class_=re.compile(r'date|time|ago', re.I))
                            date = date_elem.get_text(strip=True) if date_elem else None

                            result["discussions"].append({
                                "title": title,
                                "url": href if href.startswith("http") else f"{BASE_URL}{href}",
                                "author": author,
                                "replies": replies,
                                "date": date,
                            })
                except Exception:
                    continue

            result["count"] = len(result["discussions"])
            result["success"] = True

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)

        if result["success"] and self._cache:
            self._cache.set(cache_key, result)

        return result

    def _get_meta(self, soup: BeautifulSoup, property_name: str) -> Optional[str]:
        """Get meta tag content by property or name."""
        tag = soup.find("meta", property=property_name) or soup.find("meta", attrs={"name": property_name})
        return tag.get("content") if tag else None


async def _extract_project_from_card(card, link, client) -> Optional[dict]:
    """Extract project info from a gallery card."""
    try:
        title_elem = card.find(["h2", "h3", "h4", ".title", ".name"]) or link
        title = title_elem.get_text(strip=True) if title_elem else "Unknown"

        href = link.get("href", "")
        url = f"https://devpost.com{href}" if href.startswith("/") else href

        tagline_elem = card.find(class_=re.compile(r'tagline|description|summary', re.I))
        tagline = tagline_elem.get_text(strip=True) if tagline_elem else None

        img = card.find("img")
        thumbnail = img.get("src") if img else None

        winner_badge = card.find(class_=re.compile(r'winner|1st|2nd|3rd|finalist', re.I))
        is_winner = bool(winner_badge)
        prize = None
        if winner_badge:
            prize = winner_badge.get_text(strip=True)

        team_elem = card.find(class_=re.compile(r'team|creator|author', re.I))
        team = team_elem.get_text(strip=True) if team_elem else None

        return {
            "title": title,
            "url": url,
            "tagline": tagline,
            "thumbnail": thumbnail,
            "is_winner": is_winner,
            "prize": prize,
            "team": team,
        }
    except Exception as e:
        logger.debug("Could not extract project from card: %s", e)
        return None


class AuthenticatedClient:
    """Authenticated client for Devpost with session persistence."""

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        headed: bool = False,
    ) -> None:
        self.email = email
        self.password = password
        self.headed = headed
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False

    async def close(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    @staticmethod
    def get_credentials() -> tuple[str, str]:
        """Get credentials from environment or session."""
        creds = get_credentials()
        if not creds:
            raise DevpostError(
                "DEVPOST_EMAIL and DEVPOST_PASSWORD must be set. "
                "Use `devpost auth login` or set environment variables.",
                code="AUTH_REQUIRED",
            )
        return creds

    async def _get_browser_and_page(self) -> tuple[Any, Any]:
        """Get or create browser context with session persistence."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise DevpostError(
                "Playwright not installed. Install with: pip install playwright && playwright install chromium",
                code="DEPENDENCY_MISSING",
            )

        if self._page and self._browser:
            try:
                await self._page.goto("https://devpost.com/", wait_until="networkidle", timeout=10000)
                return self._browser, self._page
            except Exception as e:
                logger.debug("Existing browser session invalid, recreating: %s", e)
                await self.close()

        session = load_session()

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=not self.headed,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ]
        )

        if session and session.get("cookies"):
            self._context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            await self._context.add_cookies(session["cookies"])
            self._page = await self._context.new_page()

            try:
                await self._page.goto("https://devpost.com/", wait_until="networkidle", timeout=15000)
                await asyncio.sleep(2)
                if "Log in" not in await self._page.content():
                    return self._browser, self._page
            except Exception as e:
                logger.debug("Session cookies invalid, re-authenticating: %s", e)

            await self._context.close()
            self._context = None
            self._page = None

        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        self._page = await self._context.new_page()

        await self._page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
        """)

        await self._page.goto("https://devpost.com/users/login", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        email, password = self.email, self.password
        if not email or not password:
            email, password = self.get_credentials()

        await self._page.fill("input#user_email", email)
        await self._page.fill("input#user_password", password)
        await self._page.click("button#submit-form")
        await self._page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        error_selector = ".alert.alert-error, .error-message, .flash-error"
        try:
            error_elem = await self._page.wait_for_selector(error_selector, timeout=2000)
            if error_elem:
                error_text = await error_elem.text_content()
                await self.close()
                raise DevpostError(
                    f"Login failed: {error_text.strip() if error_text else 'Invalid credentials'}",
                    code="AUTH_FAILED",
                )
        except DevpostError:
            raise
        except Exception:
            pass

        if "users/login" in self._page.url:
            await self.close()
            raise DevpostError("Login failed - check credentials", code="AUTH_FAILED")

        cookies = await self._context.cookies()
        save_session(cookies, email)

        return self._browser, self._page

    async def submit_project(
        self,
        hackathon_slug: str,
        title: str,
        tagline: str,
        description: Optional[str] = None,
        built_with: Optional[list[str]] = None,
        links: Optional[dict] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Submit a project to a hackathon."""
        validate_slug(hackathon_slug)
        result = {
            "success": False,
            "hackathon_slug": hackathon_slug,
            "project_title": title,
            "dry_run": dry_run,
            "steps": [],
        }

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            result["steps"].append("Navigating to hackathon")
            await page.goto(f"https://{hackathon_slug}.devpost.com/", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            result["steps"].append("Looking for submit button")
            submit_button = page.locator("a:has-text('Submit project'), a:has-text('Start a submission'), a:has-text('Start submission')").first
            if await submit_button.count() == 0:
                raise DevpostError("Submit button not found - hackathon may not be accepting submissions", code="SUBMISSION_CLOSED")

            await submit_button.click()
            await page.wait_for_url("**/challenges/start_a_submission**", timeout=15000)
            await asyncio.sleep(2)

            result["steps"].append("Looking for project creation link")
            create_link = page.locator("a:has-text('Create a project'), a:has-text('New project')").first
            if await create_link.count() > 0:
                await create_link.click()
                await page.wait_for_url("**/software/new**", timeout=15000)
                await asyncio.sleep(2)

            if dry_run:
                result["success"] = True
                result["message"] = "DRY RUN - Form would be submitted"
                return result

            result["steps"].append("Filling form")
            await page.fill("input[name='software[name]']", title)
            await page.fill("input[name='software[tagline]']", tagline)

            if description:
                await page.fill("textarea[name='software[description]']", description)

            if built_with:
                tech_input = page.locator("input[placeholder*='technology'], input[name*='built_with']").first
                for tech in built_with:
                    await tech_input.fill(tech)
                    await tech_input.press("Enter")
                    await asyncio.sleep(0.5)

            if links:
                if links.get("github"):
                    try:
                        await page.fill("input[name*='github'], input[placeholder*='github']", links["github"])
                    except Exception as e:
                        logger.warning("Could not fill GitHub link: %s", e)
                if links.get("demo"):
                    try:
                        await page.fill("input[name*='demo'], input[placeholder*='demo']", links["demo"])
                    except Exception as e:
                        logger.warning("Could not fill demo link: %s", e)

            result["steps"].append("Submitting")
            await page.click("input[type='submit'], button[type='submit'], button:has-text('Save'), button:has-text('Submit')")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            current_url = page.url
            if "/software/" in current_url:
                result["success"] = True
                result["url"] = current_url
                result["message"] = "Project submitted successfully!"
            else:
                errors = await page.locator(".error, .alert-error, .field_with_errors").all_text_contents()
                if errors:
                    raise DevpostError(f"Submission failed: {'; '.join(errors)}", code="SUBMISSION_FAILED")
                result["message"] = "Submission completed - check your dashboard"
                result["success"] = True

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            result["steps"].append(f"Error: {e.message}")
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def list_my_submissions(self, limit: int = 20) -> dict[str, Any]:
        """List user's submitted projects."""
        result = {"success": False, "submissions": [], "steps": []}

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            result["steps"].append("Navigating to portfolio")
            await page.goto("https://devpost.com/software?ref_content=portfolio&ref_feature=portfolio&ref_medium=global-nav", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            await page.wait_for_selector(".software-item, .project-card, .challenge-portfolio, [data-testid]", timeout=10000)

            projects = await page.locator(".software-item, .project-card, [data-testid='project-card']").all()

            for i, project in enumerate(projects[:limit]):
                try:
                    title_elem = await project.locator("h3, .title, .software-name").text_content()
                    link_elem = await project.locator("a").first.get_attribute("href")

                    result["submissions"].append({
                        "index": i,
                        "title": title_elem.strip() if title_elem else "Unknown",
                        "url": f"https://devpost.com{link_elem}" if link_elem and link_elem.startswith("/") else link_elem,
                    })
                except Exception as e:
                    logger.debug("Error parsing project %d: %s", i, e)
                    result["steps"].append(f"Error parsing project {i}: {e}")

            result["success"] = True
            result["count"] = len(result["submissions"])

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def get_submission_details(self, project_url: str) -> dict[str, Any]:
        """Get detailed info about a specific project submission."""
        validate_devpost_url(project_url)
        result = {"success": False, "url": project_url, "steps": []}

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            result["steps"].append(f"Navigating to {project_url}")
            await page.goto(project_url, timeout=30000)
            await page.wait_for_load_state("networkidle")

            details = {}

            try:
                title_elem = await page.wait_for_selector("h1#app-title, h1.software-title, header h1", timeout=5000)
                details["title"] = await title_elem.text_content()
                details["title"] = details["title"].strip() if details["title"] else None
            except Exception:
                logger.debug("Could not extract submission title")

            try:
                tagline_elem = await page.query_selector(".tagline, .elevator-pitch, #app-tagline, .software-tagline")
                details["tagline"] = await tagline_elem.text_content()
                details["tagline"] = details["tagline"].strip() if details["tagline"] else None
            except Exception:
                logger.debug("Could not extract submission tagline")

            try:
                desc_elem = await page.query_selector("#app-details, .description, .software-description, .project-description")
                details["description"] = await desc_elem.text_content()
                details["description"] = details["description"].strip() if details["description"] else None
            except Exception:
                logger.debug("Could not extract submission description")

            try:
                built_elem = await page.query_selector(".built-with, #built-with, .technologies")
                built_text = await built_elem.text_content()
                if built_text:
                    details["built_with"] = [t.strip() for t in built_text.replace("Built with:", "").split(",")]
            except Exception:
                logger.debug("Could not extract built-with from submission")

            links = {}
            try:
                github = await page.query_selector("a[href*='github.com']")
                if github:
                    links["github"] = await github.get_attribute("href")
            except Exception:
                logger.debug("Could not extract GitHub link from submission")
            try:
                demo = await page.query_selector("a[href*='demo'], a[rel*='demo']")
                if demo:
                    links["demo"] = await demo.get_attribute("href")
            except Exception:
                logger.debug("Could not extract demo link from submission")
            try:
                video = await page.query_selector("a[href*='youtube.com'], a[href*='vimeo.com']")
                if video:
                    links["video"] = await video.get_attribute("href")
            except Exception:
                logger.debug("Could not extract video link from submission")
            if links:
                details["links"] = links

            team = []
            try:
                team_section = await page.query_selector(".team-members, .contributors, .collaborators")
                if team_section:
                    members = await team_section.query_selector_all("a[href*='/users/']")
                    for member in members:
                        username = await member.get_attribute("href")
                        name = await member.text_content()
                        if username:
                            team.append({
                                "username": username.replace("/users/", "").strip("/"),
                                "name": name.strip() if name else None,
                            })
            except Exception:
                logger.debug("Could not extract team from submission")
            if team:
                details["team_members"] = team

            try:
                hackathon_elem = await page.query_selector(".challenge-info a, .hackathon-link")
                if hackathon_elem:
                    details["hackathon"] = {
                        "name": await hackathon_elem.text_content(),
                        "url": await hackathon_elem.get_attribute("href"),
                    }
            except Exception:
                logger.debug("Could not extract hackathon info from submission")

            result["details"] = details
            result["success"] = True

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def update_submission(
        self,
        project_url: str,
        title: Optional[str] = None,
        tagline: Optional[str] = None,
        description: Optional[str] = None,
        built_with: Optional[list[str]] = None,
        links: Optional[dict] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Update an existing project submission."""
        validate_devpost_url(project_url)
        result = {
            "success": False,
            "url": project_url,
            "dry_run": dry_run,
            "steps": [],
            "updated_fields": [],
        }

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            edit_url = f"{project_url.rstrip('/')}/edit"
            result["steps"].append(f"Navigating to edit page: {edit_url}")
            await page.goto(edit_url, timeout=30000)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            if title:
                try:
                    await page.fill("input[name='software[name]']", title)
                    result["updated_fields"].append("title")
                    result["steps"].append("Updated title")
                except Exception as e:
                    logger.warning("Could not update title: %s", e)
                    result["steps"].append(f"Could not update title: {e}")

            if tagline:
                try:
                    await page.fill("input[name='software[tagline]']", tagline)
                    result["updated_fields"].append("tagline")
                    result["steps"].append("Updated tagline")
                except Exception as e:
                    logger.warning("Could not update tagline: %s", e)
                    result["steps"].append(f"Could not update tagline: {e}")

            if description:
                try:
                    await page.fill("textarea[name='software[description]']", description)
                    result["updated_fields"].append("description")
                    result["steps"].append("Updated description")
                except Exception as e:
                    logger.warning("Could not update description: %s", e)
                    result["steps"].append(f"Could not update description: {e}")

            if built_with:
                try:
                    tech_string = ", ".join(built_with)
                    await page.fill("input[name='software[built_with]']", tech_string)
                    result["updated_fields"].append("built_with")
                    result["steps"].append("Updated technologies")
                except Exception as e:
                    logger.warning("Could not update technologies: %s", e)
                    result["steps"].append(f"Could not update technologies: {e}")

            if links:
                if links.get("github"):
                    try:
                        await page.fill("input[name='software[github_url]']", links["github"])
                        result["updated_fields"].append("github_link")
                    except Exception as e:
                        logger.warning("Could not update GitHub link: %s", e)
                if links.get("demo"):
                    try:
                        await page.fill("input[name='software[try_it_out_url]']", links["demo"])
                        result["updated_fields"].append("demo_link")
                    except Exception as e:
                        logger.warning("Could not update demo link: %s", e)
                if links.get("video"):
                    try:
                        await page.fill("input[name='software[video_url]']", links["video"])
                        result["updated_fields"].append("video_link")
                    except Exception as e:
                        logger.warning("Could not update video link: %s", e)

            if dry_run:
                result["steps"].append("DRY RUN - Changes not saved")
                result["success"] = True
                result["message"] = "Dry run completed - changes would be saved"
            else:
                try:
                    await page.click("input[type='submit'], button[type='submit'], button:has-text('Save'), button:has-text('Update')")
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(2)
                    result["steps"].append("Saved changes")
                    result["success"] = True
                    result["message"] = "Project updated successfully"
                except Exception as e:
                    result["error"] = f"Failed to save: {e}"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def add_team_member(self, project_url: str, username: str) -> dict[str, Any]:
        """Add a team member to a project."""
        validate_devpost_url(project_url)
        result = {"success": False, "project_url": project_url, "username": username, "steps": []}

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            team_url = f"{project_url.rstrip('/')}/team"
            result["steps"].append(f"Navigating to team page: {team_url}")
            await page.goto(team_url, timeout=30000)
            await page.wait_for_load_state("networkidle")

            result["steps"].append("Looking for add member field")
            try:
                await page.fill("input[name*='user'], input[name*='email'], input[name*='username']", username)
                result["steps"].append(f"Entered username: {username}")

                await page.click("input[value*='Add'], button:has-text('Add'), button:has-text('Invite')")
                await page.wait_for_load_state("networkidle")
                result["steps"].append("Clicked add member button")

                result["success"] = True
                result["message"] = f"Added {username} to project (or invitation sent)"

            except Exception as e:
                result["error"] = f"Could not add member: {e}"
                result["steps"].append(f"Error adding member: {e}")

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def remove_team_member(self, project_url: str, username: str) -> dict[str, Any]:
        """Remove a team member from a project."""
        validate_devpost_url(project_url)
        result = {"success": False, "project_url": project_url, "username": username, "steps": []}

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            team_url = f"{project_url.rstrip('/')}/team"
            result["steps"].append(f"Navigating to team page: {team_url}")
            await page.goto(team_url, timeout=30000)
            await page.wait_for_load_state("networkidle")

            result["steps"].append(f"Looking for member: {username}")
            try:
                member_elem = await page.query_selector(f"text={username}")
                if member_elem:
                    container = await member_elem.evaluate("el => el.closest('tr, .member, .team-member')")
                    if container:
                        remove_btn = await container.query_selector("a[href*='remove'], button:has-text('Remove'), .remove")
                        if remove_btn:
                            await remove_btn.click()
                            await page.wait_for_load_state("networkidle")
                            result["steps"].append("Clicked remove button")

                            try:
                                await page.click("button:has-text('Confirm'), input[value='Remove']")
                                await page.wait_for_load_state("networkidle")
                                result["steps"].append("Confirmed removal")
                            except Exception:
                                logger.debug("No confirmation dialog needed for removal")

                            result["success"] = True
                            result["message"] = f"Removed {username} from project"
                        else:
                            result["error"] = f"Could not find remove button for {username}"
                    else:
                        result["error"] = f"Could not find member container for {username}"
                else:
                    result["error"] = f"Could not find team member: {username}"

            except Exception as e:
                result["error"] = f"Error removing member: {e}"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def delete_submission(self, project_url: str, confirm: bool = False) -> dict[str, Any]:
        """Delete a project submission permanently."""
        validate_devpost_url(project_url)
        if not confirm:
            return {
                "error": "Confirmation required",
                "code": "CONFIRMATION_REQUIRED",
                "message": "Set confirm=true to actually delete this project. THIS CANNOT BE UNDONE.",
                "project_url": project_url,
                "warning": "This will permanently delete the project and all its data.",
            }

        result = {"success": False, "project_url": project_url, "steps": []}

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            edit_url = f"{project_url.rstrip('/')}/edit"
            result["steps"].append(f"Navigating to edit page: {edit_url}")
            await page.goto(edit_url, timeout=30000)
            await page.wait_for_load_state("networkidle")

            result["steps"].append("Looking for delete option")
            try:
                delete_link = await page.query_selector("a[href*='delete'], a:has-text('Delete'), .delete-project")
                if delete_link:
                    await delete_link.click()
                    await page.wait_for_load_state("networkidle")
                    result["steps"].append("Clicked delete link")

                    try:
                        await page.click("button:has-text('Delete'), input[value='Delete'], button[type='submit']")
                        await page.wait_for_load_state("networkidle")
                        result["steps"].append("Confirmed deletion")
                        result["success"] = True
                        result["message"] = "Project deleted permanently"
                    except Exception as e:
                        result["error"] = f"Could not confirm deletion: {e}"
                else:
                    result["error"] = "Could not find delete option on page"
                    result["code"] = "NOT_FOUND"

            except Exception as e:
                result["error"] = f"Error during deletion: {e}"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def upload_screenshots(
        self,
        project_url: str,
        image_paths: list[str],
        set_main_image: int = 0,
    ) -> dict[str, Any]:
        """Upload screenshots to a project."""
        validate_devpost_url(project_url)
        result = {
            "success": False,
            "project_url": project_url,
            "image_paths": image_paths,
            "uploaded": [],
            "failed": [],
            "steps": [],
        }

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            edit_url = f"{project_url.rstrip('/')}/edit"
            result["steps"].append(f"Navigating to edit page: {edit_url}")
            await page.goto(edit_url, timeout=30000)
            await page.wait_for_load_state("networkidle")

            result["steps"].append("Looking for image upload section")

            for i, image_path in enumerate(image_paths):
                try:
                    file_input = await page.wait_for_selector(
                        "input[type='file'], input[name*='image'], input[name*='screenshot']",
                        timeout=5000,
                    )

                    if file_input:
                        await file_input.set_input_files(image_path)
                        result["steps"].append(f"Selected file: {image_path}")

                        await page.wait_for_timeout(3000)

                        result["uploaded"].append(image_path)
                        result["steps"].append(f"Uploaded: {image_path}")
                    else:
                        result["failed"].append({"path": image_path, "reason": "File input not found"})

                except Exception as e:
                    result["failed"].append({"path": image_path, "reason": str(e)})
                    result["steps"].append(f"Failed to upload {image_path}: {e}")

            if set_main_image < len(result["uploaded"]):
                try:
                    images = await page.query_selector_all(".thumbnail, .project-image, .uploaded-image")
                    if set_main_image < len(images):
                        await images[set_main_image].click()
                        result["steps"].append(f"Set image {set_main_image} as main")
                except Exception as e:
                    logger.debug("Could not set main image: %s", e)
                    result["steps"].append(f"Could not set main image: {e}")

            try:
                await page.click("input[type='submit'], button:has-text('Save')")
                await page.wait_for_load_state("networkidle")
                result["steps"].append("Saved changes")
                result["success"] = len(result["uploaded"]) > 0
            except Exception as e:
                result["error"] = f"Failed to save: {e}"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def join_hackathon(self, hackathon_slug: str) -> dict[str, Any]:
        """Join/register for a hackathon."""
        validate_slug(hackathon_slug)
        result: dict[str, Any] = {
            "success": False,
            "data": {
                "hackathon_slug": hackathon_slug,
                "already_joined": False,
            },
            "error": None,
            "steps": [],
        }

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            result["steps"].append(f"Navigating to {hackathon_slug}.devpost.com")
            await page.goto(f"https://{hackathon_slug}.devpost.com/", wait_until="networkidle", timeout=30000)

            result["steps"].append("Looking for join/register button")
            join_button = page.locator(
                "a:has-text('Join'), a:has-text('Register'), button:has-text('Join'), button:has-text('Register')"
            ).first

            if await join_button.count() == 0:
                result["data"]["already_joined"] = True
                result["data"]["message"] = "Already registered or registration not available"
                result["success"] = True
                return result

            await join_button.click()
            await page.wait_for_load_state("networkidle")

            result["steps"].append("Clicked join button")

            if "manage/submissions" in page.url or "challenges" in page.url:
                result["success"] = True
                result["data"]["message"] = f"Successfully joined {hackathon_slug}"
            else:
                result["data"]["message"] = "Join action completed - check your dashboard"
                result["success"] = True

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def leave_hackathon(self, hackathon_slug: str, confirm: bool = False) -> dict[str, Any]:
        """Leave/withdraw from a hackathon."""
        validate_slug(hackathon_slug)
        if not confirm:
            return {
                "success": False,
                "data": {"hackathon_slug": hackathon_slug, "confirmation_required": True},
                "error": "Confirmation required - use --confirm flag",
                "code": "CONFIRMATION_REQUIRED",
            }

        result: dict[str, Any] = {
            "success": False,
            "data": {
                "hackathon_slug": hackathon_slug,
                "already_left": False,
            },
            "error": None,
            "steps": [],
        }

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            result["steps"].append(f"Navigating to {hackathon_slug}.devpost.com")
            await page.goto(f"https://{hackathon_slug}.devpost.com/", wait_until="networkidle", timeout=30000)

            result["steps"].append("Looking for leave/withdraw option")
            leave_link = page.locator(
                "a:has-text('Leave'), a:has-text('Withdraw'), button:has-text('Leave'), button:has-text('Withdraw')"
            ).first

            if await leave_link.count() == 0:
                result["data"]["already_left"] = True
                result["data"]["message"] = "Not registered or already left"
                result["success"] = True
                return result

            await leave_link.click()
            await page.wait_for_load_state("networkidle")
            result["steps"].append("Clicked leave button")

            try:
                confirm_btn = page.locator("button:has-text('Confirm'), button:has-text('Yes'), input[value='Leave']")
                if await confirm_btn.count() > 0:
                    await confirm_btn.first.click()
                    await page.wait_for_load_state("networkidle")
                    result["steps"].append("Confirmed leave")

                result["success"] = True
                result["data"]["message"] = f"Successfully left {hackathon_slug}"
            except Exception as e:
                result["error"] = f"Could not confirm: {e}"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def like_project(self, project_url: str) -> dict[str, Any]:
        """Like/bookmark a project."""
        validate_devpost_url(project_url)
        result: dict[str, Any] = {
            "success": False,
            "data": {
                "project_url": project_url,
                "already_liked": False,
            },
            "error": None,
            "steps": [],
        }

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            result["steps"].append(f"Navigating to {project_url}")
            await page.goto(project_url, timeout=30000)
            await page.wait_for_load_state("networkidle")

            result["steps"].append("Looking for like button")
            like_button = page.locator(
                "button:has-text('Like'), a:has-text('Like'), [data-action='like'], .like-button"
            ).first

            if await like_button.count() == 0:
                result["data"]["already_liked"] = True
                result["data"]["message"] = "Already liked or like button not available"
                result["success"] = True
                return result

            await like_button.click()
            await page.wait_for_timeout(1000)

            result["success"] = True
            result["data"]["message"] = "Project liked successfully"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def create_team(
        self,
        hackathon_slug: str,
        team_name: str,
        invite_usernames: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Create a team for a hackathon."""
        validate_slug(hackathon_slug)
        result = {
            "success": False,
            "hackathon_slug": hackathon_slug,
            "team_name": team_name,
            "steps": [],
        }

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            result["steps"].append(f"Navigating to {hackathon_slug} team page")
            await page.goto(f"https://{hackathon_slug}.devpost.com/team", wait_until="networkidle", timeout=30000)

            result["steps"].append("Looking for create team option")
            create_button = page.locator(
                "a:has-text('Create team'), button:has-text('Create team'), a:has-text('Form a team')"
            ).first

            if await create_button.count() == 0:
                result["error"] = "Create team option not found"
                result["code"] = "NOT_FOUND"
                return result

            await create_button.click()
            await page.wait_for_load_state("networkidle")
            result["steps"].append("Clicked create team")

            result["steps"].append("Filling team name")
            await page.fill("input[name*='team_name'], input[name*='name'], input[placeholder*='team name']", team_name)

            if invite_usernames:
                result["steps"].append("Adding invitees")
                for username in invite_usernames:
                    try:
                        await page.fill("input[name*='email'], input[name*='username'], input[placeholder*='username']", username)
                        await page.click("button:has-text('Add'), input[value*='Add']")
                        await page.wait_for_timeout(500)
                    except Exception:
                        logger.debug("Could not add invitee %s", username)

            result["steps"].append("Submitting team creation")
            await page.click("input[type='submit'], button:has-text('Create'), button:has-text('Save')")
            await page.wait_for_load_state("networkidle")

            result["success"] = True
            result["message"] = f"Team '{team_name}' created successfully"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def join_team(self, hackathon_slug: str, invite_url: Optional[str] = None) -> dict[str, Any]:
        """Join a team for a hackathon."""
        validate_slug(hackathon_slug)
        if invite_url:
            validate_devpost_url(invite_url)
        result = {
            "success": False,
            "hackathon_slug": hackathon_slug,
            "steps": [],
        }

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            if invite_url:
                result["steps"].append(f"Navigating to invite URL")
                await page.goto(invite_url, wait_until="networkidle", timeout=30000)
            else:
                result["steps"].append(f"Navigating to {hackathon_slug} team page")
                await page.goto(f"https://{hackathon_slug}.devpost.com/team", wait_until="networkidle", timeout=30000)

            result["steps"].append("Looking for join team option")
            join_button = page.locator(
                "a:has-text('Join team'), button:has-text('Join team'), a:has-text('Accept invite'), input[value*='Join']"
            ).first

            if await join_button.count() == 0:
                result["error"] = "Join team option not found"
                result["code"] = "NOT_FOUND"
                return result

            await join_button.click()
            await page.wait_for_load_state("networkidle")
            result["steps"].append("Clicked join team")

            result["success"] = True
            result["message"] = "Successfully joined team"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result


async def save_credentials_interactive(email: str, password: str) -> dict[str, Any]:
    """Save credentials interactively.

    Only saves credentials after successful login verification.
    """
    try:
        test_client = AuthenticatedClient(email=email, password=password)
        browser, page = await test_client._get_browser_and_page()
        await test_client.close()

        save_credentials(email, password)
        return {
            "success": True,
            "message": "Credentials saved and verified successfully",
            "email": email,
        }
    except DevpostError as e:
        return {
            "success": False,
            "error": e.message,
            "code": e.code,
            "message": "Failed to save or verify credentials",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to save or verify credentials",
        }


async def clear_credentials() -> dict[str, Any]:
    """Clear saved credentials."""
    clear_session()
    return {
        "success": True,
        "message": "Credentials and session cleared",
    }
