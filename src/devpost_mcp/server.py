"""MCP server for Devpost hackathons."""

import asyncio
import json
import re
import os
from typing import Any

import httpx
from bs4 import BeautifulSoup
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

BASE_URL = "https://devpost.com"
API_BASE = "https://devpost.com/api"

# Browser automation for submissions (requires DEVPOST_EMAIL and DEVPOST_PASSWORD env vars)


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

    async def list_hackathons(
        self,
        limit: int = 20,
        open_state: str | None = None,
        sort_by: str = "recently-added",
        query: str | None = None,
    ) -> list[dict]:
        """List hackathons via API."""
        params: dict[str, Any] = {"limit": limit, "sort_by": sort_by}
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

    async def get_hackathon_by_url(self, url_slug: str) -> dict | None:
        """Get hackathon by URL slug."""
        resp = await self.client.get(
            f"{API_BASE}/hackathons",
            params={"url": url_slug, "limit": 1},
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        hackathons = data.get("hackathons", [])
        return hackathons[0] if hackathons else None

    async def get_hackathon_details(self, hackathon_url: str) -> dict[str, Any]:
        """Scrape detailed hackathon info from its page."""
        resp = await self.client.get(hackathon_url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract from meta tags
        title = self._get_meta(soup, "og:title") or self._get_meta(soup, "twitter:title")
        description = (
            self._get_meta(soup, "og:description")
            or self._get_meta(soup, "description")
            or self._get_meta(soup, "twitter:description")
        )
        image = self._get_meta(soup, "og:image")

        # Try to find rules/requirements from page content
        rules_url = f"{hackathon_url.rstrip('/')}/rules" if not hackathon_url.endswith("/rules") else hackathon_url
        
        return {
            "title": title,
            "description": description,
            "image_url": image,
            "url": hackathon_url,
            "rules_url": rules_url,
        }

    def _get_meta(self, soup: BeautifulSoup, property_name: str) -> str | None:
        """Get meta tag content by property or name."""
        tag = soup.find("meta", property=property_name) or soup.find("meta", attrs={"name": property_name})
        return tag.get("content") if tag else None

    async def close(self) -> None:
        await self.client.aclose()


# MCP Server
app = Server("devpost-mcp")
client = DevpostClient()


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_hackathons",
            description="List hackathons on Devpost. Filter by open state, sort order, or search query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of hackathons to return (default: 20)",
                        "default": 20,
                    },
                    "open_state": {
                        "type": "string",
                        "description": "Filter by state: 'open', 'closed', 'upcoming', 'judging', 'submitting'",
                        "enum": ["open", "closed", "upcoming", "judging", "submitting"],
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Sort order",
                        "enum": ["recently-added", "submission-deadline", "prize-amount", "popularity"],
                        "default": "recently-added",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query string",
                    },
                },
            },
        ),
        Tool(
            name="search_hackathons",
            description="Search hackathons by keyword or URL slug",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'AI', 'blockchain', 'healthcare')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of results (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_hackathon_by_url",
            description="Get hackathon details by its URL slug (e.g., 'zervehack' from zervehack.devpost.com)",
            inputSchema={
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "URL slug of the hackathon (e.g., 'zervehack', 'agents-assemble')",
                    },
                },
                "required": ["slug"],
            },
        ),
        Tool(
            name="get_hackathon_details",
            description="Get full details for a hackathon by scraping its page. Returns description, rules URL, and metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full hackathon URL (e.g., https://zervehack.devpost.com/)",
                    },
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="scrape_hackathon_page",
            description="SCRAPE any hackathon page directly by URL. Works for active AND past/closed hackathons that the API doesn't return. Use this when searching for historical hackathons.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full hackathon URL (e.g., https://datahacks-2025.devpost.com/, https://hackathon-name.devpost.com/)",
                    },
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="submit_project",
            description="SUBMIT a project to a hackathon. Requires DEVPOST_EMAIL and DEVPOST_PASSWORD env vars. Uses browser automation to log in and submit.",
            inputSchema={
                "type": "object",
                "properties": {
                    "hackathon_slug": {
                        "type": "string",
                        "description": "Hackathon URL slug (e.g., 'zervehack' from zervehack.devpost.com)",
                    },
                    "project_title": {
                        "type": "string",
                        "description": "Title of your project",
                    },
                    "project_tagline": {
                        "type": "string",
                        "description": "Short tagline/description (max 140 chars)",
                    },
                    "project_description": {
                        "type": "string",
                        "description": "Full project description with markdown support",
                    },
                    "built_with": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of technologies/languages used (e.g., ['Python', 'React', 'OpenAI'])",
                    },
                    "links": {
                        "type": "object",
                        "properties": {
                            "github": {"type": "string"},
                            "demo": {"type": "string"},
                            "video": {"type": "string"},
                            "website": {"type": "string"},
                        },
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, only validates the form without actually submitting",
                        "default": False,
                    },
                },
                "required": ["hackathon_slug", "project_title", "project_tagline"],
            },
        ),
        Tool(
            name="list_my_submissions",
            description="List all projects you've submitted to hackathons. Returns titles, URLs, and hackathon info.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of submissions to return",
                        "default": 20,
                    },
                },
            },
        ),
        Tool(
            name="get_submission_details",
            description="Get detailed info about a specific project submission including title, tagline, description, links, and team members.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_url": {
                        "type": "string",
                        "description": "Full URL to the project (e.g., https://devpost.com/software/my-project)",
                    },
                },
                "required": ["project_url"],
            },
        ),
        Tool(
            name="update_submission",
            description="UPDATE an existing project submission. Modify title, tagline, description, tech stack, or links.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_url": {
                        "type": "string",
                        "description": "Full URL to the project to update",
                    },
                    "project_title": {
                        "type": "string",
                        "description": "New title (omit to keep current)",
                    },
                    "project_tagline": {
                        "type": "string",
                        "description": "New tagline (omit to keep current)",
                    },
                    "project_description": {
                        "type": "string",
                        "description": "New description (omit to keep current)",
                    },
                    "built_with": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New tech stack (omit to keep current)",
                    },
                    "links": {
                        "type": "object",
                        "properties": {
                            "github": {"type": "string"},
                            "demo": {"type": "string"},
                            "video": {"type": "string"},
                            "website": {"type": "string"},
                        },
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "Test the update without saving",
                        "default": False,
                    },
                },
                "required": ["project_url"],
            },
        ),
        Tool(
            name="add_team_member",
            description="Add a team member to your project by their Devpost username or email.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_url": {
                        "type": "string",
                        "description": "URL of the project to add member to",
                    },
                    "username": {
                        "type": "string",
                        "description": "Devpost username or email of the person to add",
                    },
                },
                "required": ["project_url", "username"],
            },
        ),
        Tool(
            name="remove_team_member",
            description="Remove a team member from your project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_url": {
                        "type": "string",
                        "description": "URL of the project",
                    },
                    "username": {
                        "type": "string",
                        "description": "Username of the person to remove",
                    },
                },
                "required": ["project_url", "username"],
            },
        ),
        Tool(
            name="delete_submission",
            description="DELETE a project submission permanently. This cannot be undone!",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_url": {
                        "type": "string",
                        "description": "URL of the project to delete",
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "Must be true to actually delete",
                        "default": False,
                    },
                },
                "required": ["project_url"],
            },
        ),
        Tool(
            name="upload_screenshots",
            description="Upload screenshots/images to a project. Provide file paths to local images.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_url": {
                        "type": "string",
                        "description": "URL of the project",
                    },
                    "image_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of local file paths to images (PNG, JPG, GIF)",
                    },
                    "set_main_image": {
                        "type": "integer",
                        "description": "Index of which image should be main (0-based)",
                        "default": 0,
                    },
                },
                "required": ["project_url", "image_paths"],
            },
        ),
        Tool(
            name="list_hackathon_projects",
            description="List all projects/submissions from a hackathon's project gallery. Works for closed/past hackathons to see winners and submissions. Automatically handles pagination to get all projects.",
            inputSchema={
                "type": "object",
                "properties": {
                    "hackathon_url": {
                        "type": "string",
                        "description": "Hackathon URL (e.g., https://datahacks.devpost.com/ or https://zervehack.devpost.com/)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum projects to return (0 = unlimited, get all)",
                        "default": 50,
                    },
                    "include_winners_only": {
                        "type": "boolean",
                        "description": "If true, only return winning projects",
                        "default": False,
                    },
                    "fetch_all_pages": {
                        "type": "boolean",
                        "description": "If true, automatically fetch all pages of results",
                        "default": True,
                    },
                },
                "required": ["hackathon_url"],
            },
        ),
        Tool(
            name="get_project_details",
            description="Get detailed info about a specific project including description, team, tech stack, links, and screenshots.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_url": {
                        "type": "string",
                        "description": "Full project URL (e.g., https://devpost.com/software/project-name)",
                    },
                },
                "required": ["project_url"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "list_hackathons":
            results = await client.list_hackathons(
                limit=arguments.get("limit", 20),
                open_state=arguments.get("open_state"),
                sort_by=arguments.get("sort_by", "recently-added"),
                query=arguments.get("query"),
            )
            # Clean up HTML from prize amounts
            for r in results:
                if "prize_amount" in r and isinstance(r["prize_amount"], str):
                    # Extract from HTML like $<span data-currency-value>10,000</span>
                    match = re.search(r'data-currency-value>([^<]+)', r["prize_amount"])
                    if match:
                        r["prize_amount_clean"] = f"${match.group(1)}"
            return [TextContent(type="text", text=json.dumps(results, indent=2))]

        elif name == "search_hackathons":
            results = await client.list_hackathons(
                query=arguments["query"],
                limit=arguments.get("limit", 10),
            )
            for r in results:
                if "prize_amount" in r and isinstance(r["prize_amount"], str):
                    match = re.search(r'data-currency-value>([^<]+)', r["prize_amount"])
                    if match:
                        r["prize_amount_clean"] = f"${match.group(1)}"
            return [TextContent(type="text", text=json.dumps(results, indent=2))]

        elif name == "get_hackathon_by_url":
            result = await client.get_hackathon_by_url(arguments["slug"])
            if result is None:
                return [TextContent(type="text", text=json.dumps({"error": "Hackathon not found"}, indent=2))]
            # Clean prize amount
            if "prize_amount" in result and isinstance(result["prize_amount"], str):
                match = re.search(r'data-currency-value>([^<]+)', result["prize_amount"])
                if match:
                    result["prize_amount_clean"] = f"${match.group(1)}"
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_hackathon_details":
            result = await client.get_hackathon_details(arguments["url"])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "scrape_hackathon_page":
            result = await scrape_hackathon_page(arguments["url"])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "submit_project":
            result = await submit_project_to_hackathon(arguments)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "list_my_submissions":
            result = await list_my_submissions(arguments.get("limit", 20))
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_submission_details":
            result = await get_submission_details(arguments["project_url"])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "update_submission":
            result = await update_submission(arguments)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "add_team_member":
            result = await add_team_member(arguments["project_url"], arguments["username"])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "remove_team_member":
            result = await remove_team_member(arguments["project_url"], arguments["username"])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "delete_submission":
            result = await delete_submission(arguments["project_url"], arguments.get("confirm", False))
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "upload_screenshots":
            result = await upload_screenshots(
                arguments["project_url"],
                arguments["image_paths"],
                arguments.get("set_main_image", 0)
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "list_hackathon_projects":
            result = await list_hackathon_projects(
                arguments["hackathon_url"],
                arguments.get("limit", 50),
                arguments.get("include_winners_only", False),
                arguments.get("fetch_all_pages", True)
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_project_details":
            result = await get_project_details(arguments["project_url"])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except httpx.HTTPError as e:
        return [TextContent(type="text", text=json.dumps({"error": f"HTTP error: {e}"}, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]


async def submit_project_to_hackathon(args: dict) -> dict[str, Any]:
    """Submit a project to a hackathon using browser automation."""
    email = os.getenv("DEVPOST_EMAIL")
    password = os.getenv("DEVPOST_PASSWORD")
    
    if not email or not password:
        return {
            "error": "Missing credentials",
            "message": "Set DEVPOST_EMAIL and DEVPOST_PASSWORD environment variables",
            "dry_run": args.get("dry_run", False),
        }
    
    slug = args["hackathon_slug"]
    title = args["project_title"]
    tagline = args["project_tagline"]
    description = args.get("project_description", "")
    built_with = args.get("built_with", [])
    links = args.get("links", {})
    dry_run = args.get("dry_run", False)
    
    # Import playwright here to avoid startup overhead when not submitting
    try:
        from playwright.async_api import async_playwright, expect
    except ImportError:
        return {
            "error": "Playwright not installed",
            "message": "Install with: pip install playwright && playwright install chromium",
        }
    
    result = {
        "success": False,
        "hackathon_slug": slug,
        "project_title": title,
        "dry_run": dry_run,
        "steps": [],
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Step 1: Login
            result["steps"].append("Navigating to login page")
            await page.goto("https://devpost.com/login")
            await page.wait_for_load_state("networkidle")
            
            result["steps"].append("Filling credentials")
            await page.fill("input#user_email", email)
            await page.fill("input#user_password", password)
            
            result["steps"].append("Clicking login button")
            await page.click("input[type='submit']")
            await page.wait_for_load_state("networkidle")
            
            # Check for login errors
            error_selector = ".alert.alert-error, .error-message, .flash-error"
            try:
                error_elem = await page.wait_for_selector(error_selector, timeout=2000)
                if error_elem:
                    error_text = await error_elem.text_content()
                    return {
                        "error": "Login failed",
                        "message": error_text.strip() if error_text else "Invalid credentials",
                        "steps": result["steps"],
                    }
            except:
                pass  # No error found, continue
            
            # Step 2: Navigate to hackathon submission page
            submission_url = f"https://{slug}.devpost.com/challenges/start_a_submission"
            result["steps"].append(f"Navigating to submission page: {submission_url}")
            await page.goto(submission_url)
            await page.wait_for_load_state("networkidle")
            
            # Check if redirected to manage submissions (already registered)
            current_url = page.url
            if "manage/submissions" in current_url:
                result["steps"].append("Already registered for hackathon, on submissions page")
            elif "register" in current_url:
                # Need to register first
                result["steps"].append("Registering for hackathon first")
                await page.click("input[type='submit'], button[type='submit']")
                await page.wait_for_load_state("networkidle")
            
            # Step 3: Click "Start a submission" or "Create submission"
            result["steps"].append("Looking for submission button")
            try:
                # Try different possible button texts
                for btn_text in ["Start a submission", "Create submission", "Submit", "Enter a submission"]:
                    try:
                        btn = page.get_by_text(btn_text, exact=False).first
                        await btn.wait_for(timeout=2000)
                        await btn.click()
                        result["steps"].append(f"Clicked '{btn_text}' button")
                        await page.wait_for_load_state("networkidle")
                        break
                    except:
                        continue
            except Exception as e:
                result["steps"].append(f"Could not find submission button: {e}")
            
            # Step 4: Fill in project form
            result["steps"].append("Filling project form")
            
            # Title
            try:
                await page.fill("input[name*='title'], input#project_title, input[name='project[title]']", title)
                result["steps"].append("Filled project title")
            except Exception as e:
                result["steps"].append(f"Could not fill title: {e}")
            
            # Tagline/elevator pitch
            try:
                await page.fill("textarea[name*='tagline'], textarea#project_tagline, textarea[name='project[elevator_pitch]']", tagline)
                result["steps"].append("Filled project tagline")
            except Exception as e:
                result["steps"].append(f"Could not fill tagline: {e}")
            
            # Description (if provided)
            if description:
                try:
                    await page.fill("textarea[name*='description'], textarea#project_description, textarea[name='project[description]']", description)
                    result["steps"].append("Filled project description")
                except Exception as e:
                    result["steps"].append(f"Could not fill description: {e}")
            
            # Built with / technologies
            if built_with:
                try:
                    # Try to find and fill the built_with field
                    tech_string = ", ".join(built_with)
                    await page.fill("input[name*='built_with'], input#project_built_with, input[name='project[built_with]']", tech_string)
                    result["steps"].append(f"Filled technologies: {tech_string}")
                except Exception as e:
                    result["steps"].append(f"Could not fill technologies: {e}")
            
            # Links
            if links.get("github"):
                try:
                    await page.fill("input[name*='github'], input[name='project[github_url]']", links["github"])
                    result["steps"].append("Filled GitHub link")
                except:
                    pass
            
            if links.get("demo"):
                try:
                    await page.fill("input[name*='demo'], input[name='project[demo_url]'], input[name='project[try_it_out_url]']", links["demo"])
                    result["steps"].append("Filled demo link")
                except:
                    pass
            
            if links.get("video"):
                try:
                    await page.fill("input[name*='video'], input[name='project[video_url]']", links["video"])
                    result["steps"].append("Filled video link")
                except:
                    pass
            
            # Step 5: Submit or save
            if dry_run:
                result["steps"].append("DRY RUN - Form filled but not submitted")
                result["success"] = True
                result["message"] = "Form filled successfully (dry run - not actually submitted)"
            else:
                result["steps"].append("Submitting project")
                try:
                    # Try to find submit button
                    for btn_text in ["Save", "Submit", "Create Project", "Publish", "Submit project"]:
                        try:
                            btn = page.get_by_text(btn_text, exact=False).first
                            await btn.wait_for(timeout=2000)
                            await btn.click()
                            result["steps"].append(f"Clicked '{btn_text}' button")
                            await page.wait_for_load_state("networkidle")
                            break
                        except:
                            continue
                    
                    # Check for success
                    result["steps"].append("Checking submission result")
                    current_url = page.url
                    if "submissions" in current_url or "projects" in current_url:
                        result["success"] = True
                        result["message"] = "Project submitted successfully!"
                        result["submission_url"] = current_url
                    else:
                        result["message"] = "Submission may have succeeded - check your Devpost dashboard"
                        
                except Exception as e:
                    result["error"] = f"Submission failed: {e}"
            
            # Capture screenshot for debugging
            try:
                screenshot_path = f"/tmp/devpost_submit_{slug}_{int(asyncio.get_event_loop().time())}.png"
                await page.screenshot(path=screenshot_path, full_page=True)
                result["screenshot"] = screenshot_path
                result["steps"].append(f"Screenshot saved to {screenshot_path}")
            except:
                pass
            
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")
        finally:
            await browser.close()
    
    return result


async def list_my_submissions(limit: int = 20) -> dict[str, Any]:
    """List all projects submitted by the authenticated user."""
    email, password, creds_error = _get_credentials()
    if creds_error:
        return creds_error
    
    result = {"success": False, "submissions": [], "steps": []}
    
    async with _get_playwright() as p:
        browser, page = await _login(p, email, password, result["steps"])
        if not browser:
            return browser  # Error dict
        
        try:
            # Navigate to user's portfolio/projects page
            result["steps"].append("Navigating to portfolio")
            await page.goto("https://devpost.com/software?ref_content=portfolio&ref_feature=portfolio&ref_medium=global-nav")
            await page.wait_for_load_state("networkidle")
            
            # Extract project information
            projects = await page.query_selector_all(".software-entry, .project-item, [data-testid='project-card']")
            
            submissions = []
            for i, project in enumerate(projects[:limit]):
                try:
                    # Extract title
                    title_elem = await project.query_selector("h2, h3, .title, .software-name")
                    title = await title_elem.text_content() if title_elem else "Unknown"
                    
                    # Extract URL
                    link_elem = await project.query_selector("a[href*='/software/']")
                    href = await link_elem.get_attribute("href") if link_elem else ""
                    url = f"https://devpost.com{href}" if href.startswith("/") else href
                    
                    # Extract hackathon name if available
                    hackathon_elem = await project.query_selector(".challenge, .hackathon-name, .contest")
                    hackathon = await hackathon_elem.text_content() if hackathon_elem else None
                    
                    submissions.append({
                        "index": i,
                        "title": title.strip() if title else "Unknown",
                        "url": url,
                        "hackathon": hackathon.strip() if hackathon else None,
                    })
                except Exception as e:
                    result["steps"].append(f"Error parsing project {i}: {e}")
            
            result["submissions"] = submissions
            result["success"] = True
            result["count"] = len(submissions)
            
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")
        finally:
            await browser.close()
    
    return result


async def get_submission_details(project_url: str) -> dict[str, Any]:
    """Get detailed info about a specific project."""
    email, password, creds_error = _get_credentials()
    if creds_error:
        return creds_error
    
    result = {"success": False, "url": project_url, "steps": []}
    
    async with _get_playwright() as p:
        browser, page = await _login(p, email, password, result["steps"])
        if not browser:
            return browser
        
        try:
            result["steps"].append(f"Navigating to {project_url}")
            await page.goto(project_url)
            await page.wait_for_load_state("networkidle")
            
            # Extract all project details
            details = {}
            
            # Title
            try:
                title_elem = await page.wait_for_selector("h1#app-title, h1.software-title, header h1", timeout=5000)
                details["title"] = await title_elem.text_content()
                details["title"] = details["title"].strip() if details["title"] else None
            except:
                pass
            
            # Tagline/elevator pitch
            try:
                tagline_elem = await page.query_selector(".tagline, .elevator-pitch, #app-tagline, .software-tagline")
                details["tagline"] = await tagline_elem.text_content()
                details["tagline"] = details["tagline"].strip() if details["tagline"] else None
            except:
                pass
            
            # Description
            try:
                desc_elem = await page.query_selector("#app-details, .description, .software-description, .project-description")
                details["description"] = await desc_elem.text_content()
                details["description"] = details["description"].strip() if details["description"] else None
            except:
                pass
            
            # Built with
            try:
                built_elem = await page.query_selector(".built-with, #built-with, .technologies")
                built_text = await built_elem.text_content()
                if built_text:
                    details["built_with"] = [t.strip() for t in built_text.replace("Built with:", "").split(",")]
            except:
                pass
            
            # Links
            links = {}
            try:
                github = await page.query_selector("a[href*='github.com']")
                if github:
                    links["github"] = await github.get_attribute("href")
            except:
                pass
            try:
                demo = await page.query_selector("a[href*='demo'], a[rel*='demo']")
                if demo:
                    links["demo"] = await demo.get_attribute("href")
            except:
                pass
            try:
                video = await page.query_selector("a[href*='youtube.com'], a[href*='vimeo.com']")
                if video:
                    links["video"] = await video.get_attribute("href")
            except:
                pass
            if links:
                details["links"] = links
            
            # Team members
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
            except Exception as e:
                result["steps"].append(f"Error parsing team: {e}")
            if team:
                details["team_members"] = team
            
            # Hackathon
            try:
                hackathon_elem = await page.query_selector(".challenge-info a, .hackathon-link")
                if hackathon_elem:
                    details["hackathon"] = {
                        "name": await hackathon_elem.text_content(),
                        "url": await hackathon_elem.get_attribute("href"),
                    }
            except:
                pass
            
            result["details"] = details
            result["success"] = True
            
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")
        finally:
            await browser.close()
    
    return result


async def update_submission(args: dict) -> dict[str, Any]:
    """Update an existing project submission."""
    email, password, creds_error = _get_credentials()
    if creds_error:
        return creds_error
    
    project_url = args["project_url"]
    dry_run = args.get("dry_run", False)
    
    result = {
        "success": False,
        "url": project_url,
        "dry_run": dry_run,
        "steps": [],
        "updated_fields": [],
    }
    
    async with _get_playwright() as p:
        browser, page = await _login(p, email, password, result["steps"])
        if not browser:
            return browser
        
        try:
            # Navigate to edit page
            edit_url = f"{project_url.rstrip('/')}/edit"
            result["steps"].append(f"Navigating to edit page: {edit_url}")
            await page.goto(edit_url)
            await page.wait_for_load_state("networkidle")
            
            # Update fields
            if "project_title" in args:
                try:
                    await page.fill("input[name*='title'], input#project_title", args["project_title"])
                    result["updated_fields"].append("title")
                    result["steps"].append("Updated title")
                except Exception as e:
                    result["steps"].append(f"Could not update title: {e}")
            
            if "project_tagline" in args:
                try:
                    await page.fill("textarea[name*='tagline'], input[name*='elevator_pitch']", args["project_tagline"])
                    result["updated_fields"].append("tagline")
                    result["steps"].append("Updated tagline")
                except Exception as e:
                    result["steps"].append(f"Could not update tagline: {e}")
            
            if "project_description" in args:
                try:
                    await page.fill("textarea[name*='description'], textarea#project_description", args["project_description"])
                    result["updated_fields"].append("description")
                    result["steps"].append("Updated description")
                except Exception as e:
                    result["steps"].append(f"Could not update description: {e}")
            
            if "built_with" in args:
                try:
                    tech_string = ", ".join(args["built_with"])
                    await page.fill("input[name*='built_with']", tech_string)
                    result["updated_fields"].append("built_with")
                    result["steps"].append("Updated technologies")
                except Exception as e:
                    result["steps"].append(f"Could not update technologies: {e}")
            
            links = args.get("links", {})
            if links.get("github"):
                try:
                    await page.fill("input[name*='github']", links["github"])
                    result["updated_fields"].append("github_link")
                except:
                    pass
            if links.get("demo"):
                try:
                    await page.fill("input[name*='demo'], input[name*='try_it_out']", links["demo"])
                    result["updated_fields"].append("demo_link")
                except:
                    pass
            if links.get("video"):
                try:
                    await page.fill("input[name*='video']", links["video"])
                    result["updated_fields"].append("video_link")
                except:
                    pass
            
            # Save changes
            if dry_run:
                result["steps"].append("DRY RUN - Changes not saved")
                result["success"] = True
                result["message"] = "Dry run completed - changes would be saved"
            else:
                try:
                    await page.click("input[type='submit'][value*='Save'], button:has-text('Save'), input[value='Update Project']")
                    await page.wait_for_load_state("networkidle")
                    result["steps"].append("Saved changes")
                    result["success"] = True
                    result["message"] = "Project updated successfully"
                except Exception as e:
                    result["error"] = f"Failed to save: {e}"
            
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")
        finally:
            await browser.close()
    
    return result


async def add_team_member(project_url: str, username: str) -> dict[str, Any]:
    """Add a team member to a project."""
    email, password, creds_error = _get_credentials()
    if creds_error:
        return creds_error
    
    result = {"success": False, "project_url": project_url, "username": username, "steps": []}
    
    async with _get_playwright() as p:
        browser, page = await _login(p, email, password, result["steps"])
        if not browser:
            return browser
        
        try:
            # Go to team management page
            team_url = f"{project_url.rstrip('/')}/team"
            result["steps"].append(f"Navigating to team page: {team_url}")
            await page.goto(team_url)
            await page.wait_for_load_state("networkidle")
            
            # Look for add member button/field
            result["steps"].append("Looking for add member field")
            try:
                # Try to find username/email input
                await page.fill("input[name*='user'], input[name*='email'], input[name*='username']", username)
                result["steps"].append(f"Entered username: {username}")
                
                # Click add/invite button
                await page.click("input[value*='Add'], button:has-text('Add'), button:has-text('Invite')")
                await page.wait_for_load_state("networkidle")
                result["steps"].append("Clicked add member button")
                
                result["success"] = True
                result["message"] = f"Added {username} to project (or invitation sent)"
                
            except Exception as e:
                result["error"] = f"Could not add member: {e}"
                result["steps"].append(f"Error adding member: {e}")
            
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")
        finally:
            await browser.close()
    
    return result


async def remove_team_member(project_url: str, username: str) -> dict[str, Any]:
    """Remove a team member from a project."""
    email, password, creds_error = _get_credentials()
    if creds_error:
        return creds_error
    
    result = {"success": False, "project_url": project_url, "username": username, "steps": []}
    
    async with _get_playwright() as p:
        browser, page = await _login(p, email, password, result["steps"])
        if not browser:
            return browser
        
        try:
            team_url = f"{project_url.rstrip('/')}/team"
            result["steps"].append(f"Navigating to team page: {team_url}")
            await page.goto(team_url)
            await page.wait_for_load_state("networkidle")
            
            # Find the team member and click remove
            result["steps"].append(f"Looking for member: {username}")
            try:
                # Look for remove button near the username
                member_elem = await page.query_selector(f"text={username}")
                if member_elem:
                    # Find the remove button in the same row/container
                    container = await member_elem.evaluate("el => el.closest('tr, .member, .team-member')")
                    if container:
                        remove_btn = await container.query_selector("a[href*='remove'], button:has-text('Remove'), .remove")
                        if remove_btn:
                            await remove_btn.click()
                            await page.wait_for_load_state("networkidle")
                            result["steps"].append("Clicked remove button")
                            
                            # Confirm removal if prompted
                            try:
                                await page.click("button:has-text('Confirm'), input[value='Remove']")
                                await page.wait_for_load_state("networkidle")
                                result["steps"].append("Confirmed removal")
                            except:
                                pass
                            
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
            
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")
        finally:
            await browser.close()
    
    return result


async def delete_submission(project_url: str, confirm: bool = False) -> dict[str, Any]:
    """Delete a project submission permanently."""
    if not confirm:
        return {
            "error": "Confirmation required",
            "message": "Set confirm=true to actually delete this project. THIS CANNOT BE UNDONE.",
            "project_url": project_url,
            "warning": "This will permanently delete the project and all its data.",
        }
    
    email, password, creds_error = _get_credentials()
    if creds_error:
        return creds_error
    
    result = {"success": False, "project_url": project_url, "steps": []}
    
    async with _get_playwright() as p:
        browser, page = await _login(p, email, password, result["steps"])
        if not browser:
            return browser
        
        try:
            # Go to edit page and look for delete option
            edit_url = f"{project_url.rstrip('/')}/edit"
            result["steps"].append(f"Navigating to edit page: {edit_url}")
            await page.goto(edit_url)
            await page.wait_for_load_state("networkidle")
            
            result["steps"].append("Looking for delete option")
            try:
                # Look for delete link/button (usually at bottom or in danger zone)
                delete_link = await page.query_selector("a[href*='delete'], a:has-text('Delete'), .delete-project")
                if delete_link:
                    await delete_link.click()
                    await page.wait_for_load_state("networkidle")
                    result["steps"].append("Clicked delete link")
                    
                    # Confirm deletion
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
                    
            except Exception as e:
                result["error"] = f"Error during deletion: {e}"
            
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")
        finally:
            await browser.close()
    
    return result


async def upload_screenshots(project_url: str, image_paths: list[str], set_main_image: int = 0) -> dict[str, Any]:
    """Upload screenshots to a project."""
    email, password, creds_error = _get_credentials()
    if creds_error:
        return creds_error
    
    result = {
        "success": False,
        "project_url": project_url,
        "image_paths": image_paths,
        "uploaded": [],
        "failed": [],
        "steps": [],
    }
    
    async with _get_playwright() as p:
        browser, page = await _login(p, email, password, result["steps"])
        if not browser:
            return browser
        
        try:
            # Go to edit page
            edit_url = f"{project_url.rstrip('/')}/edit"
            result["steps"].append(f"Navigating to edit page: {edit_url}")
            await page.goto(edit_url)
            await page.wait_for_load_state("networkidle")
            
            result["steps"].append("Looking for image upload section")
            
            for i, image_path in enumerate(image_paths):
                try:
                    # Look for file input
                    file_input = await page.wait_for_selector("input[type='file'], input[name*='image'], input[name*='screenshot']", timeout=5000)
                    
                    if file_input:
                        await file_input.set_input_files(image_path)
                        result["steps"].append(f"Selected file: {image_path}")
                        
                        # Wait for upload to complete (look for thumbnail or success indicator)
                        await page.wait_for_timeout(3000)  # Give time for upload
                        
                        result["uploaded"].append(image_path)
                        result["steps"].append(f"Uploaded: {image_path}")
                    else:
                        result["failed"].append({"path": image_path, "reason": "File input not found"})
                        
                except Exception as e:
                    result["failed"].append({"path": image_path, "reason": str(e)})
                    result["steps"].append(f"Failed to upload {image_path}: {e}")
            
            # Set main image if specified
            if set_main_image < len(result["uploaded"]):
                try:
                    # Look for option to set main image
                    images = await page.query_selector_all(".thumbnail, .project-image, .uploaded-image")
                    if set_main_image < len(images):
                        # Click to set as main
                        await images[set_main_image].click()
                        result["steps"].append(f"Set image {set_main_image} as main")
                except Exception as e:
                    result["steps"].append(f"Could not set main image: {e}")
            
            # Save changes
            try:
                await page.click("input[type='submit'], button:has-text('Save')")
                await page.wait_for_load_state("networkidle")
                result["steps"].append("Saved changes")
                result["success"] = len(result["uploaded"]) > 0
            except Exception as e:
                result["error"] = f"Failed to save: {e}"
            
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")
        finally:
            await browser.close()
    
    return result


# Helper functions

def _get_credentials() -> tuple[str, str, dict | None]:
    """Get Devpost credentials from environment."""
    email = os.getenv("DEVPOST_EMAIL")
    password = os.getenv("DEVPOST_PASSWORD")
    
    if not email or not password:
        return None, None, {
            "error": "Missing credentials",
            "message": "Set DEVPOST_EMAIL and DEVPOST_PASSWORD environment variables",
        }
    return email, password, None


async def _get_playwright():
    """Get playwright async context manager."""
    from playwright.async_api import async_playwright
    return async_playwright()


async def _login(p, email: str, password: str, steps: list) -> tuple[Any, Any]:
    """Login to Devpost and return browser, page."""
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()
    
    try:
        steps.append("Navigating to login page")
        await page.goto("https://devpost.com/login")
        await page.wait_for_load_state("networkidle")
        
        steps.append("Filling credentials")
        await page.fill("input#user_email", email)
        await page.fill("input#user_password", password)
        
        steps.append("Clicking login button")
        await page.click("input[type='submit']")
        await page.wait_for_load_state("networkidle")
        
        # Check for login errors
        try:
            error_elem = await page.wait_for_selector(".alert.alert-error, .error-message, .flash-error", timeout=2000)
            if error_elem:
                error_text = await error_elem.text_content()
                await browser.close()
                return {"error": "Login failed", "message": error_text.strip() if error_text else "Invalid credentials"}, None
        except:
            pass  # No error, continue
        
        return browser, page
        
    except Exception as e:
        await browser.close()
        return {"error": "Login failed", "message": str(e)}, None


async def list_hackathon_projects(hackathon_url: str, limit: int = 50, winners_only: bool = False, fetch_all_pages: bool = True) -> dict[str, Any]:
    """List all projects from a hackathon's project gallery. Supports pagination."""
    result = {"success": False, "hackathon_url": hackathon_url, "steps": [], "projects": []}
    
    # Construct gallery URL
    base_gallery_url = f"{hackathon_url.rstrip('/')}/project-gallery"
    result["steps"].append(f"Fetching gallery: {base_gallery_url}")
    
    async with DevpostClient() as client:
        try:
            all_projects = []
            seen_urls = set()
            page = 1
            max_pages = 10 if fetch_all_pages else 1
            
            while page <= max_pages:
                # Construct page URL
                gallery_url = f"{base_gallery_url}?page={page}" if page > 1 else base_gallery_url
                result["steps"].append(f"Fetching page {page}: {gallery_url}")
                
                try:
                    resp = await client.client.get(gallery_url)
                    resp.raise_for_status()
                    
                    soup = BeautifulSoup(resp.text, "html.parser")
                    
                    # Extract hackathon year/title from page
                    if page == 1:
                        title_elem = soup.find("h1") or soup.find("title")
                        if title_elem:
                            result["hackathon_title"] = title_elem.get_text(strip=True)
                        
                        # Check for year/date info
                        date_elem = soup.find(class_=re.compile(r'date|time|period', re.I))
                        if date_elem:
                            result["hackathon_date_info"] = date_elem.get_text(strip=True)
                    
                    # Find all project entries on the page
                    page_projects = []
                    project_cards = soup.find_all(class_=re.compile(r'software-entry|project-item|gallery-item|submission', re.I))
                    
                    if not project_cards:
                        # Try broader selectors
                        project_cards = soup.find_all("article")
                    
                    if not project_cards:
                        # Try finding by link patterns
                        project_links = soup.find_all("a", href=re.compile(r'/software/'))
                        for link in project_links:
                            href = link.get("href", "")
                            if href in seen_urls or not href:
                                continue
                            
                            seen_urls.add(href)
                            card = link.find_parent(class_=re.compile(r'entry|card|item', re.I)) or link.parent
                            
                            proj = await _extract_project_from_card(card, link, client)
                            if proj:
                                # Check winner filter
                                if winners_only and not proj.get("is_winner"):
                                    continue
                                page_projects.append(proj)
                    else:
                        # Process found cards
                        for card in project_cards:
                            try:
                                link = card.find("a", href=re.compile(r'/software/'))
                                if not link:
                                    continue
                                
                                href = link.get("href", "")
                                if href in seen_urls or not href:
                                    continue
                                seen_urls.add(href)
                                
                                proj = await _extract_project_from_card(card, link, client)
                                if proj:
                                    # Check winner filter
                                    if winners_only and not proj.get("is_winner"):
                                        continue
                                    page_projects.append(proj)
                                    
                            except Exception as e:
                                result["steps"].append(f"Error parsing card: {e}")
                    
                    # Check if we got any projects on this page
                    if not page_projects:
                        result["steps"].append(f"No projects found on page {page}, stopping")
                        break
                    
                    all_projects.extend(page_projects)
                    result["steps"].append(f"Found {len(page_projects)} projects on page {page}")
                    
                    # Check limit
                    if limit > 0 and len(all_projects) >= limit:
                        all_projects = all_projects[:limit]
                        result["steps"].append(f"Reached limit of {limit} projects")
                        break
                    
                    # Check for next page link
                    next_link = soup.find("a", href=re.compile(r'page=\d+'))
                    if not next_link or f"page={page+1}" not in str(next_link):
                        # Try to find pagination
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
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        result["steps"].append(f"Page {page} not found (404), stopping")
                        break
                    raise
            
            result["projects"] = all_projects
            result["count"] = len(all_projects)
            result["pages_fetched"] = page
            result["success"] = True
            
        except httpx.HTTPStatusError as e:
            result["error"] = f"HTTP {e.response.status_code}: Gallery not accessible"
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")
    
    return result


async def _extract_project_from_card(card, link, client) -> dict | None:
    """Extract project info from a gallery card."""
    try:
        # Title
        title_elem = card.find(["h2", "h3", "h4", ".title", ".name"]) or link
        title = title_elem.get_text(strip=True) if title_elem else "Unknown"
        
        # URL
        href = link.get("href", "")
        url = f"https://devpost.com{href}" if href.startswith("/") else href
        
        # Tagline
        tagline_elem = card.find(class_=re.compile(r'tagline|description|summary', re.I))
        tagline = tagline_elem.get_text(strip=True) if tagline_elem else None
        
        # Thumbnail
        img = card.find("img")
        thumbnail = img.get("src") if img else None
        
        # Check for winner badge
        winner_badge = card.find(class_=re.compile(r'winner|1st|2nd|3rd|finalist', re.I))
        is_winner = bool(winner_badge)
        prize = None
        if winner_badge:
            prize = winner_badge.get_text(strip=True)
        
        # Team name
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
    except Exception:
        return None


async def get_project_details(project_url: str) -> dict[str, Any]:
    """Get detailed info about a specific project using browser automation for full JS-rendered content."""
    result = {"success": False, "url": project_url, "steps": [], "data": {}}
    
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "error": "Playwright not installed",
            "message": "Install with: pip install playwright && playwright install chromium",
        }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            result["steps"].append(f"Loading {project_url}")
            await page.goto(project_url)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(1)  # Extra wait for JS render
            
            data = {}
            
            # Title
            try:
                title = await page.wait_for_selector("h1#app-title, h1", timeout=5000)
                data["title"] = await title.text_content()
            except:
                pass
            
            # Tagline
            try:
                tagline = await page.query_selector("p.tagline, .elevator-pitch, #app-tagline")
                data["tagline"] = await tagline.text_content() if tagline else None
            except:
                pass
            
            # Full description (the main content)
            try:
                desc = await page.query_selector("#app-details, .description, .software-description")
                if desc:
                    data["description"] = await desc.text_content()
                    data["description_html"] = await desc.inner_html()
            except Exception as e:
                result["steps"].append(f"Description error: {e}")
            
            # Built with
            try:
                built = await page.query_selector("#built-with, .built-with")
                if built:
                    text = await built.text_content()
                    # Parse tags like "opencv, python, react"
                    techs = [t.strip() for t in text.replace("Built With", "").split() if t.strip()]
                    data["built_with"] = techs
            except:
                pass
            
            # Links
            links = {}
            try:
                github = await page.query_selector("a[href*='github.com']")
                if github:
                    links["github"] = await github.get_attribute("href")
            except:
                pass
            try:
                demo = await page.query_selector("a[href*='try-it-out'], a.demo-link, a[title*='demo' i]")
                if demo:
                    href = await demo.get_attribute("href")
                    if href:
                        links["demo"] = href
            except:
                pass
            try:
                video = await page.query_selector("a[href*='youtube.com'], a[href*='vimeo.com'], a[href*='youtu.be']")
                if video:
                    links["video"] = await video.get_attribute("href")
            except:
                pass
            try:
                website = await page.query_selector("a[rel*='external'], a.website-link")
                if website:
                    href = await website.get_attribute("href")
                    if href and "devpost.com" not in href:
                        links["website"] = href
            except:
                pass
            if links:
                data["links"] = links
            
            # Team members
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
                        except:
                            pass
            except Exception as e:
                result["steps"].append(f"Team error: {e}")
            if team:
                data["team"] = team
            
            # Screenshots from gallery
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
                        except:
                            pass
            except:
                pass
            if screenshots:
                data["screenshots"] = screenshots
            
            # Hackathon info
            try:
                hackathon = await page.query_selector("a[href*='devpost.com/'][href$='/']")
                if hackathon:
                    hack_name = await hackathon.text_content()
                    hack_url = await hackathon.get_attribute("href")
                    data["hackathon"] = {
                        "name": hack_name.strip() if hack_name else None,
                        "url": hack_url,
                    }
            except:
                pass
            
            # Winner info
            try:
                winner_badge = await page.query_selector(".winner, .winner-badge, .prize-winner")
                if winner_badge:
                    data["is_winner"] = True
                    prize_text = await winner_badge.text_content()
                    data["prize"] = prize_text.strip() if prize_text else "Winner"
            except:
                pass
            
            result["data"] = data
            result["success"] = True
            result["steps"].append("Successfully extracted project details")
            
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")
        finally:
            await browser.close()
    
    return result


async def scrape_hackathon_page(url: str) -> dict[str, Any]:
    """Deep scrape a hackathon page to extract all available info. Works for past/closed hackathons."""
    result = {"success": False, "url": url, "steps": [], "data": {}}
    
    async with DevpostClient() as client:
        try:
            result["steps"].append(f"Fetching {url}")
            resp = await client.client.get(url)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, "html.parser")
            data = {}
            
            # Try to find JSON data in script tags (Next.js/React data)
            scripts = soup.find_all("script")
            for script in scripts:
                text = script.string or ""
                if "__INITIAL_STATE__" in text or "window.__DATA__" in text:
                    try:
                        # Extract JSON from window.__INITIAL_STATE__ = {...}
                        json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', text, re.DOTALL)
                        if json_match:
                            data["initial_state"] = json.loads(json_match.group(1))
                    except:
                        pass
            
            # Meta tags
            data["title"] = (
                client._get_meta(soup, "og:title")
                or client._get_meta(soup, "twitter:title")
                or (soup.find("h1").get_text(strip=True) if soup.find("h1") else None)
            )
            data["description"] = (
                client._get_meta(soup, "og:description")
                or client._get_meta(soup, "description")
                or client._get_meta(soup, "twitter:description")
            )
            data["image"] = client._get_meta(soup, "og:image")
            
            # Extract dates from page content
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
                data["dates_mentioned"] = list(set(dates_found))[:5]  # dedupe, limit
            
            # Look for prize info (but filter out scripts)
            prize_elems = soup.find_all(string=re.compile(r'\$[\d,]+', re.I))
            for elem in prize_elems:
                parent = elem.parent
                if parent and parent.name not in ['script', 'style', 'noscript']:
                    text = parent.get_text(strip=True)
                    if len(text) < 200 and '$' in text:
                        data["prize_text"] = text
                        break
            
            # Submission count / participants
            stats = {}
            for pattern in [r'(\d+)\s+submissions?', r'(\d+)\s+participants?', r'(\d+)\s+registrations?']:
                match = re.search(pattern, text_content, re.I)
                if match:
                    key = pattern.split()[-1].replace('?', '').replace('s', '')
                    stats[key] = int(match.group(1))
            if stats:
                data["stats"] = stats
            
            # Winners announced?
            if "winner" in text_content.lower() or "winners" in text_content.lower():
                data["winners_announced"] = True
                # Try to find winner section
                winner_section = soup.find(string=re.compile(r'winners?', re.I))
                if winner_section:
                    data["has_winners_section"] = True
            
            # Rules link
            rules_link = soup.find("a", href=re.compile(r'rules|guidelines', re.I))
            if rules_link:
                rules_href = rules_link.get("href", "")
                data["rules_url"] = rules_href if rules_href.startswith("http") else f"{url.rstrip('/')}/{rules_href.lstrip('/')}"
            
            # Submission gallery link
            gallery_link = soup.find("a", href=re.compile(r'project-gallery|submissions', re.I))
            if gallery_link:
                data["gallery_url"] = gallery_link.get("href")
            
            # Themes/tags
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
            
        except httpx.HTTPStatusError as e:
            result["error"] = f"HTTP {e.response.status_code}: Page not found or not accessible"
            result["steps"].append(f"Failed to fetch: {e}")
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")
    
    return result


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
