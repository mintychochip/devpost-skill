"""CLI for Devpost hackathons."""

import asyncio
import json
import sys
from typing import Any, Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .core import (
    AuthenticatedClient,
    DevpostClient,
    DevpostError,
    clear_credentials,
    save_credentials_interactive,
    get_credentials,
)
from .cache import CacheManager, parse_days_left, parse_prize_amount, _matches
from .session import load_credentials, load_credentials_from_env
from .logging_config import setup_logging, get_logger

logger = get_logger("cli")
console = Console()

_cli_config: dict = {"headed": False}


def output_json(data: Any, is_json_flag: Optional[bool] = None) -> bool:
    """Output data as JSON if --json flag is set or if stdout is not a TTY."""
    if is_json_flag is None:
        is_json_flag = not sys.stdout.isatty()

    if is_json_flag:
        click.echo(json.dumps(data, indent=2, default=str))
        return True
    return False


def _run_async(coro):
    """Run an async coroutine with user-friendly error handling."""
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)
    except DevpostError as e:
        if output_json({"error": e.message, "code": e.code}):
            sys.exit(1)
        console.print(f"[red]Error: {e.message}[/red]")
        sys.exit(1)
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            console.print("[red]Error: Cannot run async commands from an existing event loop.[/red]")
            sys.exit(1)
        raise


@click.group()
@click.version_option(version="0.3.0", prog_name="devpost")
@click.option("--headed", is_flag=True, help="Run browser in headed mode (visible window) for debugging")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def cli(headed: bool, verbose: bool):
    """Devpost CLI - Browse hackathons, scout competition, and submit projects.
    
    \b
    Quick Start:
      devpost list                    # Browse open hackathons
      devpost search "AI"             # Search by keyword
      devpost info zervehack          # Get hackathon details
      devpost join zervehack          # Register for a hackathon
      devpost submit project ...      # Submit your project
    
    \b
    Authentication (for submissions):
      devpost auth login              # Interactive login
      export DEVPOST_EMAIL="..."      # Or use env vars
      export DEVPOST_PASSWORD="..."
    """
    _cli_config["headed"] = headed
    setup_logging(verbose)


@cli.command(name="hackathons")
@click.option("--limit", "-l", default=20, help="Number of hackathons to show (default: 20)")
@click.option("--state", "-s", type=click.Choice(["open", "closed", "ended", "upcoming", "judging", "submitting"]),
              help="Filter by hackathon state ('closed' is an alias for 'ended')")
@click.option("--sort", type=click.Choice(["recently-added", "submission-deadline", "prize-amount", "popularity"]),
              default="recently-added", help="Sort order (default: recently-added)")
@click.option("--query", "-q", help="Search query string")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def hackathons(limit: int, state: Optional[str], sort: str, query: Optional[str], is_json: Optional[bool]):
    """List hackathons on Devpost.
    
    \b
    Examples:
      devpost hackathons                   # Top 20 recently-added hackathons
      devpost hackathons --state open      # Only open hackathons
      devpost hackathons -s closed -l 5    # 5 closed hackathons (for scouting)
      devpost hackathons --sort prize-amount
      devpost hackathons -q "AI" -l 10     # Search for AI hackathons
      devpost hackathons --json            # Output as JSON
    
    Hidden alias: devpost list (deprecated)
    """
    async def _list():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            hackathons = await client.list_hackathons(
                limit=limit,
                open_state=state,
                sort_by=sort,
                query=query,
            )

            if output_json(hackathons, is_json):
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
                ends = h.get("ends_at", "N/A")

                table.add_row(
                    h.get("title", "Unknown")[:50],
                    status,
                    prize if prize else "N/A",
                    ends if ends else "N/A",
                )

            console.print(table)

    _run_async(_list())


@cli.command(name="list", hidden=True)
@click.option("--limit", "-l", default=20, help="Number of hackathons to show (default: 20)")
@click.option("--state", "-s", type=click.Choice(["open", "closed", "ended", "upcoming", "judging", "submitting"]),
              help="Filter by hackathon state ('closed' is an alias for 'ended')")
@click.option("--sort", type=click.Choice(["recently-added", "submission-deadline", "prize-amount", "popularity"]),
              default="recently-added", help="Sort order (default: recently-added)")
@click.option("--query", "-q", help="Search query string")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def list_cmd(limit: int, state: Optional[str], sort: str, query: Optional[str], is_json: Optional[bool]):
    """Legacy alias for hackathons command (deprecated)."""
    _run_async(_list_cmd(limit, state, sort, query, is_json))


async def _list_cmd(limit: int, state: Optional[str], sort: str, query: Optional[str], is_json: Optional[bool]):
    """Internal list command logic (legacy alias)."""
    async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
        hackathons_list = await client.list_hackathons(
            limit=limit,
            open_state=state,
            sort_by=sort,
            query=query,
        )

        if output_json(hackathons_list, is_json):
            return

        if not hackathons_list:
            console.print("[yellow]No hackathons found.[/yellow]")
            return

        table = Table(title="Hackathons on Devpost")
        table.add_column("Title", style="cyan", no_wrap=True)
        table.add_column("Status", style="green")
        table.add_column("Prize", style="yellow")
        table.add_column("Ends", style="magenta")

        for h in hackathons_list:
            status = h.get("open_state", "unknown")
            prize = h.get("prize_amount", "N/A")
            ends = h.get("ends_at", "N/A")

            table.add_row(
                h.get("title", "Unknown")[:50],
                status,
                prize if prize else "N/A",
                ends if ends else "N/A",
            )

        console.print(table)


@cli.command()
@click.argument("slug")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def overview(slug: str, is_json: Optional[bool]):
    """Get hackathon details by URL slug.
    
    The slug is the subdomain from the hackathon URL.
    
    \b
    Examples:
      devpost overview zervehack         # zervehack.devpost.com
      devpost overview datahacks-2025    # datahacks-2025.devpost.com
      devpost overview agents-assemble   # agents-assemble.devpost.com
      devpost overview myhackathon --json
    
    Hidden alias: devpost info (deprecated)
    """
    async def _info():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            hackathon = await client.get_hackathon_by_slug(slug)

            if not hackathon:
                if output_json({"error": f"Hackathon '{slug}' not found", "code": "NOT_FOUND"}, is_json):
                    sys.exit(3)
                console.print(f"[red]Hackathon '{slug}' not found.[/red]")
                sys.exit(3)

            if output_json(hackathon, is_json):
                return

            console.print(Panel(
                f"[bold cyan]{hackathon.get('title', 'Unknown')}[/bold cyan]\n\n"
                f"[green]URL:[/green] {hackathon.get('url', 'N/A')}\n"
                f"[green]Status:[/green] {hackathon.get('open_state', 'unknown')}\n"
                f"[green]Prize:[/green] {hackathon.get('prize_amount', 'N/A')}\n"
                f"[green]Submissions:[/green] {hackathon.get('submissions_count', 'N/A')}\n"
                f"[green]Ends:[/green] {hackathon.get('ends_at', 'N/A')}\n\n"
                f"{hackathon.get('tagline', 'No description')[:300]}",
                title="Hackathon Details",
                border_style="blue"
            ))

    _run_async(_info())


@cli.command(name="info", hidden=True)
@click.argument("slug")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def info_cmd(slug: str, is_json: Optional[bool]):
    """Legacy alias for overview command (deprecated)."""
    _run_async(_info_cmd(slug, is_json))


