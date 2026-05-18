"""CLI for Devpost hackathons."""

import asyncio
import json
import re
import sys
from typing import Any, Optional

import click
from rich.console import Console

from .core import (
    AuthenticatedClient,
    DevpostClient,
    DevpostError,
    BASE_URL,
    API_BASE,
    clear_credentials,
    save_credentials_interactive,
    get_credentials,
)
from .cache import CacheManager, parse_days_left, parse_prize_amount, _matches
from .core import clean_html
from .session import load_credentials, load_credentials_from_env
from .logging_config import setup_logging, get_logger

logger = get_logger("cli")
console = Console(color_system=None, force_terminal=False)

_cli_config: dict = {"headed": False, "debug_screenshots": False}


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
@click.version_option(version="0.7.0", prog_name="devpost")
@click.option("--headed", is_flag=True, help="Run browser in headed mode (visible window) for debugging")
@click.option("--debug-screenshots", is_flag=True, help="Save debug screenshots on Playwright errors (saves to /tmp/playwright_error_*.png)")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def cli(headed: bool, debug_screenshots: bool, verbose: bool):
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
    _cli_config["debug_screenshots"] = debug_screenshots
    setup_logging(verbose)


@cli.command(name="hackathons")
@click.option("--limit", "-l", default=20, help="Number of hackathons to show (default: 20)")
@click.option("--state", "-s", type=click.Choice(["open", "closed", "ended", "upcoming"]),
              help="Filter by hackathon state ('closed' is an alias for 'ended')")
@click.option("--sort", type=click.Choice(["most-relevant", "deadline", "recently-added", "prize-amount"]),
              default="most-relevant", help="Sort order (default: most-relevant)")
@click.option("--query", "-q", help="Search query string")
@click.option("--location", type=click.Choice(["online", "in-person"]), multiple=True, help="Location type (repeatable)")
@click.option("--duration", type=click.Choice(["days", "weeks", "months"]), multiple=True, help="Duration (repeatable)")
@click.option("--theme", multiple=True, help="Theme filter (repeatable, e.g. 'Machine Learning/AI')")
@click.option("--organization", help="Organization name")
@click.option("--access", type=click.Choice(["public", "invite-only"]), multiple=True, help="Access type (repeatable)")
@click.option("--devpost-managed", is_flag=True, help="Only Devpost-managed hackathons")
@click.option("--featured", is_flag=True, help="Only featured hackathons")
@click.option("--page", type=int, default=1, help="Page number")
@click.option("--per-page", type=int, default=9, help="Results per page")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def hackathons(
    limit: int,
    state: Optional[str],
    sort: str,
    query: Optional[str],
    location: tuple[str],
    duration: tuple[str],
    theme: tuple[str],
    organization: Optional[str],
    access: tuple[str],
    devpost_managed: bool,
    featured: bool,
    page: int,
    per_page: int,
    is_json: Optional[bool],
):
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
    async def _hackathons():
        async with DevpostClient(headed=_cli_config.get("headed", False), debug_screenshots=_cli_config.get("debug_screenshots", False)) as client:
            result = await client.list_hackathons(
                limit=limit,
                open_state=state,
                order_by=sort,
                search=query,
                challenge_type=list(location) if location else None,
                length=list(duration) if duration else None,
                themes=list(theme) if theme else None,
                organization=organization,
                open_to=[a.replace("-", "_") for a in access] if access else None,
                managed_by_devpost_badge=devpost_managed,
                page=page,
                per_page=per_page,
            )

            hackathons_list = result.get("hackathons", [])
            meta = result.get("meta", {})
            
            # Filter by featured if requested
            if featured:
                hackathons_list = [h for h in hackathons_list if h.get("featured")]

            if output_json(result, is_json):
                return

            if not hackathons_list:
                console.print("[yellow]No hackathons found.[/yellow]")
                return

            total = meta.get("total_count", len(hackathons_list))
            console.print(f"[dim]({len(hackathons_list)} of {total})[/dim]")
            console.print("")

            for h in hackathons_list:
                status = h.get("open_state", "unknown")
                prize = h.get("prize_amount") or "N/A"
                ends = h.get("ends_at") or "N/A"
                title = h.get("title", "Unknown")[:50]
                console.print(f"{title}\t{status}\t{prize}\t{ends}")

    _run_async(_hackathons())


@cli.command()
@click.option("--type", "challenge_type", type=click.Choice(["online", "in-person"]), default="online",
              help="Filter by challenge type (default: online)")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON")
def featured(challenge_type: str, is_json: Optional[bool]):
    """List featured hackathons.
    
    \b
    Examples:
      devpost featured                     # Featured online hackathons
      devpost featured --type in-person    # Featured in-person hackathons
      devpost featured --json              # Output as JSON
    """
    async def _featured():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            hackathons_list = await client.get_featured_hackathons(challenge_type=challenge_type)
            
            if output_json({"hackathons": hackathons_list, "count": len(hackathons_list)}, is_json):
                return
            
            if not hackathons_list:
                console.print("[yellow]No featured hackathons found.[/yellow]")
                return
            
            console.print(f"[dim]({len(hackathons_list)} featured)[/dim]\n")
            for h in hackathons_list:
                status = h.get("open_state", "unknown")
                prize = clean_html(h.get("prize_amount")) or "N/A"
                ends = h.get("time_left_to_submission") or h.get("submission_period_dates") or "N/A"
                title = h.get("title", "Unknown")[:50]
                console.print(f"{title}\t{status}\t{prize}\t{ends}")
    
    _run_async(_featured())


@cli.command()
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON")
def recommended(is_json: Optional[bool]):
    """List recommended hackathons (requires auth for personalized results).
    
    \b
    Examples:
      devpost recommended                  # Recommended hackathons
      devpost recommended --json           # Output as JSON
    
    Note: Returns generic results without authentication.
    """
    async def _recommended():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            hackathons_list = await client.get_recommended_hackathons()
            
            if output_json({"hackathons": hackathons_list, "count": len(hackathons_list)}, is_json):
                return
            
            if not hackathons_list:
                console.print("[yellow]No recommended hackathons found.[/yellow]")
                return
            
            console.print(f"[dim]({len(hackathons_list)} recommended)[/dim]\n")
            for h in hackathons_list:
                status = h.get("open_state", "unknown")
                prize = clean_html(h.get("prize_amount")) or "N/A"
                ends = h.get("time_left_to_submission") or h.get("submission_period_dates") or "N/A"
                title = h.get("title", "Unknown")[:50]
                console.print(f"{title}\t{status}\t{prize}\t{ends}")
    
    _run_async(_recommended())


