"""CLI for Devpost hackathons."""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import click
import httpx
from bs4 import BeautifulSoup
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich import print as rprint

# Optional Playwright import
try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

console = Console()

BASE_URL = "https://devpost.com"
API_BASE = "https://devpost.com/api"


class DevpostClient:
    """HTTP client for Devpost API and scraping."""

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/html",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False

    async def close(self) -> None:
        await self.client.aclose()

    async def list_hackathons(
        self,
        limit: int = 20,
        open_state: Optional[str] = None,
        sort_by: str = "recently-added",
        query: Optional[str] = None,
    ) -> list[dict]:
        """List hackathons via API."""
        params: dict = {"limit": limit, "sort_by": sort_by}
        if open_state:
            params["open_state"] = open_state
        if query:
            params["q"] = query

        resp = await self.client.get(
            f"{API_BASE}/hackathons",
            params=params,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("hackathons", [])

    async def get_hackathon_by_slug(self, slug: str) -> Optional[dict]:
        """Get hackathon by URL slug."""
        resp = await self.client.get(
            f"{API_BASE}/hackathons",
            params={"url": slug, "limit": 1},
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        hackathons = data.get("hackathons", [])
        return hackathons[0] if hackathons else None

    async def scrape_hackathon_page(self, url: str, use_browser: bool = True) -> dict:
        """Deep scrape any hackathon page by URL. Uses browser automation if HTTP fails."""
        # Try HTTP first, fall back to browser
        html = await self._fetch_with_fallback(url, use_browser)
        if not html:
            raise Exception(f"Failed to fetch {url} - both HTTP and browser methods failed")

        soup = BeautifulSoup(html, "html.parser")

        # Extract basic info - try multiple selectors
        title = None
        # Try meta tag first
        title = self._get_meta(soup, "og:title") or self._get_meta(soup, "twitter:title")
        # Try h1
        if not title:
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)
        # Try title tag
        if not title:
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(strip=True).replace(" - Devpost", "")
        if not title:
            title = "Unknown"

        description = (
            self._get_meta(soup, "og:description")
            or self._get_meta(soup, "description")
            or self._get_meta(soup, "twitter:description")
            or ""
        )
        image = self._get_meta(soup, "og:image")

        # Extract dates, prizes, stats from page content
        body_text = soup.get_text()

        # Look for prize amounts in the page text
        prize_text = None
        # Look for prize amounts with $ sign
        prize_matches = re.findall(r"\$[\d,]+(?:\.\d{2})?", body_text)
        if prize_matches:
            prize_text = f"Prizes: {', '.join(prize_matches[:3])}"

        # Try to find gallery and rules links
        gallery_url = f"{url.rstrip('/')}/project-gallery"
        rules_url = f"{url.rstrip('/')}/rules"

        # Look for submission count, participants, etc.
        stats = {}
        # Look for patterns like "123 submissions" or "45 participants"
        stat_patterns = [
            (r"(\d+)\s+submissions?", "submissions"),
            (r"(\d+)\s+participants?", "participants"),
            (r"(\d+)\s+developers?", "developers"),
        ]
        for pattern, key in stat_patterns:
            matches = re.findall(pattern, body_text, re.IGNORECASE)
            if matches:
                # Take the first/largest number found
                stats[key] = max(int(m) for m in matches)

        return {
            "title": title,
            "description": description[:500] + "..." if len(description) > 500 else description,
            "url": url,
            "image_url": image,
            "gallery_url": gallery_url,
            "rules_url": rules_url,
            "prize_summary": prize_text,
            "stats": stats,
        }

    async def _fetch_with_fallback(self, url: str, use_browser: bool = True) -> Optional[str]:
        """Try HTTP first, fall back to Playwright browser if blocked."""
        # Try HTTP first
        try:
            resp = await self.client.get(url)
            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass

        # Fall back to browser
        if use_browser and HAS_PLAYWRIGHT:
            console.print("[dim]HTTP blocked, using browser automation...[/dim]")
            return await self._fetch_with_browser(url)

        return None

    async def _fetch_with_browser(self, url: str) -> Optional[str]:
        """Use Playwright browser to fetch page content with stealth mode."""
        if not HAS_PLAYWRIGHT:
            return None

        try:
            async with async_playwright() as p:
                # Launch with stealth args to avoid detection
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-web-security",
                        "--disable-features=IsolateOrigins,site-per-process",
                    ]
                )

                # Create context with realistic viewport and user agent
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )

                page = await context.new_page()

                # Set realistic browser headers
                await page.set_extra_http_headers({
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Referer": "https://devpost.com/hackathons",
                })

                # Inject script to hide automation
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                """)

                await page.goto(url, wait_until="networkidle", timeout=30000)
                # Wait for content to render and scroll down to trigger lazy loading
                await asyncio.sleep(3)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1)
                # Wait for specific content to appear
                try:
                    await page.wait_for_selector("h1, .hackathon-title, [data-testid='hackathon-title']", timeout=5000)
                except Exception:
                    pass  # Continue even if selector not found
                content = await page.content()
                await context.close()
                await browser.close()
                return content
        except Exception as e:
            console.print(f"[red]Browser error: {e}[/red]")
            return None

    async def list_hackathon_projects(
        self,
        hackathon_url: str,
        limit: int = 20,
        winners_only: bool = False,
        use_browser: bool = True,
    ) -> list[dict]:
        """List projects from a hackathon's gallery."""
        gallery_url = f"{hackathon_url.rstrip('/')}/project-gallery"

        html = await self._fetch_with_fallback(gallery_url, use_browser)
        if not html:
            raise Exception(f"Failed to fetch gallery at {gallery_url}")

        soup = BeautifulSoup(html, "html.parser")
        projects = []

        # Find project entries - they usually have specific class patterns
        for project_elem in soup.find_all("a", href=re.compile(r"/software/"))[:limit]:
            href = project_elem.get("href", "")
            if not href:
                continue

            # Extract title
            title_elem = project_elem.find(["h3", "h4", "h5", "span"], class_=re.compile(r"title|name", re.I))
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"

            # Check for winner badge
            is_winner = bool(project_elem.find(class_=re.compile(r"winner|badge|prize", re.I)))

            if winners_only and not is_winner:
                continue

            projects.append({
                "title": title,
                "url": f"https://devpost.com{href}" if href.startswith("/") else href,
                "is_winner": is_winner,
            })

        return projects

    async def get_project_details(self, project_url: str, use_browser: bool = True) -> dict:
        """Get detailed info about a specific project."""
        html = await self._fetch_with_fallback(project_url, use_browser)
        if not html:
            raise Exception(f"Failed to fetch project at {project_url}")

        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title = (
            self._get_meta(soup, "og:title")
            or (soup.find("h1").get_text(strip=True) if soup.find("h1") else "Unknown")
        )

        # Extract description
        description = (
            self._get_meta(soup, "og:description")
            or ""
        )

        # Extract built with (tech stack)
        built_with = []
        for elem in soup.find_all(string=re.compile(r"built with|technologies|stack", re.I)):
            parent = elem.find_parent(["div", "section", "ul"])
            if parent:
                for tech in parent.find_all(["li", "span", "a"]):
                    text = tech.get_text(strip=True)
                    if text and len(text) < 50:
                        built_with.append(text)

        # Extract links
        links = {}
        for link in soup.find_all("a", href=re.compile(r"github|demo|video|website", re.I)):
            href = link.get("href", "")
            text = link.get_text(strip=True).lower()
            if "github" in text or "github" in href:
                links["github"] = href
            elif "demo" in text or "demo" in href:
                links["demo"] = href
            elif "video" in text or "youtube" in href or "youtu.be" in href:
                links["video"] = href

        # Check if winner
        is_winner = bool(soup.find(class_=re.compile(r"winner|badge|prize", re.I)))

        return {
            "title": title,
            "description": description,
            "url": project_url,
            "built_with": list(set(built_with))[:10],
            "links": links,
            "is_winner": is_winner,
        }

    def _get_meta(self, soup: BeautifulSoup, property_name: str) -> Optional[str]:
        """Get meta tag content by property or name."""
        tag = soup.find("meta", property=property_name) or soup.find("meta", attrs={"name": property_name})
        return tag.get("content") if tag else None