async def _info_cmd(slug: str, is_json: Optional[bool]):
    """Internal info command logic (legacy alias)."""
    async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
        hackathon = await client.get_hackathon_by_slug(slug)

        if not hackathon:
            if output_json({"error": f"Hackathon '{slug}' not found", "code": "NOT_FOUND"}, is_json):
                sys.exit(3)
            console.print(f"[red]Hackathon '{slug}' not found.[/red]")
            sys.exit(3)

        if output_json(hackathon, is_json):
            return

        console.print(Panel(
            f"[bold cyan]{hackathon.get('title', 'Unknown')}[/bold cyan]\n\n"
            f"[green]URL:[/green] {hackathon.get('url', 'N/A')}\n"
            f"[green]Status:[/green] {hackathon.get('open_state', 'unknown')}\n"
            f"[green]Prize:[/green] {hackathon.get('prize_amount', 'N/A')}\n"
            f"[green]Submissions:[/green] {hackathon.get('submissions_count', 'N/A')}\n"
            f"[green]Ends:[/green] {hackathon.get('ends_at', 'N/A')}\n\n"
            f"{hackathon.get('tagline', 'No description')[:300]}",
            title="Hackathon Details",
            border_style="blue"
        ))


@cli.command()
@click.argument("url")
@click.option("--json", "is_json", is_flag=True, help="Output as JSON")
@click.option("--output", "-o", type=click.Path(), help="Save output to file")
def scrape(url: str, is_json: bool, output: Optional[str]):
    """Deep scrape any hackathon page by URL.
    
    Works for active AND past/closed hackathons that the API doesn't return.
    Extracts title, description, dates, prizes, stats, rules, and gallery URLs.
    
    \b
    Examples:
      devpost scrape https://datahacks-2025.devpost.com/
      devpost scrape https://myhack.devpost.com/ --json
      devpost scrape https://oldhack.devpost.com/ -o data.json
    """
    async def _scrape():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            data = await client.scrape_hackathon_page(url)

            if is_json or output:
                output_data = json.dumps(data, indent=2, default=str)
                if output:
                    from pathlib import Path
                    Path(output).write_text(output_data, encoding="utf-8")
                    console.print(f"[green]Saved to {output}[/green]")
                else:
                    click.echo(output_data)
                return

            console.print(Panel(
                f"[bold cyan]{data.get('data', {}).get('title', 'Unknown')}[/bold cyan]\n\n"
                f"[green]URL:[/green] {data.get('url', 'N/A')}\n"
                f"[green]Gallery:[/green] {data.get('data', {}).get('gallery_url', 'N/A')}\n"
                f"[green]Rules:[/green] {data.get('data', {}).get('rules_url', 'N/A')}\n"
                f"[green]Prizes:[/green] {data.get('data', {}).get('prize_summary', 'N/A')}\n\n"
                f"[dim]Stats:[/dim] {json.dumps(data.get('data', {}).get('stats', {}), default=str)}\n\n"
                f"{data.get('data', {}).get('description', 'No description')[:400]}",
                title="Scraped Hackathon Data",
                border_style="green"
            ))

    _run_async(_scrape())


@cli.command(name="gallery")
@click.argument("slug")
@click.option("--limit", "-l", default=20, help="Number of projects to show (default: 20)")
@click.option("--winners", "-w", is_flag=True, help="Only show winning projects")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def gallery(slug: str, limit: int, winners: bool, is_json: Optional[bool]):
    """List projects from a hackathon's project gallery.
    
    Works for active AND closed/past hackathons. Scrapes the gallery page
    to extract project titles, URLs, and winner status.
    
    \b
    Examples:
      devpost gallery datahacks-2025     # datahacks-2025.devpost.com
      devpost gallery hack --winners     # Only winners
      devpost gallery hack -l 50 --json
    
    Hidden alias: devpost projects <url> (deprecated)
    """
    async def _gallery():
        hackathon_url = f"https://{slug}.devpost.com/"
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            result = await client.list_hackathon_projects(
                hackathon_url=hackathon_url,
                limit=limit,
                winners_only=winners,
            )

            if output_json(result, is_json):
                return

            if not result.get("projects"):
                console.print("[yellow]No projects found.[/yellow]")
                return

            table = Table(title=f"Gallery: {slug}")
            table.add_column("Title", style="cyan")
            table.add_column("Winner", style="yellow")
            table.add_column("URL", style="dim")

            for p in result["projects"]:
                table.add_row(
                    p.get("title", "Unknown")[:50],
                    "★ YES" if p.get("is_winner") else "No",
                    p.get("url", "N/A")[:60],
                )

            console.print(table)
            console.print(f"\n[dim]Showing {len(result['projects'])} projects[/dim]")

    _run_async(_gallery())


@cli.command(name="projects", hidden=True)
@click.argument("url")
@click.option("--limit", "-l", default=20, help="Number of projects to show (default: 20)")
@click.option("--winners", "-w", is_flag=True, help="Only show winning projects")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def projects_cmd(url: str, limit: int, winners: bool, is_json: Optional[bool]):
    """Legacy alias for gallery command (deprecated)."""
    if url.startswith("http"):
        slug = url.rstrip("/").rsplit("/", maxsplit=1)[-1].replace(".devpost.com", "").replace("https://", "")
    else:
        slug = url
    _run_async(_projects_cmd(slug, limit, winners, is_json))


async def _projects_cmd(slug: str, limit: int, winners: bool, is_json: Optional[bool]):
    """Internal projects command logic (legacy alias)."""
    hackathon_url = f"https://{slug}.devpost.com/"
    async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
        result = await client.list_hackathon_projects(
            hackathon_url=hackathon_url,
            limit=limit,
            winners_only=winners,
        )

        if output_json(result, is_json):
            return

        if not result.get("projects"):
            console.print("[yellow]No projects found.[/yellow]")
            return

        table = Table(title=f"Projects from {url}")
        table.add_column("Title", style="cyan")
        table.add_column("Winner", style="yellow")
        table.add_column("URL", style="dim")

        for p in result["projects"]:
            table.add_row(
                p.get("title", "Unknown")[:50],
                "★ YES" if p.get("is_winner") else "No",
                p.get("url", "N/A")[:60],
            )

        console.print(table)
        console.print(f"\n[dim]Showing {len(result['projects'])} projects[/dim]")


@cli.command()
@click.argument("url")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def project(url: str, is_json: Optional[bool]):
    """Get detailed info about a specific project.
    
    Uses browser automation to extract title, description, tech stack,
    team members, links, and screenshots from the project page.
    
    \b
    Examples:
      devpost project https://devpost.com/software/myproject
      devpost project https://devpost.com/software/winner --json
    """
    async def _project():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            details = await client.get_project_details(url)

            if output_json(details, is_json):
                return

            if not details.get("success"):
                console.print(f"[red]Error: {details.get('error', 'Unknown error')}[/red]")
                sys.exit(1)

            data = details.get("data", {})
            winner_badge = "[yellow]★ WINNER[/yellow]\n" if data.get("is_winner") else ""

            tech_stack = ", ".join(data.get("built_with", [])) or "Not specified"
            links = data.get("links", {})
            links_str = "\n".join([f"[green]{k}:[/green] {v}" for k, v in links.items()]) or "None"

            console.print(Panel(
                f"[bold cyan]{data.get('title', 'Unknown')}[/bold cyan]\n"
                f"{winner_badge}\n"
                f"[green]URL:[/green] {details.get('url', 'N/A')}\n\n"
                f"[dim]Description:[/dim]\n{data.get('description', 'No description')[:500]}\n\n"
                f"[dim]Tech Stack:[/dim] {tech_stack}\n\n"
                f"[dim]Links:[/dim]\n{links_str}",
                title="Project Details",
                border_style="cyan" if data.get("is_winner") else "blue"
            ))

    _run_async(_project())