@cli.command()
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON")
def nearby(is_json: Optional[bool]):
    """List nearby hackathons (requires location/auth for meaningful results).
    
    \b
    Examples:
      devpost nearby                       # Nearby hackathons
      devpost nearby --json                # Output as JSON
    
    Note: Returns empty list without location/authentication.
    """
    async def _nearby():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            hackathons_list = await client.get_nearby_hackathons()
            
            if output_json({"hackathons": hackathons_list, "count": len(hackathons_list)}, is_json):
                return
            
            if not hackathons_list:
                console.print("[yellow]No nearby hackathons found (try authenticating).[/yellow]")
                return
            
            console.print(f"[dim]({len(hackathons_list)} nearby)[/dim]\n")
            for h in hackathons_list:
                status = h.get("open_state", "unknown")
                prize = clean_html(h.get("prize_amount")) or "N/A"
                ends = h.get("time_left_to_submission") or h.get("submission_period_dates") or "N/A"
                title = h.get("title", "Unknown")[:50]
                console.print(f"{title}\t{status}\t{prize}\t{ends}")
    
    _run_async(_nearby())


@cli.command()
@click.option("--query", "-q", default="", help="Search term (empty returns all)")
@click.option("--limit", "-l", type=int, default=20, help="Max results (default: 20)")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON")
def organizations(query: str, limit: int, is_json: Optional[bool]):
    """Search organizations.
    
    \b
    Examples:
      devpost organizations                # List all organizations
      devpost organizations -q "Google"    # Search for "Google"
      devpost organizations --json         # Output as JSON
    """
    async def _organizations():
        async with DevpostClient(headed=_cli_config.get("headed", False)) as client:
            orgs = await client.search_organizations(term=query)
            orgs = orgs[:limit]
            
            if output_json({"organizations": orgs, "count": len(orgs)}, is_json):
                return
            
            if not orgs:
                console.print("[yellow]No organizations found.[/yellow]")
                return
            
            console.print(f"[dim]({len(orgs)} organizations)\n[/dim]")
            for org in orgs:
                name = org.get("name", "Unknown")
                count = org.get("count", 0)
                console.print(f"{name}\t{count} hackathons")
    
    _run_async(_organizations())


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
        async with DevpostClient(headed=_cli_config.get("headed", False), debug_screenshots=_cli_config.get("debug_screenshots", False)) as client:
            hackathon = await client.get_hackathon_by_slug(slug)

            if not hackathon:
                if output_json({"error": f"Hackathon '{slug}' not found", "code": "NOT_FOUND"}, is_json):
                    sys.exit(3)
                console.print(f"[red]Hackathon '{slug}' not found.[/red]")
                sys.exit(3)

            if output_json(hackathon, is_json):
                return

            console.print(f"[cyan]{hackathon.get('title', 'Unknown')}[/cyan]")
            console.print(f"url: {hackathon.get('url', 'N/A')}")
            console.print(f"status: {hackathon.get('open_state', 'unknown')}")
            
            if hackathon.get("featured"):
                console.print("featured: yes")
            
            console.print(f"prize: {hackathon.get('prize_amount', 'N/A')}")
            
            prize_counts = hackathon.get('prizes_counts', {})
            if prize_counts:
                cash = prize_counts.get('cash', 0)
                other = prize_counts.get('other', 0)
                console.print(f"prize_categories: {cash} cash, {other} other")
            
            console.print(f"submissions: {hackathon.get('submissions_count', 'N/A')}")
            if hackathon.get('registrations_count') != 'N/A':
                console.print(f"registrations: {hackathon['registrations_count']}")
            
            console.print(f"ends: {hackathon.get('ends_at', 'N/A')}")
            if hackathon.get('submission_period_dates'):
                console.print(f"period: {hackathon['submission_period_dates']}")
            
            access = "invite-only" if hackathon.get('invite_only') else "public"
            console.print(f"access: {access}")
            
            if hackathon.get('organization_name'):
                console.print(f"organization: {hackathon['organization_name']}")
            
            if hackathon.get('managed_by_devpost_badge'):
                console.print("managed_by: Devpost")
            
            themes = hackathon.get('themes', [])
            if themes:
                theme_names = [t.get('name', '') for t in themes if t.get('name')]
                if theme_names:
                    console.print(f"themes: {', '.join(theme_names[:5])}")
            
            if hackathon.get('submission_gallery_url'):
                console.print(f"gallery: {hackathon['submission_gallery_url']}")
            
            tagline = hackathon.get('tagline', 'No description')
            console.print(f"\n{tagline[:300]}")

    _run_async(_info())




@cli.command(name="gallery")
@click.argument("slug")
@click.option("--limit", "-l", default=20, help="Number of projects to show (default: 20)")
@click.option("--sort", type=click.Choice(["recent", "winners"]), default="recent", help="Sort order")
@click.option("--category", help="Filter by category (hackathon-specific)")
@click.option("--query", "-q", help="Search within gallery")
@click.option("--page", type=int, default=1, help="Page number")
@click.option("--winners", "-w", is_flag=True, help="Only show winning projects (alias for --sort winners)")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def gallery(
    slug: str,
    limit: int,
    sort: str,
    category: Optional[str],
    query: Optional[str],
    page: int,
    winners: bool,
    is_json: Optional[bool],
):
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
        actual_winners = winners or (sort == "winners")
        async with DevpostClient(headed=_cli_config.get("headed", False), debug_screenshots=_cli_config.get("debug_screenshots", False)) as client:
            result = await client.list_hackathon_projects(
                hackathon_url=hackathon_url,
                limit=limit,
                winners_only=actual_winners,
                sort_by=sort if sort != "recent" else None,
                category=category,
                search_query=query,
                page=page,
            )

            if output_json(result, is_json):
                return

            if not result.get("projects"):
                console.print("[yellow]No projects found.[/yellow]")
                return

            console.print(f"[dim]({len(result['projects'])} projects)[/dim]")
            for p in result["projects"]:
                title = p.get("title", "Unknown")[:50]
                winner = "★" if p.get("is_winner") else ""
                url = p.get("url", "N/A")
                console.print(f"{title}{winner}\t{url}")

    _run_async(_gallery())


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
        async with DevpostClient(headed=_cli_config.get("headed", False), debug_screenshots=_cli_config.get("debug_screenshots", False)) as client:
            details = await client.get_project_details(url)

            if output_json(details, is_json):
                return

            if not details.get("success"):
                console.print(f"[red]Error: {details.get('error', 'Unknown error')}[/red]")
                sys.exit(1)

            data = details.get("data", {})
            
            console.print(f"[cyan]{data.get('title', 'Unknown')}[/cyan]")
            if data.get("is_winner"):
                console.print("winner: yes")
            console.print(f"url: {details.get('url', 'N/A')}")
            console.print(f"\n[dim]Description:[/dim]")
            console.print(f"{data.get('description', 'No description')[:500]}")
            
            tech_stack = ", ".join(data.get("built_with", [])) or "Not specified"
            console.print(f"\ntech_stack: {tech_stack}")
            
            links = data.get("links", {})
            if links:
                console.print("\nlinks:")
                for k, v in links.items():
                    console.print(f"  {k}: {v}")

    _run_async(_project())


