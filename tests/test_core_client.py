"""Tests for DevpostClient HTTP client."""

import pytest
import respx
from httpx import Response
from unittest.mock import patch, AsyncMock

from devpost_cli.core import DevpostClient, DevpostError, _signal_time_pressure, _signal_prize_density, _signal_competition_density, _signal_submission_gap, _signal_theme_fit, _compute_verdict


class TestDevpostClient:
    """Test the unauthenticated HTTP client."""

    @pytest.mark.asyncio
    async def test_list_hackathons_returns_dict(self, mock_devpost_api):
        """Test that list_hackathons returns a dict with hackathons list."""
        async with DevpostClient() as client:
            result = await client.list_hackathons(limit=5)
            assert isinstance(result, dict)
            assert "hackathons" in result
            assert isinstance(result["hackathons"], list)

    @pytest.mark.asyncio
    async def test_list_hackathons_with_status(self, mock_devpost_api):
        """Test filtering by status[]."""
        async with DevpostClient(use_cache=False) as client:
            await client.list_hackathons(open_state="open", limit=5)
            
            request = mock_devpost_api["hackathons"].calls.last.request
            assert "status[]" in request.url.params
            assert request.url.params["status[]"] == "open"

    @pytest.mark.asyncio
    async def test_list_hackathons_with_order_by(self, mock_devpost_api):
        """Test sorting by different criteria."""
        async with DevpostClient(use_cache=False) as client:
            await client.list_hackathons(order_by="prize-amount", limit=5)
            
            request = mock_devpost_api["hackathons"].calls.last.request
            assert request.url.params["order_by"] == "prize-amount"

    @pytest.mark.asyncio
    async def test_list_hackathons_with_search(self, mock_devpost_api):
        """Test searching with search parameter."""
        async with DevpostClient(use_cache=False) as client:
            await client.list_hackathons(search="AI", limit=5)
            
            request = mock_devpost_api["hackathons"].calls.last.request
            assert request.url.params["search"] == "AI"

    @pytest.mark.asyncio
    async def test_get_hackathon_by_slug_found(self, mock_devpost_api):
        """Test getting hackathon by slug when it exists."""
        async with DevpostClient() as client:
            result = await client.get_hackathon_by_slug("test-hackathon")
            assert result is not None
            assert result["title"] == "Test Hackathon"

    @pytest.mark.asyncio
    async def test_get_hackathon_by_slug_not_found(self, mock_devpost_api):
        """Test getting hackathon by slug when it doesn't exist."""
        # Mock empty response
        mock_devpost_api.get("https://devpost.com/api/hackathons").mock(
            return_value=Response(200, json={"hackathons": []})
        )
        
        async with DevpostClient() as client:
            result = await client.get_hackathon_by_slug("nonexistent")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_hackathon_details(self, mock_hackathon_html):
        """Test scraping hackathon details."""
        with respx.mock:
            respx.get("https://test.devpost.com/").mock(
                return_value=Response(200, text=mock_hackathon_html)
            )
            
            async with DevpostClient() as client:
                result = await client.get_hackathon_details("https://test.devpost.com/")
                
                assert result["title"] == "Test Hackathon"
                assert result["description"] == "Test description"
                assert result["image_url"] == "https://example.com/image.jpg"
                assert result["rules_url"] == "https://test.devpost.com/rules"

    @pytest.mark.asyncio
    async def test_scrape_hackathon_page(self, mock_hackathon_html):
        """Test deep scraping hackathon page."""
        with respx.mock:
            respx.get("https://test.devpost.com/").mock(
                return_value=Response(200, text=mock_hackathon_html)
            )
            
            async with DevpostClient() as client:
                result = await client.scrape_hackathon_page("https://test.devpost.com/")
                
                assert result["success"] is True
                assert result["data"]["title"] == "Test Hackathon"
                assert "prize_text" in result["data"]

    @pytest.mark.asyncio
    async def test_list_hackathon_projects(self, mock_gallery_html):
        """Test listing projects from gallery."""
        with respx.mock:
            respx.get("https://test.devpost.com/project-gallery").mock(
                return_value=Response(200, text=mock_gallery_html)
            )
            
            async with DevpostClient(use_cache=False) as client:
                result = await client.list_hackathon_projects(
                    "https://test.devpost.com/",
                    limit=10,
                )
                
                assert result["success"] is True
                assert result["count"] == 2
                assert len(result["projects"]) == 2
                assert result["projects"][0]["title"] == "Project One"
                assert result["projects"][0]["is_winner"] is True

    @pytest.mark.asyncio
    async def test_list_hackathon_projects_winners_only(self, mock_gallery_html):
        """Test filtering to winners only."""
        with respx.mock:
            respx.get("https://test.devpost.com/project-gallery").mock(
                return_value=Response(200, text=mock_gallery_html)
            )
            
            async with DevpostClient(use_cache=False) as client:
                result = await client.list_hackathon_projects(
                    "https://test.devpost.com/",
                    winners_only=True,
                )
                
                assert result["success"] is True
                assert result["count"] == 1
                assert result["projects"][0]["is_winner"] is True

    @pytest.mark.asyncio
    async def test_get_project_details(self, mock_playwright):
        """Test getting project details with browser automation."""
        mock_page = mock_playwright["page"]
        
        # Setup proper async mocks for page methods
        from unittest.mock import AsyncMock
        
        async def mock_text_content():
            return "Test Project"
        
        mock_title_elem = AsyncMock()
        mock_title_elem.text_content = mock_text_content
        mock_page.wait_for_selector = AsyncMock(return_value=mock_title_elem)
        mock_page.query_selector = AsyncMock(return_value=None)
        mock_page.goto = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        
        async with DevpostClient() as client:
            result = await client.get_project_details("https://devpost.com/software/test")
            
            assert result["success"] is True
            # Title should be extracted from mock
            assert result["data"]["title"] is not None

    @pytest.mark.asyncio
    async def test_client_cleanup(self):
        """Test that client closes HTTP client properly."""
        client = DevpostClient()
        await client.close()
        assert client.client.is_closed

    @pytest.mark.asyncio
    async def test_parse_rules_page_success(self):
        """Test parsing a rules page with structured sections."""
        rules_html = """
        <html><body>
            <h2>Eligibility</h2>
            <ul><li>Must be 18 or older</li><li>Individuals and teams</li></ul>
            <h2>Requirements</h2>
            <ul><li>Use sponsor API</li><li>Submit by deadline</li></ul>
            <h2>Judging Criteria</h2>
            <ul><li>Innovation (40%)</li><li>Impact (30%)</li></ul>
            <h2>Sponsor APIs</h2>
            <ul><li>Must use Baidu API</li></ul>
            <p>Grand Prize $10,000</p>
            <p>Second Place $5,000</p>
        </body></html>
        """
        with respx.mock:
            respx.get("https://test-hack.devpost.com/rules").mock(
                return_value=Response(200, text=rules_html)
            )
            async with DevpostClient(use_cache=False) as client:
                result = await client.parse_rules_page("test-hack")
                assert result["success"] is True
                assert "Must be 18 or older" in result["eligibility"]
                assert "Use sponsor API" in result["requirements"]
                assert "Innovation (40%)" in result["judging_criteria"]
                assert "Must use Baidu API" in result["sponsor_apis"]
                assert len(result["prize_categories"]) >= 1

    @pytest.mark.asyncio
    async def test_parse_rules_page_cache_hit(self):
        """Test that parse_rules_page returns cached data."""
        from devpost_cli.cache import CacheManager
        cache = CacheManager(default_ttl=3600)
        cached_data = {
            "success": True, "slug": "test-hack", "url": "https://test-hack.devpost.com/rules",
            "eligibility": ["cached item"], "requirements": [], "judging_criteria": [],
            "prize_categories": [], "key_dates": [], "sponsor_apis": [],
        }
        from devpost_cli.cache import make_rules_key
        cache.set(make_rules_key("test-hack"), cached_data)

        with patch("devpost_cli.core.CacheManager", return_value=cache):
            async with DevpostClient(use_cache=True) as client:
                client._cache = cache
                result = await client.parse_rules_page("test-hack")
                assert result["eligibility"] == ["cached item"]

    @pytest.mark.asyncio
    async def test_parse_rules_page_not_found(self):
        """Test parse_rules_page with 404."""
        with respx.mock:
            respx.get("https://notfound.devpost.com/rules").mock(
                return_value=Response(404, text="Not Found")
            )
            async with DevpostClient(use_cache=False) as client:
                result = await client.parse_rules_page("notfound")
                assert result["success"] is False
                assert result.get("code") == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_parse_rules_page_api_error(self):
        """Test parse_rules_page when API returns a retryable server error."""
        with respx.mock:
            route = respx.get("https://broken.devpost.com/rules").mock(
                return_value=Response(503, text="Service Unavailable")
            )
            async with DevpostClient(use_cache=False) as client:
                result = await client.parse_rules_page("broken")
                assert result["success"] is False
                assert result.get("error") is not None

    @pytest.mark.asyncio
    async def test_get_winners_from_gallery(self):
        """Test get_winners returning winners from gallery."""
        gallery_html = """
        <html><body>
            <div class="software-entry">
                <a href="/software/winner-1"><h3>Winner Project</h3></a>
                <span class="winner-badge">1st Place</span>
            </div>
        </body></html>
        """
        with respx.mock:
            respx.get("https://test-hack.devpost.com/project-gallery").mock(
                return_value=Response(200, text=gallery_html)
            )
            async with DevpostClient(use_cache=False) as client:
                result = await client.get_winners("test-hack")
                assert result["success"] is True
                assert result["count"] >= 1

    @pytest.mark.asyncio
    async def test_get_winners_no_winners(self):
        """Test get_winners when no winners found."""
        gallery_html = """<html><body><h1>No projects</h1></body></html>"""
        with respx.mock:
            respx.get("https://test-hack.devpost.com/project-gallery").mock(
                return_value=Response(200, text=gallery_html)
            )
            respx.get("https://test-hack.devpost.com/winners").mock(
                return_value=Response(200, text="<html><body><p>No winners yet</p></body></html>")
            )
            async with DevpostClient(use_cache=False) as client:
                result = await client.get_winners("test-hack")
                assert result["success"] is True
                assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_list_hackathons_closed_alias(self):
        """Test that --state closed maps to ended and pages through API."""
        ended_hackathon = {
            "title": "Ended Hack",
            "url": "https://ended.devpost.com/",
            "open_state": "ended",
            "prize_amount": "$5,000",
        }
        open_hackathon = {
            "title": "Open Hack",
            "url": "https://open.devpost.com/",
            "open_state": "open",
        }

        def side_effect(request):
            page = int(request.url.params.get("page", "1"))
            if page == 18:
                return Response(200, json={"hackathons": [ended_hackathon]})
            return Response(200, json={"hackathons": [open_hackathon]})

        with respx.mock:
            respx.get("https://devpost.com/api/hackathons").mock(side_effect=side_effect)
            async with DevpostClient(use_cache=False) as client:
                result = await client.list_hackathons(limit=5, open_state="closed")
                hackathons_list = result.get("hackathons", [])
                assert len(hackathons_list) >= 1
                assert hackathons_list[0]["open_state"] == "ended"

    @pytest.mark.asyncio
    async def test_evaluate_hackathon_success(self):
        """Test evaluate_hackathon with full mock data."""
        info_data = {"hackathons": [{
            "title": "Test Hack",
            "url": "https://test-hack.devpost.com/",
            "open_state": "open",
            "prize_amount": "$50,000",
            "registrations_count": 1000,
            "prizes_counts": {"cash": 5, "other": 0},
            "submission_period_dates": "Jan 1 - Mar 1, 2026",
            "time_left_to_submission": "30 days left",
            "themes": [{"name": "AI"}],
            "organization_name": "TestOrg",
            "featured": False,
        }]}
        scrape_html = '<html><head><meta property="og:title" content="Test"></head><body></body></html>'
        rules_html = '<html><body><h2>Eligibility</h2><ul><li>Open to all</li></ul></body></html>'
        gallery_html = '<html><body><div class="software-entry"><a href="/software/p1"><h3>Proj</h3></a></div></body></html>'

        with respx.mock:
            respx.get("https://devpost.com/api/hackathons").mock(
                return_value=Response(200, json=info_data)
            )
            respx.get("https://test-hack.devpost.com/").mock(
                return_value=Response(200, text=scrape_html)
            )
            respx.get("https://test-hack.devpost.com/rules").mock(
                return_value=Response(200, text=rules_html)
            )
            respx.get("https://test-hack.devpost.com/project-gallery").mock(
                return_value=Response(200, text=gallery_html)
            )
            async with DevpostClient(use_cache=False) as client:
                result = await client.evaluate_hackathon("test-hack")
                assert result["success"] is True
                assert result["verdict"] in ("Enter", "Maybe", "Skip")
                assert "basics" in result
                assert "competition" in result
                assert "signals" in result

    @pytest.mark.asyncio
    async def test_evaluate_hackathon_with_skills(self):
        """Test evaluate with --skills flag for theme fit."""
        info_data = {"hackathons": [{
            "title": "AI Hack",
            "url": "https://ai-hack.devpost.com/",
            "open_state": "open",
            "prize_amount": "$10,000",
            "registrations_count": 500,
            "prizes_counts": {"cash": 3, "other": 0},
            "time_left_to_submission": "14 days left",
            "themes": [{"name": "Machine Learning/AI"}],
            "organization_name": "TestOrg",
            "featured": False,
        }]}
        scrape_html = '<html><body></body></html>'
        rules_html = '<html><body><h2>Sponsor APIs</h2><ul><li>Must use Python and OpenAI API</li></ul></body></html>'
        gallery_html = '<html><body></body></html>'

        with respx.mock:
            respx.get("https://devpost.com/api/hackathons").mock(
                return_value=Response(200, json=info_data)
            )
            respx.get("https://ai-hack.devpost.com/").mock(
                return_value=Response(200, text=scrape_html)
            )
            respx.get("https://ai-hack.devpost.com/rules").mock(
                return_value=Response(200, text=rules_html)
            )
            respx.get("https://ai-hack.devpost.com/project-gallery").mock(
                return_value=Response(200, text=gallery_html)
            )
            async with DevpostClient(use_cache=False) as client:
                result = await client.evaluate_hackathon("ai-hack", skills=["Python", "OpenAI"])
                assert result["success"] is True
                assert result["signals"]["theme_fit"]["level"] == "high"
                assert "python" in result["signals"]["theme_fit"]["matched_skills"]

    @pytest.mark.asyncio
    async def test_evaluate_hackathon_partial_data(self):
        """Test evaluate gracefully handles partial data (rules page fails)."""
        info_data = {"hackathons": [{
            "title": "Partial Hack",
            "url": "https://partial.devpost.com/",
            "open_state": "open",
            "prize_amount": "$5,000",
            "registrations_count": 100,
            "prizes_counts": {"cash": 1, "other": 0},
            "time_left_to_submission": "7 days left",
            "themes": [],
            "organization_name": "TestOrg",
            "featured": False,
        }]}
        scrape_html = '<html><body></body></html>'
        gallery_html = '<html><body></body></html>'

        with respx.mock:
            respx.get("https://devpost.com/api/hackathons").mock(
                return_value=Response(200, json=info_data)
            )
            respx.get("https://partial.devpost.com/").mock(
                return_value=Response(200, text=scrape_html)
            )
            respx.get("https://partial.devpost.com/rules").mock(
                return_value=Response(404, text="Not Found")
            )
            respx.get("https://partial.devpost.com/project-gallery").mock(
                return_value=Response(200, text=gallery_html)
            )
            async with DevpostClient(use_cache=False) as client:
                result = await client.evaluate_hackathon("partial")
                assert result["success"] is True
                assert len(result["errors"]) >= 1


