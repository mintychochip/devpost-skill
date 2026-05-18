"""Core business logic for Devpost CLI and MCP server."""

import asyncio
from datetime import datetime
import json
import os
import random
import re
from typing import Any, Callable, Optional
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
    make_user_followers_key,
    make_user_following_key,
    make_user_likes_key,
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
from .api import DevpostAPI

logger = get_logger("core")

BASE_URL = "https://devpost.com"
API_BASE = "https://devpost.com/api"

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0
RETRY_STATUS_CODES = {429, 502, 503, 504}

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", re.IGNORECASE)
_DEVPOST_URL_RE = re.compile(r"^https://([a-z0-9-]+\.)?devpost\.com/", re.IGNORECASE)

# Playwright selectors for Devpost pages
PROJECT_SELECTORS = {
    "title": ["h1#app-title", "h1.software-title", "[data-test='project-title']", "h1"],
    "tagline": ["p.tagline", ".elevator-pitch", "#app-tagline", ".tagline"],
    "description": ["#app-details", ".description", ".software-description"],
    "built_with": ["#built-with", ".built-with", ".tech-stack"],
    "team": ["#app-team", ".team-members", ".collaborators"],
    "gallery": ["#gallery", ".gallery", ".screenshots"],
    "winner_badge": [".winner", ".winner-badge", ".prize-winner"],
}

USER_SELECTORS = {
    "name": ["h1", ".name", ".profile-name"],
    "bio": [".bio", ".about", ".description"],
    "skills": [".skill", ".tag", ".pill"],
    "projects": ["h5", ".project-title"],
}