@cli.command()
@click.argument("username")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def user(username: str, is_json: Optional[bool]):
    """Get complete user profile.
    
    Fetches all user data in one command: profile, projects, hackathons,
    achievements, followers, following, and likes.
    
    \b
    Examples:
      devpost user tech-dawg015
      devpost user mintychochip --json
    """
    async def _user():
        async with DevpostClient(headed=_cli_config.get("headed", False), debug_screenshots=_cli_config.get("debug_screenshots", False)) as client:
            result = await client.get_user_full(username)

            if output_json(result, is_json):
                return

            if not result.get("success"):
                console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
                sys.exit(1)

            data = result.get("data", {})
            
            console.print(f"[cyan]{data.get('name', username)}[/cyan]")
            console.print(f"username: {username}")
            console.print(f"profile: {BASE_URL}/users/{username}")
            
            if data.get("bio"):
                console.print(f"\n[dim]{data['bio'][:300]}[/dim]")
            
            if data.get("location"):
                console.print(f"location: {data['location']}")
            
            if data.get("skills"):
                console.print(f"skills: {', '.join(data['skills'][:10])}")
            
            if data.get("links"):
                for k, v in data["links"].items():
                    console.print(f"{k}: {v}")
            
            projects = data.get("projects", [])
            console.print(f"\nprojects: {data.get('project_count', len(projects))}")
            for p in projects[:5]:
                title = p.get('title', 'Unknown')
                console.print(f"  {title}")
                if p.get('hackathon'):
                    console.print(f"    [dim]from {p['hackathon']}[/dim]")
            if len(projects) > 5:
                console.print(f"  [dim]... and {len(projects) - 5} more[/dim]")
            
            hackathons = data.get("hackathons", [])
            console.print(f"\nhackathons: {data.get('hackathon_count', len(hackathons))}")
            for h in hackathons[:5]:
                name = h.get('name', 'Unknown')
                url = h.get('url', '')
                console.print(f"  {name}")
                console.print(f"    [dim]{url}[/dim]")
            if len(hackathons) > 5:
                console.print(f"  [dim]... and {len(hackathons) - 5} more[/dim]")
            
            achievements = data.get("achievements", [])
            console.print(f"\nachievements: {data.get('achievement_count', len(achievements))}")
            for a in achievements[:5]:
                title = a.get('title', 'Unknown')
                console.print(f"  {title}")
                if a.get('earned'):
                    console.print(f"    [dim]earned: {a['earned']}[/dim]")
            if len(achievements) > 5:
                console.print(f"  [dim]... and {len(achievements) - 5} more[/dim]")
            
            followers = data.get("followers", [])
            console.print(f"\nfollowers: {data.get('follower_count', len(followers))}")
            for f in followers[:5]:
                name = f.get('name') or f.get('username', 'Unknown')
                console.print(f"  {name}")
                if f.get('bio'):
                    console.print(f"    [dim]{f['bio'][:100]}[/dim]")
            if len(followers) > 5:
                console.print(f"  [dim]... and {len(followers) - 5} more[/dim]")
            
            following = data.get("following", [])
            console.print(f"\nfollowing: {data.get('following_count', len(following))}")
            for f in following[:5]:
                name = f.get('name') or f.get('username', 'Unknown')
                console.print(f"  {name}")
                if f.get('bio'):
                    console.print(f"    [dim]{f['bio'][:100]}[/dim]")
            if len(following) > 5:
                console.print(f"  [dim]... and {len(following) - 5} more[/dim]")
            
            likes = data.get("likes", [])
            console.print(f"\nlikes: {data.get('like_count', len(likes))}")
            for p in likes[:5]:
                title = p.get('title', 'Unknown')
                console.print(f"  {title}")
                if p.get('tagline'):
                    console.print(f"    [dim]{p['tagline'][:100]}[/dim]")
            if len(likes) > 5:
                console.print(f"  [dim]... and {len(likes) - 5} more[/dim]")

    _run_async(_user())