class TestSignalFunctions:
    """Test signal computation helper functions."""

    def test_time_pressure_critical(self):
        sig = _signal_time_pressure(0.5, "open")
        assert sig["level"] == "critical"

    def test_time_pressure_high(self):
        sig = _signal_time_pressure(3.0, "open")
        assert sig["level"] == "high"

    def test_time_pressure_medium(self):
        sig = _signal_time_pressure(10.0, "open")
        assert sig["level"] == "medium"

    def test_time_pressure_low(self):
        sig = _signal_time_pressure(30.0, "open")
        assert sig["level"] == "low"

    def test_time_pressure_ended(self):
        sig = _signal_time_pressure(None, "ended")
        assert sig["level"] == "closed"

    def test_prize_density_high(self):
        sig = _signal_prize_density(6000)
        assert sig["level"] == "high"

    def test_prize_density_none(self):
        sig = _signal_prize_density(0)
        assert sig["level"] == "none"

    def test_competition_density_high(self):
        sig = _signal_competition_density(600)
        assert sig["level"] == "high"

    def test_competition_density_low(self):
        sig = _signal_competition_density(50)
        assert sig["level"] == "low"

    def test_submission_gap_wide_open(self):
        sig = _signal_submission_gap(1000, 0, "open")
        assert sig["level"] == "wide_open"

    def test_submission_gap_filling(self):
        sig = _signal_submission_gap(100, 50, "open")
        assert sig["level"] == "filling"

    def test_theme_fit_high(self):
        sig = _signal_theme_fit(["python", "ai"], ["Must use Python API"], ["AI"])
        assert sig["level"] == "high"
        assert "python" in sig["matched_skills"]

    def test_theme_fit_no_skills(self):
        sig = _signal_theme_fit(None, [], [])
        assert sig["level"] == "unknown"

    def test_compute_verdict_enter(self):
        signals = {
            "time_pressure": {"level": "low"},
            "prize_density": {"level": "high"},
            "competition_density": {"level": "low"},
            "submission_gap": {"level": "wide_open"},
            "theme_fit": {"level": "high"},
        }
        verdict, reason = _compute_verdict(signals, "open")
        assert verdict == "Enter"

    def test_compute_verdict_skip(self):
        signals = {
            "time_pressure": {"level": "critical"},
            "prize_density": {"level": "none"},
            "competition_density": {"level": "high"},
            "submission_gap": {"level": "filling"},
            "theme_fit": {"level": "low"},
        }
        verdict, reason = _compute_verdict(signals, "open")
        assert verdict == "Skip"

    def test_compute_verdict_ended(self):
        signals = {}
        verdict, reason = _compute_verdict(signals, "ended")
        assert verdict == "Skip"
        assert "ended" in reason.lower()