@cli.command()
@click.argument("slug")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
@click.option("--no-cache", is_flag=True, help="Bypass cache, fetch fresh data")
def rules(slug: str, is_json: Optional[bool], no_cache: bool):
    """Extract structured rules from a hackathon's rules page.

    Parses eligibility, requirements, judging criteria, prize categories,
    key dates, and sponsor API requirements.

    \b
    Examples:
      devpost rules medo                       # Parse MeDo hackathon rules
      devpost rules google-cloud-rapid-agent   # Parse Google Cloud rules
      devpost rules myhack --json              # Output as JSON
      devpost rules myhack --no-cache          # Force fresh fetch
    """
    async def _rules():
        async with DevpostClient(headed=_cli_config.get("headed", False), use_cache=not no_cache) as client:
            result = await client.parse_rules_page(slug)

            if output_json(result, is_json):
                return

            if not result.get("success"):
                console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
                sys.exit(1)

            sections = [
                ("Eligibility", result.get("eligibility", [])),
                ("Requirements", result.get("requirements", [])),
                ("Judging Criteria", result.get("judging_criteria", [])),
                ("Sponsor APIs / Tech Requirements", result.get("sponsor_apis", [])),
                ("Key Dates", result.get("key_dates", [])),
            ]

            content_parts = [f"[bold cyan]{slug}[/bold cyan] — Rules\n"]

            for label, items in sections:
                if items:
                    content_parts.append(f"[green]{label}:[/green]")
                    for item in items:
                        content_parts.append(f"  • {item[:200]}")
                    content_parts.append("")

            if result.get("prize_categories"):
                content_parts.append("[green]Prize Categories:[/green]")
                for cat in result["prize_categories"]:
                    content_parts.append(f"  • {cat[:200]}")
                content_parts.append("")

            if len(content_parts) <= 2:
                content_parts.append("[dim]No structured rules sections found on the page.[/dim]")
                content_parts.append(f"[dim]Raw text length: {result.get('raw_text_length', 0)} chars[/dim]")

            console.print(Panel(
                "\n".join(content_parts),
                title=f"Rules: {slug}",
                border_style="blue",
            ))

    _run_async(_rules())


@cli.command()
@click.argument("slug")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
@click.option("--no-cache", is_flag=True, help="Bypass cache, fetch fresh data")
def winners(slug: str, is_json: Optional[bool], no_cache: bool):
    """List winning projects from a hackathon.

    Tries the project gallery first (filtered to winners), then falls back
    to scraping the /winners page.

    \b
    Examples:
      devpost winners agents-assemble           # List winners from a hackathon
      devpost winners google-cloud-rapid-agent   # Winners by slug
      devpost winners myhack --json              # Output as JSON
    """
    async def _winners():
        async with DevpostClient(headed=_cli_config.get("headed", False), use_cache=not no_cache) as client:
            result = await client.get_winners(slug)

            if output_json(result, is_json):
                return

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            if not result.get("winners"):
                msg = result.get("message", "No winners found.")
                console.print(f"[yellow]{msg}[/yellow]")
                return

            table = Table(title=f"Winners: {slug}")
            table.add_column("Title", style="cyan")
            table.add_column("Prize", style="yellow")
            table.add_column("URL", style="dim")

            for w in result["winners"]:
                table.add_row(
                    w.get("title", "Unknown")[:50],
                    w.get("prize", "Winner"),
                    w.get("url", "N/A")[:60],
                )

            console.print(table)
            console.print(f"\n[dim]Showing {result['count']} winning project(s)[/dim]")

    _run_async(_winners())


@cli.command()
@click.argument("slug")
@click.option("--skills", help="Your skills (comma-separated) for theme-fit signal (e.g. 'Python,AI,GCP')")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
@click.option("--no-cache", is_flag=True, help="Bypass cache, fetch fresh data")
def evaluate(slug: str, skills: Optional[str], is_json: Optional[bool], no_cache: bool):
    """Evaluate whether a hackathon is worth entering.

    Combines info, scrape, rules, and projects into a decision report
    with verdict (Enter/Maybe/Skip) and recommendation signals.

    \b
    Examples:
      devpost evaluate medo                           # Evaluate MeDo hackathon
      devpost evaluate rapid-agent --skills "Python,AI,GCP"
      devpost evaluate myhack --json                  # Output as JSON
      devpost evaluate myhack --no-cache              # Force fresh fetch
    """
    skills_list = [s.strip() for s in skills.split(",")] if skills else None

    async def _evaluate():
        async with DevpostClient(headed=_cli_config.get("headed", False), use_cache=not no_cache) as client:
            result = await client.evaluate_hackathon(slug, skills=skills_list)

            if output_json(result, is_json):
                return

            if not result.get("success"):
                console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
                sys.exit(1)

            verdict = result.get("verdict", "Maybe")
            reason = result.get("verdict_reason", "")
            verdict_style = {"Enter": "green", "Maybe": "yellow", "Skip": "red"}.get(verdict, "white")

            basics = result.get("basics", {})
            competition = result.get("competition", {})
            signals = result.get("signals", {})

            content_parts = [
                f"[bold {verdict_style}]VERDICT: {verdict.upper()}[/bold {verdict_style}]",
                f"{reason}",
                "",
                f"[bold]Basics[/bold]",
                f"  [green]Title:[/green] {basics.get('title', 'Unknown')}",
                f"  [green]Prize:[/green] {basics.get('prize', 'N/A')}",
                f"  [green]Status:[/green] {basics.get('status', 'unknown')}",
                f"  [green]Dates:[/green] {basics.get('dates', 'N/A')}",
                f"  [green]Org:[/green] {basics.get('organization', 'N/A')}",
                f"  [green]Themes:[/green] {', '.join(basics.get('themes', [])) or 'N/A'}",
                "",
                f"[bold]Competition[/bold]",
                f"  Registrants: {competition.get('registrants', 'N/A')}",
                f"  Submissions: {competition.get('submissions', 'N/A')}",
                f"  Prize per project: ${competition.get('prize_per_project', 0):,.0f}",
                f"  Registrants per prize: {competition.get('registrants_per_prize', 0):.0f}",
            ]

            if result.get("eligibility"):
                content_parts.append(f"\n[bold]Eligibility[/bold]")
                for item in result["eligibility"][:5]:
                    content_parts.append(f"  • {item[:150]}")

            if result.get("requirements"):
                content_parts.append(f"\n[bold]Requirements[/bold]")
                for item in result["requirements"][:5]:
                    content_parts.append(f"  • {item[:150]}")

            if result.get("judging_criteria"):
                content_parts.append(f"\n[bold]Judging Criteria[/bold]")
                for item in result["judging_criteria"][:5]:
                    content_parts.append(f"  • {item[:150]}")

            if result.get("sponsor_apis"):
                content_parts.append(f"\n[bold]Sponsor APIs / Tech[/bold]")
                for item in result["sponsor_apis"][:5]:
                    content_parts.append(f"  • {item[:150]}")

            if result.get("prize_categories"):
                content_parts.append(f"\n[bold]Prize Categories[/bold]")
                for cat in result["prize_categories"][:8]:
                    content_parts.append(f"  • {cat[:150]}")

            if result.get("key_dates"):
                content_parts.append(f"\n[bold]Key Dates[/bold]")
                for d in result["key_dates"][:5]:
                    content_parts.append(f"  • {d[:150]}")

            signal_rows = []
            for name, sig in signals.items():
                level = sig.get("level", "unknown")
                level_style = {"high": "green", "medium": "yellow", "low": "red", "wide_open": "green", "critical": "bold red", "closed": "dim"}.get(level, "white")
                signal_rows.append(f"  {name.replace('_', ' ').title()}: [{level_style}]{level}[/{level_style}] — {sig.get('detail', '')}")

            content_parts.append(f"\n[bold]Signals[/bold]")
            content_parts.extend(signal_rows)

            if result.get("errors"):
                content_parts.append(f"\n[dim]Partial data errors: {'; '.join(result['errors'])}[/dim]")

            console.print(Panel(
                "\n".join(content_parts),
                title=f"Evaluate: {slug}",
                border_style=verdict_style,
            ))

    _run_async(_evaluate())