@cli.command()
@click.argument("slug")
@click.option("--type", "-t", type=click.Choice(["participants", "resources", "updates", "discussions", "winners", "rules"]), required=True, help="Type of data to fetch")
@click.option("--limit", "-l", default=20, help="Number of results (default: 20)")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON")
@click.option("--no-cache", is_flag=True, help="Bypass cache (for rules/winners)")
def get(slug: str, type: str, limit: int, is_json: Optional[bool], no_cache: bool):
    """Get hackathon data.
    
    Unified command for fetching various hackathon data types.
    
    \b
    Examples:
      devpost get hackathon -t participants      # List participants
      devpost get hackathon --type=resources     # List resources
      devpost get hackathon -t updates           # List updates
      devpost get hackathon -t discussions       # List discussions
      devpost get hackathon -t winners           # List winners
      devpost get hackathon -t rules             # Get rules
      devpost get hackathon -t winners --json    # JSON output
    """
    async def _get():
        async with DevpostClient(headed=_cli_config.get("headed", False), use_cache=not no_cache, debug_screenshots=_cli_config.get("debug_screenshots", False)) as client:
            if type == "participants":
                result = await client.get_participants(slug, limit=limit)
                if output_json(result, is_json):
                    return
                if result.get("error"):
                    console.print(f"[red]Error: {result['error']}[/red]")
                    sys.exit(1)
                if not result.get("participants"):
                    console.print("[yellow]No participants found.[/yellow]")
                    return
                console.print(f"[dim]({result['count']} participants)[/dim]")
                for p in result["participants"]:
                    username = p.get("username", "Unknown")[:30]
                    name = p.get("name", "")[:30]
                    url = p.get("url", "")
                    console.print(f"{username}\t{name}\t{url}")
            
            elif type == "resources":
                result = await client.get_resources(slug)
                if output_json(result, is_json):
                    return
                if result.get("error"):
                    console.print(f"[red]Error: {result['error']}[/red]")
                    sys.exit(1)
                if not result.get("resources"):
                    console.print("[yellow]No resources found.[/yellow]")
                    return
                console.print(f"[dim]({len(result['resources'])} resources)[/dim]")
                for r in result["resources"]:
                    title = r.get("title", "Unknown")[:50]
                    url = r.get("url", "")
                    console.print(f"{title}\t{url}")
            
            elif type == "updates":
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
            
            elif type == "discussions":
                result = await client.get_discussions(slug, limit=limit)
                if output_json(result, is_json):
                    return
                if result.get("error"):
                    console.print(f"[red]Error: {result['error']}[/red]")
                    sys.exit(1)
                if not result.get("discussions"):
                    console.print("[yellow]No discussions found.[/yellow]")
                    return
                console.print(f"[dim]({result['count']} discussions)[/dim]")
                for d in result["discussions"]:
                    title = d.get("title", "Untitled")[:40]
                    author = d.get("author", "")[:20] or "N/A"
                    replies = d.get("replies", "") or "0"
                    date = d.get("date", "") or "N/A"
                    console.print(f"{title}\t{author}\t{replies}\t{date}")
            
            elif type == "winners":
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
                console.print(f"[dim]({result['count']} winning projects)[/dim]")
                for w in result["winners"]:
                    title = w.get("title", "Unknown")[:50]
                    prize = w.get("prize", "Winner")
                    url = w.get("url", "N/A")
                    console.print(f"{title}\t{prize}\t{url}")
            
            elif type == "rules":
                result = await client.parse_rules_page(slug)
                if output_json(result, is_json):
                    return
                if not result.get("success"):
                    console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
                    sys.exit(1)
                console.print(f"[cyan]{slug}[/cyan] — Rules\n")
                sections = [
                    ("Eligibility", result.get("eligibility", [])),
                    ("Requirements", result.get("requirements", [])),
                    ("Judging Criteria", result.get("judging_criteria", [])),
                    ("Sponsor APIs / Tech Requirements", result.get("sponsor_apis", [])),
                    ("Key Dates", result.get("key_dates", [])),
                ]
                for label, items in sections:
                    if items:
                        console.print(f"{label}:")
                        for item in items:
                            console.print(f"  - {item[:200]}")
                        console.print("")
                if result.get("prize_categories"):
                    console.print("Prize Categories:")
                    for cat in result["prize_categories"]:
                        console.print(f"  - {cat[:200]}")
                    console.print("")
                if not any([result.get("eligibility"), result.get("requirements"), result.get("judging_criteria"), result.get("sponsor_apis"), result.get("key_dates"), result.get("prize_categories")]):
                    console.print("[dim]No structured rules sections found.[/dim]")
                    console.print(f"[dim]Raw text length: {result.get('raw_text_length', 0)} chars[/dim]")
    
    _run_async(_get())


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
        async with DevpostClient(headed=_cli_config.get("headed", False), use_cache=not no_cache, debug_screenshots=_cli_config.get("debug_screenshots", False)) as client:
            result = await client.evaluate_hackathon(slug, skills=skills_list)

            if output_json(result, is_json):
                return

            if not result.get("success"):
                console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
                sys.exit(1)

            verdict = result.get("verdict", "Maybe")
            reason = result.get("verdict_reason", "")
            
            basics = result.get("basics", {})
            competition = result.get("competition", {})
            signals = result.get("signals", {})

            console.print(f"verdict: {verdict.upper()}")
            console.print(f"reason: {reason}")
            console.print("")
            
            console.print("basics:")
            console.print(f"  title: {basics.get('title', 'Unknown')}")
            console.print(f"  prize: {basics.get('prize', 'N/A')}")
            console.print(f"  status: {basics.get('status', 'unknown')}")
            console.print(f"  dates: {basics.get('dates', 'N/A')}")
            console.print(f"  organization: {basics.get('organization', 'N/A')}")
            console.print(f"  themes: {', '.join(basics.get('themes', [])) or 'N/A'}")
            console.print("")
            
            console.print("competition:")
            console.print(f"  registrants: {competition.get('registrants', 'N/A')}")
            console.print(f"  submissions: {competition.get('submissions', 'N/A')}")
            console.print(f"  prize_per_project: ${competition.get('prize_per_project', 0):,.0f}")
            console.print(f"  registrants_per_prize: {competition.get('registrants_per_prize', 0):.0f}")
            console.print("")

            for label, key in [
                ("eligibility", "eligibility"),
                ("requirements", "requirements"),
                ("judging_criteria", "judging_criteria"),
                ("sponsor_apis", "sponsor_apis"),
                ("prize_categories", "prize_categories"),
                ("key_dates", "key_dates"),
            ]:
                if result.get(key):
                    console.print(f"{label}:")
                    for item in result[key][:5]:
                        console.print(f"  - {item[:150]}")
                    console.print("")

            console.print("signals:")
            for name, sig in signals.items():
                level = sig.get("level", "unknown")
                detail = sig.get("detail", "")
                console.print(f"  {name.replace('_', ' ')}: {level} — {detail}")

            if result.get("errors"):
                console.print(f"\n[dim]errors: {'; '.join(result['errors'])}[/dim]")

    _run_async(_evaluate())


@cli.command()
@click.argument("query")
@click.option("--in", "hackathon", help="Search within a specific hackathon (slug)")
@click.option("--limit", "-l", default=20, help="Number of results (default: 20)")
@click.option("--sort", type=click.Choice(["newest", "popular", "trending"]), default="newest", help="Sort order")
@click.option("--winner", is_flag=True, help="Winners only (is:winner)")
@click.option("--featured", is_flag=True, help="Staff picks only (is:featured)")
@click.option("--has-video", is_flag=True, help="Projects with video (has:video)")
@click.option("--has-image", is_flag=True, help="Projects with images (has:image)")
@click.option("--by-user", help="By username (@username)")
@click.option("--at", "at_hackathon", help="From hackathon (at:\"hackathon\")")
@click.option("--winners", is_flag=True, help="In-hackathon: search only winning projects")
@click.option("--tech", is_flag=True, help="In-hackathon: search only tech stacks")
@click.option("--include-rules", is_flag=True, help="In-hackathon: also search hackathon description and rules")
@click.option("--no-cache", is_flag=True, help="Bypass cache, fetch fresh data")
@click.option("--playwright", is_flag=True, help="Use browser automation (bypasses WAF, slower but reliable)")
@click.option("--across", is_flag=True, help="Search across multiple hackathons (not just global search)")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def search(
    query: str,
    hackathon: Optional[str],
    limit: int,
    sort: str,
    winner: bool,
    featured: bool,
    has_video: bool,
    has_image: bool,
    by_user: Optional[str],
    at_hackathon: Optional[str],
    winners: bool,
    tech: bool,
    include_rules: bool,
    no_cache: bool,
    playwright: bool,
    across: bool,
    is_json: Optional[bool],
):
    """Search projects on Devpost.
    
    \b
    Global project search (all Devpost):
      devpost search "AI"                          # Search all projects
      devpost search "chatbot" -l 30               # More results
      devpost search "AI" --sort popular           # Sort by popularity
      devpost search "AI" --playwright             # Use browser (bypasses WAF)
      devpost search "AI" --winner --has-video     # Winners with video
    
    \b
    Advanced operators (type directly in query):
      is:winner, is:featured, has:video, has:image
      @username, at:"hackathon name", #python
    
    \b
    In-hackathon search:
      devpost search "RAG" --in medo               # Search projects in MeDo
      devpost search "agent" --in medo --winners   # Only winners
      devpost search "OpenAI" --in medo --tech     # Search tech stacks
    
    \b
    Cross-hackathon search:
      devpost search "AI" --across                 # Search across open hackathons
    
    For hackathon search, use: devpost hackathons --query "AI"
    """
    use_cache = not no_cache

    if hackathon:
        _search_in_hackathon(
            query, hackathon, winners, tech, include_rules,
            use_cache, is_json,
        )
    elif across:
        _search_projects_across(
            query, limit, use_cache, playwright, is_json,
        )
    else:
        _search_projects_global(
            query, limit, sort, winner, featured, has_video, has_image,
            by_user, at_hackathon, use_cache, playwright, is_json,
        )