# CLI Commands

@click.group()
@click.version_option(version="0.1.0", prog_name="devpost")
def cli():
    """Devpost CLI - Browse hackathons, scout competition, submit projects."""
    pass


@cli.command()
@click.option("--limit", "-l", default=20, help="Number of hackathons to show")
@click.option("--state", "-s", type=click.Choice(["open", "closed", "upcoming", "judging", "submitting"]),
              help="Filter by hackathon state")
@click.option("--sort", type=click.Choice(["recently-added", "submission-deadline", "prize-amount", "popularity"]),
              default="recently-added", help="Sort order")
@click.option("--query", "-q", help="Search query")
@click.option("--json", "is_json", is_flag=True, help="Output as JSON")
def list(limit: int, state: Optional[str], sort: str, query: Optional[str], is_json: bool):
    """List hackathons on Devpost."""
    async def _list():
        async with DevpostClient() as client:
            hackathons = await client.list_hackathons(
                limit=limit,
                open_state=state,
                sort_by=sort,
                query=query,
            )

            if is_json:
                click.echo(json.dumps(hackathons, indent=2))
                return

            if not hackathons:
                console.print("[yellow]No hackathons found.[/yellow]")
                return

            table = Table(title="Hackathons on Devpost")
            table.add_column("Title", style="cyan", no_wrap=True)
            table.add_column("Status", style="green")
            table.add_column("Prize", style="yellow")
            table.add_column("Ends", style="magenta")

            for h in hackathons:
                status = h.get("open_state", "unknown")
                prize = h.get("prize_amount", "N/A")
                ends = h.get("submission_period_ends_at", "N/A")
                if ends and ends != "N/A":
                    ends = ends[:10]  # Just date part

                # Strip HTML from prize
                prize_clean = re.sub(r"<[^>]+>", "", str(prize)) if prize else "N/A"

                table.add_row(
                    h.get("title", "Unknown")[:50],
                    status,
                    prize_clean,
                    ends,
                )

            console.print(table)

    asyncio.run(_list())


