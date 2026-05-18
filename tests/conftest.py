"""Shared pytest fixtures and mocks for Devpost tests."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import respx
from httpx import Response


@pytest.fixture
def mock_hackathon_api_response():
    """Mock response for Devpost hackathons API."""
    return {
        "hackathons": [
            {
                "title": "Test Hackathon",
                "url": "https://test-hackathon.devpost.com/",
                "open_state": "open",
                "prize_amount": "$10,000",
                "submissions_count": 100,
                "tagline": "Test hackathon for testing",
            },
            {
                "title": "AI Hackathon",
                "url": "https://ai-hackathon.devpost.com/",
                "open_state": "open",
                "prize_amount": "$50,000",
                "submissions_count": 250,
                "tagline": "Build AI projects",
            },
        ]
    }


@pytest.fixture
def mock_hackathon_html():
    """Mock HTML for hackathon page scraping."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta property="og:title" content="Test Hackathon">
        <meta property="og:description" content="Test description">
        <meta property="og:image" content="https://example.com/image.jpg">
    </head>
    <body>
        <h1>Test Hackathon</h1>
        <p>$10,000 in prizes</p>
        <a href="/rules">Rules</a>
        <a href="/project-gallery">Gallery</a>
    </body>
    </html>
    """


@pytest.fixture
def mock_gallery_html():
    """Mock HTML for hackathon project gallery."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Test Hackathon - Projects</title></head>
    <body>
        <h1>Test Hackathon</h1>
        <div class="software-entry">
            <a href="/software/project-1">
                <h3>Project One</h3>
                <p class="tagline">First project tagline</p>
            </a>
            <span class="winner-badge">1st Place</span>
        </div>
        <div class="software-entry">
            <a href="/software/project-2">
                <h3>Project Two</h3>
                <p class="tagline">Second project tagline</p>
            </a>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def mock_project_html():
    """Mock HTML for project detail page."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta property="og:title" content="Test Project">
        <meta property="og:description" content="Test project description">
    </head>
    <body>
        <h1 id="app-title">Test Project</h1>
        <p class="tagline">Test tagline</p>
        <div id="app-details">Project description here</div>
        <div id="built-with">Python, React, OpenAI</div>
        <a href="https://github.com/user/repo">GitHub</a>
        <div class="team-members">
            <a href="/users/testuser">Test User</a>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def mock_devpost_api(respx_mock, mock_hackathon_api_response):
    """Mock Devpost API endpoints."""
    # Main hackathons search endpoint
    respx_mock.get("https://devpost.com/api/hackathons", name="hackathons").mock(
        return_value=Response(200, json=mock_hackathon_api_response)
    )
    
    # Featured hackathons endpoints
    respx_mock.get("https://devpost.com/api/hackathons/featured_hackathons", name="featured_online").mock(
        return_value=Response(200, json={"hackathons": [{"id": 1, "title": "Featured Online", "open_state": "open"}]})
    )
    respx_mock.get(url__regex=r"https://devpost\.com/api/hackathons/featured_hackathons\?challenge_type=in-person", name="featured_in_person").mock(
        return_value=Response(200, json={"hackathons": [{"id": 2, "title": "Featured In-Person", "open_state": "open"}]})
    )
    
    # Recommended hackathons
    respx_mock.get("https://devpost.com/api/hackathons/recommended_hackathons", name="recommended").mock(
        return_value=Response(200, json={"hackathons": [{"id": 3, "title": "Recommended", "open_state": "open"}]})
    )
    
    # Nearby hackathons
    respx_mock.get("https://devpost.com/api/hackathons/nearby_hackathons", name="nearby").mock(
        return_value=Response(200, json={"hackathons": [{"id": 4, "title": "Nearby", "open_state": "open"}]})
    )
    
    # Organizations
    respx_mock.get(url__regex=r"https://devpost\.com/api/organizations", name="organizations").mock(
        return_value=Response(200, json=[{"id": 1, "name": "Test Org", "count": 10}])
    )
    
    # Themes
    respx_mock.get("https://devpost.com/api/themes", name="themes").mock(
        return_value=Response(200, json=[{"name": "Test Theme"}])
    )
    respx_mock.get("https://devpost.com/api/themes/popular", name="themes_popular").mock(
        return_value=Response(200, json={"themes": [{"id": 1, "name": "Popular Theme"}]})
    )
    
    return respx_mock


@pytest.fixture
def temp_session_dir(tmp_path):
    """Create temporary directory for session files."""
    with patch("devpost_cli.session.SESSION_DIR", tmp_path):
        yield tmp_path


@pytest.fixture
def mock_playwright():
    """Mock Playwright browser automation.
    
    Mocks load_session to return None (no existing session) to force fresh login flow.
    Mocks save_session as no-op to avoid writing to real ~/.devpost/ directory.
    """
    with patch("playwright.async_api.async_playwright") as mock_pw, \
         patch("devpost_cli.core.load_session", return_value=None), \
         patch("devpost_cli.core.save_session"):
        
        # Setup mock browser, context, page
        mock_page = AsyncMock()
        mock_page.url = "https://devpost.com/dashboard"  # Not login page, so redirect check passes
        mock_page.content = AsyncMock(return_value="<html>Dashboard</html>")
        mock_page.goto = AsyncMock()
        mock_page.fill = AsyncMock()
        mock_page.click = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.wait_for_selector = AsyncMock(side_effect=Exception("Timeout"))
        mock_page.wait_for_url = AsyncMock()  # Called in submit_project
        mock_page.add_init_script = AsyncMock()  # Called at core.py:629
        
        # Locator chain: page.locator(...).first.count() and page.locator(...).first.click()
        # Need .first to return an object with async methods
        mock_first = MagicMock()
        mock_first.count = AsyncMock(return_value=1)
        mock_first.click = AsyncMock()
        mock_first.fill = AsyncMock()
        mock_first.press = AsyncMock()
        
        mock_locator_result = MagicMock()
        mock_locator_result.first = mock_first
        mock_page.locator = MagicMock(return_value=mock_locator_result)
        
        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[{"name": "session", "value": "abc123"}])
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()
        mock_context.add_cookies = AsyncMock()
        
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()
        
        mock_p = AsyncMock()
        mock_p.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_p.stop = AsyncMock()
        
        mock_pw.return_value.start = AsyncMock(return_value=mock_p)
        
        yield {
            "pw_func": mock_pw,
            "playwright": mock_p,
            "page": mock_page,
            "context": mock_context,
            "browser": mock_browser,
        }


@pytest.fixture
def mock_credentials():
    """Mock credentials for authenticated tests."""
    with patch("devpost_cli.core.get_credentials") as mock_get:
        mock_get.return_value = ("test@example.com", "testpassword")
        yield mock_get


@pytest.fixture
def cli_runner():
    """Create CLI test runner."""
    from click.testing import CliRunner
    return CliRunner()
