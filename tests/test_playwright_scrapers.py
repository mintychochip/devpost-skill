"""Tests for Playwright-based scrapers and helpers."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from devpost_cli.core import DevpostClient, _get_random_user_agent, USER_AGENTS


class TestPlaywrightHelpers:
    """Test Playwright helper functions."""
    
    @pytest.mark.asyncio
    async def test_playwright_scrape_success(self):
        """Test _playwright_scrape with successful extraction."""
        client = DevpostClient()
        
        async def mock_extractor(page, result):
            result["data"] = {"title": "Test Project"}
        
        with patch("playwright.async_api.async_playwright") as mock_pw:
            mock_page = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_pw.return_value.__aenter__.return_value.chromium.launch.return_value = mock_browser
            mock_browser.new_page.return_value = mock_page
            mock_browser.__aenter__.return_value = mock_browser
            mock_browser.__aexit__.return_value = None
            mock_browser.new_context.return_value = mock_context
            mock_context.__aenter__.return_value = mock_context
            mock_context.__aexit__.return_value = None
            mock_context.new_page.return_value = mock_page
            
            result = await client._playwright_scrape(
                url="https://devpost.com/software/test",
                extractor_fn=mock_extractor,
            )
            
            assert result["success"] is True
            assert result["data"]["title"] == "Test Project"
    
    @pytest.mark.asyncio
    async def test_playwright_scrape_error(self):
        """Test _playwright_scrape with extraction error."""
        client = DevpostClient()
        
        async def failing_extractor(page, result):
            raise Exception("Selector not found")
        
        with patch("playwright.async_api.async_playwright") as mock_pw:
            mock_page = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_pw.return_value.__aenter__.return_value.chromium.launch.return_value = mock_browser
            mock_browser.new_page.return_value = mock_page
            mock_browser.__aenter__.return_value = mock_browser
            mock_browser.__aexit__.return_value = None
            mock_browser.new_context.return_value = mock_context
            mock_context.__aenter__.return_value = mock_context
            mock_context.__aexit__.return_value = None
            mock_context.new_page.return_value = mock_page
            
            result = await client._playwright_scrape(
                url="https://devpost.com/software/test",
                extractor_fn=failing_extractor,
            )
            
            assert result["success"] is False
            assert "error" in result
    
    @pytest.mark.asyncio
    async def test_extract_with_fallback(self):
        """Test selector fallback strategy."""
        client = DevpostClient()
        
        mock_page = AsyncMock()
        
        # First selector fails, second succeeds
        mock_page.wait_for_selector.side_effect = [
            Exception("Not found"),  # First selector fails
            MagicMock(),  # Second selector succeeds
        ]
        
        result = await client._extract_with_fallback(
            mock_page,
            ["#nonexistent", "h1"]
        )
        
        assert result is not None
        assert mock_page.wait_for_selector.call_count == 2
    
    @pytest.mark.asyncio
    async def test_extract_text_with_fallback(self):
        """Test text extraction with fallback."""
        client = DevpostClient()
        
        mock_page = AsyncMock()
        mock_elem = AsyncMock()
        mock_elem.text_content.return_value = "Test Content"
        
        mock_page.wait_for_selector.return_value = mock_elem
        
        result = await client._extract_text_with_fallback(
            mock_page,
            ["h1"],
            default="Default"
        )
        
        assert result == "Test Content"
    
    @pytest.mark.asyncio
    async def test_extract_text_with_fallback_default(self):
        """Test text extraction returns default when not found."""
        client = DevpostClient()
        
        mock_page = AsyncMock()
        mock_page.wait_for_selector.return_value = None
        
        result = await client._extract_text_with_fallback(
            mock_page,
            ["#nonexistent"],
            default="Default Value"
        )
        
        assert result == "Default Value"
    
    @pytest.mark.asyncio
    async def test_retry_selector_success(self):
        """Test retry selector succeeds on first try."""
        client = DevpostClient()
        
        mock_page = AsyncMock()
        mock_elem = MagicMock()
        mock_page.query_selector.return_value = mock_elem
        
        result = await client._retry_selector(mock_page, "h1")
        
        assert result == mock_elem
        assert mock_page.query_selector.call_count == 1
    
    @pytest.mark.asyncio
    async def test_retry_selector_success_after_retry(self):
        """Test retry selector succeeds after retry."""
        client = DevpostClient()
        
        mock_page = AsyncMock()
        mock_elem = MagicMock()
        
        # First call returns None, second returns element
        mock_page.query_selector.side_effect = [None, mock_elem]
        
        result = await client._retry_selector(mock_page, "h1", retries=3)
        
        assert result == mock_elem
        assert mock_page.query_selector.call_count == 2
    
    @pytest.mark.asyncio
    async def test_retry_selector_failure(self):
        """Test retry selector returns None after all retries."""
        client = DevpostClient()
        
        mock_page = AsyncMock()
        mock_page.query_selector.return_value = None
        
        result = await client._retry_selector(mock_page, "#nonexistent", retries=3)
        
        assert result is None
        assert mock_page.query_selector.call_count == 3


class TestUserAgentRotation:
    """Test user-agent rotation."""
    
    def test_get_random_user_agent(self):
        """Test that random UA is from valid list."""
        ua = _get_random_user_agent()
        assert ua in USER_AGENTS
        assert ua.startswith("Mozilla/5.0")
    
    def test_user_agent_variety(self):
        """Test that we get different UAs on multiple calls."""
        uas = [_get_random_user_agent() for _ in range(20)]
        # Should get at least 2 different UAs in 20 tries
        assert len(set(uas)) >= 2
    
    def test_user_agents_format(self):
        """Test all user agents have correct format."""
        for ua in USER_AGENTS:
            assert ua.startswith("Mozilla/5.0")
            assert "AppleWebKit" in ua or "Gecko" in ua
            assert len(ua) > 50
            assert len(ua) < 300


class TestJavaScriptExtractors:
    """Test JavaScript-based extraction helpers."""
    
    @pytest.mark.asyncio
    async def test_extract_project_cards(self):
        """Test project card extraction."""
        client = DevpostClient()
        
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = [
            {"title": "Project 1", "url": "https://devpost.com/software/p1", "tagline": "Cool project", "is_winner": False},
            {"title": "Project 2", "url": "https://devpost.com/software/p2", "tagline": "Winner project", "is_winner": True},
        ]
        
        result = await client._extract_project_cards(mock_page)
        
        assert len(result) == 2
        assert result[0]["title"] == "Project 1"
        assert result[1]["is_winner"] is True
        mock_page.evaluate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_extract_user_info(self):
        """Test user info extraction."""
        client = DevpostClient()
        
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = {
            "name": "John Doe",
            "bio": "Software developer",
            "skills": ["Python", "JavaScript"],
            "links": {"github": "https://github.com/john"},
        }
        
        result = await client._extract_user_info(mock_page)
        
        assert result["name"] == "John Doe"
        assert result["skills"] == ["Python", "JavaScript"]
        assert result["links"]["github"] == "https://github.com/john"
        mock_page.evaluate.assert_called_once()


class TestPlaywrightIntegration:
    """Integration tests for Playwright scrapers (require real browser)."""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_project_details_real(self):
        """Test get_project_details with real Devpost page."""
        client = DevpostClient(headless=True)
        
        # Use a well-known project that's unlikely to change
        result = await client.get_project_details(
            "https://devpost.com/software/example"
        )
        
        # Just verify the structure, not content (content may change)
        assert "success" in result
        assert "data" in result
        assert "steps" in result
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_user_profile_real(self):
        """Test get_user_profile with real Devpost user."""
        client = DevpostClient(headless=True)
        
        result = await client.get_user_profile("example")
        
        # Just verify the structure
        assert "success" in result
        assert "data" in result
        assert "username" in result or "data" in result