def _search_projects_across(
    query: str,
    limit: int,
    use_cache: bool,
    playwright: bool,
    is_json: Optional[bool],
):
    """Search projects across multiple hackathons."""
    async def _run():
        async with DevpostClient(headed=_cli_config.get("headed", False), use_cache=use_cache, debug_screenshots=_cli_config.get("debug_screenshots", False)) as client:
            projects = await client.search_projects_across_hackathons(
                query=query,
                hackathon_states=["open", "upcoming"],
                limit=limit,
                max_hackathons=20,
            )

            if output_json(projects, is_json):
                return

            if not projects:
                console.print(f"[yellow]No projects found for '{query}' across hackathons[/yellow]")
                return

            console.print(f"[green]Found {len(projects)} projects for '{query}' across hackathons:[/green]\n")

            for p in projects:
                title = p.get('title', 'Unknown')
                tagline = p.get('tagline') or ''
                winner_badge = " [yellow]★ WINNER[/yellow]" if p.get("is_winner") else ""
                hackathon = p.get("hackathon", {})
                hack_name = hackathon.get("name", "Unknown")
                console.print(f"[cyan]{title}{winner_badge}[/cyan]")
                if tagline:
                    console.print(f"  [dim]{tagline[:100]}[/dim]")
                if p.get("built_with"):
                    console.print(f"  [dim]Built with: {', '.join(p['built_with'][:5])}[/dim]")
                console.print(f"  [dim]Hackathon: {hack_name}[/dim]")
                console.print(f"  [dim]{p.get('url', '')}[/dim]")
                console.print("")

    _run_async(_run())


def _search_projects_global(
    query: str,
    limit: int,
    sort: str,
    winner: bool,
    featured: bool,
    has_video: bool,
    has_image: bool,
    by_user: Optional[str],
    at_hackathon: Optional[str],
    use_cache: bool,
    playwright: bool,
    is_json: Optional[bool],
):
    async def _run():
        full_query = query

        operators = []
        if winner:
            operators.append("is:winner")
        if featured:
            operators.append("is:featured")
        if has_video:
            operators.append("has:video")
        if has_image:
            operators.append("has:image")
        if by_user:
            operators.append(f"@{by_user}")
        if at_hackathon:
            operators.append(f'at:"{at_hackathon}"')

        if operators:
            full_query = f"{query} {' '.join(operators)}"

        async with DevpostClient(headed=_cli_config.get("headed", False), use_cache=use_cache, debug_screenshots=_cli_config.get("debug_screenshots", False)) as client:
            projects = await client.search_projects(
                query=full_query,
                limit=limit,
                order_by=sort if sort != "newest" else None,
                use_playwright=playwright,
            )

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
        async with DevpostClient(headed=_cli_config.get("headed", False), use_cache=use_cache, debug_screenshots=_cli_config.get("debug_screenshots", False)) as client:
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
@click.argument("query")
@click.option("--limit", "-l", default=20, help="Number of results (default: 20)")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON (auto-detected if stdout is not a TTY)")
def search_users(query: str, limit: int, is_json: Optional[bool]):
    """Search for users on Devpost.
    
    Searches usernames and names from hackathon participant lists.
    For detailed user info, use: devpost user <username>
    
    \b
    Examples:
      devpost search-users "john"              # Search for users named john
      devpost search-users "python" -l 30      # Find Python developers
      devpost search-users "AI" --json
    """
    async def _search():
        async with DevpostClient(headed=_cli_config.get("headed", False), debug_screenshots=_cli_config.get("debug_screenshots", False)) as client:
            users = await client.search_users(query=query, limit=limit)

            if output_json(users, is_json):
                return

            if not users:
                console.print(f"[yellow]No users found for '{query}'[/yellow]")
                return

            console.print(f"[green]Found {len(users)} users for '{query}':[/green]\n")

            for u in users:
                username = u.get('username', 'Unknown')
                name = u.get('name', '')
                url = u.get('url', '')
                console.print(f"[cyan]{username}[/cyan]")
                if name and name != username:
                    console.print(f"  [dim]{name}[/dim]")
                console.print(f"  [dim]{url}[/dim]")
                console.print("")

    _run_async(_search())




@cli.command()
@click.argument("slug")
@click.option("--section", "-s", type=click.Choice(["dates", "eligibility", "requirements", "judging", "prizes", "faq", "all"]), default="all", help="Specific section to view (default: all)")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON")
def details(slug: str, section: str, is_json: Optional[bool]):
    """View hackathon details.
    
    Shows all sections by default, or use --section to view a specific section.
    
    \b
    Examples:
      devpost details hackathon                  # All sections
      devpost details hackathon -s eligibility   # Eligibility only
      devpost details hackathon --section=prizes
      devpost details hackathon --json
    """
    async def _show():
        async with DevpostClient(headed=_cli_config.get("headed", False), debug_screenshots=_cli_config.get("debug_screenshots", False)) as client:
            if section in ("all", "dates"):
                hackathon = await client.get_hackathon_by_slug(slug)
                if not hackathon:
                    if output_json({"error": f"Hackathon '{slug}' not found", "code": "NOT_FOUND"}, is_json):
                        sys.exit(3)
                    console.print(f"[red]Hackathon '{slug}' not found.[/red]")
                    sys.exit(3)
                
                dates_info = hackathon.get("submission_period_dates", "No dates available")
                time_left = hackathon.get("time_left_to_submission", "")
                
                if section == "dates":
                    result = {"slug": slug, "title": hackathon.get("title"), "dates": dates_info, "time_left": time_left}
                    if output_json(result, is_json):
                        return
                    console.print(f"[cyan]{hackathon.get('title', slug)}[/cyan]")
                    console.print(f"dates: {dates_info}")
                    console.print(f"time_left: {time_left or 'N/A'}")
            
            if section in ("all", "eligibility", "requirements", "judging", "prizes"):
                rules = await client.parse_rules_page(slug)
                
                if section == "eligibility":
                    if output_json(rules, is_json):
                        return
                    eligibility = rules.get("eligibility", [])
                    if not eligibility:
                        console.print("[yellow]No eligibility rules found.[/yellow]")
                        return
                    console.print(f"[cyan]{slug}[/cyan] — Eligibility\n")
                    for item in eligibility[:10]:
                        console.print(f"  - {item[:200]}")
                
                elif section == "requirements":
                    if output_json(rules, is_json):
                        return
                    requirements = rules.get("requirements", [])
                    if not requirements:
                        console.print("[yellow]No requirements found.[/yellow]")
                        return
                    console.print(f"[cyan]{slug}[/cyan] — Requirements\n")
                    for item in requirements[:10]:
                        console.print(f"  - {item[:200]}")
                
                elif section == "judging":
                    if output_json(rules, is_json):
                        return
                    judging = rules.get("judging_criteria", [])
                    if not judging:
                        console.print("[yellow]No judging criteria found.[/yellow]")
                        return
                    console.print(f"[cyan]{slug}[/cyan] — Judging Criteria\n")
                    for item in judging[:10]:
                        console.print(f"  - {item[:200]}")
                
                elif section == "prizes":
                    if output_json(rules, is_json):
                        return
                    prizes = rules.get("prize_categories", [])
                    if not prizes:
                        hackathon = await client.get_hackathon_by_slug(slug)
                        prize_amount = hackathon.get("prize_amount", "N/A") if hackathon else "N/A"
                        console.print(f"[yellow]No detailed prize breakdown found. Total: {prize_amount}[/yellow]")
                        return
                    console.print(f"[cyan]{slug}[/cyan] — Prizes\n")
                    for item in prizes[:15]:
                        console.print(f"  - {item[:200]}")
            
            if section in ("all", "faq"):
                from httpx import AsyncClient
                client_http = AsyncClient(headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html",
                }, follow_redirects=True)
                
                try:
                    resp = await client_http.get(f"https://{slug}.devpost.com/details/faq")
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "html.parser")
                    
                    faq_items = []
                    for elem in soup.find_all(['div', 'section', 'article'], class_=re.compile(r'faq|question|answer|qa', re.I)):
                        text = elem.get_text(strip=True)
                        if text and len(text) > 20:
                            faq_items.append(text[:500])
                    
                    help_links = []
                    for a in soup.find_all('a', href=re.compile(r'help\.devpost\.com', re.I)):
                        href = a.get('href', '')
                        if href and href not in help_links:
                            help_links.append(href)
                    
                    if section == "faq":
                        result = {"slug": slug, "faq_items": faq_items[:10], "help_links": help_links}
                        if output_json(result, is_json):
                            return
                        if faq_items:
                            console.print(f"[cyan]{slug}[/cyan] — FAQ\n")
                            for item in faq_items[:5]:
                                console.print(f"  {item[:300]}\n")
                        elif help_links:
                            console.print(f"[yellow]No hackathon-specific FAQ found. Check the Devpost Help Desk:[/yellow]")
                            for link in help_links[:2]:
                                console.print(f"  {link}")
                        else:
                            console.print("[yellow]No FAQ content found.[/yellow]")
                            console.print("  Check: https://help.devpost.com/")
                finally:
                    await client_http.aclose()
    
    _run_async(_show())


