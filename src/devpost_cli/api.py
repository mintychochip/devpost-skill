"""Lightweight HTTP API client for Devpost's public JSON endpoints.

This module provides direct API access to Devpost's public JSON endpoints,
avoiding the need for Playwright browser automation for hackathon search/listing.

All endpoints in this module work without authentication and return structured JSON.
"""

import asyncio
import httpx
from typing import Any, Optional

from .logging_config import get_logger

logger = get_logger("api")

API_BASE = "https://devpost.com/api"

# Default HTTP client configuration
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3
RETRY_STATUS_CODES = {429, 502, 503, 504}


class DevpostAPI:
    """Lightweight HTTP client for Devpost's public JSON API endpoints.
    
    This class provides direct access to Devpost's API without requiring
    Playwright browser automation. All methods return structured Python dicts.
    
    Example:
        api = DevpostAPI()
        hackathons = await api.search_hackathons(open_state="open", limit=10)
    """
    
    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ):
        self.timeout = timeout
        self.retries = retries
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                },
                follow_redirects=True,
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def _request_with_retry(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
    ) -> httpx.Response:
        """Make HTTP request with retry logic for transient errors."""
        client = await self._get_client()
        last_error = None
        
        for attempt in range(self.retries):
            try:
                response = await client.request(method, url, params=params)
                
                # Don't retry on client errors (4xx) except 429
                if response.status_code < 500 and response.status_code != 429:
                    return response
                
                if response.status_code in RETRY_STATUS_CODES:
                    last_error = httpx.HTTPStatusError(
                        f"Server error {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                    if attempt < self.retries - 1:
                        delay = 1.0 * (2 ** attempt)  # Exponential backoff
                        logger.debug(f"Retrying {url} in {delay}s (attempt {attempt + 1}/{self.retries})")
                        await asyncio.sleep(delay)
                        continue
                
                return response
                
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteError) as e:
                last_error = e
                if attempt < self.retries - 1:
                    delay = 1.0 * (2 ** attempt)
                    logger.debug(f"Retrying {url} after error: {e} (attempt {attempt + 1}/{self.retries})")
                    await asyncio.sleep(delay)
                    continue
                raise
        
        raise last_error or httpx.HTTPError("Unknown error")
    
    async def search_hackathons(
        self,
        search: Optional[str] = None,
        open_state: Optional[str] = None,
        status: Optional[list[str]] = None,
        themes: Optional[list[str]] = None,
        open_to: Optional[list[str]] = None,
        eligibility: Optional[bool] = None,
        managed_by_devpost_badge: Optional[bool] = None,
        limit: int = 20,
        page: int = 1,
        sort_by: Optional[str] = None,
    ) -> dict[str, Any]:
        """Search and list hackathons.
        
        Args:
            search: Text search query
            open_state: Filter by open state ("open", "upcoming", "ended")
            status: List of status filters (alternative to open_state)
            themes: List of theme names to filter by
            open_to: List of eligibility filters (e.g., ["all"])
            eligibility: Filter by eligibility requirement
            managed_by_devpost_badge: Filter by Devpost-managed badge
            limit: Number of results per page
            page: Page number
            sort_by: Sort order (e.g., "prize amount", "recently added")
        
        Returns:
            Dict with "hackathons" list and "meta" dict
        
        Example:
            result = await api.search_hackathons(
                open_state="open",
                themes=["Machine Learning/AI"],
                limit=10
            )
            for h in result["hackathons"]:
                print(h["title"], h["prize_amount"])
        """
        params: dict[str, Any] = {"limit": limit}
        
        if search:
            params["search"] = search
        if open_state:
            params["open_state"] = open_state
        if status:
            for s in status:
                params.setdefault("status[]", []).append(s)
        if themes:
            for t in themes:
                params.setdefault("themes[]", []).append(t)
        if open_to:
            for o in open_to:
                params.setdefault("open_to[]", []).append(o)
        if eligibility is not None:
            params["eligibility"] = "1" if eligibility else "0"
        if managed_by_devpost_badge is not None:
            params["managed_by_devpost_badge"] = "1" if managed_by_devpost_badge else "0"
        if page > 1:
            params["page"] = page
        if sort_by:
            params["sort_by"] = sort_by
        
        response = await self._request_with_retry(
            "GET",
            f"{API_BASE}/hackathons",
            params=params,
        )
        response.raise_for_status()
        return response.json()
    
    async def get_hackathon_by_slug(self, slug: str) -> Optional[dict[str, Any]]:
        """Get a single hackathon by its slug.
        
        Args:
            slug: Hackathon slug (e.g., "rapid-agent" for rapid-agent.devpost.com)
        
        Returns:
            Hackathon dict or None if not found
        """
        result = await self.search_hackathons(search=slug, limit=1)
        hackathons = result.get("hackathons", [])
        return hackathons[0] if hackathons else None
    
    async def get_featured_hackathons(
        self,
        challenge_type: str = "online",
    ) -> list[dict[str, Any]]:
        """Get featured hackathons.
        
        Args:
            challenge_type: "online" or "in-person"
        
        Returns:
            List of featured hackathons
        """
        response = await self._request_with_retry(
            "GET",
            f"{API_BASE}/hackathons/featured_hackathons",
            params={"challenge_type": challenge_type},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("hackathons", [])
    
    async def get_recommended_hackathons(self) -> list[dict[str, Any]]:
        """Get recommended hackathons.
        
        Note: Returns empty list without authentication.
        
        Returns:
            List of recommended hackathons (may be empty)
        """
        response = await self._request_with_retry(
            "GET",
            f"{API_BASE}/hackathons/recommended_hackathons",
        )
        response.raise_for_status()
        data = response.json()
        return data.get("hackathons", [])
    
    async def get_nearby_hackathons(self) -> list[dict[str, Any]]:
        """Get nearby hackathons.
        
        Note: Returns empty list without authentication/location.
        
        Returns:
            List of nearby hackathons (may be empty)
        """
        response = await self._request_with_retry(
            "GET",
            f"{API_BASE}/hackathons/nearby_hackathons",
        )
        response.raise_for_status()
        data = response.json()
        return data.get("hackathons", [])
    
    async def get_themes(self, popular: bool = False) -> list[dict[str, Any]]:
        """Get all themes or popular themes.
        
        Args:
            popular: If True, get popular themes with metadata
        
        Returns:
            List of themes
        """
        endpoint = "themes/popular" if popular else "themes"
        response = await self._request_with_retry(
            "GET",
            f"{API_BASE}/{endpoint}",
        )
        response.raise_for_status()
        data = response.json()
        
        # Handle both response formats
        if isinstance(data, dict):
            return data.get("themes", [])
        elif isinstance(data, list):
            return data
        return []
    
    async def search_organizations(self, term: str = "") -> list[dict[str, Any]]:
        """Search organizations.
        
        Args:
            term: Search term (empty string returns all)
        
        Returns:
            List of organizations with id, name, count
        """
        response = await self._request_with_retry(
            "GET",
            f"{API_BASE}/organizations",
            params={"term": term},
        )
        response.raise_for_status()
        return response.json()
    
    async def get_user_eligibility(self) -> dict[str, Any]:
        """Get current user's eligibility status.
        
        Note: Requires authentication (session cookies).
        
        Returns:
            Dict with eligibility_filled_in, user_signed_in, url
        """
        response = await self._request_with_retry(
            "GET",
            f"{API_BASE}/user_eligibility",
        )
        response.raise_for_status()
        return response.json()
    
    async def get_hackathons_rss(self) -> dict[str, Any]:
        """Get hackathons RSS feed (returns JSON).
        
        Returns:
            Dict with "hackathons" list and "meta" dict
        """
        response = await self._request_with_retry(
            "GET",
            f"{API_BASE}/hackathons.rss",
        )
        response.raise_for_status()
        return response.json()


# Convenience function for quick API access
async def search_hackathons(**kwargs) -> dict[str, Any]:
    """Convenience function to search hackathons.
    
    Example:
        result = await search_hackathons(open_state="open", limit=10)
    """
    api = DevpostAPI()
    try:
        return await api.search_hackathons(**kwargs)
    finally:
        await api.close()


async def get_themes(popular: bool = False) -> list[dict[str, Any]]:
    """Convenience function to get themes."""
    api = DevpostAPI()
    try:
        return await api.get_themes(popular=popular)
    finally:
        await api.close()