@cli.command()
@click.argument("slug")
@click.option("--json", "is_json", is_flag=True, help="Output as JSON")
def info(slug: str, is_json: bool):
    """Get hackathon details by URL slug (e.g., 'zervehack')."""
    async def _info():
        async with DevpostClient() as client:
            hackathon = await client.get_hackathon_by_slug(slug)

            if not hackathon:
                console.print(f"[red]Hackathon '{slug}' not found.[/red]")
                sys.exit(1)

            if is_json:
                click.echo(json.dumps(hackathon, indent=2))
                return

            # Pretty print
            prize_clean = re.sub(r"<[^>]+>", "", str(hackathon.get('prize_amount', 'N/A')))
            console.print(Panel(
                f"[bold cyan]{hackathon.get('title', 'Unknown')}[/bold cyan]\n\n"
                f"[green]URL:[/green] {hackathon.get('url', 'N/A')}\n"
                f"[green]Status:[/green] {hackathon.get('open_state', 'unknown')}\n"
                f"[green]Prize:[/green] {prize_clean}\n"
                f"[green]Submissions:[/green] {hackathon.get('submissions_count', 'N/A')}\n"
                f"[green]Ends:[/green] {hackathon.get('submission_period_ends_at', 'N/A')[:10] if hackathon.get('submission_period_ends_at') else 'N/A'}\n\n"
                f"{hackathon.get('tagline', 'No description')[:300]}",
                title="Hackathon Details",
                border_style="blue"
            ))

    asyncio.run(_info())


@cli.command()
@click.argument("url")
@click.option("--json", "is_json", is_flag=True, help="Output as JSON")
@click.option("--output", "-o", type=click.Path(), help="Save to file")
def scrape(url: str, is_json: bool, output: Optional[str]):
    """Deep scrape any hackathon page by URL. Works for past/closed hackathons."""
    async def _scrape():
        async with DevpostClient() as client:
            data = await client.scrape_hackathon_page(url)

            if is_json or output:
                output_data = json.dumps(data, indent=2)
                if output:
                    Path(output).write_text(output_data)
                    console.print(f"[green]Saved to {output}[/green]")
                else:
                    click.echo(output_data)
                return

            # Pretty print
            console.print(Panel(
                f"[bold cyan]{data.get('title', 'Unknown')}[/bold cyan]\n\n"
                f"[green]URL:[/green] {data['url']}\n"
                f"[green]Gallery:[/green] {data.get('gallery_url', 'N/A')}\n"
                f"[green]Rules:[/green] {data.get('rules_url', 'N/A')}\n"
                f"[green]Prizes:[/green] {data.get('prize_summary', 'N/A')}\n\n"
                f"[dim]Stats:[/dim] {json.dumps(data.get('stats', {}))}\n\n"
                f"{data.get('description', 'No description')[:400]}",
                title="Scraped Hackathon Data",
                border_style="green"
            ))

    asyncio.run(_scrape())