@cli.command()
@click.option("--popular", is_flag=True, help="Show popular themes with active counts")
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON")
def themes(popular: bool, is_json: Optional[bool]):
    """List all Devpost hackathon themes.
    
    \b
    Examples:
      devpost themes                         # All 29 themes
      devpost themes --popular               # Popular themes with counts
      devpost themes --json                  # JSON output
    """
    async def _themes():
        async with DevpostClient(headed=_cli_config.get("headed", False), debug_screenshots=_cli_config.get("debug_screenshots", False)) as client:
            themes_list = await client.get_themes(popular=popular)
            
            if output_json(themes_list, is_json):
                return
            
            if not themes_list:
                console.print("[yellow]No themes found.[/yellow]")
                return
            
            if popular:
                console.print("(Popular Themes)")
                for t in themes_list:
                    name = t.get("name", "Unknown")
                    count = t.get("active_count", 0)
                    prize = t.get("total_prize", "N/A")
                    console.print(f"{name}\t{count}\t{prize}")
            else:
                for i, t in enumerate(themes_list, 1):
                    console.print(f"{i:2}. {t.get('name', 'Unknown')}")
    
    _run_async(_themes())


@cli.command()
@click.option("--json", "is_json", flag_value=True, default=None, help="Output as JSON")
def trending(is_json: Optional[bool]):
    """List trending technology tags on Devpost.
    
    Shows the most popular technologies used in projects.
    
    \b
    Examples:
      devpost trending                       # All trending tech
      devpost trending --json                # JSON output
    """
    async def _trending():
        async with DevpostClient(headed=_cli_config.get("headed", False), debug_screenshots=_cli_config.get("debug_screenshots", False)) as client:
            technologies = await client.get_trending_technologies()
            
            if output_json(technologies, is_json):
                return
            
            if not technologies:
                console.print("[yellow]No trending technologies found.[/yellow]")
                return
            
            for i, tech in enumerate(technologies, 1):
                console.print(f"{i:2}. {tech}")
    
    _run_async(_trending())









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

            console.print(f"[dim]({len(result['submissions'])} submissions)[/dim]")
            for p in result["submissions"]:
                title = p.get("title", "Unknown")
                url = p.get("url", "N/A")
                console.print(f"{title}\t{url}")

    _run_async(_list())


@cli.command()
@click.argument("hackathon_slug")
@click.option("--title", "-t", required=True, help="Project title")
@click.option("--tagline", required=True, help="Short description (max 140 chars)")
@click.option("--description", "-d", help="Full project description (markdown)")
@click.option("--description-file", help="Path to markdown file for description")
@click.option("--built-with", "-b", help="Comma-separated technologies")
@click.option("--github", help="GitHub repository URL")
@click.option("--demo", help="Live demo URL")
@click.option("--video", help="Demo video URL")
@click.option("--dry-run", is_flag=True, help="Test without actually submitting")
def submit(hackathon_slug: str, title: str, tagline: str, description: Optional[str],
           description_file: Optional[str], built_with: Optional[str], github: Optional[str],
           demo: Optional[str], video: Optional[str], dry_run: bool):
    """Submit a new project to a hackathon.
    
    Requires authentication. Always test with --dry-run first!
    
    \b
    Examples:
      devpost submit rapid-agent -t "My Project" --tagline "AI-powered solution"
      devpost submit rapid-agent -t "Demo" --tagline "Cool demo" --dry-run
      devpost submit rapid-agent -t "Project" --tagline "Tagline" \\
        --github "https://github.com/user/repo" \\
        --demo "https://demo.example.com"
    """
    async def _submit():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            console.print(f"[red]Error: {e.message}[/red]")
            console.print("Set credentials with: devpost auth login")
            sys.exit(1)

        # Process description from file if specified
        final_description = description
        if description_file:
            try:
                from pathlib import Path
                final_description = Path(description_file).read_text(encoding='utf-8')
                console.print(f"[dim]Loaded description from {description_file}[/dim]")
            except FileNotFoundError:
                console.print(f"[red]Error: Description file not found: {description_file}[/red]")
                sys.exit(1)

        if not final_description:
            console.print("[red]Error: --description or --description-file is required[/red]")
            sys.exit(1)

        tech_list = [t.strip() for t in built_with.split(",")] if built_with else None

        links = {}
        if github:
            links["github"] = github
        if demo:
            links["demo"] = demo
        if video:
            links["video"] = video

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            result = await client.submit_project(
                hackathon_slug=hackathon_slug,
                title=title,
                tagline=tagline,
                description=final_description,
                built_with=tech_list,
                links=links if links else None,
                image_paths=None,
                dry_run=dry_run,
            )

            if result.get("error"):
                console.print(f"[red]Error:[/red] {result['error']}")
                sys.exit(1)

            if dry_run:
                console.print(f"[yellow]=== DRY RUN - No changes made ===[/yellow]")
                console.print(f"\n[bold]Would submit to:[/bold] {hackathon_slug}")
                console.print(f"[bold]Project title:[/bold] {title}")
                console.print(f"[bold]Tagline:[/bold] {tagline}")
                if tech_list:
                    console.print(f"[bold]Built with:[/bold] {', '.join(tech_list)}")
                if links:
                    console.print(f"[bold]Links:[/bold]")
                    for k, v in links.items():
                        console.print(f"  {k}: {v}")
            else:
                console.print(f"\n[green]✓ Successfully submitted![/green]")
                console.print(f"\n[bold]Project Details:[/bold]")
                console.print(f"  url: {result.get('url', 'N/A')}")
                console.print(f"  title: {result['project_title']}")

    _run_async(_submit())



