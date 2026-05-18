"""Hackathon hosting functionality for Devpost CLI.

Provides methods for creating and configuring hackathons via manage.devpost.com.
"""

import asyncio
from pathlib import Path
from typing import Any, Optional

from .logging_config import get_logger
from .session import get_credentials

logger = get_logger("host")

MANAGE_BASE_URL = "https://manage.devpost.com"


class HackathonHostingClient:
    """Client for creating and managing hackathons on Devpost.
    
    Uses authenticated browser sessions to interact with manage.devpost.com.
    """

    # OAuth provider selectors (same as AuthenticatedClient)
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
        """Close browser session."""
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
            from .core import DevpostError
            raise DevpostError(
                "DEVPOST_EMAIL and DEVPOST_PASSWORD must be set. "
                "Use `devpost auth login` or set environment variables.",
                code="AUTH_REQUIRED",
            )
        return creds

    async def _get_browser_and_page(self) -> tuple[Any, Any]:
        """Get or create browser context with Devpost authentication.
        
        Supports both password and OAuth login flows.
        OAuth login auto-forces headed mode for user interaction.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            from .core import DevpostError
            raise DevpostError(
                "Playwright not installed. Install with: pip install playwright && playwright install chromium",
                code="DEPENDENCY_MISSING",
            )

        if self._page and self._browser:
            try:
                await self._page.goto(MANAGE_BASE_URL, wait_until="networkidle", timeout=10000)
                return self._browser, self._page
            except Exception as e:
                logger.debug("Existing browser session invalid, recreating: %s", e)
                await self.close()

        # Import session loading
        from .session import load_session, save_session

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
                await self._page.goto(MANAGE_BASE_URL, wait_until="networkidle", timeout=15000)
                await asyncio.sleep(2)
                # Check if we're still logged in
                if "login" in self._page.url.lower():
                    raise Exception("Session expired")
                return self._browser, self._page
            except Exception as e:
                logger.debug("Session cookies invalid, re-authenticating: %s", e)
                await self._context.close()
                self._context = None
                self._page = None

        # Create new context and authenticate
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        self._page = await self._context.new_page()

        await self._page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        """)

        # Navigate to login
        await self._page.goto(f"{MANAGE_BASE_URL}/users/login", wait_until="networkidle", timeout=30000)
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

        # Fill login form
        await self._page.fill("input#user_email", email)
        await self._page.fill("input#user_password", password)
        await self._page.click("button#submit-form")
        await self._page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # Check for login errors
        error_selector = ".alert.alert-error, .error-message, .flash-error"
        try:
            error_elem = await self._page.wait_for_selector(error_selector, timeout=2000)
            if error_elem:
                error_text = await error_elem.text_content()
                await self.close()
                from .core import DevpostError
                raise DevpostError(
                    f"Login failed: {error_text.strip() if error_text else 'Invalid credentials'}",
                    code="AUTH_FAILED",
                )
        except Exception:
            pass  # No error element found, login likely succeeded

        if "users/login" in self._page.url:
            await self.close()
            from .core import DevpostError
            raise DevpostError("Login failed - check credentials", code="AUTH_FAILED")

    async def _oauth_login(self) -> None:
        """Perform OAuth login via social provider.
        
        Clicks the appropriate OAuth button and waits for redirect back to Devpost.
        Timeout is extended to 120s to allow for user interaction on OAuth provider page.
        """
        provider = self.OAUTH_PROVIDERS.get(self.auth_method)
        if not provider:
            from .core import DevpostError
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
            from .core import DevpostError
            raise DevpostError(
                f"Could not find {provider_name} login button. Page may have changed.",
                code="OAUTH_BUTTON_NOT_FOUND",
            ) from e

        # Wait for OAuth flow to complete (user authenticates on provider site, redirects back)
        logger.info(f"Waiting for {provider_name} authentication... (timeout: 120s)")
        try:
            # Wait for redirect back to devpost.com (not on login page anymore)
            await self._page.wait_for_url(
                lambda url: "devpost.com" in url and "login" not in url.lower(),
                timeout=120000
            )
            await self._page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)
        except Exception as e:
            await self.close()
            from .core import DevpostError
            raise DevpostError(
                f"OAuth login timed out. Please try again and complete authentication on {provider_name}.",
                code="OAUTH_TIMEOUT",
            ) from e

        # Verify we're logged in (not on login page anymore)
        if "login" in self._page.url.lower():
            await self.close()
            from .core import DevpostError
            raise DevpostError(
                f"OAuth login did not complete. You may need to authorize the application on {provider_name}.",
                code="OAUTH_INCOMPLETE",
            )

        logger.info(f"{provider_name} OAuth login successful")
        # Extract email from session if possible (not always available with OAuth)
        self.email = self.email or f"{self.auth_method}-oauth"

    async def create_hackathon(
        self,
        name: str,
        start_date: str,
        hackathon_type: str = "in-person",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Create a new hackathon draft.
        
        Args:
            name: Hackathon name
            start_date: Start date for collecting projects (YYYY-MM-DD format)
            hackathon_type: "in-person", "online-student", or "online-paid"
            dry_run: If True, don't actually create, just validate
            
        Returns:
            Result dict with hackathon slug if successful
        """
        from .core import DevpostError
        
        result = {
            "success": False,
            "name": name,
            "type": hackathon_type,
            "start_date": start_date,
            "dry_run": dry_run,
            "steps": [],
        }

        # Validate hackathon type
        if hackathon_type == "online-paid":
            result["error"] = "Online paid hackathons require contacting Devpost sales"
            result["code"] = "ONLINE_PAID_UNSUPPORTED"
            result["message"] = "Please contact Devpost sales to create an online paid hackathon. Visit: https://info.devpost.com/product/public-hackathons"
            return result

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            # Navigate to creation page
            if hackathon_type == "online-student":
                create_url = f"{MANAGE_BASE_URL}/online-student-hackathon/new"
            else:
                create_url = f"{MANAGE_BASE_URL}/hackathon/new"

            result["steps"].append(f"Navigating to {create_url}")
            await page.goto(create_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # Check if we need to login
            if "login" in page.url.lower():
                result["error"] = "Authentication required"
                result["code"] = "AUTH_REQUIRED"
                return result

            if dry_run:
                result["success"] = True
                result["message"] = "DRY RUN - Hackathon would be created"
                return result

            # Fill initial form
            result["steps"].append("Filling hackathon name")
            await page.fill("input[name*='name'], input[placeholder*='name']", name)

            result["steps"].append("Filling start date")
            await page.fill("input[name*='start_date'], input[type='date']", start_date)

            result["steps"].append("Submitting creation form")
            await page.click("button[type='submit'], input[type='submit'], button:has-text('Create'), button:has-text('Draft')")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            # Extract slug from URL or page
            current_url = page.url
            if "/manage/" in current_url or "/hackathons/" in current_url:
                # Try to extract slug from URL
                import re
                match = re.search(r"/manage/([a-z0-9-]+)/", current_url)
                if match:
                    slug = match.group(1)
                else:
                    # Fallback: use name as slug
                    slug = name.lower().replace(" ", "-").replace("_", "-")
                
                result["success"] = True
                result["slug"] = slug
                result["url"] = f"https://{slug}.devpost.com/"
                result["manage_url"] = f"{MANAGE_BASE_URL}/{slug}"
                result["message"] = f"Hackathon '{name}' created successfully"
            else:
                result["error"] = "Unexpected redirect after creation"
                result["steps"].append(f"Current URL: {current_url}")

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            result["steps"].append(f"Error: {e.message}")
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def configure_essentials(
        self,
        slug: str,
        url_slug: Optional[str] = None,
        tagline: Optional[str] = None,
        manager_email: Optional[str] = None,
        host: Optional[str] = None,
        themes: Optional[list[str]] = None,
        timezone: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Configure Essentials tab settings.
        
        Args:
            slug: Hackathon slug
            url_slug: URL slug (locked after publish)
            tagline: Short CTA phrase
            manager_email: Manager contact email
            host: Host organization name
            themes: Up to 3 theme tags
            timezone: Timezone for dates
            dry_run: If True, don't save changes
            
        Returns:
            Result dict
        """
        from .core import DevpostError
        
        result = {
            "success": False,
            "slug": slug,
            "updated_fields": [],
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
            # Navigate to essentials tab
            edit_url = f"{MANAGE_BASE_URL}/{slug}/edit#essentials"
            result["steps"].append(f"Navigating to {edit_url}")
            await page.goto(edit_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            if url_slug:
                try:
                    await page.fill("input[name*='url'], input[name*='slug'], input[placeholder*='url']", url_slug)
                    result["updated_fields"].append("url_slug")
                    result["steps"].append("Updated URL slug")
                except Exception as e:
                    logger.debug("Could not update URL slug: %s", e)
                    result["steps"].append(f"Could not update URL slug: {e}")

            if tagline:
                try:
                    await page.fill("input[name*='tagline'], textarea[name*='tagline']", tagline)
                    result["updated_fields"].append("tagline")
                    result["steps"].append("Updated tagline")
                except Exception as e:
                    logger.debug("Could not update tagline: %s", e)
                    result["steps"].append(f"Could not update tagline: {e}")

            if manager_email:
                try:
                    await page.fill("input[name*='manager_email'], input[type='email']", manager_email)
                    result["updated_fields"].append("manager_email")
                    result["steps"].append("Updated manager email")
                except Exception as e:
                    logger.debug("Could not update manager email: %s", e)
                    result["steps"].append(f"Could not update manager email: {e}")

            if host:
                try:
                    await page.fill("input[name*='host'], input[name*='organization']", host)
                    result["updated_fields"].append("host")
                    result["steps"].append("Updated host organization")
                except Exception as e:
                    logger.debug("Could not update host: %s", e)
                    result["steps"].append(f"Could not update host: {e}")

            if themes and len(themes) > 0:
                try:
                    # Themes are typically a multi-select or tag input
                    theme_input = page.locator("input[name*='theme'], input[placeholder*='theme']").first
                    for theme in themes[:3]:  # Max 3 themes
                        await theme_input.fill(theme)
                        await theme_input.press("Enter")
                        await asyncio.sleep(0.5)
                    result["updated_fields"].append("themes")
                    result["steps"].append(f"Updated themes: {', '.join(themes[:3])}")
                except Exception as e:
                    logger.debug("Could not update themes: %s", e)
                    result["steps"].append(f"Could not update themes: {e}")

            if timezone:
                try:
                    await page.select_option("select[name*='timezone']", timezone)
                    result["updated_fields"].append("timezone")
                    result["steps"].append(f"Updated timezone to {timezone}")
                except Exception as e:
                    logger.debug("Could not update timezone: %s", e)
                    result["steps"].append(f"Could not update timezone: {e}")

            if dry_run:
                result["success"] = True
                result["message"] = "DRY RUN - Changes would be saved"
                return result

            if result["updated_fields"]:
                result["steps"].append("Saving changes")
                await page.click("button[type='submit'], input[type='submit'], button:has-text('Save'), button:has-text('Update')")
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)

            result["success"] = True
            result["message"] = "Essentials updated successfully"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def configure_eligibility(
        self,
        slug: str,
        community: Optional[str] = None,
        invite_community_name: Optional[str] = None,
        min_age: Optional[int] = None,
        occupation: Optional[str] = None,
        team_mode: Optional[str] = None,
        min_team_size: Optional[int] = None,
        max_team_size: Optional[int] = None,
        geo_restrictions: Optional[list[str]] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Configure Eligibility tab settings."""
        from .core import DevpostError
        
        result = {
            "success": False,
            "slug": slug,
            "updated_fields": [],
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
            edit_url = f"{MANAGE_BASE_URL}/{slug}/edit#eligibility"
            result["steps"].append(f"Navigating to {edit_url}")
            await page.goto(edit_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            if community:
                try:
                    if community == "public":
                        await page.click("input[type='radio'][value='public'], input[type='radio']:has-text('Public')")
                    else:
                        await page.click("input[type='radio'][value='invite-only'], input[type='radio']:has-text('Invite')")
                    result["updated_fields"].append("community")
                    result["steps"].append(f"Updated community to {community}")
                except Exception as e:
                    logger.debug("Could not update community: %s", e)
                    result["steps"].append(f"Could not update community: {e}")

            if invite_community_name and community == "invite-only":
                try:
                    await page.fill("input[name*='invite_community']", invite_community_name)
                    result["updated_fields"].append("invite_community_name")
                    result["steps"].append("Updated invite community name")
                except Exception as e:
                    logger.debug("Could not update invite community name: %s", e)
                    result["steps"].append(f"Could not update invite community name: {e}")

            if min_age:
                try:
                    await page.fill("input[name*='min_age'], input[name*='age']", str(min_age))
                    result["updated_fields"].append("min_age")
                    result["steps"].append(f"Updated minimum age to {min_age}")
                except Exception as e:
                    logger.debug("Could not update min age: %s", e)
                    result["steps"].append(f"Could not update min age: {e}")

            if occupation:
                try:
                    await page.select_option(f"select[name*='occupation']", occupation)
                    result["updated_fields"].append("occupation")
                    result["steps"].append(f"Updated occupation to {occupation}")
                except Exception as e:
                    logger.debug("Could not update occupation: %s", e)
                    result["steps"].append(f"Could not update occupation: {e}")

            if team_mode:
                try:
                    await page.select_option(f"select[name*='team_mode']", team_mode)
                    result["updated_fields"].append("team_mode")
                    result["steps"].append(f"Updated team mode to {team_mode}")
                except Exception as e:
                    logger.debug("Could not update team mode: %s", e)
                    result["steps"].append(f"Could not update team mode: {e}")

            if min_team_size:
                try:
                    await page.fill("input[name*='min_team_size']", str(min_team_size))
                    result["updated_fields"].append("min_team_size")
                    result["steps"].append(f"Updated min team size to {min_team_size}")
                except Exception as e:
                    logger.debug("Could not update min team size: %s", e)
                    result["steps"].append(f"Could not update min team size: {e}")

            if max_team_size:
                try:
                    await page.fill("input[name*='max_team_size']", str(max_team_size))
                    result["updated_fields"].append("max_team_size")
                    result["steps"].append(f"Updated max team size to {max_team_size}")
                except Exception as e:
                    logger.debug("Could not update max team size: %s", e)
                    result["steps"].append(f"Could not update max team size: {e}")

            if dry_run:
                result["success"] = True
                result["message"] = "DRY RUN - Changes would be saved"
                return result

            if result["updated_fields"]:
                result["steps"].append("Saving changes")
                await page.click("button[type='submit'], input[type='submit'], button:has-text('Save')")
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)

            result["success"] = True
            result["message"] = "Eligibility updated successfully"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def configure_dates(
        self,
        slug: str,
        submission_open: Optional[str] = None,
        submission_close: Optional[str] = None,
        judging_start: Optional[str] = None,
        judging_end: Optional[str] = None,
        winners_announced: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Configure Dates tab settings."""
        from .core import DevpostError
        
        result = {
            "success": False,
            "slug": slug,
            "updated_fields": [],
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
            edit_url = f"{MANAGE_BASE_URL}/{slug}/edit#submissions"
            result["steps"].append(f"Navigating to {edit_url}")
            await page.goto(edit_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            if submission_open:
                try:
                    await page.fill("input[name*='submission_open'], input[name*='start_date']", submission_open)
                    result["updated_fields"].append("submission_open")
                    result["steps"].append(f"Updated submission open date")
                except Exception as e:
                    logger.debug("Could not update submission open: %s", e)
                    result["steps"].append(f"Could not update submission open: {e}")

            if submission_close:
                try:
                    await page.fill("input[name*='submission_close'], input[name*='end_date']", submission_close)
                    result["updated_fields"].append("submission_close")
                    result["steps"].append(f"Updated submission close date")
                except Exception as e:
                    logger.debug("Could not update submission close: %s", e)
                    result["steps"].append(f"Could not update submission close: {e}")

            if winners_announced:
                try:
                    await page.fill("input[name*='winners_announced']", winners_announced)
                    result["updated_fields"].append("winners_announced")
                    result["steps"].append(f"Updated winners announced date")
                except Exception as e:
                    logger.debug("Could not update winners announced: %s", e)
                    result["steps"].append(f"Could not update winners announced: {e}")

            if dry_run:
                result["success"] = True
                result["message"] = "DRY RUN - Changes would be saved"
                return result

            if result["updated_fields"]:
                result["steps"].append("Saving changes")
                await page.click("button[type='submit'], input[type='submit'], button:has-text('Save')")
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)

            result["success"] = True
            result["message"] = "Dates updated successfully"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def configure_description(
        self,
        slug: str,
        overview: Optional[str] = None,
        eligibility_blurb: Optional[str] = None,
        submission_requirements: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Configure Overview Page Text (description) settings."""
        from .core import DevpostError
        
        result = {
            "success": False,
            "slug": slug,
            "updated_fields": [],
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
            edit_url = f"{MANAGE_BASE_URL}/{slug}/edit#hackathon_site"
            result["steps"].append(f"Navigating to {edit_url}")
            await page.goto(edit_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            if overview:
                try:
                    await page.fill("textarea[name*='overview'], textarea[name*='description']", overview)
                    result["updated_fields"].append("overview")
                    result["steps"].append("Updated overview description")
                except Exception as e:
                    logger.debug("Could not update overview: %s", e)
                    result["steps"].append(f"Could not update overview: {e}")

            if eligibility_blurb:
                try:
                    await page.fill("textarea[name*='eligibility']", eligibility_blurb)
                    result["updated_fields"].append("eligibility_blurb")
                    result["steps"].append("Updated eligibility blurb")
                except Exception as e:
                    logger.debug("Could not update eligibility blurb: %s", e)
                    result["steps"].append(f"Could not update eligibility blurb: {e}")

            if submission_requirements:
                try:
                    await page.fill("textarea[name*='submission_requirements'], textarea[name*='requirements']", submission_requirements)
                    result["updated_fields"].append("submission_requirements")
                    result["steps"].append("Updated submission requirements")
                except Exception as e:
                    logger.debug("Could not update submission requirements: %s", e)
                    result["steps"].append(f"Could not update submission requirements: {e}")

            if dry_run:
                result["success"] = True
                result["message"] = "DRY RUN - Changes would be saved"
                return result

            if result["updated_fields"]:
                result["steps"].append("Saving changes")
                await page.click("button[type='submit'], input[type='submit'], button:has-text('Save')")
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)

            result["success"] = True
            result["message"] = "Description updated successfully"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def configure_rules(
        self,
        slug: str,
        rules_text: Optional[str] = None,
        resources: Optional[list[dict[str, str]]] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Configure Rules & Resources settings."""
        from .core import DevpostError
        
        result = {
            "success": False,
            "slug": slug,
            "updated_fields": [],
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
            edit_url = f"{MANAGE_BASE_URL}/{slug}/edit#hackathon_site"
            result["steps"].append(f"Navigating to {edit_url}")
            await page.goto(edit_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            if rules_text:
                try:
                    # Rules is typically a rich text editor
                    await page.fill("textarea[name*='rules'], div[name*='rules']", rules_text)
                    result["updated_fields"].append("rules")
                    result["steps"].append("Updated rules text")
                except Exception as e:
                    logger.debug("Could not update rules: %s", e)
                    result["steps"].append(f"Could not update rules: {e}")

            if resources:
                for i, resource in enumerate(resources[:10]):  # Limit to 10 resources
                    try:
                        # Add resource link
                        await page.click("button:has-text('Add Resource'), a:has-text('Add Resource')")
                        await asyncio.sleep(0.5)
                        
                        # Fill title
                        title_input = page.locator(f"input[name*='resource[{i}][title]']").first
                        await title_input.fill(resource.get("title", ""))
                        
                        # Fill URL
                        url_input = page.locator(f"input[name*='resource[{i}][url]']").first
                        await url_input.fill(resource.get("url", ""))
                        
                        result["steps"].append(f"Added resource: {resource.get('title')}")
                    except Exception as e:
                        logger.debug("Could not add resource %d: %s", i, e)
                
                if resources:
                    result["updated_fields"].append("resources")

            if dry_run:
                result["success"] = True
                result["message"] = "DRY RUN - Changes would be saved"
                return result

            if result["updated_fields"]:
                result["steps"].append("Saving changes")
                await page.click("button[type='submit'], input[type='submit'], button:has-text('Save')")
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)

            result["success"] = True
            result["message"] = "Rules & Resources updated successfully"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def list_managed_hackathons(self, limit: int = 20) -> dict[str, Any]:
        """List hackathons managed by the current user.
        
        Args:
            limit: Maximum number of hackathons to return
            
        Returns:
            Dict with list of hackathons
        """
        from .core import DevpostError
        
        result = {
            "success": False,
            "hackathons": [],
            "steps": [],
        }

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            result["steps"].append(f"Navigating to manage dashboard")
            await page.goto(MANAGE_BASE_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # Extract hackathon list
            hackathons = await page.evaluate("""() => {
                const items = document.querySelectorAll('.hackathon-item, .manage-item, tr');
                const results = [];
                items.forEach(item => {
                    const link = item.querySelector('a[href*="/manage/"]');
                    if (link) {
                        const href = link.getAttribute('href');
                        const match = href.match(/\\/manage\\/([a-z0-9-]+)/);
                        if (match) {
                            results.push({
                                slug: match[1],
                                name: link.textContent.trim(),
                                url: href.startsWith('http') ? href : 'https://manage.devpost.com' + href,
                            });
                        }
                    }
                });
                return results.slice(0, 20);
            }""")

            result["hackathons"] = hackathons
            result["count"] = len(hackathons)
            result["success"] = True

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def get_hackathon_status(self, slug: str) -> dict[str, Any]:
        """Get the configuration status of a hackathon.
        
        Shows which tabs are complete/incomplete.
        
        Args:
            slug: Hackathon slug
            
        Returns:
            Status dict with completion info for each tab
        """
        from .core import DevpostError
        
        result = {
            "success": False,
            "slug": slug,
            "tabs": {},
            "steps": [],
        }

        try:
            browser, page = await self._get_browser_and_page()
        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
            return result

        try:
            edit_url = f"{MANAGE_BASE_URL}/{slug}/edit"
            result["steps"].append(f"Navigating to {edit_url}")
            await page.goto(edit_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # Extract tab completion status
            status = await page.evaluate("""() => {
                const tabs = document.querySelectorAll('.tab, .edit-tab, nav a[href*="#"]');
                const results = {};
                tabs.forEach(tab => {
                    const href = tab.getAttribute('href');
                    const text = tab.textContent.trim().toLowerCase();
                    if (href && href.includes('#')) {
                        const tabName = href.split('#')[1];
                        const isComplete = tab.classList.contains('complete') || 
                                          tab.classList.contains('filled') ||
                                          tab.querySelector('.complete, .filled, .check');
                        results[tabName] = {
                            name: text,
                            complete: !!isComplete,
                        };
                    }
                });
                return results;
            }""")

            result["tabs"] = status
            result["success"] = True

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result

    async def publish_hackathon(self, slug: str, dry_run: bool = False) -> dict[str, Any]:
        """Publish a hackathon (submit for Devpost review).
        
        Args:
            slug: Hackathon slug
            dry_run: If True, don't actually publish
            
        Returns:
            Result dict
        """
        from .core import DevpostError
        
        result = {
            "success": False,
            "slug": slug,
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
            edit_url = f"{MANAGE_BASE_URL}/{slug}/edit"
            result["steps"].append(f"Navigating to {edit_url}")
            await page.goto(edit_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            if dry_run:
                result["success"] = True
                result["message"] = "DRY RUN - Hackathon would be submitted for review"
                return result

            # Look for publish button
            result["steps"].append("Looking for publish button")
            publish_button = page.locator("button:has-text('Publish'), button:has-text('Submit'), input[value='Publish']")
            
            if await publish_button.count() == 0:
                result["error"] = "Publish button not found"
                result["code"] = "NOT_FOUND"
                return result

            await publish_button.first.click()
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            # Check for confirmation dialog
            try:
                confirm_btn = page.locator("button:has-text('Confirm'), button:has-text('Yes'), input[value='Publish']")
                if await confirm_btn.count() > 0:
                    await confirm_btn.first.click()
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(2)
            except Exception:
                pass  # No confirmation needed

            result["success"] = True
            result["message"] = "Hackathon submitted for Devpost review. You will be notified once approved."
            result["url"] = f"https://{slug}.devpost.com/"

        except DevpostError as e:
            result["error"] = e.message
            result["code"] = e.code
        except Exception as e:
            result["error"] = str(e)
            result["steps"].append(f"Error: {e}")

        return result