# User agents for rotation (anti-detection)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def _get_random_user_agent() -> str:
    """Get random user agent string."""
    return random.choice(USER_AGENTS)


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
    """Extract content for a rules section (eligibility, requirements, judging, etc.).
    
    Handles both:
    1. Traditional h1-h6 headings followed by lists/paragraphs
    2. Devpost rules page structure with numbered sections like:
       "4. ELIGIBILITY: To be eligible..." in <strong> tags
    """
    items = []
    
    # First pass: traditional h1-h6 headings (for tests and simple pages)
    for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
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
                sibling = sibling.find_next_sibling()
    
    # Second pass: strong tags with numbered sections (for Devpost rules pages)
    for strong in soup.find_all('strong'):
        text = strong.get_text(strip=True).lower()
        if any(re.search(p, text) for p in heading_patterns):
            parent = strong.parent
            
            # Extract content from the same paragraph (after the heading)
            if parent and parent.name == 'p':
                # Get all text from paragraph, remove the heading prefix
                full_text = parent.get_text(strip=True)
                heading_text = strong.get_text(strip=True)
                # Remove heading and any colon/numbering prefix
                content = full_text.replace(heading_text, '', 1).lstrip(':').strip()
                
                # Split long content by numbered items (1), (2), etc.
                if content:
                    if len(content) > 500:
                        # Split by numbered patterns like (1), (2), etc.
                        numbered_items = re.split(r'\s*\((\d+)\)\s*', content)
                        if len(numbered_items) > 1:
                            # Reconstruct numbered items
                            for i in range(1, len(numbered_items), 2):
                                num = numbered_items[i]
                                text_part = numbered_items[i + 1] if i + 1 < len(numbered_items) else ''
                                item_text = f"({num}) {text_part}".strip()
                                if item_text and len(item_text) < 500:
                                    items.append(item_text)
                        else:
                            # Split by sentences (period followed by space and capital letter)
                            sentences = re.split(r'(?<=[.;])\s+(?=[A-Z])', content)
                            for sent in sentences:
                                if sent and len(sent) < 500:
                                    items.append(sent)
                    elif len(content) < 500:
                        items.append(content)
                
                # Extract from following sibling paragraphs until next numbered section
                sibling = parent.find_next_sibling()
                while sibling:
                    # Stop at next numbered section (e.g., "5.", "6.", etc.)
                    if sibling.name == 'p':
                        sib_text = sibling.get_text(strip=True)
                        if re.match(r'^\d+\.\s', sib_text):
                            break
                        if sib_text and len(sib_text) < 500 and sib_text.strip() != '\uFFFD':
                            items.append(sib_text)
                    elif sibling.name in ('ul', 'ol'):
                        for li in sibling.find_all('li'):
                            li_text = li.get_text(strip=True)
                            if li_text and len(li_text) < 500:
                                items.append(li_text)
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

    def __init__(self, headed: bool = False, use_cache: bool = True, debug_screenshots: bool = False) -> None:
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
        self.debug_screenshots = debug_screenshots
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
        order_by: str = "recently-added",
        search: Optional[str] = None,
        challenge_type: Optional[list[str]] = None,
        length: Optional[list[str]] = None,
        themes: Optional[list[str]] = None,
        organization: Optional[str] = None,
        open_to: Optional[list[str]] = None,
        managed_by_devpost_badge: bool = False,
        eligibility: bool = False,
        page: int = 1,
        per_page: int = 9,
    ) -> dict[str, Any]:
        """List hackathons via API with full filter support.

        Returns a dict with 'hackathons' list and 'meta' info from API.

        API parameters match the website:
        - status[]: open, upcoming, ended (not open_state)
        - order_by: most-relevant, deadline, recently-added, prize-amount (not sort_by)
        - search: text search (not q)
        - challenge_type[]: online, in-person
        - length[]: days, weeks, months
        - themes[]: theme names (URL-encoded)
        - organization: org name
        - open_to[]: public, invite_only
        - managed_by_devpost_badge: 1 or 0
        - eligibility: 1 or 0 (requires auth)
        - page, per_page: pagination
        """
        api_states = [open_state] if open_state else []
        if "closed" in api_states:
            api_states = [s if s != "closed" else "ended" for s in api_states]

        cache_key = make_list_key(
            state=open_state,
            order_by=order_by,
            search=search,
            challenge_type=challenge_type,
            length=length,
            themes=themes,
            organization=organization,
            open_to=open_to,
            managed_by_devpost_badge=managed_by_devpost_badge,
            eligibility=eligibility,
            page=page,
            per_page=per_page,
        )
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        # Use lightweight DevpostAPI client instead of Playwright
        api = DevpostAPI()
        try:
            result = await api.search_hackathons(
                search=search,
                open_state=api_states[0] if api_states else None,
                status=api_states if len(api_states) > 1 else None,
                themes=themes,
                open_to=open_to,
                eligibility=eligibility,
                managed_by_devpost_badge=managed_by_devpost_badge,
                limit=per_page,
                page=page,
                sort_by=order_by if order_by and order_by != "most-relevant" else None,
            )
        finally:
            await api.close()
        
        hackathons = result.get("hackathons", [])
        meta = result.get("meta", {})

        for h in hackathons:
            if h.get("prize_amount"):
                h["prize_amount"] = clean_html(h["prize_amount"])
            h["ends_at"] = h.get("time_left_to_submission") or h.get("submission_period_dates")

        result = {"hackathons": hackathons, "meta": meta}

        if self._cache:
            self._cache.set(cache_key, result)

        return result

    async def list_all_hackathons(
        self,
        open_state: Optional[str] = None,
        order_by: str = "recently-added",
        search: Optional[str] = None,
        challenge_type: Optional[list[str]] = None,
        length: Optional[list[str]] = None,
        themes: Optional[list[str]] = None,
        organization: Optional[str] = None,
        open_to: Optional[list[str]] = None,
        managed_by_devpost_badge: bool = False,
        eligibility: bool = False,
        per_page: int = 50,
        max_pages: Optional[int] = None,
    ) -> list[dict]:
        """Fetch ALL hackathons with auto-pagination.
        
        Automatically paginates through all results up to max_pages.
        Useful for building a complete local index or comprehensive search.
        
        Args:
            open_state: Filter by state (open, upcoming, ended)
            order_by: Sort order
            search: Search query
            challenge_type: Filter by type (online, in-person)
            length: Filter by duration (days, weeks, months)
            themes: Filter by themes
            organization: Filter by organization
            open_to: Filter by access (public, invite_only)
            managed_by_devpost_badge: Only Devpost-managed
            eligibility: Only hackathons user is eligible for (requires auth)
            per_page: Results per page (max 50)
            max_pages: Max pages to fetch (None = fetch all)
        
        Returns:
            List of all hackathon dicts
        """
        all_hackathons = []
        page = 1
        
        while True:
            result = await self.list_hackathons(
                limit=per_page,
                open_state=open_state,
                order_by=order_by,
                search=search,
                challenge_type=challenge_type,
                length=length,
                themes=themes,
                organization=organization,
                open_to=open_to,
                managed_by_devpost_badge=managed_by_devpost_badge,
                eligibility=eligibility,
                page=page,
                per_page=per_page,
            )
            
            hackathons = result.get("hackathons", [])
            if not hackathons:
                break
            
            all_hackathons.extend(hackathons)
            
            meta = result.get("meta", {})
            total_count = meta.get("total_count", 0)
            total_pages = meta.get("total_pages", 0)
            
            if len(hackathons) < per_page:
                break
            
            if max_pages and page >= max_pages:
                break
            
            if page >= total_pages:
                break
            
            page += 1
            await asyncio.sleep(0.5)
        
        return all_hackathons

    async def search_users(
        self,
        query: str,
        limit: int = 20,
    ) -> list[dict]:
        """Search for users on Devpost.
        
        Uses participant lists from hackathons to discover users.
        For detailed user info, use get_user_full(username).
        
        Args:
            query: Search query (matches username or name)
            limit: Max users to return
        
        Returns:
            List of user dicts with username, name, url
        """
        if not query:
            return []
        
        q = query.lower()
        found_users = {}
        
        hackathons = await self.list_hackathons(limit=10, open_state="open")
        
        for h in hackathons.get("hackathons", []):
            if len(found_users) >= limit:
                break
            
            slug = h.get("url", "").rstrip("/").split("/")[-1]
            if not slug:
                continue
            
            try:
                participants = await self.get_participants(slug, limit=50)
                for p in participants.get("participants", []):
                    username = p.get("username", "").lower()
                    name = p.get("name", "").lower()
                    
                    if q in username or q in name:
                        key = p.get("username", "")
                        if key and key not in found_users:
                            found_users[key] = p
            except Exception:
                continue
            
            await asyncio.sleep(0.3)
        
        return list(found_users.values())[:limit]

    async def get_hackathon_by_slug(self, slug: str) -> Optional[dict]:
        """Get hackathon by URL slug."""
        validate_slug(slug)
        cache_key = make_hackathon_key(slug)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        # Use lightweight DevpostAPI client instead of Playwright
        api = DevpostAPI()
        try:
            h = await api.get_hackathon_by_slug(slug)
        finally:
            await api.close()
        
        if h:
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

    async def get_featured_hackathons(self, challenge_type: str = "online") -> list[dict]:
        """Get featured hackathons.
        
        Args:
            challenge_type: "online" or "in-person"
        
        Returns:
            List of featured hackathons
        """
        api = DevpostAPI()
        try:
            return await api.get_featured_hackathons(challenge_type=challenge_type)
        finally:
            await api.close()

    async def get_recommended_hackathons(self) -> list[dict]:
        """Get recommended hackathons (requires auth for personalized results)."""
        api = DevpostAPI()
        try:
            return await api.get_recommended_hackathons()
        finally:
            await api.close()

    async def get_nearby_hackathons(self) -> list[dict]:
        """Get nearby hackathons (requires location/auth for meaningful results)."""
        api = DevpostAPI()
        try:
            return await api.get_nearby_hackathons()
        finally:
            await api.close()

    async def search_organizations(self, term: str = "") -> list[dict]:
        """Search organizations.
        
        Args:
            term: Search term (empty string returns all)
        
        Returns:
            List of organizations with id, name, count
        """
        api = DevpostAPI()
        try:
            return await api.search_organizations(term=term)
        finally:
            await api.close()

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
                
                # Parse JSON-LD structured data (Event schema)
                if 'application/ld+json' in (script.get('type', '') or ''):
                    try:
                        json_ld = json.loads(text)
                        if isinstance(json_ld, dict) and json_ld.get('@type') == 'Event':
                            data["json_ld"] = {
                                "name": json_ld.get('name'),
                                "start_date": json_ld.get('startDate'),
                                "end_date": json_ld.get('endDate'),
                                "organizer": json_ld.get('organizer', {}).get('name') if json_ld.get('organizer') else None,
                                "event_status": json_ld.get('eventStatus'),
                                "event_attendance_mode": json_ld.get('eventAttendanceMode'),
                            }
                    except (json.JSONDecodeError, ValueError, TypeError) as e:
                        logger.debug("Could not parse JSON-LD: %s", e)

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
        sort_by: Optional[str] = None,
        category: Optional[str] = None,
        search_query: Optional[str] = None,
        page: int = 1,
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
        
        params = {}
        if sort_by:
            if sort_by == "winners":
                params["winners_only"] = "true"
            elif sort_by in ("recent", "alpha"):
                params["sort_by"] = sort_by
            # Note: "liked" sorting is not supported by the Devpost gallery page
        if category:
            params["filter[category]"] = category
        if search_query:
            params["query"] = search_query
        if page > 1:
            params["page"] = str(page)

        gallery_url = base_gallery_url
        if params:
            from urllib.parse import urlencode
            gallery_url = f"{base_gallery_url}?{urlencode(params)}"
        
        result["steps"].append(f"Fetching gallery: {gallery_url}")

        try:
            all_projects = []
            seen_urls = set()
            current_page = 1
            max_pages = 10 if fetch_all_pages else 1

            while current_page <= max_pages:
                if current_page > 1:
                    params["page"] = str(current_page)
                    gallery_url = f"{base_gallery_url}?{urlencode(params)}"
                result["steps"].append(f"Fetching page {current_page}: {gallery_url}")

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
                    if not next_link or f"page={current_page+1}" not in str(next_link):
                        pagination = soup.find(class_=re.compile(r'pagination', re.I))
                        if pagination:
                            next_page_link = pagination.find("a", href=re.compile(rf'page={current_page+1}'))
                            if not next_page_link:
                                result["steps"].append("No more pages found")
                                break
                        else:
                            result["steps"].append("No pagination found, assuming last page")
                            break

                    current_page += 1

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

    # ========================================================================
    # Playwright Helper Methods
    # ========================================================================

    async def _playwright_scrape(
        self,
        url: str,
        extractor_fn: Callable,
        cache_key: Optional[str] = None,
        wait_for_selector: Optional[str] = None,
        timeout: int = 30000,
        skip_rate_limit: bool = False,
    ) -> dict:
        """Generic Playwright scraper with caching, rate limiting, and error handling.
        
        Args:
            url: Page URL to scrape
            extractor_fn: Async function that takes (page, result) and extracts data
            cache_key: Optional cache key for result caching
            wait_for_selector: Optional selector to wait for before extraction
            timeout: Page load timeout in ms
        
        Returns:
            dict with 'success', 'data', 'error', 'steps' keys
        """
        result = {"success": False, "url": url, "steps": [], "data": {}}
        
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return {
                "error": "Playwright not installed. Install with: pip install playwright && playwright install chromium",
                "code": "DEPENDENCY_MISSING",
            }
        
        # Rate limiter: 3 requests per 10 seconds to avoid Cloudflare blocks
        # Skip in test environments
        import sys
        if not skip_rate_limit and "pytest" not in sys.modules:
            try:
                from aiolimiter import AsyncLimiter
                limiter = AsyncLimiter(3, 10)
                await limiter.acquire()
            except ImportError:
                pass  # Rate limiting optional
        
        async with async_playwright() as p:
            user_agent = _get_random_user_agent()
            browser_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                f"--user-agent={user_agent}",
            ]
            
            browser = await p.chromium.launch(headless=not self.headed, args=browser_args)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
            )
            page = await context.new_page()
            
            try:
                result["steps"].append(f"Loading {url}")
                await page.goto(url, timeout=timeout, wait_until="networkidle")
                
                # Wait for specific content if specified
                if wait_for_selector:
                    await page.wait_for_selector(wait_for_selector, timeout=5000, state="visible")
                    result["steps"].append(f"Waited for {wait_for_selector}")
                
                # Double network idle for late-loading resources
                await asyncio.sleep(0.5)
                await page.wait_for_load_state("networkidle")
                
                # Run extractor
                await extractor_fn(page, result)
                
                result["success"] = True
                result["steps"].append("Successfully extracted data")
                
            except Exception as e:
                result["error"] = str(e)
                result["steps"].append(f"Error: {e}")
                
                # Capture debug screenshot if enabled
                if getattr(self, 'debug_screenshots', False):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    screenshot_path = f"/tmp/playwright_error_{timestamp}.png"
                    await page.screenshot(path=screenshot_path)
                    result["debug_screenshot"] = screenshot_path
            finally:
                await browser.close()
        
        # Cache if successful
        if result["success"] and cache_key and self._cache:
            self._cache.set(cache_key, result, ttl=1800)
        
        return result

    async def _extract_with_fallback(self, page, selectors: list[str], timeout: int = 5000):
        """Try multiple selectors in order of preference."""
        for selector in selectors:
            try:
                elem = await page.wait_for_selector(selector, timeout=timeout)
                if elem:
                    return elem
            except Exception:
                continue
        return None

    async def _extract_text_with_fallback(self, page, selectors: list[str], default: str = None) -> Optional[str]:
        """Extract text content with fallback selectors."""
        elem = await self._extract_with_fallback(page, selectors)
        return await elem.text_content() if elem else default

    async def _retry_selector(self, page, selector: str, retries: int = 3, backoff: float = 0.5):
        """Retry selector with exponential backoff."""
        for attempt in range(retries):
            elem = await page.query_selector(selector)
            if elem:
                return elem
            if attempt < retries - 1:
                delay = backoff * (2 ** attempt)
                logger.debug("Selector '%s' not found, retrying in %.1fs (attempt %d/%d)", 
                            selector, delay, attempt + 1, retries)
                await asyncio.sleep(delay)
        return None

    async def _extract_project_cards(self, page) -> list[dict]:
        """Extract project cards using JavaScript for reliability."""
        return await page.evaluate('''() => {
            const cards = document.querySelectorAll('.gallery-item, .software-entry');
            return Array.from(cards).slice(0, 50).map(card => {
                const link = card.querySelector('a[href*="/software/"]');
                const titleElem = card.querySelector('h5, .title');
                const taglineElem = card.querySelector('.tagline, .description');
                
                return {
                    title: titleElem?.textContent.trim() || null,
                    url: link?.href || null,
                    tagline: taglineElem?.textContent.trim() || null,
                    is_winner: card.classList.contains('winner') || 
                              !!card.querySelector('.winner-badge'),
                };
            });
        }''')

    async def _extract_user_info(self, page) -> dict:
        """Extract user profile info using JavaScript."""
        return await page.evaluate('''() => {
            const data = {};
            
            // Name
            const nameElem = document.querySelector('h1, .name, .profile-name');
            data.name = nameElem?.textContent.trim();
            
            // Bio
            const bioElem = document.querySelector('.bio, .about, .description');
            data.bio = bioElem?.textContent.trim();
            
            // Skills
            const skills = Array.from(document.querySelectorAll('.skill, .tag, .pill'))
                .slice(0, 20)
                .map(s => s.textContent.trim())
                .filter(s => s && s.length < 50);
            data.skills = skills;
            
            // Links
            const links = {};
            const githubLink = document.querySelector('a[href*="github.com"]');
            const twitterLink = document.querySelector('a[href*="twitter.com"], a[href*="x.com"]');
            const websiteLink = document.querySelector('a[rel="external"], a.website-link');
            
            if (githubLink) links.github = githubLink.href;
            if (twitterLink) links.twitter = twitterLink.href;
            if (websiteLink && !websiteLink.href.includes('devpost.com')) {
                links.website = websiteLink.href;
            }
            data.links = links;
            
            return data;
        }''')

    async def get_project_details(self, project_url: str) -> dict[str, Any]:
        """Get detailed info about a specific project using browser automation."""
        validate_devpost_url(project_url)
        cache_key = make_project_key(project_url)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        async def extractor(page, result):
            """Extract project data from page."""
            data = {}
            
            # Title with fallback selectors
            title = await self._extract_with_fallback(page, PROJECT_SELECTORS["title"])
            data["title"] = await title.text_content() if title else None
            
            # Tagline
            tagline = await self._extract_with_fallback(page, PROJECT_SELECTORS["tagline"])
            data["tagline"] = await tagline.text_content() if tagline else None
            
            # Description
            desc = await self._extract_with_fallback(page, PROJECT_SELECTORS["description"])
            if desc:
                data["description"] = await desc.text_content()
                data["description_html"] = await desc.inner_html()
            
            # Built with
            built = await self._extract_with_fallback(page, PROJECT_SELECTORS["built_with"])
            if built:
                text = await built.text_content()
                techs = [t.strip() for t in text.replace("Built With", "").split() if t.strip()]
                data["built_with"] = techs
            
            # Links
            links = {}
            github = await page.query_selector("a[href*='github.com']")
            if github:
                links["github"] = await github.get_attribute("href")
            demo = await page.query_selector("a[href*='try-it-out'], a.demo-link, a[title*='demo' i]")
            if demo:
                links["demo"] = await demo.get_attribute("href")
            video = await page.query_selector("a[href*='youtube.com'], a[href*='vimeo.com'], a[href*='youtu.be']")
            if video:
                links["video"] = await video.get_attribute("href")
            website = await page.query_selector("a[rel*='external'], a.website-link")
            if website and "devpost.com" not in await website.get_attribute("href"):
                links["website"] = await website.get_attribute("href")
            if links:
                data["links"] = links
            
            # Team members
            team = []
            team_section = await self._extract_with_fallback(page, PROJECT_SELECTORS["team"])
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
                                team.append({"username": username_clean, "name": name.strip() if name else username_clean})
                    except Exception:
                        logger.debug("Could not extract team member info")
            if team:
                data["team"] = team
            
            # Screenshots
            screenshots = []
            gallery = await self._extract_with_fallback(page, PROJECT_SELECTORS["gallery"])
            if gallery:
                imgs = await gallery.query_selector_all("img")
                for img in imgs:
                    try:
                        src = await img.get_attribute("src")
                        if src and "placeholder" not in src:
                            screenshots.append(src)
                    except Exception:
                        pass
            if screenshots:
                data["screenshots"] = screenshots
            
            # Hackathon info
            hackathon = await page.query_selector("a[href*='devpost.com/'][href$='/']")
            if hackathon:
                hack_name = await hackathon.text_content()
                hack_url = await hackathon.get_attribute("href")
                data["hackathon"] = {"name": hack_name.strip() if hack_name else None, "url": hack_url}
            
            # Winner badge
            winner_badge = await self._extract_with_fallback(page, PROJECT_SELECTORS["winner_badge"])
            if winner_badge:
                data["is_winner"] = True
                data["prize"] = (await winner_badge.text_content()).strip() or "Winner"
            
            result["data"] = data

        result = await self._playwright_scrape(
            url=project_url,
            extractor_fn=extractor,
            cache_key=cache_key,
            wait_for_selector="h1",
        )
        
        return result

    async def get_user_profile(self, username: str) -> dict[str, Any]:
        """Get user profile info using Playwright (profile pages are JS-rendered)."""
        cache_key = f"user_profile_{username}"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        user_url = f"{BASE_URL}/users/{username}"
        
        async def extractor(page, result):
            """Extract user profile data."""
            # Check if page is 404
            if "404" in await page.title():
                result["error"] = f"User '{username}' not found"
                result["code"] = "NOT_FOUND"
                return
            
            data = {}
            
            # Use JavaScript extractor for basic info
            basic_info = await self._extract_user_info(page)
            data.update(basic_info)
            
            # Name with fallback
            if not data.get("name"):
                name = await self._extract_with_fallback(page, USER_SELECTORS["name"])
                if name:
                    raw_name = await name.text_content()
                    data["name"] = " ".join(raw_name.split())
            
            # Extract projects using JavaScript
            projects = await page.evaluate('''() => {
                const projects = [];
                const seen = new Set();
                document.querySelectorAll('h5').forEach(h5 => {
                    const title = h5.textContent.trim();
                    if (!title || title.length < 3 || title.length > 100) return;
                    if (['back', 'view all', 'software', 'projects', 'connect'].includes(title.toLowerCase())) return;
                    if (seen.has(title)) return;
                    seen.add(title);
                    
                    const parent = h5.parentElement.parentElement;
                    const projLink = parent.querySelector('a[href*="/software/"]');
                    const hackLink = parent.querySelector('a[href*=".devpost.com"]:not([href*="/users/"]):not([href*="/software/"])');
                    
                    const proj = { title, url: projLink?.href };
                    if (hackLink) {
                        const hackText = hackLink.textContent.trim().split('\\n')[0];
                        if (hackText && !['log in', 'sign up', 'about'].includes(hackText.toLowerCase())) {
                            proj.hackathon = hackText;
                            proj.hackathon_url = hackLink.href;
                        }
                    }
                    projects.push(proj);
                });
                return projects.slice(0, 20);
            }''')
            data["projects"] = projects
            data["project_count"] = len(projects)
            
            # Extract hackathons from challenges page
            challenges_url = f"{BASE_URL}/{username}/challenges"
            await page.goto(challenges_url, timeout=30000)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(1)
            
            hackathons = await page.evaluate('''() => {
                const hacks = [];
                const seen = new Set();
                document.querySelectorAll('a[href*=".devpost.com"]').forEach(link => {
                    const href = link.href;
                    if (!href || href.includes('/users/') || href.includes('info.devpost.com') || href.includes('help.devpost.com')) return;
                    if (!href.includes('.devpost.com/')) return;
                    if (seen.has(href)) return;
                    
                    const match = href.match(/https?:\\/\\/([a-z0-9-]+)\\.devpost\\.com/);
                    if (match && !['devpost', 'info', 'help', 'secure', 'api', 'www'].includes(match[1])) {
                        seen.add(href);
                        const text = link.textContent.trim().split('\\n')[0].trim() || match[1];
                        hacks.push({ name: text, url: href });
                    }
                });
                return hacks.slice(0, 20);
            }''')
            data["hackathons"] = hackathons
            
            # Get count from nav
            nav_link = await page.query_selector("a[href*='/challenges']")
            if nav_link:
                count_elem = await nav_link.query_selector(".totals span")
                if count_elem:
                    count_text = await count_elem.text_content()
                    if count_text:
                        data["hackathon_count"] = int(count_text.strip())
            
            # Navigate back
            await page.goto(user_url, timeout=30000)
            await page.wait_for_load_state("networkidle")
            
            # Location
            location = await page.query_selector(".location, .location-icon + *")
            if location:
                data["location"] = await location.text_content()
            
            result["data"] = data
            result["success"] = True

        result = await self._playwright_scrape(
            url=user_url,
            extractor_fn=extractor,
            cache_key=cache_key,
            wait_for_selector="h1",
        )
        
        # Handle 404 case
        if result.get("error") == f"User '{username}' not found":
            result["code"] = "NOT_FOUND"
        
        return result

    async def get_rss(self) -> dict[str, Any]:
        """Get hackathons RSS feed from /api/hackathons.rss.
        
        Note: This endpoint returns JSON (not RSS XML as the name suggests).
        """
        cache_key = "rss_hackathons"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, */*",
        }

        try:
            resp = await self._request_with_retry(
                "GET",
                f"{API_BASE}/hackathons.rss",
                headers=headers,
            )
            data = resp.json()
            
            hackathons = data.get("hackathons", [])
            
            result = {
                "success": True,
                "channel": "Devpost Hackathons",
                "items": hackathons,
                "count": len(hackathons),
            }

            if self._cache:
                self._cache.set(cache_key, result, ttl=600)

            return result
        except DevpostError as e:
            return {
                "success": False,
                "error": e.message,
                "code": e.code,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "code": "ERROR",
            }

    async def get_user_full(self, username: str) -> dict[str, Any]:
        """Get complete user profile including achievements, followers, following, and likes.
        
        Uses a single Playwright browser session to fetch all 5 pages sequentially.
        Returns a composite dict with all user data.
        """
        cache_key = f"user_full_{username}"
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

        result = {
            "success": False,
            "username": username,
            "steps": [],
            "data": {
                "name": None,
                "bio": None,
                "location": None,
                "skills": [],
                "links": {},
                "projects": [],
                "project_count": 0,
                "hackathons": [],
                "hackathon_count": 0,
                "achievements": [],
                "achievement_count": 0,
                "followers": [],
                "follower_count": 0,
                "following": [],
                "following_count": 0,
                "likes": [],
                "like_count": 0,
            }
        }

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not self.headed)
            page = await browser.new_page()

            try:
                user_url = f"{BASE_URL}/users/{username}"
                result["steps"].append(f"Loading {user_url}")
                await page.goto(user_url, timeout=30000)
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)

                data = result["data"]

                # Check if page is 404
                if "404" in await page.title():
                    result["error"] = f"User '{username}' not found"
                    result["code"] = "NOT_FOUND"
                    return result

                # === Extract profile data ===
                try:
                    name = await page.wait_for_selector("h1", timeout=5000)
                    raw_name = await name.text_content()
                    data["name"] = " ".join(raw_name.split())
                except Exception:
                    logger.debug("Could not extract user name")

                try:
                    bio = await page.query_selector(".bio, .about, .description, p")
                    if bio:
                        data["bio"] = (await bio.text_content()).strip()
                except Exception:
                    logger.debug("Could not extract bio")

                try:
                    skills = []
                    skill_elems = await page.query_selector_all(".skill, .tag, .pill")
                    for skill in skill_elems[:20]:
                        text = await skill.text_content()
                        if text and len(text) < 50:
                            skills.append(text.strip())
                    if skills:
                        data["skills"] = skills
                except Exception:
                    logger.debug("Could not extract skills")

                # Extract projects (H5 headings with parent links)
                try:
                    projects = []
                    seen_titles = set()
                    h5_elements = await page.query_selector_all("h5")
                    
                    for h5 in h5_elements[:20]:
                        title = await h5.text_content()
                        title = title.strip() if title else ""
                        
                        if not title or len(title) < 3 or len(title) > 100:
                            continue
                        if title.lower() in ['back', 'view all', 'software', 'projects', 'connect']:
                            continue
                        if title in seen_titles:
                            continue
                        
                        seen_titles.add(title)
                        parent = await h5.query_selector("xpath=../..")
                        project_info = {"title": title}
                        
                        if parent:
                            proj_link = await parent.query_selector("a[href*='/software/']")
                            if proj_link:
                                href = await proj_link.get_attribute("href")
                                if href and '/built-with/' not in href:
                                    project_info["url"] = f"{BASE_URL}{href}" if href.startswith('/') else href
                            
                            hack_link = await parent.query_selector("a[href*='.devpost.com']:not([href*='/users/']):not([href*='/software/'])")
                            if hack_link:
                                hack_text = await hack_link.text_content()
                                hack_href = await hack_link.get_attribute("href")
                                if hack_text and hack_href and len(hack_text) < 60:
                                    hack_text = hack_text.strip()
                                    if hack_text.lower() not in ['log in', 'sign up', 'about', 'careers', 'contact', 'help', 'blog']:
                                        if 'info.devpost.com' not in hack_href and 'help.devpost.com' not in hack_href:
                                            project_info["hackathon"] = hack_text
                                            project_info["hackathon_url"] = hack_href
                            
                            stats_elem = await parent.query_selector(".counts, .stats")
                            if stats_elem:
                                stats_text = await stats_elem.text_content()
                                if stats_text:
                                    project_info["stats"] = stats_text.strip()
                        
                        projects.append(project_info)
                    
                    data["projects"] = projects
                    data["project_count"] = len(projects)
                except Exception as e:
                    logger.debug("Could not extract projects: %s", e)

                # Extract hackathons from /challenges tab
                try:
                    hackathons = []
                    nav_link = await page.query_selector("a[href*='/challenges']")
                    if nav_link:
                        count_elem = await nav_link.query_selector(".totals span")
                        if count_elem:
                            count_text = await count_elem.text_content()
                            if count_text:
                                data["hackathon_count"] = int(count_text.strip())
                    
                    challenges_url = f"{BASE_URL}/{username}/challenges"
                    result["steps"].append(f"Loading {challenges_url}")
                    await page.goto(challenges_url, timeout=30000)
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(2)
                    
                    all_links = await page.query_selector_all("a[href*='.devpost.com']")
                    seen_hackathons = set()
                    seen_urls = set()
                    
                    for link in all_links[:50]:
                        hack_href = await link.get_attribute("href")
                        if not hack_href:
                            continue
                        if '/users/' in hack_href or '/hackathons' in hack_href:
                            continue
                        if 'info.devpost.com' in hack_href or 'help.devpost.com' in hack_href or 'secure.devpost.com' in hack_href:
                            continue
                        if '.devpost.com/' not in hack_href:
                            continue
                        
                        match = re.search(r'https?://([a-z0-9-]+)\.devpost\.com', hack_href)
                        if match:
                            hack_subdomain = match.group(1)
                            if hack_subdomain in ['devpost', 'info', 'help', 'secure', 'api', 'www']:
                                continue
                            
                            if hack_href not in seen_urls:
                                seen_urls.add(hack_href)
                                hack_text = await link.text_content()
                                if hack_text:
                                    hack_text = hack_text.strip().split('\n')[0].strip()[:50]
                                
                                hackathons.append({
                                    "name": hack_text or hack_subdomain,
                                    "url": hack_href,
                                })
                    
                    data["hackathons"] = hackathons
                    if not data.get("hackathon_count"):
                        data["hackathon_count"] = len(hackathons)
                    
                    result["steps"].append(f"Returning to profile")
                    await page.goto(user_url, timeout=30000)
                    await page.wait_for_load_state("networkidle")
                except Exception as e:
                    logger.debug("Could not extract hackathons: %s", e)
                    try:
                        await page.goto(user_url, timeout=10000)
                    except:
                        pass

                # Extract location
                try:
                    location = await page.query_selector(".location, .location-icon + *")
                    if location:
                        data["location"] = await location.text_content()
                except Exception:
                    logger.debug("Could not extract location")

                # Extract social links - scope to profile header area only
                links = {}
                try:
                    # Look for social links in the profile header/portfolio area, not site-wide
                    profile_header = await page.query_selector(".portfolio-header, .user-profile, #profile-header")
                    search_context = profile_header if profile_header else page
                    
                    github = await search_context.query_selector("a[href*='github.com']")
                    if github:
                        links["github"] = await github.get_attribute("href")
                    
                    twitter = await search_context.query_selector("a[href*='twitter.com'], a[href*='x.com']")
                    if twitter:
                        href = await twitter.get_attribute("href")
                        if href and "devpost" not in href:
                            links["twitter"] = href
                    
                    linkedin = await search_context.query_selector("a[href*='linkedin.com']")
                    if linkedin:
                        href = await linkedin.get_attribute("href")
                        if href and "devpost" not in href:
                            links["linkedin"] = href
                    
                    website = await search_context.query_selector("a.website-link, a[rel='me']")
                    if website:
                        href = await website.get_attribute("href")
                        if href and "devpost.com" not in href:
                            links["website"] = href
                except Exception:
                    logger.debug("Could not extract social links")
                if links:
                    data["links"] = links

                # === Extract achievements ===
                try:
                    achievements_url = f"{BASE_URL}/{username}/achievements"
                    result["steps"].append(f"Loading {achievements_url}")
                    await page.goto(achievements_url, timeout=30000)
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(3)

                    achievements = []
                    nav_link = await page.query_selector("a[href*='/achievements']")
                    if nav_link:
                        count_elem = await nav_link.query_selector(".totals span")
                        if count_elem:
                            count_text = await count_elem.text_content()
                            if count_text:
                                data["achievement_count"] = int(count_text.strip())

                    achievement_cards = await page.query_selector_all("div.content")
                    for card in achievement_cards[:50]:
                        achievement_info = {}
                        
                        title_elem = await card.query_selector("h5")
                        if title_elem:
                            title = await title_elem.text_content()
                            if title:
                                achievement_info["title"] = " ".join(title.split()).strip()
                        
                        desc_elems = await card.query_selector_all("p")
                        for p_elem in desc_elems:
                            p_class = await p_elem.get_attribute("class") or ""
                            if "progression" not in p_class:
                                p_text = await p_elem.text_content()
                                if p_text:
                                    achievement_info["description"] = " ".join(p_text.split()).strip()
                                    break
                        
                        date_elem = await card.query_selector("small.achieved-at, small.faded")
                        if date_elem:
                            date_text = await date_elem.text_content()
                            if date_text:
                                achievement_info["earned"] = " ".join(date_text.split()).strip()
                        
                        parent = await card.query_selector("xpath=..")
                        if parent:
                            img_elem = await parent.query_selector("img")
                            if img_elem:
                                img_src = await img_elem.get_attribute("src")
                                if img_src:
                                    achievement_info["badge_url"] = img_src if img_src.startswith("http") else f"{BASE_URL}{img_src}"
                        
                        if achievement_info.get("title"):
                            achievements.append(achievement_info)
                    
                    data["achievements"] = achievements
                    if not data["achievement_count"]:
                        data["achievement_count"] = len(achievements)
                except Exception as e:
                    logger.debug("Could not extract achievements: %s", e)

                # === Extract followers ===
                try:
                    followers_url = f"{BASE_URL}/{username}/followers"
                    result["steps"].append(f"Loading {followers_url}")
                    await page.goto(followers_url, timeout=30000)
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(2)

                    followers = []
                    nav_link = await page.query_selector("a[href*='/followers']")
                    if nav_link:
                        count_elem = await nav_link.query_selector(".totals span")
                        if count_elem:
                            count_text = await count_elem.text_content()
                            if count_text:
                                data["follower_count"] = int(count_text.strip())

                    followers = await page.evaluate('''() => {
                        const items = document.querySelectorAll('.gallery-item');
                        const results = [];
                        items.forEach((item, idx) => {
                            const link = item.querySelector('a.user-profile-link, a[href*="/users/"], a[href^="https://devpost.com/"]');
                            
                            let username = null;
                            let url = null;
                            if (link) {
                                const href = link.getAttribute('href');
                                url = href;
                                const match = href.match(/devpost\\.com\\/([^\\/]+)/);
                                if (match && match[1] !== 'users') {
                                    username = match[1];
                                }
                            }
                            
                            const nameDiv = item.querySelector('.entry-body');
                            let name = null;
                            let bio = null;
                            if (nameDiv) {
                                const texts = nameDiv.textContent.trim().split('\\n').filter(t => t.trim());
                                if (texts.length > 0) {
                                    name = texts[0].trim();
                                    if (name === 'Follow' || name === 'Following') name = null;
                                }
                                if (texts.length > 1) {
                                    bio = texts[1].trim();
                                    if (bio === 'Follow' || bio === 'Following' || bio.length < 5) bio = null;
                                }
                            }
                            
                            if (username || (name && name !== 'Follow')) {
                                results.push({
                                    username: username,
                                    name: name,
                                    url: url ? (url.startsWith('http') ? url : 'https://devpost.com' + url) : null,
                                    bio: bio
                                });
                            }
                        });
                        return results;
                    }''')
                    
                    data["followers"] = followers
                    if not data["follower_count"]:
                        data["follower_count"] = len(followers)
                except Exception as e:
                    logger.debug("Could not extract followers: %s", e)

                # === Extract following ===
                try:
                    following_url = f"{BASE_URL}/{username}/following"
                    result["steps"].append(f"Loading {following_url}")
                    await page.goto(following_url, timeout=30000)
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(2)

                    following = []
                    nav_link = await page.query_selector("a[href*='/following']")
                    if nav_link:
                        count_elem = await nav_link.query_selector(".totals span")
                        if count_elem:
                            count_text = await count_elem.text_content()
                            if count_text:
                                data["following_count"] = int(count_text.strip())

                    following = await page.evaluate('''() => {
                        const items = document.querySelectorAll('.gallery-item');
                        const results = [];
                        items.forEach((item, idx) => {
                            const link = item.querySelector('a.user-profile-link, a[href*="/users/"], a[href^="https://devpost.com/"]');
                            
                            let username = null;
                            let url = null;
                            if (link) {
                                const href = link.getAttribute('href');
                                url = href;
                                const match = href.match(/devpost\\.com\\/([^\\/]+)/);
                                if (match && match[1] !== 'users') {
                                    username = match[1];
                                }
                            }
                            
                            const nameDiv = item.querySelector('.entry-body');
                            let name = null;
                            let bio = null;
                            if (nameDiv) {
                                const texts = nameDiv.textContent.trim().split('\\n').filter(t => t.trim());
                                if (texts.length > 0) {
                                    name = texts[0].trim();
                                    if (name === 'Follow' || name === 'Following') name = null;
                                }
                                if (texts.length > 1) {
                                    bio = texts[1].trim();
                                    if (bio === 'Follow' || bio === 'Following' || bio.length < 5) bio = null;
                                }
                            }
                            
                            if (username || (name && name !== 'Follow')) {
                                results.push({
                                    username: username,
                                    name: name,
                                    url: url ? (url.startsWith('http') ? url : 'https://devpost.com' + url) : null,
                                    bio: bio
                                });
                            }
                        });
                        return results;
                    }''')
                    
                    data["following"] = following
                    if not data["following_count"]:
                        data["following_count"] = len(following)
                except Exception as e:
                    logger.debug("Could not extract following: %s", e)

                # === Extract likes ===
                try:
                    likes_url = f"{BASE_URL}/{username}/likes"
                    result["steps"].append(f"Loading {likes_url}")
                    await page.goto(likes_url, timeout=30000)
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(2)

                    likes = []
                    nav_link = await page.query_selector("a[href*='/likes']")
                    if nav_link:
                        count_elem = await nav_link.query_selector(".totals span")
                        if count_elem:
                            count_text = await count_elem.text_content()
                            if count_text:
                                data["like_count"] = int(count_text.strip())

                    likes = await page.evaluate('''() => {
                        const items = document.querySelectorAll('.gallery-item');
                        const results = [];
                        items.forEach(item => {
                            const link = item.querySelector('a[href*="/software/"]');
                            
                            let url = null;
                            let title = null;
                            let tagline = null;
                            let hackathon = null;
                            
                            if (link) {
                                const href = link.getAttribute('href');
                                url = href.startsWith('http') ? href : 'https://devpost.com' + href;
                                
                                const titleElem = item.querySelector('h5, .title');
                                if (titleElem) {
                                    title = titleElem.textContent.trim();
                                } else {
                                    const linkText = link.textContent.trim().split('\\n')[0].trim();
                                    if (linkText && linkText.length < 80) {
                                        title = linkText;
                                    }
                                }
                                
                                const taglineElem = item.querySelector('.tagline');
                                if (taglineElem) {
                                    const taglineText = taglineElem.textContent.trim();
                                    tagline = taglineText.substring(0, 200);
                                }
                                
                                const hackathonElem = item.querySelector('.hackathon, .challenge-name');
                                if (hackathonElem) {
                                    hackathon = hackathonElem.textContent.trim();
                                }
                            }
                            
                            if (title || url) {
                                results.push({
                                    title: title,
                                    url: url,
                                    tagline: tagline,
                                    hackathon: hackathon
                                });
                            }
                        });
                        return results;
                    }''')
                    
                    data["likes"] = likes
                    if not data["like_count"]:
                        data["like_count"] = len(likes)
                except Exception as e:
                    logger.debug("Could not extract likes: %s", e)

                result["success"] = True
                result["steps"].append("Successfully extracted full user profile")

            except Exception as e:
                result["error"] = str(e)
                result["steps"].append(f"Error: {e}")
            finally:
                await browser.close()

        if result["success"] and self._cache:
            self._cache.set(cache_key, result, ttl=3600)

        return result

    async def get_user_achievements(self, username: str) -> dict[str, Any]:
        """Get user achievements/badges using Playwright (JS-rendered page)."""
        cache_key = f"user_achievements_{username}"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        achievements_url = f"{BASE_URL}/{username}/achievements"
        
        async def extractor(page, result):
            """Extract achievement data."""
            if "404" in await page.title():
                result["error"] = f"User '{username}' not found"
                result["code"] = "NOT_FOUND"
                return
            
            data = {"achievements": [], "total_count": 0}
            
            # Get count from nav
            nav_link = await page.query_selector("a[href*='/achievements']")
            if nav_link:
                count_elem = await nav_link.query_selector(".totals span")
                if count_elem:
                    count_text = await count_elem.text_content()
                    if count_text:
                        data["total_count"] = int(count_text.strip())
            
            # Extract achievements using JavaScript
            achievements = await page.evaluate('''() => {
                const achievements = [];
                document.querySelectorAll('div.content').forEach(card => {
                    const h5 = card.querySelector('h5');
                    const ps = card.querySelectorAll('p');
                    const dateElem = card.querySelector('small.achieved-at, small.faded');
                    const parent = card.parentElement;
                    const img = parent?.querySelector('img');
                    
                    const achievement = {};
                    if (h5) achievement.title = h5.textContent.trim();
                    
                    // Get description (first p that's not progression)
                    for (const p of ps) {
                        if (!p.classList.contains('progression')) {
                            achievement.description = p.textContent.trim();
                            break;
                        }
                    }
                    
                    if (dateElem) achievement.earned = dateElem.textContent.trim();
                    if (img) achievement.badge_url = img.src.startsWith('http') ? img.src : 'https://devpost.com' + img.src;
                    
                    if (achievement.title) achievements.push(achievement);
                });
                return achievements.slice(0, 50);
            }''')
            
            data["achievements"] = achievements
            if not data["total_count"]:
                data["total_count"] = len(achievements)
            
            result["data"] = data
            result["success"] = True

        result = await self._playwright_scrape(
            url=achievements_url,
            extractor_fn=extractor,
            cache_key=cache_key,
            wait_for_selector="div.content",
        )
        
        if result.get("error") == f"User '{username}' not found":
            result["code"] = "NOT_FOUND"
        
        return result

    async def _extract_user_list(self, page, list_type: str) -> list[dict]:
        """Extract user list (followers/following/likes) using JavaScript."""
        return await page.evaluate(f'''() => {{
            const items = document.querySelectorAll('.gallery-item');
            const results = [];
            items.forEach(item => {{
                const link = item.querySelector('a.user-profile-link, a[href*="/users/"], a[href^="https://devpost.com/"]');
                
                let username = null, url = null;
                if (link) {{
                    const href = link.getAttribute('href');
                    url = href;
                    const match = href.match(/devpost\\\\.com\\\\/([^\\\\/]+)/);
                    if (match && match[1] !== 'users') username = match[1];
                }}
                
                const nameDiv = item.querySelector('.entry-body');
                let name = null, bio = null;
                if (nameDiv) {{
                    const texts = nameDiv.textContent.trim().split('\\\\n').filter(t => t.trim());
                    if (texts.length > 0) {{
                        name = texts[0].trim();
                        if (name === 'Follow' || name === 'Following') name = null;
                    }}
                    if (texts.length > 1) {{
                        bio = texts[1].trim();
                        if (bio === 'Follow' || bio === 'Following' || bio.length < 5) bio = null;
                    }}
                }}
                
                if (username || (name && name !== 'Follow')) {{
                    const result = {{ username, name, url: url ? (url.startsWith('http') ? url : 'https://devpost.com' + url) : null }};
                    {'bio: bio' if list_type == 'followers' else ''}
                    results.push(result);
                }}
            }});
            return results;
        }}''')

    async def get_user_followers(self, username: str) -> dict[str, Any]:
        """Get list of users following this user."""
        cache_key = make_user_followers_key(username)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        followers_url = f"{BASE_URL}/{username}/followers"
        
        async def extractor(page, result):
            if "404" in await page.title():
                result["error"] = f"User '{username}' not found"
                result["code"] = "NOT_FOUND"
                return
            
            data = {"followers": [], "total_count": 0}
            
            # Get count from nav
            nav_link = await page.query_selector("a[href*='/followers']")
            if nav_link:
                count_elem = await nav_link.query_selector(".totals span")
                if count_elem:
                    data["total_count"] = int((await count_elem.text_content()).strip())
            
            # Extract followers using JavaScript
            data["followers"] = await self._extract_user_list(page, "followers")
            if not data["total_count"]:
                data["total_count"] = len(data["followers"])
            
            result["data"] = data
            result["success"] = True

        result = await self._playwright_scrape(
            url=followers_url,
            extractor_fn=extractor,
            cache_key=cache_key,
            wait_for_selector=".gallery-item",
        )
        
        if result.get("error") == f"User '{username}' not found":
            result["code"] = "NOT_FOUND"
        
        return result

    async def get_user_following(self, username: str) -> dict[str, Any]:
        """Get list of users this user is following."""
        cache_key = make_user_following_key(username)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        following_url = f"{BASE_URL}/{username}/following"
        
        async def extractor(page, result):
            if "404" in await page.title():
                result["error"] = f"User '{username}' not found"
                result["code"] = "NOT_FOUND"
                return
            
            data = {"following": [], "total_count": 0}
            
            # Get count from nav
            nav_link = await page.query_selector("a[href*='/following']")
            if nav_link:
                count_elem = await nav_link.query_selector(".totals span")
                if count_elem:
                    data["total_count"] = int((await count_elem.text_content()).strip())
            
            # Extract following using JavaScript
            data["following"] = await self._extract_user_list(page, "following")
            if not data["total_count"]:
                data["total_count"] = len(data["following"])
            
            result["data"] = data
            result["success"] = True

        result = await self._playwright_scrape(
            url=following_url,
            extractor_fn=extractor,
            cache_key=cache_key,
            wait_for_selector=".gallery-item",
        )
        
        if result.get("error") == f"User '{username}' not found":
            result["code"] = "NOT_FOUND"
        
        return result

    async def get_user_likes(self, username: str) -> dict[str, Any]:
        """Get list of projects this user has liked."""
        cache_key = make_user_likes_key(username)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        likes_url = f"{BASE_URL}/{username}/likes"
        
        async def extractor(page, result):
            if "404" in await page.title():
                result["error"] = f"User '{username}' not found"
                result["code"] = "NOT_FOUND"
                return
            
            data = {"likes": [], "total_count": 0}
            
            # Get count from nav
            nav_link = await page.query_selector("a[href*='/likes']")
            if nav_link:
                count_elem = await nav_link.query_selector(".totals span")
                if count_elem:
                    data["total_count"] = int((await count_elem.text_content()).strip())
            
            # Extract liked projects using JavaScript
            data["likes"] = await page.evaluate('''() => {
                const items = document.querySelectorAll('.gallery-item');
                const results = [];
                items.forEach(item => {
                    const link = item.querySelector('a[href*="/software/"]');
                    
                    let url = null, title = null, tagline = null, hackathon = null;
                    
                    if (link) {
                        const href = link.getAttribute('href');
                        url = href.startsWith('http') ? href : 'https://devpost.com' + href;
                        
                        const titleElem = item.querySelector('h5, .title');
                        if (titleElem) {
                            title = titleElem.textContent.trim();
                        } else {
                            const linkText = link.textContent.trim().split('\\n')[0].trim();
                            if (linkText && linkText.length < 80) title = linkText;
                        }
                        
                        const taglineElem = item.querySelector('.tagline');
                        if (taglineElem) tagline = taglineElem.textContent.trim().substring(0, 200);
                        
                        const hackathonElem = item.querySelector('.hackathon, .challenge-name');
                        if (hackathonElem) hackathon = hackathonElem.textContent.trim();
                    }
                    
                    if (title || url) {
                        results.push({ title, url, tagline, hackathon });
                    }
                });
                return results;
            }''')
            
            if not data["total_count"]:
                data["total_count"] = len(data["likes"])
            
            result["data"] = data
            result["success"] = True

        result = await self._playwright_scrape(
            url=likes_url,
            extractor_fn=extractor,
            cache_key=cache_key,
            wait_for_selector=".gallery-item",
        )
        
        if result.get("error") == f"User '{username}' not found":
            result["code"] = "NOT_FOUND"
        
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

            # Fetch scrape, rules, and projects data in parallel for faster evaluation
            scrape_task = self.scrape_hackathon_page(hackathon_url)
            rules_task = self.parse_rules_page(slug)
            projects_task = self.list_hackathon_projects(hackathon_url=hackathon_url, limit=500)
            
            scrape_data, rules_data, projects_data = await asyncio.gather(
                scrape_task, rules_task, projects_task,
                return_exceptions=True,
            )
            
            # Process scrape data
            if isinstance(scrape_data, DevpostError):
                result["errors"].append(f"Scrape failed: {scrape_data.message}")
                scrape_data = None
            elif scrape_data and scrape_data.get("success"):
                data = scrape_data.get("data", {})
                if data.get("stats"):
                    if submissions_count is None:
                        submissions_count = data["stats"].get("submission")

            # Process rules data
            if isinstance(rules_data, DevpostError):
                result["errors"].append(f"Rules parse failed: {rules_data.message}")
                rules_data = None
            elif rules_data and not rules_data.get("success"):
                err = rules_data.get("error", "Unknown rules error")
                if err:
                    result["errors"].append(f"Rules parse failed: {err}")
            elif rules_data and rules_data.get("success"):
                result["eligibility"] = rules_data.get("eligibility", [])
                result["requirements"] = rules_data.get("requirements", [])
                result["judging_criteria"] = rules_data.get("judging_criteria", [])
                result["prize_categories"] = rules_data.get("prize_categories", [])
                result["key_dates"] = rules_data.get("key_dates", [])
                result["sponsor_apis"] = rules_data.get("sponsor_apis", [])

            # Process projects data
            if isinstance(projects_data, DevpostError):
                result["errors"].append(f"Projects fetch failed: {projects_data.message}")
                projects_data = None

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

    async def search_projects_across_hackathons(
        self,
        query: str,
        hackathon_states: list[str] = ["open"],
        limit: int = 50,
        max_hackathons: int = 20,
    ) -> list[dict]:
        """Search for projects across multiple hackathons.
        
        Fetches project galleries from multiple hackathons and filters locally.
        Useful for finding projects matching a keyword across all open/upcoming hackathons.
        
        Args:
            query: Search query (matches project title, tagline, or tech stack)
            hackathon_states: List of states to include (open, upcoming, ended)
            limit: Max projects to return
            max_hackathons: Max hackathons to search
        
        Returns:
            List of matching projects with hackathon info
        """
        q = query.lower()
        all_matches = []
        seen_urls = set()
        
        for state in hackathon_states:
            if len(all_matches) >= limit:
                break
            
            hackathons = await self.list_hackathons(limit=max_hackathons, open_state=state)
            
            for h in hackathons.get("hackathons", []):
                if len(all_matches) >= limit:
                    break
                
                hackathon_url = h.get("url", "")
                if not hackathon_url:
                    continue
                
                try:
                    projects_data = await self.list_hackathon_projects(
                        hackathon_url=hackathon_url,
                        limit=100,
                        winners_only=False,
                    )
                    
                    for proj in projects_data.get("projects", []):
                        if proj.get("url") in seen_urls:
                            continue
                        
                        title = (proj.get("title") or "").lower()
                        tagline = (proj.get("tagline") or "").lower()
                        tech_stack = ", ".join(proj.get("built_with", []) or []).lower()
                        
                        if q in title or q in tagline or q in tech_stack:
                            seen_urls.add(proj.get("url"))
                            proj["hackathon"] = {
                                "name": h.get("title"),
                                "slug": h.get("url", "").rstrip("/").split("/")[-1],
                                "url": hackathon_url,
                                "prize_amount": h.get("prize_amount"),
                            }
                            all_matches.append(proj)
                    
                    await asyncio.sleep(0.3)
                    
                except Exception:
                    continue
        
        return all_matches[:limit]

    async def search_projects(
        self,
        query: str,
        limit: int = 20,
        order_by: Optional[str] = None,
        use_playwright: bool = False,
    ) -> list[dict]:
        """Search projects via /software/search.
        
        Args:
            query: Search query (supports operators: is:winner, is:featured, has:video, has:image, @username, at:"hackathon", #tech)
            limit: Max projects to return
            order_by: Sort order - "newest", "popular", or "trending"
            use_playwright: If True, use browser automation to bypass WAF (slower but reliable)
        
        Note: HTTP-based search is protected by AWS WAF and may fail. Set use_playwright=True
        for reliable search at the cost of speed.
        """
        cache_key = make_search_projects_key(query, limit, order_by)
        if self._cache and not use_playwright:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        if use_playwright:
            projects = await self._search_projects_playwright(query, limit, order_by)
        else:
            projects = await self._search_projects_http(query, limit, order_by)

        projects = projects[:limit]
        if self._cache and not use_playwright:
            self._cache.set(cache_key, projects)
        return projects

    async def _search_projects_http(
        self,
        query: str,
        limit: int = 20,
        order_by: Optional[str] = None,
    ) -> list[dict]:
        """Search projects via HTTP request (fast but may be WAF-blocked)."""
        projects = []
        page = 1
        max_pages = (limit + 23) // 24

        waf_detected = False
        
        while page <= max_pages and len(projects) < limit:
            try:
                params = {"query": query, "page": page}
                if order_by and order_by != "newest":
                    params["order_by"] = order_by
                resp = await self._request_with_retry(
                    "GET",
                    f"{BASE_URL}/software/search",
                    params=params,
                )
                
                if resp.status_code == 202 or "awsWafCookieDomainList" in resp.text or "gokuProps" in resp.text:
                    waf_detected = True
                    break
                
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

        if waf_detected:
            raise DevpostError(
                "Project search is blocked by AWS WAF. "
                "Use use_playwright=True or 'devpost gallery <hackathon>' for specific hackathons.",
                code="WAF_BLOCKED",
            )

        return projects

    async def _search_projects_playwright(
        self,
        query: str,
        limit: int = 20,
        order_by: Optional[str] = None,
    ) -> list[dict]:
        """Search projects using Playwright browser automation (bypasses WAF)."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise DevpostError(
                "Playwright not installed. Install with: pip install playwright && playwright install chromium",
                code="DEPENDENCY_MISSING",
            )

        result = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not self.headed)
            page = await browser.new_page()

            try:
                search_url = f"{BASE_URL}/software/search"
                params = {"query": query}
                if order_by and order_by != "newest":
                    params["order_by"] = order_by
                
                from urllib.parse import urlencode
                full_url = f"{search_url}?{urlencode(params)}"
                
                await page.goto(full_url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)

                while len(result) < limit:
                    projects = await page.evaluate('''() => {
                        const items = document.querySelectorAll('.software-entry, .project-item, .gallery-item, article');
                        const results = [];
                        items.forEach(item => {
                            const link = item.querySelector('a[href*="/software/"]');
                            if (!link) return;
                            
                            const href = link.getAttribute('href');
                            const titleElem = item.querySelector('h2, h3, h4, h5, .title');
                            const taglineElem = item.querySelector('.tagline, .description, .summary');
                            const winnerBadge = item.querySelector('.winner, .winner-badge, .prize-winner');
                            const builtWithElem = item.querySelector('.built-with, .tech-stack');
                            
                            let title = '';
                            if (titleElem) title = titleElem.textContent.trim();
                            else title = link.textContent.trim().split('\\n')[0].trim();
                            
                            let tagline = '';
                            if (taglineElem) tagline = taglineElem.textContent.trim().substring(0, 200);
                            
                            let built_with = [];
                            if (builtWithElem) {
                                const techText = builtWithElem.textContent;
                                built_with = techText.split(',').map(t => t.trim()).filter(t => t);
                            }
                            
                            results.push({
                                title: title || 'Unknown',
                                url: href.startsWith('http') ? href : 'https://devpost.com' + href,
                                tagline: tagline,
                                is_winner: !!winnerBadge,
                                built_with: built_with,
                            });
                        });
                        return results;
                    }''')

                    if not projects:
                        break

                    for p in projects:
                        if p not in result:
                            result.append(p)
                    
                    if len(result) >= limit:
                        break

                    next_btn = await page.query_selector('a[rel="next"], .pagination a[href*="page="]:not(.disabled)')
                    if not next_btn:
                        break
                    
                    await next_btn.click()
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(1)

            except Exception as e:
                logger.debug("Playwright search error: %s", e)
            finally:
                await browser.close()

        return result

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
        order_by: Optional[str] = None,
    ) -> list[dict]:
        """Get projects built with a specific technology from /software/built-with/<tech>.
        
        Args:
            tech: Technology name (e.g., "Python", "React")
            limit: Max projects to return
            order_by: Sort order - "newest", "popular", or "trending"
        """
        cache_key = make_built_with_key(tech, limit)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        tech_slug = tech.lower().replace(" ", "-").replace("+", "plus")
        projects = []
        page = 1
        max_pages = (limit + 23) // 24

        while page <= max_pages and len(projects) < limit:
            try:
                params = {"page": page}
                if order_by and order_by != "newest":
                    params["order_by"] = order_by
                    
                resp = await self._request_with_retry(
                    "GET",
                    f"{BASE_URL}/software/built-with/{tech_slug}",
                    params=params,
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
        """Get staff picks/featured projects from /software/search?query=is:featured."""
        cache_key = make_featured_projects_key(limit)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        projects = []
        page = 1
        max_pages = (limit + 23) // 24

        while page <= max_pages and len(projects) < limit:
            try:
                resp = await self._request_with_retry(
                    "GET",
                    f"{BASE_URL}/software/search",
                    params={"query": "is:featured", "page": page},
                )
                
                # Check for WAF block
                if resp.status_code == 202 or "awsWafCookieDomainList" in resp.text:
                    break
                
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

    async def get_trending_technologies(self) -> list[str]:
        """Get trending technology tags from /software page."""
        cache_key = "trending_technologies"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            resp = await self._request_with_retry("GET", f"{BASE_URL}/software")
            soup = BeautifulSoup(resp.text, "html.parser")
            
            technologies = []
            # Find technology tag links
            for a in soup.find_all('a', href=lambda h: h and '/software/built-with/' in h):
                text = a.get_text(strip=True)
                if text and text.lower() != 'view all':
                    technologies.append(text)
            
            # Remove duplicates while preserving order
            seen = set()
            unique = []
            for tech in technologies:
                if tech not in seen:
                    seen.add(tech)
                    unique.append(tech)
            
            if self._cache:
                self._cache.set(cache_key, unique, ttl=3600)
            
            return unique

        except DevpostError as e:
            logger.debug("Could not fetch trending technologies: %s", e.message)
            return []
        except Exception as e:
            logger.debug("Error fetching trending technologies: %s", e)
            return []

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

    async def get_themes(self, popular: bool = False) -> list[dict]:
        """Get all themes or popular themes from API.
        
        Handles both response formats:
        - /api/themes returns bare list: [{"name": "..."}, ...]
        - /api/themes/popular returns wrapped: {"themes": [{"name": "..."}, ...]}
        """
        endpoint = "themes/popular" if popular else "themes"
        cache_key = f"themes_{'popular' if popular else 'all'}"
        
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        resp = await self._request_with_retry(
            "GET",
            f"{API_BASE}/{endpoint}",
            headers={"Accept": "application/json"},
        )
        data = resp.json()
        
        # Handle both response formats
        if isinstance(data, dict):
            themes = data.get("themes", [])
        elif isinstance(data, list):
            themes = data
        else:
            themes = []
        
        if self._cache:
            self._cache.set(cache_key, themes)
        
        return themes

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

    # OAuth provider selectors and metadata
    OAUTH_PROVIDERS = {
        "github": {
            "selector": "a[data-role='github-login social-login']",
            "name": "GitHub",
        },
        "google": {
            "selector": "a[data-role='google_oauth2-login social-login']",
            "name": "Google",
        },
        "facebook": {
            "selector": "a[data-role='facebook-login social-login']",
            "name": "Facebook",
        },
        "linkedin": {
            "selector": "a[data-role='linkedin-login social-login']",
            "name": "LinkedIn",
        },
    }

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        headed: bool = False,
        auth_method: Optional[str] = None,
    ) -> None:
        self.email = email
        self.password = password
        self.headed = headed
        # Auto-detect auth method from session if not specified
        if auth_method is None:
            from .session import get_auth_method
            self.auth_method = get_auth_method() or "password"
        else:
            self.auth_method = auth_method
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
        """Get or create browser context with session persistence.
        
        Supports both password and OAuth login flows.
        OAuth login auto-forces headed mode for user interaction.
        """
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

        # OAuth requires headed mode for user interaction
        effective_headed = self.headed
        if self.auth_method != "password":
            if not self.headed:
                logger.info("OAuth login requires visible browser. Switching to headed mode.")
            effective_headed = True

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=not effective_headed,
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

        # OAuth login flow
        if self.auth_method != "password":
            await self._oauth_login()
        else:
            # Password login flow
            await self._password_login()

        # Save session cookies
        cookies = await self._context.cookies()
        save_session(cookies, self.email or "oauth-user", self.auth_method)

        return self._browser, self._page

    async def _password_login(self) -> None:
        """Perform password-based login."""
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

    async def _oauth_login(self) -> None:
        """Perform OAuth login via social provider.
        
        Clicks the appropriate OAuth button and waits for redirect back to Devpost.
        Timeout is extended to 120s to allow for user interaction on OAuth provider page.
        """
        provider = self.OAUTH_PROVIDERS.get(self.auth_method)
        if not provider:
            raise DevpostError(
                f"Unknown OAuth method: {self.auth_method}. Valid: {', '.join(self.OAUTH_PROVIDERS.keys())}",
                code="INVALID_OAUTH_METHOD",
            )

        provider_name = provider["name"]
        selector = provider["selector"]

        logger.info(f"Initiating {provider_name} OAuth login...")

        # Click the OAuth button
        try:
            await self._page.wait_for_selector(selector, timeout=10000)
            await self._page.click(selector)
        except Exception as e:
            await self.close()
            raise DevpostError(
                f"Could not find {provider_name} login button. Page may have changed.",
                code="OAUTH_BUTTON_NOT_FOUND",
            ) from e

        # Wait for OAuth flow to complete (user authenticates on provider site, redirects back)
        logger.info(f"Waiting for {provider_name} authentication... (timeout: 120s)")
        try:
            # Wait for redirect back to devpost.com (not on login page anymore)
            await self._page.wait_for_url(
                lambda url: "devpost.com" in url and "users/login" not in url,
                timeout=120000
            )
            await self._page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)
        except Exception as e:
            await self.close()
            raise DevpostError(
                f"OAuth login timed out. Please try again and complete authentication on {provider_name}.",
                code="OAUTH_TIMEOUT",
            ) from e

        # Verify we're logged in (no "Log in" button visible)
        page_content = await self._page.content()
        if "Log in" in page_content:
            # Check if we're still on a login page
            if "login" in self._page.url.lower():
                await self.close()
                raise DevpostError(
                    f"OAuth login did not complete. You may need to authorize the application on {provider_name}.",
                    code="OAUTH_INCOMPLETE",
                )

        logger.info(f"{provider_name} OAuth login successful")
        # Extract email from session if possible (not always available with OAuth)
        self.email = self.email or f"{self.auth_method}-oauth"

        cookies = await self._context.cookies()
        save_session(cookies, email)

        return self._browser, self._page

    async def _fill_project_form(
        self,
        page,
        title: Optional[str] = None,
        tagline: Optional[str] = None,
        description: Optional[str] = None,
        built_with: Optional[list[str]] = None,
        links: Optional[dict] = None,
    ) -> list[str]:
        """Fill project submission form fields.
        
        Args:
            page: Playwright page object
            title: Project title
            tagline: Project tagline
            description: Project description
            built_with: List of technologies
            links: Dict with github, demo, video URLs
        
        Returns:
            List of field names that were successfully filled
        """
        filled_fields = []
        
        if title:
            await page.fill("input[name='software[name]']", title)
            filled_fields.append("title")
        
        if tagline:
            await page.fill("input[name='software[tagline]']", tagline)
            filled_fields.append("tagline")
        
        if description:
            await page.fill("textarea[name='software[description]']", description)
            filled_fields.append("description")
        
        if built_with:
            tech_input = page.locator("input[placeholder*='technology'], input[name*='built_with']").first
            for tech in built_with:
                await tech_input.fill(tech)
                await tech_input.press("Enter")
                await asyncio.sleep(0.5)
            filled_fields.append("built_with")
        
        if links:
            link_fields = {
                "github": ("input[name*='github'], input[placeholder*='github']", "github_link"),
                "demo": ("input[name*='demo'], input[placeholder*='demo']", "demo_link"),
                "video": ("input[name*='video'], input[placeholder*='video']", "video_link"),
            }
            for key, (selector, field_name) in link_fields.items():
                if links.get(key):
                    try:
                        await page.fill(selector, links[key])
                        filled_fields.append(field_name)
                    except Exception as e:
                        logger.warning("Could not fill %s: %s", key, e)
        
        return filled_fields

    async def submit_project(
        self,
        hackathon_slug: str,
        title: str,
        tagline: str,
        description: Optional[str] = None,
        built_with: Optional[list[str]] = None,
        links: Optional[dict] = None,
        image_paths: Optional[list[str]] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Submit a project to a hackathon.
        
        Args:
            hackathon_slug: Hackathon URL slug
            title: Project title
            tagline: Project tagline (max 140 chars)
            description: Project description (can be HTML from markdown conversion)
            built_with: List of technologies
            links: Dict with github, demo, video URLs
            image_paths: List of image file paths to upload after submission
            dry_run: If True, don't actually submit
            
        Returns:
            Result dict with project URL if successful
        """
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

            # Check if user has joined the hackathon, join if not
            result["steps"].append("Checking hackathon registration status")
            join_button = page.locator(
                "a:has-text('Join hackathon'), a:has-text('Join'), button:has-text('Join'), button:has-text('Register')"
            ).first
            
            if await join_button.count() > 0:
                result["steps"].append("Joining hackathon (required before submission)")
                await join_button.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                result["steps"].append("Successfully joined hackathon")

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
                if image_paths:
                    result["steps"].append(f"Would upload {len(image_paths)} image(s) after submission")
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
                
                # Upload images after successful submission
                if image_paths:
                    result["steps"].append(f"Uploading {len(image_paths)} image(s)...")
                    upload_result = await self._upload_images_to_project(page, current_url, image_paths)
                    result["uploaded_images"] = upload_result.get("uploaded", [])
                    result["failed_images"] = upload_result.get("failed", [])
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
            filled_fields = await self._fill_project_form(
                page,
                title=title,
                tagline=tagline,
                description=description,
                built_with=built_with,
                links=links,
            )
            result["steps"].append(f"Filled fields: {', '.join(filled_fields)}")

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
        image_paths: Optional[list[str]] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Update an existing project submission.
        
        Args:
            project_url: Project URL to update
            title: New title (optional)
            tagline: New tagline (optional)
            description: New description (optional, can be HTML)
            built_with: New technologies list (optional)
            links: New links dict (optional)
            image_paths: New images to upload (optional)
            dry_run: If True, don't actually save
            
        Returns:
            Result dict with updated fields
        """
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

            result["steps"].append("Filling form")
            filled_fields = await self._fill_project_form(
                page,
                title=title,
                tagline=tagline,
                description=description,
                built_with=built_with,
                links=links,
            )
            result["updated_fields"] = filled_fields
            result["steps"].append(f"Updated fields: {', '.join(filled_fields)}")

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
                    
                    # Upload images after saving form changes
                    if image_paths:
                        result["steps"].append(f"Uploading {len(image_paths)} image(s)...")
                        upload_result = await self._upload_images_to_project(page, project_url, image_paths)
                        result["uploaded_images"] = upload_result.get("uploaded", [])
                        result["failed_images"] = upload_result.get("failed", [])
                        if result["uploaded_images"]:
                            result["updated_fields"].append("images")
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

    async def _upload_images_to_project(
        self,
        page,
        project_url: str,
        image_paths: list[str],
    ) -> dict[str, Any]:
        """Upload images to a project (internal helper for submit_project).
        
        This is a simplified version that reuses the existing page context
        instead of creating a new browser session.
        
        Args:
            page: Existing Playwright page object
            project_url: Project URL
            image_paths: List of image file paths
            
        Returns:
            Result dict with uploaded/failed lists
        """
        result = {
            "uploaded": [],
            "failed": [],
        }
        
        try:
            edit_url = f"{project_url.rstrip('/')}/edit"
            await page.goto(edit_url, timeout=30000)
            await page.wait_for_load_state("networkidle")
            
            for image_path in image_paths:
                try:
                    file_input = await page.wait_for_selector(
                        "input[type='file'], input[name*='image'], input[name*='screenshot']",
                        timeout=5000,
                    )
                    
                    if file_input:
                        await file_input.set_input_files(image_path)
                        await page.wait_for_timeout(3000)
                        result["uploaded"].append(image_path)
                    else:
                        result["failed"].append({"path": image_path, "reason": "File input not found"})
                        
                except Exception as e:
                    result["failed"].append({"path": image_path, "reason": str(e)})
            
            # Save after all uploads
            if result["uploaded"]:
                await page.click("input[type='submit'], button:has-text('Save')")
                await page.wait_for_load_state("networkidle")
                
        except Exception as e:
            logger.warning("Image upload failed: %s", e)
            result["failed"].append({"path": "unknown", "reason": str(e)})
        
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
        invite_emails: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Create a team for a hackathon with optional invites.
        
        Args:
            hackathon_slug: Hackathon URL slug
            team_name: Name for the new team
            invite_usernames: List of Devpost usernames to invite
            invite_emails: List of email addresses to invite (if Devpost UI supports it)
        
        Returns:
            dict with success status, team_url, invites_sent, invites_failed
        """
        validate_slug(hackathon_slug)
        result = {
            "success": False,
            "hackathon_slug": hackathon_slug,
            "team_name": team_name,
            "invites_sent": [],
            "invites_failed": [],
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
                result["error"] = "Create team option not found. You may already be in a team or team formation may be closed."
                result["code"] = "NOT_FOUND"
                return result

            await create_button.click()
            await page.wait_for_load_state("networkidle")
            result["steps"].append("Clicked create team")

            result["steps"].append("Filling team name")
            try:
                await page.fill("input[name*='team_name'], input[name*='name'], input[placeholder*='team name']", team_name)
            except Exception as e:
                logger.debug("Could not fill team name: %s", e)
                result["steps"].append(f"Warning: Could not auto-fill team name")

            # Combine usernames and emails for inviting
            all_invitees = []
            if invite_usernames:
                all_invitees.extend(invite_usernames)
            if invite_emails:
                all_invitees.extend(invite_emails)
            
            if all_invitees:
                result["steps"].append(f"Adding {len(all_invitees)} invitees")
                for invitee in all_invitees:
                    try:
                        # Detect if this is an email or username
                        is_email = "@" in invitee
                        
                        # Try to find invite input field
                        invite_input = page.locator(
                            "input[name*='email'], input[name*='username'], input[placeholder*='username'], input[placeholder*='email']"
                        ).first
                        
                        if await invite_input.count() > 0:
                            await invite_input.fill(invitee)
                            
                            # Click add button
                            add_button = page.locator("button:has-text('Add'), input[value*='Add'], button:has-text('Invite')").first
                            if await add_button.count() > 0:
                                await add_button.click()
                                await page.wait_for_timeout(500)
                                result["invites_sent"].append(invitee)
                                invite_type = "email" if is_email else "username"
                                result["steps"].append(f"Added {invite_type} invite: {invitee}")
                            else:
                                result["invites_failed"].append(invitee)
                                result["steps"].append(f"Warning: Could not find add button for {invitee}")
                        else:
                            result["invites_failed"].append(invitee)
                            result["steps"].append(f"Warning: Could not find invite input for {invitee}")
                    except Exception as e:
                        logger.debug("Could not add invitee %s: %s", invitee, e)
                        result["invites_failed"].append(invitee)
                        result["steps"].append(f"Warning: Failed to invite {invitee}")

            result["steps"].append("Submitting team creation")
            submit_button = page.locator("input[type='submit'], button:has-text('Create'), button:has-text('Save'), button:has-text('Form team')").first
            if await submit_button.count() > 0:
                await submit_button.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                
                # Check if team was created successfully
                current_url = page.url
                if "/team" in current_url or "/teams/" in current_url:
                    result["success"] = True
                    result["message"] = f"Team '{team_name}' created successfully"
                    result["team_url"] = current_url
                else:
                    result["success"] = True
                    result["message"] = f"Team creation initiated - check your email for confirmation"
            else:
                result["error"] = "Submit button not found"
                result["code"] = "NOT_FOUND"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def add_team_member(self, project_url: str, username: str) -> dict[str, Any]:
        """Add a team member to an existing project."""
        validate_devpost_url(project_url)
        result = {
            "success": False,
            "project_url": project_url,
            "username": username,
            "steps": [],
        }

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            # Navigate to project edit page
            edit_url = f"{project_url}/edit"
            result["steps"].append(f"Navigating to {edit_url}")
            await page.goto(edit_url, wait_until="networkidle", timeout=30000)

            result["steps"].append("Looking for team management section")
            
            # Try to find team/add member section
            add_member_input = page.locator(
                "input[name*='username'], input[name*='email'], input[placeholder*='username'], input[placeholder*='Add member']"
            ).first

            if await add_member_input.count() == 0:
                result["error"] = "Could not find team member input field. You may not have permission to edit this project."
                result["code"] = "NOT_FOUND"
                return result

            result["steps"].append(f"Adding {username} to project")
            await add_member_input.fill(username)
            
            # Click add/save button
            add_button = page.locator("button:has-text('Add'), input[value*='Add'], button:has-text('Save'), button:has-text('Update')").first
            if await add_button.count() > 0:
                await add_button.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                
                # Check if member was added successfully
                page_content = await page.content()
                if username in page_content:
                    result["success"] = True
                    result["message"] = f"Successfully added {username} to project"
                else:
                    result["success"] = True
                    result["message"] = f"Invitation sent to {username}"
            else:
                result["error"] = "Add button not found"
                result["code"] = "NOT_FOUND"

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