@cli.command()
@click.argument("query")
@click.option("--in", "hackathon", help="Search within a specific hackathon (slug)")
@click.option("--limit", "-l", default=20, help="Number of results (default: 20)")
@click.option("--winners", is_flag=True, help="In-hackathon: search only winning projects")
@click.option("--tech", is_flag=True, help="In-hackathon: search only tech stacks")
@click.option("--include-rules", is_flag=True, help="In-hackathon: also search hackathon description and rules")
@click.option("--no-cache", is_flag=True, help="Bypass cache, fetch fresh data")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def search(
    query: str,
    hackathon: Optional[str],
    limit: int,
    winners: bool,
    tech: bool,
    include_rules: bool,
    no_cache: bool,
    is_json: Optional[bool],
):
    """Search projects on Devpost (matches /software/search).
    
    With --in flag, searches within a specific hackathon's projects.
    
    \b
    Global project search:
      devpost search "AI"                          # Search projects
      devpost search "chatbot" -l 30               # More results
    
    \b
    In-hackathon search:
      devpost search "RAG" --in medo               # Search projects in MeDo
      devpost search "agent" --in medo --winners   # Only winners
      devpost search "OpenAI" --in medo --tech     # Search tech stacks
      devpost search "requirement" --in medo --include-rules
    
    For hackathon search, use: devpost hackathons --query "AI"
    """
    use_cache = not no_cache

    if hackathon:
        _search_in_hackathon(
            query, hackathon, winners, tech, include_rules,
            use_cache, is_json,
        )
    else:
        _search_projects_global(query, limit, use_cache, is_json)


def _search_projects_global(
    query: str,
    limit: int,
    use_cache: bool,
    is_json: Optional[bool],
):
    async def _run():
        async with DevpostClient(headed=_cli_config.get("headed", False), use_cache=use_cache) as client:
            projects = await client.search_projects(query=query, limit=limit)

            if output_json(projects, is_json):
                return

            if not projects:
                console.print(f"[yellow]No projects found for '{query}'[/yellow]")
                return

            console.print(f"[green]Found {len(projects)} projects for '{query}':[/green]\n")

            for p in projects:
                title = p.get('title', 'Unknown')
                tagline = p.get('tagline') or ''
                winner_badge = " [yellow]★ WINNER[/yellow]" if p.get("is_winner") else ""
                console.print(f"[cyan]{title}{winner_badge}[/cyan]")
                if tagline:
                    console.print(f"  [dim]{tagline[:100]}[/dim]")
                if p.get("built_with"):
                    console.print(f"  [dim]Built with: {', '.join(p['built_with'][:5])}[/dim]")
                console.print(f"  [dim]{p.get('url', '')}[/dim]")
                console.print("")

    _run_async(_run())


def _search_in_hackathon(
    query: str,
    hackathon: str,
    winners: bool,
    tech: bool,
    include_rules: bool,
    use_cache: bool,
    is_json: Optional[bool],
):
    async def _run():
        async with DevpostClient(headed=_cli_config.get("headed", False), use_cache=use_cache) as client:
            result = await client.search_in_hackathon(
                hackathon_slug_or_url=hackathon,
                query=query,
                winners_only=winners,
                tech_only=tech,
                include_rules=include_rules,
            )

            if output_json(result, is_json):
                return

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                return

            slug = result.get("hackathon_slug", hackathon)
            total = result.get("total_matches", 0)
            project_matches = result["matches"].get("projects", [])
            desc_matches = result["matches"].get("description", [])
            rules_matches = result["matches"].get("rules", [])

            if total == 0:
                console.print(f"[yellow]No matches for '{query}' in {slug}[/yellow]")
                return

            console.print(f"[green]Found {total} match(es) for '{query}' in {slug}:[/green]\n")

            if project_matches:
                console.print(f"[bold]Projects ({len(project_matches)}):[/bold]")
                for p in project_matches:
                    winner_badge = " [yellow]★ WINNER[/yellow]" if p.get("is_winner") else ""
                    matched_in = ", ".join(p.get("matched_in", []))
                    console.print(f"  [cyan]{p.get('title', 'Unknown')}[/cyan]{winner_badge}")
                    if p.get("tagline"):
                        console.print(f"    [dim]{p['tagline'][:100]}[/dim]")
                    console.print(f"    [dim]Matched in: {matched_in}[/dim]")
                    console.print(f"    [dim]{p.get('url', '')}[/dim]")
                    console.print("")

            if desc_matches:
                console.print(f"[bold]In description ({len(desc_matches)}):[/bold]")
                for m in desc_matches:
                    console.print(f"  [dim]...{m.get('snippet', '')}...[/dim]")
                console.print("")

            if rules_matches:
                console.print(f"[bold]In rules ({len(rules_matches)}):[/bold]")
                for m in rules_matches:
                    console.print(f"  [dim]...{m.get('snippet', '')}...[/dim]")
                console.print("")

    _run_async(_run())


