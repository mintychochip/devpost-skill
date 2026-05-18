"""Tests for DevpostAPI class."""

import pytest
import respx
from httpx import Response

from devpost_cli.api import DevpostAPI, API_BASE


class TestDevpostAPISearchHackathons:
    """Test search_hackathons method."""

    @respx.mock
    async def test_search_hackathons_basic(self):
        """Test basic hackathon search."""
        mock_response = {
            "hackathons": [
                {"id": 1, "title": "Hackathon 1", "open_state": "open"},
                {"id": 2, "title": "Hackathon 2", "open_state": "upcoming"},
            ],
            "meta": {"total_count": 2, "per_page": 20},
        }
        respx.get(f"{API_BASE}/hackathons").mock(return_value=Response(200, json=mock_response))

        api = DevpostAPI()
        try:
            result = await api.search_hackathons(limit=20)
            
            assert "hackathons" in result
            assert "meta" in result
            assert len(result["hackathons"]) == 2
            assert result["meta"]["total_count"] == 2
        finally:
            await api.close()

    @respx.mock
    async def test_search_hackathons_with_filters(self):
        """Test hackathon search with filters."""
        mock_response = {
            "hackathons": [{"id": 1, "title": "AI Hack", "themes": [{"name": "Machine Learning/AI"}]}],
            "meta": {"total_count": 1},
        }
        route = respx.get(f"{API_BASE}/hackathons").mock(return_value=Response(200, json=mock_response))

        api = DevpostAPI()
        try:
            result = await api.search_hackathons(
                open_state="open",
                themes=["Machine Learning/AI"],
                limit=10,
            )
            
            assert len(result["hackathons"]) == 1
            # Verify query params were sent (check for URL-encoded theme param)
            request_url = str(route.calls.last.request.url)
            assert "themes%5B%5D" in request_url  # themes[]
            assert "Machine" in request_url
        finally:
            await api.close()

    @respx.mock
    async def test_search_hackathons_empty(self):
        """Test search with no results."""
        mock_response = {"hackathons": [], "meta": {"total_count": 0}}
        respx.get(f"{API_BASE}/hackathons").mock(return_value=Response(200, json=mock_response))

        api = DevpostAPI()
        try:
            result = await api.search_hackathons(search="nonexistent")
            assert result["hackathons"] == []
            assert result["meta"]["total_count"] == 0
        finally:
            await api.close()


class TestDevpostAPIGetThemes:
    """Test get_themes method."""

    @respx.mock
    async def test_get_themes_all(self):
        """Test getting all themes."""
        mock_response = [{"name": "Beginner Friendly"}, {"name": "Machine Learning/AI"}]
        respx.get(f"{API_BASE}/themes").mock(return_value=Response(200, json=mock_response))

        api = DevpostAPI()
        try:
            themes = await api.get_themes(popular=False)
            assert len(themes) == 2
            assert themes[0]["name"] == "Beginner Friendly"
        finally:
            await api.close()

    @respx.mock
    async def test_get_themes_popular(self):
        """Test getting popular themes."""
        mock_response = {
            "themes": [
                {"id": 23, "name": "Beginner Friendly", "formatted_current_usd_prize_amount": "$202,000"},
            ]
        }
        respx.get(f"{API_BASE}/themes/popular").mock(return_value=Response(200, json=mock_response))

        api = DevpostAPI()
        try:
            themes = await api.get_themes(popular=True)
            assert len(themes) == 1
            assert themes[0]["id"] == 23
        finally:
            await api.close()


class TestDevpostAPIGetFeaturedHackathons:
    """Test get_featured_hackathons method."""

    @respx.mock
    async def test_get_featured_online(self):
        """Test getting featured online hackathons."""
        mock_response = {
            "hackathons": [
                {"id": 1, "title": "Featured Hack", "featured": True},
            ]
        }
        route = respx.get(f"{API_BASE}/hackathons/featured_hackathons").mock(
            return_value=Response(200, json=mock_response)
        )

        api = DevpostAPI()
        try:
            hackathons = await api.get_featured_hackathons(challenge_type="online")
            assert len(hackathons) == 1
            assert "challenge_type=online" in str(route.calls.last.request.url)
        finally:
            await api.close()

    @respx.mock
    async def test_get_featured_in_person(self):
        """Test getting featured in-person hackathons."""
        mock_response = {"hackathons": []}
        route = respx.get(f"{API_BASE}/hackathons/featured_hackathons").mock(
            return_value=Response(200, json=mock_response)
        )

        api = DevpostAPI()
        try:
            hackathons = await api.get_featured_hackathons(challenge_type="in-person")
            assert hackathons == []
            assert "challenge_type=in-person" in str(route.calls.last.request.url)
        finally:
            await api.close()


class TestDevpostAPIOrganizations:
    """Test search_organizations method."""

    @respx.mock
    async def test_search_organizations_with_term(self):
        """Test searching organizations with a term."""
        mock_response = [
            {"id": 151, "name": "Facebook", "count": 66},
            {"id": 177, "name": "Google", "count": 57},
        ]
        route = respx.get(f"{API_BASE}/organizations").mock(return_value=Response(200, json=mock_response))

        api = DevpostAPI()
        try:
            orgs = await api.search_organizations(term="")
            assert len(orgs) == 2
            assert orgs[0]["name"] == "Facebook"
            assert "term=" in str(route.calls.last.request.url)
        finally:
            await api.close()


class TestDevpostAPIRetry:
    """Test retry logic."""

    @respx.mock
    async def test_retry_on_503(self):
        """Test retry on 503 error."""
        # First call returns 503, second returns 200
        respx.get(f"{API_BASE}/themes").mock(
            side_effect=[
                Response(503, text="Service Unavailable"),
                Response(200, json=[{"name": "Theme"}]),
            ]
        )

        api = DevpostAPI(retries=3)
        try:
            themes = await api.get_themes()
            assert len(themes) == 1
        finally:
            await api.close()

    @respx.mock
    async def test_retry_exhausted(self):
        """Test when retries are exhausted."""
        respx.get(f"{API_BASE}/themes").mock(return_value=Response(503, text="Service Unavailable"))

        api = DevpostAPI(retries=2)
        try:
            with pytest.raises(Exception):  # Should raise after retries exhausted
                await api.get_themes()
        finally:
            await api.close()