@cli.command()
@click.argument("url")
@click.option("--limit", "-l", default=20, help="Number of projects to show")
@click.option("--winners", "-w", is_flag=True, help="Only show winning projects")
@click.option("--json", "is_json", is_flag=True, help="Output as JSON")
def projects(url: str, limit: int, winners: bool, is_json: bool):
    """List projects from a hackathon's gallery."""
    async def _projects():
        async with DevpostClient() as client:
            projects = await client.list_hackathon_projects(
                hackathon_url=url,
                limit=limit,
                winners_only=winners,
            )

            if is_json:
                click.echo(json.dumps(projects, indent=2))
                return

            if not projects:
                console.print("[yellow]No projects found.[/yellow]")
                return

            table = Table(title=f"Projects from {url}")
            table.add_column("Title", style="cyan")
            table.add_column("Winner", style="yellow")
            table.add_column("URL", style="dim")

            for p in projects:
                table.add_row(
                    p.get("title", "Unknown")[:50],
                    "★ YES" if p.get("is_winner") else "No",
                    p.get("url", "N/A")[:60],
                )

            console.print(table)
            console.print(f"\n[dim]Showing {len(projects)} projects[/dim]")

    asyncio.run(_projects())


@cli.command()
@click.argument("url")
@click.option("--json", "is_json", is_flag=True, help="Output as JSON")
def project(url: str, is_json: bool):
    """Get detailed info about a specific project."""
    async def _project():
        async with DevpostClient() as client:
            details = await client.get_project_details(url)

            if is_json:
                click.echo(json.dumps(details, indent=2))
                return

            # Pretty print
            winner_badge = "[yellow]★ WINNER[/yellow]\n" if details.get("is_winner") else ""

            tech_stack = ", ".join(details.get("built_with", [])) or "Not specified"
            links = details.get("links", {})
            links_str = "\n".join([f"[green]{k}:[/green] {v}" for k, v in links.items()]) or "None"

            console.print(Panel(
                f"[bold cyan]{details.get('title', 'Unknown')}[/bold cyan]\n"
                f"{winner_badge}\n"
                f"[green]URL:[/green] {details['url']}\n\n"
                f"[dim]Description:[/dim]\n{details.get('description', 'No description')[:500]}\n\n"
                f"[dim]Tech Stack:[/dim] {tech_stack}\n\n"
                f"[dim]Links:[/dim]\n{links_str}",
                title="Project Details",
                border_style="cyan" if details.get("is_winner") else "blue"
            ))

    asyncio.run(_project())


@cli.command()
@click.argument("query")
@click.option("--limit", "-l", default=10, help="Number of results")
@click.option("--json", "is_json", is_flag=True, help="Output as JSON")
def search(query: str, limit: int, is_json: bool):
    """Search hackathons by keyword."""
    async def _search():
        async with DevpostClient() as client:
            hackathons = await client.list_hackathons(query=query, limit=limit)

            if is_json:
                click.echo(json.dumps(hackathons, indent=2))
                return

            if not hackathons:
                console.print(f"[yellow]No hackathons found for '{query}'[/yellow]")
                return

            console.print(f"[green]Found {len(hackathons)} hackathons for '{query}':[/green]\n")

            for h in hackathons:
                tagline = h.get('tagline') or 'No description'
                console.print(f"[cyan]{h.get('title', 'Unknown')}[/cyan] - {h.get('open_state', 'unknown')}")
                console.print(f"  [dim]{tagline[:100]}[/dim]\n")

    asyncio.run(_search())


# Placeholder commands for auth-required operations
@cli.group()
def auth():
    """Authentication commands (for submissions)."""
    pass


@auth.command()
def status():
    """Check authentication status."""
    email = os.getenv("DEVPOST_EMAIL")
    if email:
        console.print(f"[green]Authenticated as:[/green] {email}")
    else:
        console.print("[yellow]Not authenticated. Set DEVPOST_EMAIL and DEVPOST_PASSWORD env vars.[/yellow]")


@auth.command()
def login():
    """Set up authentication (interactive)."""
    console.print("[yellow]Auth not yet implemented. Set env vars:[/yellow]")
    console.print("  export DEVPOST_EMAIL='your@email.com'")
    console.print("  export DEVPOST_PASSWORD='***'")


def main():
    """Entry point."""
    try:
        import re  # Ensure re is available
        globals()["re"] = re
    except ImportError:
        pass
    cli()


if __name__ == "__main__":
    main()