@cli.command()
@click.argument("slug")
@click.option("--limit", "-l", default=50, help="Number of participants to show (default: 50)")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def participants(slug: str, limit: int, is_json: Optional[bool]):
    """List participants from a hackathon.
    
    \b
    Examples:
      devpost participants medo               # List MeDo participants
      devpost participants hack --limit 100
      devpost participants hack --json
    """
    async def _participants():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            result = await client.get_participants(slug, limit=limit)

            if output_json(result, is_json):
                return

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            if not result.get("participants"):
                console.print("[yellow]No participants found.[/yellow]")
                return

            table = Table(title=f"Participants: {slug}")
            table.add_column("Username", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("URL", style="dim")

            for p in result["participants"]:
                table.add_row(
                    p.get("username", "Unknown")[:30],
                    p.get("name", "")[:30],
                    p.get("url", "")[:50],
                )

            console.print(table)
            console.print(f"\n[dim]Showing {result['count']} participants[/dim]")

    _run_async(_participants())


@cli.command()
@click.argument("slug")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def resources(slug: str, is_json: Optional[bool]):
    """List resources from a hackathon.
    
    \b
    Examples:
      devpost resources medo                  # List MeDo resources
      devpost resources hack --json
    """
    async def _resources():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            result = await client.get_resources(slug)

            if output_json(result, is_json):
                return

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            if not result.get("resources"):
                console.print("[yellow]No resources found.[/yellow]")
                return

            table = Table(title=f"Resources: {slug}")
            table.add_column("Title", style="cyan")
            table.add_column("URL", style="dim")

            for r in result["resources"]:
                table.add_row(
                    r.get("title", "Unknown")[:50],
                    r.get("url", "")[:60],
                )

            console.print(table)
            console.print(f"\n[dim]Showing {len(result['resources'])} resources[/dim]")

    _run_async(_resources())


@cli.command()
@click.argument("slug")
@click.option("--limit", "-l", default=20, help="Number of updates to show (default: 20)")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def updates(slug: str, limit: int, is_json: Optional[bool]):
    """List updates from a hackathon.
    
    \b
    Examples:
      devpost updates medo                    # List MeDo updates
      devpost updates hack --limit 50
      devpost updates hack --json
    """
    async def _updates():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            result = await client.get_updates(slug, limit=limit)

            if output_json(result, is_json):
                return

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            if not result.get("updates"):
                console.print("[yellow]No updates found.[/yellow]")
                return

            for u in result["updates"]:
                console.print(f"[cyan]{u.get('title', 'Untitled')}[/cyan]")
                if u.get("date"):
                    console.print(f"  [dim]{u['date']}[/dim]")
                if u.get("content"):
                    console.print(f"  [dim]{u['content'][:200]}[/dim]")
                if u.get("url"):
                    console.print(f"  [dim]{u['url']}[/dim]")
                console.print("")

            console.print(f"[dim]Showing {result['count']} updates[/dim]")

    _run_async(_updates())


@cli.command()
@click.argument("slug")
@click.option("--limit", "-l", default=20, help="Number of discussions to show (default: 20)")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def discussions(slug: str, limit: int, is_json: Optional[bool]):
    """List discussions/forum topics from a hackathon.
    
    \b
    Examples:
      devpost discussions medo                # List MeDo discussions
      devpost discussions hack --limit 50
      devpost discussions hack --json
    """
    async def _discussions():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            result = await client.get_discussions(slug, limit=limit)

            if output_json(result, is_json):
                return

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            if not result.get("discussions"):
                console.print("[yellow]No discussions found.[/yellow]")
                return

            table = Table(title=f"Discussions: {slug}")
            table.add_column("Title", style="cyan")
            table.add_column("Author", style="green")
            table.add_column("Replies", style="yellow")
            table.add_column("Date", style="dim")

            for d in result["discussions"]:
                table.add_row(
                    d.get("title", "Untitled")[:40],
                    d.get("author", "")[:20] or "N/A",
                    d.get("replies", "")[:10] or "0",
                    d.get("date", "")[:15] or "N/A",
                )

            console.print(table)
            console.print(f"\n[dim]Showing {result['count']} discussions[/dim]")

    _run_async(_discussions())


@cli.group()
def projects():
    """Browse projects on Devpost.
    
    \b
    Examples:
      devpost projects search "AI"           # Search projects
      devpost projects popular               # Popular projects
      devpost projects built-with Python     # Projects using Python
      devpost projects featured              # Staff picks
    """
    pass


@projects.command()
@click.argument("query")
@click.option("--limit", "-l", default=20, help="Number of results (default: 20)")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON")
def search(query: str, limit: int, is_json: Optional[bool]):
    """Search projects by keyword."""
    async def _run():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            projects = await client.search_projects(query=query, limit=limit)

            if output_json(projects, is_json):
                return

            if not projects:
                console.print(f"[yellow]No projects found for '{query}'[/yellow]")
                return

            for p in projects:
                title = p.get('title', 'Unknown')
                tagline = p.get('tagline') or ''
                winner_badge = " [yellow]★ WINNER[/yellow]" if p.get("is_winner") else ""
                console.print(f"[cyan]{title}{winner_badge}[/cyan]")
                if tagline:
                    console.print(f"  [dim]{tagline[:100]}[/dim]")
                if p.get("built_with"):
                    console.print(f"  [dim]Built with: {', '.join(p['built_with'][:5])}[/dim]")
                console.print(f"  [dim]{p.get('url', '')}[/dim]")
                console.print("")

    _run_async(_run())


@projects.command()
@click.option("--limit", "-l", default=20, help="Number of results (default: 20)")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON")
def popular(limit: int, is_json: Optional[bool]):
    """List popular projects."""
    async def _run():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            projects = await client.get_popular_projects(limit=limit)

            if output_json(projects, is_json):
                return

            if not projects:
                console.print("[yellow]No projects found.[/yellow]")
                return

            for p in projects:
                title = p.get('title', 'Unknown')
                tagline = p.get('tagline') or ''
                console.print(f"[cyan]{title}[/cyan]")
                if tagline:
                    console.print(f"  [dim]{tagline[:100]}[/dim]")
                if p.get("built_with"):
                    console.print(f"  [dim]Built with: {', '.join(p['built_with'][:5])}[/dim]")
                console.print(f"  [dim]{p.get('url', '')}[/dim]")
                console.print("")

    _run_async(_run())


@projects.command(name="built-with")
@click.argument("tech")
@click.option("--limit", "-l", default=20, help="Number of results (default: 20)")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON")
def built_with(tech: str, limit: int, is_json: Optional[bool]):
    """List projects built with a specific technology.
    
    \b
    Examples:
      devpost projects built-with Python
      devpost projects built-with "React"
      devpost projects built-with "OpenAI"
    """
    async def _run():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            projects = await client.get_built_with_projects(tech=tech, limit=limit)

            if output_json(projects, is_json):
                return

            if not projects:
                console.print(f"[yellow]No projects found using '{tech}'[/yellow]")
                return

            for p in projects:
                title = p.get('title', 'Unknown')
                tagline = p.get('tagline') or ''
                console.print(f"[cyan]{title}[/cyan]")
                if tagline:
                    console.print(f"  [dim]{tagline[:100]}[/dim]")
                if p.get("built_with"):
                    console.print(f"  [dim]Built with: {', '.join(p['built_with'][:5])}[/dim]")
                console.print(f"  [dim]{p.get('url', '')}[/dim]")
                console.print("")

    _run_async(_run())


@projects.command()
@click.option("--limit", "-l", default=20, help="Number of results (default: 20)")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON")
def featured(limit: int, is_json: Optional[bool]):
    """List staff picks / featured projects."""
    async def _run():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            projects = await client.get_featured_projects(limit=limit)

            if output_json(projects, is_json):
                return

            if not projects:
                console.print("[yellow]No featured projects found.[/yellow]")
                return

            for p in projects:
                title = p.get('title', 'Unknown')
                tagline = p.get('tagline') or ''
                featured_badge = " [yellow]★ STAFF PICK[/yellow]" if p.get("is_featured") else ""
                console.print(f"[cyan]{title}{featured_badge}[/cyan]")
                if tagline:
                    console.print(f"  [dim]{tagline[:100]}[/dim]")
                if p.get("built_with"):
                    console.print(f"  [dim]Built with: {', '.join(p['built_with'][:5])}[/dim]")
                console.print(f"  [dim]{p.get('url', '')}[/dim]")
                console.print("")

    _run_async(_run())


@cli.command()
@click.option("--this-week", is_flag=True, help="Show only hackathons closing within 7 days")
@click.option("--today", is_flag=True, help="Show only hackathons closing today")
@click.option("--limit", "-l", default=20, help="Number of results (default: 20)")
@click.option("--no-cache", is_flag=True, help="Bypass cache, fetch fresh data")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON")
def deadlines(this_week: bool, today: bool, limit: int, no_cache: bool, is_json: Optional[bool]):
    """Show hackathons sorted by soonest deadline.
    
    \b
    Examples:
      devpost deadlines                 # All open hackathons, soonest first
      devpost deadlines --this-week     # Closing within 7 days
      devpost deadlines --today         # Closing today
      devpost deadlines --json
    """
    async def _run():
        async with DevpostClient(headed=_cli_config.get("headed", False), use_cache=not no_cache) as client:
            hackathons = await client.list_hackathons(limit=200, open_state="open")

            deadline_hackathons = []
            for h in hackathons:
                days = parse_days_left(h.get("ends_at"))
                if days is not None:
                    if today and days > 0.5:
                        continue
                    if this_week and days > 7:
                        continue
                    deadline_hackathons.append((days, h))

            deadline_hackathons.sort(key=lambda x: x[0])
            result = [h for _, h in deadline_hackathons[:limit]]

            if output_json(result, is_json):
                return

            if not result:
                if today:
                    console.print("[yellow]No hackathons closing today.[/yellow]")
                elif this_week:
                    console.print("[yellow]No hackathons closing this week.[/yellow]")
                else:
                    console.print("[yellow]No hackathons with deadlines found.[/yellow]")
                return

            table = Table(title="Hackathons by Deadline")
            table.add_column("Title", style="cyan", no_wrap=True)
            table.add_column("Prize", style="yellow")
            table.add_column("Days Left", style="red")
            table.add_column("Status", style="green")

            for h in result:
                days = parse_days_left(h.get("ends_at"))
                days_str = f"{days:.0f}d" if days is not None else "?"
                if days is not None and days <= 1:
                    days_str = "[bold red]TODAY[/bold red]" if days < 0.5 else "[red]1d[/red]"
                elif days is not None and days <= 3:
                    days_str = f"[red]{days:.0f}d[/red]"
                prize = h.get("prize_amount") or "N/A"
                table.add_row(
                    h.get("title", "Unknown")[:50],
                    prize,
                    days_str,
                    h.get("open_state", "unknown"),
                )

            console.print(table)

    _run_async(_run())


@cli.group()
def cache():
    """Cache management commands.
    
    Manage the local hackathon data cache stored at ~/.devpost/cache/.
    Cached data is used for faster searches and offline --deep searches.
    """
    pass


@cache.command()
def status():
    """Show cache status and statistics.
    
    \b
    Examples:
      devpost cache status
    """
    mgr = CacheManager()
    info = mgr.status()

    console.print(Panel(
        f"[green]Entries:[/green] {info['entries']}\n"
        f"[green]Size:[/green] {_format_bytes(info['size_bytes'])}\n"
        f"[green]Oldest:[/green] {info.get('oldest') or 'N/A'}\n"
        f"[green]Newest:[/green] {info.get('newest') or 'N/A'}",
        title="Cache Status",
        border_style="blue",
    ))

    if info["keys"]:
        console.print("\n[bold]Cached keys:[/bold]")
        for key in info["keys"]:
            console.print(f"  [dim]{key}[/dim]")


@cache.command(name="clear")
def cache_clear():
    """Clear all cached data.
    
    \b
    Examples:
      devpost cache clear
    """
    mgr = CacheManager()
    count = mgr.clear()
    console.print(f"[green]Cleared {count} cache entries.[/green]")


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


@cli.group()
def submit():
    """Submit and manage projects.
    
    Requires authentication via `devpost auth login` or environment variables:
      export DEVPOST_EMAIL="your@email.com"
      export DEVPOST_PASSWORD="your_password"
    """
    pass


@submit.command(name="project")
@click.argument("hackathon_slug")
@click.option("--title", "-t", required=True, help="Project title")
@click.option("--tagline", "-tag", required=True, help="Short description (max 140 chars)")
@click.option("--description", "-d", help="Full project description (markdown)")
@click.option("--built-with", "-b", help="Comma-separated list of technologies")
@click.option("--github", help="GitHub repository URL")
@click.option("--demo", help="Live demo URL")
@click.option("--video", help="Demo video URL (YouTube, etc.)")
@click.option("--dry-run", is_flag=True, help="Test without actually submitting")
def submit_project_cmd(
    hackathon_slug: str,
    title: str,
    tagline: str,
    description: Optional[str],
    built_with: Optional[str],
    github: Optional[str],
    demo: Optional[str],
    video: Optional[str],
    dry_run: bool,
):
    """Submit a new project to a hackathon.
    
    Requires authentication. Always test with --dry-run first!
    
    \b
    Examples:
      devpost submit project zervehack \\
        --title "My Project" \\
        --tagline "AI-powered solution" \\
        --built-with "Python,React,OpenAI" \\
        --github "https://github.com/user/repo" \\
        --dry-run
      
      devpost submit project hack2026 -t "Demo" -tag "Cool demo" -b "FastAPI"
    """
    async def _submit():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            console.print(f"[red]Error: {e.message}[/red]")
            console.print("Set them with: export DEVPOST_EMAIL='your@email.com'")
            sys.exit(1)

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            tech_list = [t.strip() for t in built_with.split(",")] if built_with else None

            links = {}
            if github:
                links["github"] = github
            if demo:
                links["demo"] = demo
            if video:
                links["video"] = video

            result = await client.submit_project(
                hackathon_slug=hackathon_slug,
                title=title,
                tagline=tagline,
                description=description,
                built_with=tech_list,
                links=links if links else None,
                dry_run=dry_run,
            )

            if result.get("error"):
                console.print(Panel(
                    f"[red]Error:[/red] {result['error']}\n\n"
                    f"[dim]Steps:[/dim] {json.dumps(result.get('steps', []), indent=2, default=str)}",
                    title="Submission Failed",
                    border_style="red"
                ))
                sys.exit(1)

            if dry_run:
                console.print(Panel(
                    f"[yellow]DRY RUN - Would submit:[/yellow]\n\n"
                    f"Hackathon: {result['hackathon_slug']}\n"
                    f"Title: {result['project_title']}\n"
                    f"Tagline: {tagline}",
                    title="Submission Preview",
                    border_style="yellow"
                ))
            else:
                console.print(Panel(
                    f"[green]Successfully submitted![/green]\n\n"
                    f"URL: {result.get('url', 'N/A')}\n"
                    f"Title: {result['project_title']}",
                    title="Submission Complete",
                    border_style="green"
                ))

    _run_async(_submit())


@cli.command()
@click.option("--limit", "-l", default=20, help="Number of submissions to show (default: 20)")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def my_submissions(limit: int, is_json: Optional[bool]):
    """List your submitted projects.
    
    Requires authentication. Shows all projects in your portfolio.
    
    \b
    Examples:
      devpost my-submissions               # List all submissions
      devpost my-submissions -l 5          # Show only 5 most recent
      devpost my-submissions --json        # Output as JSON
    """
    async def _list():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            if output_json({"error": e.message, "code": e.code}, is_json):
                sys.exit(2)
            console.print(f"[red]Error: {e.message}[/red]")
            sys.exit(2)

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            result = await client.list_my_submissions(limit=limit)

            if output_json(result, is_json):
                return

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            if not result.get("submissions"):
                console.print("[yellow]No submissions found.[/yellow]")
                return

            table = Table(title="Your Devpost Submissions")
            table.add_column("Title", style="cyan")
            table.add_column("URL", style="dim")

            for p in result["submissions"]:
                table.add_row(p.get("title", "Unknown"), p.get("url", "N/A")[:60])

            console.print(table)
            console.print(f"\n[dim]Showing {len(result['submissions'])} submissions[/dim]")

    _run_async(_list())


@cli.command()
@click.argument("project_url")
@click.option("--title", "-t", help="New title")
@click.option("--tagline", "-tag", help="New tagline")
@click.option("--description", "-d", help="New description (markdown)")
@click.option("--built-with", "-b", help="Comma-separated technologies")
@click.option("--github", help="GitHub URL")
@click.option("--demo", help="Demo URL")
@click.option("--video", help="Video URL")
@click.option("--dry-run", is_flag=True, help="Test without saving")
def update(project_url: str, title: Optional[str], tagline: Optional[str], description: Optional[str],
           built_with: Optional[str], github: Optional[str], demo: Optional[str], video: Optional[str], dry_run: bool):
    """Update an existing submission.
    
    Only specified fields are updated (patch-style). Test with --dry-run first!
    
    \b
    Examples:
      devpost update https://devpost.com/software/myproj \\
        --tagline "New improved tagline"
      
      devpost update https://devpost.com/software/myproj \\
        --github "https://github.com/new-repo" \\
        --demo "https://new-demo.com"
      
      devpost update https://devpost.com/software/myproj -t "New Title" --dry-run
    """
    async def _update():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            console.print(f"[red]Error: {e.message}[/red]")
            sys.exit(1)

        if not any([title, tagline, description, built_with, github, demo, video]):
            console.print("[yellow]Warning: No fields to update specified.[/yellow]")
            sys.exit(1)

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            tech_list = [t.strip() for t in built_with.split(",")] if built_with else None

            links = {}
            if github:
                links["github"] = github
            if demo:
                links["demo"] = demo
            if video:
                links["video"] = video

            result = await client.update_submission(
                project_url=project_url,
                title=title,
                tagline=tagline,
                description=description,
                built_with=tech_list,
                links=links if links else None,
                dry_run=dry_run,
            )

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            if dry_run:
                console.print(Panel(
                    f"[yellow]DRY RUN - Would update:[/yellow]\n\n"
                    f"Project: {result['url']}\n"
                    f"Fields: {', '.join(result['updated_fields'])}",
                    title="Update Preview",
                    border_style="yellow"
                ))
            else:
                console.print(Panel(
                    f"[green]Successfully updated![/green]\n\n"
                    f"Updated fields: {', '.join(result['updated_fields'])}",
                    title="Update Complete",
                    border_style="green"
                ))

    _run_async(_update())


@cli.command()
@click.argument("project_url")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def submission(project_url: str, is_json: Optional[bool]):
    """Get detailed info about your submission.
    
    Shows title, tagline, description, tech stack, team members, and links.
    
    \b
    Examples:
      devpost submission https://devpost.com/software/myproj
      devpost submission https://devpost.com/software/myproj --json
    """
    async def _submission():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            if output_json({"error": e.message, "code": e.code}, is_json):
                sys.exit(2)
            console.print(f"[red]Error: {e.message}[/red]")
            sys.exit(2)

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            result = await client.get_submission_details(project_url)

            if output_json(result, is_json):
                return

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            details = result.get("details", {})
            console.print(Panel(
                f"[bold cyan]{details.get('title', 'Unknown')}[/bold cyan]\n\n"
                f"[green]Tagline:[/green] {details.get('tagline', 'N/A')}\n"
                f"[green]Description:[/green] {details.get('description', 'N/A')[:200]}\n"
                f"[green]Built with:[/green] {', '.join(details.get('built_with', [])) or 'N/A'}\n"
                f"[green]Team:[/green] {', '.join([m['username'] for m in details.get('team_members', [])]) or 'Solo'}\n\n"
                f"[green]URL:[/green] {result.get('url', 'N/A')}",
                title="Submission Details",
                border_style="cyan"
            ))

    _run_async(_submission())


@cli.group()
def team():
    """Team management commands.
    
    Requires authentication. Manage team members and create/join teams.
    """
    pass


@team.command(name="add")
@click.argument("project_url")
@click.argument("username")
def team_add(project_url: str, username: str):
    """Add a team member to a project.
    
    \b
    Examples:
      devpost team add https://devpost.com/software/myproj alice
      devpost team add https://devpost.com/software/myproj bob@example.com
    """
    async def _add():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            console.print(f"[red]Error: {e.message}[/red]")
            sys.exit(1)

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            result = await client.add_team_member(project_url, username)

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            console.print(Panel(
                f"[green]{result['message']}[/green]\n\n"
                f"Project: {project_url}\n"
                f"User: {username}",
                title="Team Member Added",
                border_style="green"
            ))

    _run_async(_add())


@team.command(name="remove")
@click.argument("project_url")
@click.argument("username")
def team_remove(project_url: str, username: str):
    """Remove a team member from a project.
    
    \b
    Examples:
      devpost team remove https://devpost.com/software/myproj alice
    """
    async def _remove():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            console.print(f"[red]Error: {e.message}[/red]")
            sys.exit(1)

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            result = await client.remove_team_member(project_url, username)

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            console.print(Panel(
                f"[green]{result['message']}[/green]\n\n"
                f"Project: {project_url}\n"
                f"User: {username}",
                title="Team Member Removed",
                border_style="green"
            ))

    _run_async(_remove())


@team.command(name="create")
@click.argument("hackathon_slug")
@click.option("--name", "-n", required=True, help="Team name")
@click.option("--invite", help="Comma-separated usernames to invite")
def team_create(hackathon_slug: str, name: str, invite: Optional[str]):
    """Create a team for a hackathon.
    
    \b
    Examples:
      devpost team create zervehack --name "Team Awesome"
      devpost team create zervehack -n "My Team" --invite "alice,bob"
    """
    async def _create():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            console.print(f"[red]Error: {e.message}[/red]")
            sys.exit(1)

        invite_list = [u.strip() for u in invite.split(",")] if invite else None

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            result = await client.create_team(hackathon_slug, name, invite_list)

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            console.print(Panel(
                f"[green]{result['message']}[/green]\n\n"
                f"Hackathon: {hackathon_slug}\n"
                f"Team: {name}",
                title="Team Created",
                border_style="green"
            ))

    _run_async(_create())


@team.command(name="join")
@click.argument("hackathon_slug")
@click.option("--invite-url", "-i", help="Team invite URL")
def team_join(hackathon_slug: str, invite_url: Optional[str]):
    """Join a team for a hackathon.
    
    Use --invite-url if you have a team invitation link.
    
    \b
    Examples:
      devpost team join zervehack
      devpost team join zervehack -i "https://devpost.com/teams/invite/..."
    """
    async def _join():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            console.print(f"[red]Error: {e.message}[/red]")
            sys.exit(1)

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            result = await client.join_team(hackathon_slug, invite_url)

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            console.print(Panel(
                f"[green]{result['message']}[/green]\n\n"
                f"Hackathon: {hackathon_slug}",
                title="Joined Team",
                border_style="green"
            ))

    _run_async(_join())


@cli.command()
@click.argument("project_url")
@click.argument("image_paths", nargs=-1, required=True)
@click.option("--set-main", type=int, default=0, help="Index of main image (0-based)")
def upload(project_url: str, image_paths: tuple[str], set_main: int):
    """Upload screenshots to a project.
    
    Provide one or more image file paths. First image is main by default.
    
    \b
    Examples:
      devpost upload https://devpost.com/software/myproj screenshot.png
      devpost upload https://devpost.com/software/myproj img1.png img2.png img3.png
      devpost upload https://devpost.com/software/myproj a.png b.png --set-main 1
    """
    async def _upload():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            console.print(f"[red]Error: {e.message}[/red]")
            sys.exit(1)

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            result = await client.upload_screenshots(project_url, list(image_paths), set_main)

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            if result.get("uploaded"):
                console.print(Panel(
                    f"[green]Uploaded {len(result['uploaded'])} images[/green]\n\n"
                    + "\n".join([f"  ✓ {p}" for p in result["uploaded"]]) +
                    (f"\n\n[yellow]Failed:[/yellow]\n" + "\n".join([f"  ✗ {f['path']}: {f['reason']}"] for f in result.get("failed", [])) if result.get("failed") else ""),
                    title="Upload Complete",
                    border_style="green"
                ))

    _run_async(_upload())


@cli.command()
@click.argument("project_url")
@click.option("--confirm", is_flag=True, help="Confirm deletion (CANNOT BE UNDONE)")
def delete(project_url: str, confirm: bool):
    """Delete a project submission permanently.
    
    WARNING: This action cannot be undone!
    Requires --confirm flag to actually delete.
    
    \b
    Examples:
      devpost delete https://devpost.com/software/myproj       # Shows warning
      devpost delete https://devpost.com/software/myproj --confirm  # Deletes
    """
    async def _delete():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            console.print(f"[red]Error: {e.message}[/red]")
            sys.exit(1)

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            result = await client.delete_submission(project_url, confirm)

            if not confirm:
                console.print(Panel(
                    f"[yellow]Confirmation required[/yellow]\n\n"
                    f"{result.get('message', 'Confirmation required to delete this project.')}\n\n"
                    f"Run with [bold]--confirm[/bold] to delete: devpost delete {project_url} --confirm",
                    title="Delete Warning",
                    border_style="yellow"
                ))
                sys.exit(0)

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            console.print(Panel(
                f"[green]{result['message']}[/green]\n\n"
                f"Project: {project_url}",
                title="Project Deleted",
                border_style="green"
            ))

    _run_async(_delete())


@cli.command()
@click.argument("hackathon_slug")
def join(hackathon_slug: str):
    """Join/register for a hackathon.
    
    Required before you can submit a project.
    
    \b
    Examples:
      devpost join zervehack
      devpost join datahacks-2025
    """
    async def _join():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            console.print(f"[red]Error: {e.message}[/red]")
            sys.exit(1)

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            result = await client.join_hackathon(hackathon_slug)

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            console.print(Panel(
                f"[green]{result['data']['message']}[/green]\n\n"
                f"Hackathon: {hackathon_slug}",
                title="Joined Hackathon",
                border_style="green"
            ))

    _run_async(_join())


@cli.command()
@click.argument("hackathon_slug")
@click.option("--confirm", is_flag=True, help="Confirm leave action")
def leave(hackathon_slug: str, confirm: bool):
    """Leave/withdraw from a hackathon.
    
    Requires --confirm to actually leave.
    
    \b
    Examples:
      devpost leave zervehack              # Shows warning
      devpost leave zervehack --confirm    # Actually leaves
    """
    async def _leave():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            console.print(f"[red]Error: {e.message}[/red]")
            sys.exit(1)

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            result = await client.leave_hackathon(hackathon_slug, confirm)

            if not confirm:
                console.print(Panel(
                    f"[yellow]Confirmation required[/yellow]\n\n"
                    f"{result.get('error', 'Confirmation required to leave this hackathon.')}\n\n"
                    f"Run with [bold]--confirm[/bold] to leave: devpost leave {hackathon_slug} --confirm",
                    title="Leave Warning",
                    border_style="yellow"
                ))
                return

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            console.print(Panel(
                f"[green]{result['data']['message']}[/green]\n\n"
                f"Hackathon: {hackathon_slug}",
                title="Left Hackathon",
                border_style="green"
            ))

    _run_async(_leave())


@cli.command()
@click.argument("project_url")
def like(project_url: str):
    """Like/bookmark a project.
    
    \b
    Examples:
      devpost like https://devpost.com/software/coolproject
    """
    async def _like():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            console.print(f"[red]Error: {e.message}[/red]")
            sys.exit(1)

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            result = await client.like_project(project_url)

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            console.print(Panel(
                f"[green]{result['data']['message']}[/green]\n\n"
                f"Project: {project_url}",
                title="Project Liked",
                border_style="green"
            ))

    _run_async(_like())


@cli.command()
@click.argument("project_url")
@click.option("--github", help="GitHub URL")
@click.option("--demo", help="Demo URL")
@click.option("--video", help="Video URL (YouTube, etc.)")
@click.option("--website", help="Website URL")
@click.option("--dry-run", is_flag=True, help="Test without saving")
def links(project_url: str, github: Optional[str], demo: Optional[str],
          video: Optional[str], website: Optional[str], dry_run: bool):
    """Update project links (granular control).
    
    Only specified links are updated. Test with --dry-run first!
    
    \b
    Examples:
      devpost links https://devpost.com/software/myproj \\
        --github "https://github.com/new-repo"
      
      devpost links https://devpost.com/software/myproj \\
        --demo "https://demo.example.com" \\
        --video "https://youtube.com/watch?v=..."
    """
    async def _links():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            console.print(f"[red]Error: {e.message}[/red]")
            sys.exit(1)

        if not any([github, demo, video, website]):
            console.print("[yellow]Warning: No links specified.[/yellow]")
            sys.exit(1)

        link_updates = {}
        if github:
            link_updates["github"] = github
        if demo:
            link_updates["demo"] = demo
        if video:
            link_updates["video"] = video
        if website:
            link_updates["website"] = website

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            result = await client.update_submission(
                project_url=project_url,
                links=link_updates,
                dry_run=dry_run,
            )

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            if dry_run:
                console.print(Panel(
                    f"[yellow]DRY RUN - Would update links:[/yellow]\n\n"
                    + "\n".join([f"  {k}: {v}" for k, v in link_updates.items()]),
                    title="Links Update Preview",
                    border_style="yellow"
                ))
            else:
                console.print(Panel(
                    f"[green]Links updated successfully![/green]\n\n"
                    + "\n".join([f"  {k}: {v}" for k, v in link_updates.items()]),
                    title="Links Updated",
                    border_style="green"
                ))

    _run_async(_links())


@cli.group()
def auth():
    """Authentication commands.
    
    Use `devpost auth login` for interactive setup, or set environment
    variables DEVPOST_EMAIL and DEVPOST_PASSWORD.
    """
    pass


@auth.command()
def status():
    """Check authentication status.
    
    Shows if credentials are configured via env vars or saved login.
    
    \b
    Examples:
      devpost auth status
    """
    _do_status()


@auth.command()
@click.option("--email", "-e", help="Email address (non-interactive mode)")
def login(email: Optional[str]):
    """Authentication setup.
    
    Interactive mode: Prompts for email and password.
    Non-interactive mode: Use --email flag; password is always prompted.
    
    Saves credentials to ~/.devpost/.env and tests login with Playwright.
    
    \b
    Examples:
      devpost auth login                          # Interactive mode
      devpost auth login -e user@example.com       # Email pre-filled, prompts for password
    """
    password = None
    if email is not None:
        password = click.prompt("Devpost password", type=str, hide_input=True)
    else:
        email = click.prompt("Devpost email", type=str)
        password = click.prompt("Devpost password", type=str, hide_input=True)

    _do_login(email, password)


@auth.command()
def logout():
    """Clear saved credentials and session.
    
    Removes ~/.devpost/.env and any cached session cookies.
    
    \b
    Examples:
      devpost auth logout
    """
    _do_logout()


def _do_login(email: Optional[str], password: Optional[str]) -> None:
    """Internal login logic used by both 'auth login' and top-level 'login'."""
    if not email or not password:
        email = click.prompt("Devpost email", type=str)
        password = click.prompt("Devpost password", type=str, hide_input=True)

    console.print("[dim]Saving credentials and testing login...[/dim]")

    async def _login():
        result = await save_credentials_interactive(email, password)

        if result.get("success"):
            if output_json({"success": True, "email": email, "message": "Credentials saved to ~/.devpost/.env"}, None):
                return
            console.print(Panel(
                f"[green]Successfully authenticated![/green]\n\n"
                f"Email: {email}\n\n"
                f"[dim]Credentials saved to ~/.devpost/.env[/dim]",
                title="Authentication Successful",
                border_style="green"
            ))
        else:
            error_msg = result.get('error', 'Unknown error')
            if output_json({"success": False, "error": error_msg}, None):
                sys.exit(2)
            console.print(Panel(
                f"[red]Authentication failed:[/red] {error_msg}",
                title="Authentication Failed",
                border_style="red"
            ))
            sys.exit(2)

    _run_async(_login())


def _do_logout() -> None:
    """Internal logout logic."""
    async def _logout():
        result = await clear_credentials()
        if output_json(result, None):
            return
        console.print(Panel(
            f"[green]{result['message']}[/green]",
            title="Logged Out",
            border_style="green"
        ))

    _run_async(_logout())


def _do_status() -> None:
    """Internal status logic."""
    creds = get_credentials()
    if creds:
        email, password = creds
        data = {"authenticated": True, "email": email, "password_set": bool(password)}
        if output_json(data, None):
            return
        console.print(f"[green]Authenticated as:[/green] {email}")
        console.print("[dim]Password is configured[/dim]" if password else "[red]Password is NOT set[/red]")
    else:
        data = {"authenticated": False}
        if output_json(data, None):
            return
        console.print("[yellow]Not authenticated. Set env vars or use 'devpost login'[/yellow]")
        console.print("  export DEVPOST_EMAIL='your@email.com'")
        console.print("  export DEVPOST_PASSWORD='your_password'")


@cli.command(name="login")
@click.option("--email", "-e", help="Email address (non-interactive mode)")
def login_cmd(email: Optional[str]):
    """Authentication setup (shortcut for 'auth login').
    
    Interactive mode: Prompts for email and password.
    Non-interactive mode: Use --email flag; password is always prompted.
    
    \b
    Examples:
      devpost login                          # Interactive mode
      devpost login -e user@example.com       # Email pre-filled, prompts for password
    """
    password = None
    if email is not None:
        password = click.prompt("Devpost password", type=str, hide_input=True)
    else:
        email = click.prompt("Devpost email", type=str)
        password = click.prompt("Devpost password", type=str, hide_input=True)
    _do_login(email, password)


@cli.command(name="logout")
def logout_cmd():
    """Clear saved credentials and session (shortcut for 'auth logout').
    
    Removes ~/.devpost/.env and any cached session cookies.
    
    \b
    Examples:
      devpost logout
    """
    _do_logout()


@cli.command(name="status")
def status_cmd():
    """Check authentication status (shortcut for 'auth status').
    
    Shows if credentials are configured via env vars or saved login.
    
    \b
    Examples:
      devpost status
    """
    _do_status()


def main():
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