@cli.command()
@click.argument("project_url")
@click.option("--title", "-t", help="New title")
@click.option("--tagline", "-tag", help="New tagline")
@click.option("--description", "-d", help="New description (markdown)")
@click.option("--description-file", help="Path to markdown file for description")
@click.option("--built-with", "-b", help="Comma-separated technologies")
@click.option("--github", help="GitHub URL")
@click.option("--demo", help="Demo URL")
@click.option("--video", help="Video URL")
@click.option("--dry-run", is_flag=True, help="Test without saving")
def update(project_url: str, title: Optional[str], tagline: Optional[str], description: Optional[str],
           description_file: Optional[str], built_with: Optional[str], github: Optional[str], demo: Optional[str], video: Optional[str], dry_run: bool):
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

        if not any([title, tagline, description, description_file, built_with, github, demo, video]):
            console.print("[red]Error: No fields to update specified. Use --title, --tagline, --github, etc.[/red]")
            sys.exit(1)

        # Process description from file if specified
        final_description = description
        if description_file:
            try:
                from pathlib import Path
                final_description = Path(description_file).read_text(encoding='utf-8')
                console.print(f"[dim]Loaded description from {description_file}[/dim]")
            except FileNotFoundError:
                console.print(f"[red]Error: Description file not found: {description_file}[/red]")
                sys.exit(1)

        tech_list = [t.strip() for t in built_with.split(",")] if built_with else None

        links = {}
        if github:
            links["github"] = github
        if demo:
            links["demo"] = demo
        if video:
            links["video"] = video

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            result = await client.update_submission(
                project_url=project_url,
                title=title,
                tagline=tagline,
                description=final_description,
                built_with=tech_list,
                links=links if links else None,
                image_paths=None,
                dry_run=dry_run,
            )

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            if dry_run:
                console.print(f"[yellow]DRY RUN[/yellow]")
                console.print(f"project: {result['url']}")
                console.print(f"fields: {', '.join(result['updated_fields'])}")
            else:
                console.print(f"[green]Successfully updated![/green]")
                console.print(f"updated: {', '.join(result['updated_fields'])}")
                if result.get("uploaded_images"):
                    console.print(f"[green]Uploaded {len(result['uploaded_images'])} image(s)[/green]")

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
            console.print(f"[cyan]{details.get('title', 'Unknown')}[/cyan]")
            console.print(f"tagline: {details.get('tagline', 'N/A')}")
            console.print(f"description: {details.get('description', 'N/A')[:200]}")
            console.print(f"built_with: {', '.join(details.get('built_with', [])) or 'N/A'}")
            team_str = ', '.join([m['username'] for m in details.get('team_members', [])]) or 'Solo'
            console.print(f"team: {team_str}")
            console.print(f"url: {result.get('url', 'N/A')}")

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
@click.option("--verbose", "-v", is_flag=True, help="Show detailed steps")
def team_add(project_url: str, username: str, verbose: bool):
    """Add a team member to a project.
    
    \b
    Examples:
      devpost team add https://devpost.com/software/myproj alice
      devpost team add https://devpost.com/software/myproj bob@example.com
      devpost team add https://... alice --verbose
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

            console.print(f"[green]{result['message']}[/green]")
            console.print(f"project: {project_url}")
            console.print(f"user: {username}")
            
            if verbose and result.get("steps"):
                console.print(f"\n[dim]Steps:[/dim]")
                for step in result["steps"]:
                    console.print(f"  {step}")

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

            console.print(f"[green]{result['message']}[/green]")
            console.print(f"project: {project_url}")
            console.print(f"user: {username}")

    _run_async(_remove())


@team.command(name="create")
@click.argument("hackathon_slug")
@click.option("--name", "-n", required=True, help="Team name")
@click.option("--invite", help="Comma-separated usernames to invite")
@click.option("--invite-email", "--invite-emails", help="Comma-separated email addresses to invite (if Devpost UI supports email invites)")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed invite status")
def team_create(hackathon_slug: str, name: str, invite: Optional[str], invite_email: Optional[str], verbose: bool):
    """Create a team for a hackathon.
    
    Supports inviting by Devpost username or email address (if Devpost UI allows).
    
    \b
    Examples:
      devpost team create zervehack --name "Team Awesome"
      devpost team create zervehack -n "My Team" --invite "alice,bob"
      devpost team create zervehack -n "Team" --invite-email "alice@example.com,bob@example.com"
      devpost team create zervehack -n "Team" --invite "alice" --invite-email "bob@example.com" --verbose
    """
    async def _create():
        try:
            email, password = AuthenticatedClient.get_credentials()
        except DevpostError as e:
            console.print(f"[red]Error: {e.message}[/red]")
            sys.exit(1)

        invite_list = [u.strip() for u in invite.split(",")] if invite else None
        invite_email_list = [e.strip() for e in invite_email.split(",")] if invite_email else None

        async with AuthenticatedClient(email=email, password=password, headed=_cli_config.get("headed", False)) as client:
            result = await client.create_team(hackathon_slug, name, invite_list, invite_email_list)

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            console.print(f"[green]{result['message']}[/green]")
            console.print(f"hackathon: {hackathon_slug}")
            console.print(f"team: {name}")
            
            if result.get("team_url"):
                console.print(f"url: {result['team_url']}")
            
            if result.get("invites_sent"):
                console.print(f"\n[yellow]Invites sent ({len(result['invites_sent'])}):[/yellow]")
                for invitee in result["invites_sent"]:
                    invite_type = "email" if "@" in invitee else "username"
                    console.print(f"  ✓ {invitee} ({invite_type})")
            
            if result.get("invites_failed"):
                console.print(f"\n[red]Invites failed ({len(result['invites_failed'])}):[/red]")
                for invitee in result["invites_failed"]:
                    invite_type = "email" if "@" in invitee else "username"
                    console.print(f"  ✗ {invitee} ({invite_type})")
            
            if verbose and result.get("steps"):
                console.print(f"\n[dim]Steps:[/dim]")
                for step in result["steps"]:
                    console.print(f"  {step}")

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

            console.print(f"[green]{result['message']}[/green]")
            console.print(f"hackathon: {hackathon_slug}")

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
                console.print(f"[green]Uploaded {len(result['uploaded'])} images[/green]")
                for p in result["uploaded"]:
                    console.print(f"  {p}")
                if result.get("failed"):
                    console.print(f"\n[yellow]Failed:[/yellow]")
                    for f in result["failed"]:
                        console.print(f"  {f['path']}: {f['reason']}")

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
                console.print(f"[yellow]Confirmation required[/yellow]")
                console.print(f"{result.get('message', 'Confirmation required to delete this project.')}")
                console.print(f"\nRun with --confirm to delete: devpost delete {project_url} --confirm")
                sys.exit(0)

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            console.print(f"[green]{result['message']}[/green]")
            console.print(f"project: {project_url}")

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

            console.print(f"[green]{result['data']['message']}[/green]")
            console.print(f"hackathon: {hackathon_slug}")

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
                console.print(f"[yellow]Confirmation required[/yellow]")
                console.print(f"{result.get('error', 'Confirmation required to leave this hackathon.')}")
                console.print(f"\nRun with --confirm to leave: devpost leave {hackathon_slug} --confirm")
                return

            if result.get("error"):
                console.print(f"[red]Error: {result['error']}[/red]")
                sys.exit(1)

            console.print(f"[green]{result['data']['message']}[/green]")
            console.print(f"hackathon: {hackathon_slug}")

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

            console.print(f"[green]{result['data']['message']}[/green]")
            console.print(f"project: {project_url}")

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
                console.print(f"[yellow]DRY RUN[/yellow]")
                for k, v in link_updates.items():
                    console.print(f"  {k}: {v}")
            else:
                console.print(f"[green]Links updated[/green]")
                for k, v in link_updates.items():
                    console.print(f"  {k}: {v}")

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
@click.option("--method", "-m",
    type=click.Choice(["password", "github", "google", "facebook", "linkedin"]),
    default="password",
    help="Login method (default: password). OAuth methods open browser for authentication.")
@click.option("--email", "-e", help="Email address (password method only, non-interactive mode)")
def login(method: str, email: Optional[str]):
    """Authentication setup.
    
    Password mode (default): Prompts for email and password.
    OAuth mode (github/google/facebook/linkedin): Opens browser for OAuth authentication.
    
    \b
    Examples:
      devpost auth login                          # Password mode (interactive)
      devpost auth login -e user@example.com      # Password mode (email pre-filled)
      devpost auth login --method github          # OAuth via GitHub
      devpost auth login --method google          # OAuth via Google
      devpost auth login -m linkedin              # OAuth via LinkedIn
    """
    if method == "password":
        password = None
        if email is not None:
            password = click.prompt("Devpost password", type=str, hide_input=True)
        else:
            email = click.prompt("Devpost email", type=str)
            password = click.prompt("Devpost password", type=str, hide_input=True)
        _do_login(email, password, auth_method="password")
    else:
        # OAuth login
        _do_oauth_login(method)


@auth.command()
def logout():
    """Clear saved credentials and session.
    
    Removes ~/.devpost/.env and any cached session cookies.
    
    \b
    Examples:
      devpost auth logout
    """
    _do_logout()


def _do_login(email: Optional[str], password: Optional[str], auth_method: str = "password") -> None:
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
            console.print(f"[green]Successfully authenticated![/green]")
            console.print(f"email: {email}")
            console.print(f"[dim]Credentials saved to ~/.devpost/.env[/dim]")
        else:
            error_msg = result.get('error', 'Unknown error')
            if output_json({"success": False, "error": error_msg}, None):
                sys.exit(2)
            console.print(f"[red]Authentication failed:[/red] {error_msg}")
            sys.exit(2)

    _run_async(_login())


def _do_oauth_login(method: str) -> None:
    """Internal OAuth login logic for github/google/facebook/linkedin."""
    provider_names = {
        "github": "GitHub",
        "google": "Google",
        "facebook": "Facebook",
        "linkedin": "LinkedIn",
    }
    provider_name = provider_names.get(method, method)
    
    console.print(f"[dim]Opening browser for {provider_name} authentication...[/dim]")
    console.print(f"[yellow]Note: OAuth login requires a visible browser window.[/yellow]")
    console.print(f"[dim]You will be redirected to {provider_name} to authenticate.[/dim]")
    console.print("")

    async def _oauth_login():
        try:
            from .core import AuthenticatedClient
            # Force headed mode for OAuth
            client = AuthenticatedClient(auth_method=method, headed=True)
            async with client:
                # This will trigger the OAuth flow in _get_browser_and_page()
                await client._get_browser_and_page()
            
            # Load the session to get the email
            from .session import load_session
            session = load_session()
            email = session.get("email", "oauth-user") if session else "oauth-user"
            
            if output_json({"success": True, "email": email, "auth_method": method}, None):
                return
            console.print(f"[green]Successfully authenticated via {provider_name}![/green]")
            console.print(f"email: {email}")
            console.print(f"method: {method}")
            console.print(f"[dim]Session saved to ~/.devpost/session.json[/dim]")
        except Exception as e:
            error_msg = str(e)
            if output_json({"success": False, "error": error_msg}, None):
                sys.exit(2)
            console.print(f"[red]OAuth login failed:[/red] {error_msg}")
            sys.exit(2)

    _run_async(_oauth_login())


def _do_logout() -> None:
    """Internal logout logic."""
    async def _logout():
        result = await clear_credentials()
        if output_json(result, None):
            return
        console.print(f"[green]{result['message']}[/green]")

    _run_async(_logout())


def _do_status() -> None:
    """Internal status logic."""
    from .session import get_auth_method
    
    creds = get_credentials()
    auth_method = get_auth_method()
    
    if creds:
        email, password = creds
        data = {
            "authenticated": True,
            "email": email,
            "password_set": bool(password),
            "auth_method": auth_method or "password",
        }
        if output_json(data, None):
            return
        console.print(f"[green]Authenticated as:[/green] {email}")
        console.print(f"method: {auth_method or 'password'}")
        if auth_method == "password":
            console.print("[dim]Password is configured[/dim]" if password else "[red]Password is NOT set[/red]")
        else:
            console.print("[dim]OAuth session (no password stored)[/dim]")
    else:
        data = {"authenticated": False}
        if output_json(data, None):
            return
        console.print("[yellow]Not authenticated. Set env vars or use 'devpost auth login'[/yellow]")
        console.print("  export DEVPOST_EMAIL='your@email.com'")
        console.print("  export DEVPOST_PASSWORD='your_password'")





def main():
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
