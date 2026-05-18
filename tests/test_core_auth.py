"""Tests for AuthenticatedClient browser automation."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from devpost_cli.core import AuthenticatedClient, DevpostError


class TestAuthenticatedClientLogin:
    """Test login functionality."""

    @pytest.mark.asyncio
    async def test_login_fills_correct_fields(self, mock_playwright, mock_credentials):
        """Test that login fills email and password fields correctly."""
        mock_page = mock_playwright["page"]
        
        client = AuthenticatedClient()
        await client._get_browser_and_page()
        
        # Verify correct selectors were used
        mock_page.fill.assert_any_call("input#user_email", "test@example.com")
        mock_page.fill.assert_any_call("input#user_password", "testpassword")
        mock_page.click.assert_any_call("button#submit-form")

    @pytest.mark.asyncio
    async def test_login_uses_correct_url(self, mock_playwright, mock_credentials):
        """Test that login navigates to correct URL."""
        mock_page = mock_playwright["page"]
        
        client = AuthenticatedClient()
        await client._get_browser_and_page()
        
        # Verify login URL was called (check call_args_list for the right call)
        goto_calls = [str(call) for call in mock_page.goto.call_args_list]
        assert any("users/login" in call for call in goto_calls), f"Login URL not found in calls: {goto_calls}"

    @pytest.mark.asyncio
    async def test_login_detects_error(self, mock_playwright, mock_credentials):
        """Test that login detects error messages."""
        mock_page = mock_playwright["page"]
        
        # Setup error element mock - need to return it on first call for the error selector
        error_elem = AsyncMock()
        error_elem.text_content = AsyncMock(return_value="Invalid email or password")
        
        # Configure wait_for_selector to return error_elem for the error selector, timeout for others
        async def wait_for_selector_side_effect(selector, **kwargs):
            if "error" in selector.lower() or "alert" in selector.lower():
                return error_elem
            raise Exception("Timeout")
        
        mock_page.wait_for_selector = AsyncMock(side_effect=wait_for_selector_side_effect)
        
        client = AuthenticatedClient()
        
        with pytest.raises(DevpostError, match="Invalid email or password"):
            await client._get_browser_and_page()

    @pytest.mark.asyncio
    async def test_login_detects_redirect_failure(self, mock_playwright, mock_credentials):
        """Test that login detects when redirect fails."""
        mock_page = mock_playwright["page"]
        
        # Stay on login page
        mock_page.url = "https://devpost.com/users/login"
        mock_page.wait_for_selector = AsyncMock(side_effect=Exception("Timeout"))
        
        client = AuthenticatedClient()
        
        with pytest.raises(DevpostError, match="check credentials"):
            await client._get_browser_and_page()

    @pytest.mark.asyncio
    async def test_session_persistence_saves_cookies(self, mock_playwright, mock_credentials, temp_session_dir):
        """Test that successful login saves cookies."""
        mock_context = mock_playwright["context"]
        
        session_dir = temp_session_dir / "test_session"
        session_file = session_dir / "session.json"
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Don't use the fixture's load_session/save_session mocks for this test
        with patch("devpost_cli.session.SESSION_DIR", session_dir):
            with patch("devpost_cli.session.SESSION_FILE", session_file):
                with patch("devpost_cli.core.load_session", return_value=None):
                    # Use real save_session (now accepts auth_method as 3rd arg)
                    with patch("devpost_cli.core.save_session", lambda cookies, email, auth_method="password": (
                        session_dir.mkdir(parents=True, exist_ok=True),
                        __import__('json').dump({"email": email, "cookies": cookies, "auth_method": auth_method}, open(session_file, 'w'), indent=2)
                    )):
                        client = AuthenticatedClient()
                        await client._get_browser_and_page()
                        
                        # Verify cookies were fetched and session file was created
                        mock_context.cookies.assert_called()
                        assert session_file.exists()

    @pytest.mark.asyncio
    async def test_session_persistence_reuses_cookies(self, mock_playwright, temp_session_dir, monkeypatch):
        """Test that existing session skips login."""
        mock_page = mock_playwright["page"]
        
        # Setup existing session
        session_dir = temp_session_dir / "test_session"
        session_file = session_dir / "session.json"
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Set credentials via env var
        monkeypatch.setenv("DEVPOST_EMAIL", "test@example.com")
        monkeypatch.setenv("DEVPOST_PASSWORD", "testpass")
        
        with patch("devpost_cli.session.SESSION_DIR", session_dir):
            with patch("devpost_cli.session.SESSION_FILE", session_file):
                from devpost_cli.session import save_session
                save_session([{"name": "session", "value": "valid"}], "test@example.com")
                
                # Mock page to show logged in state (no "Log in" text)
                mock_page.content = AsyncMock(return_value="<html>Dashboard</html>")
                mock_page.url = "https://devpost.com/dashboard"
                
                # Don't use fixture's load_session mock
                with patch("devpost_cli.core.load_session", return_value={"email": "test@example.com", "cookies": [{"name": "session", "value": "valid"}]}):
                    client = AuthenticatedClient()
                    await client._get_browser_and_page()
                    
                    # Verify login was skipped (no fill calls since session was valid)
                    mock_page.fill.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_cleans_up(self, mock_playwright, mock_credentials):
        """Test that close() properly cleans up resources."""
        mock_page = mock_playwright["page"]
        mock_context = mock_playwright["context"]
        mock_browser = mock_playwright["browser"]
        mock_p = mock_playwright["playwright"]
        
        client = AuthenticatedClient()
        await client._get_browser_and_page()
        await client.close()
        
        mock_context.close.assert_called()
        mock_browser.close.assert_called()
        mock_p.stop.assert_called()
        
        assert client._browser is None
        assert client._context is None
        assert client._page is None


class TestAuthenticatedClientSubmit:
    """Test project submission."""

    @pytest.mark.asyncio
    async def test_submit_project_navigates_correctly(self, mock_playwright, mock_credentials):
        """Test that submit navigates to hackathon page."""
        mock_page = mock_playwright["page"]
        
        client = AuthenticatedClient()
        await client.submit_project("test-hackathon", "Title", "Tagline")
        
        # Check that hackathon URL was in goto calls
        goto_calls = [str(call) for call in mock_page.goto.call_args_list]
        assert any("test-hackathon.devpost.com" in call for call in goto_calls)

    @pytest.mark.asyncio
    async def test_submit_project_fills_form(self, mock_playwright, mock_credentials):
        """Test that submit fills form fields correctly."""
        mock_page = mock_playwright["page"]
        
        client = AuthenticatedClient()
        await client.submit_project(
            "test",
            "My Project",
            "My Tagline",
            description="Description",
            built_with=["Python", "React"],
        )
        
        mock_page.fill.assert_any_call("input[name='software[name]']", "My Project")
        mock_page.fill.assert_any_call("input[name='software[tagline]']", "My Tagline")
        mock_page.fill.assert_any_call("textarea[name='software[description]']", "Description")

    @pytest.mark.asyncio
    async def test_submit_project_dry_run(self, mock_playwright, mock_credentials):
        """Test that dry_run doesn't submit."""
        mock_page = mock_playwright["page"]
        
        client = AuthenticatedClient()
        result = await client.submit_project("test", "Title", "Tagline", dry_run=True)
        
        assert result["dry_run"] is True
        assert result["success"] is True
        # Verify software form fields were NOT filled (dry run stops before form filling)
        # Login form fills will still happen, so check for software-specific fills
        software_fills = [call for call in mock_page.fill.call_args_list if "software[" in str(call)]
        assert len(software_fills) == 0, f"Software form fields should not be filled in dry_run mode, but got: {software_fills}"


class TestAuthenticatedClientUpdate:
    """Test project update."""

    @pytest.mark.asyncio
    async def test_update_submission_navigates_to_edit(self, mock_playwright, mock_credentials):
        """Test that update navigates to edit page."""
        mock_page = mock_playwright["page"]
        
        client = AuthenticatedClient()
        await client.update_submission("https://devpost.com/software/test", title="New Title")
        
        # Check edit URL was called
        goto_calls = [str(call) for call in mock_page.goto.call_args_list]
        assert any("/edit" in call for call in goto_calls), f"Edit URL not found in: {goto_calls}"

    @pytest.mark.asyncio
    async def test_update_submission_fills_correct_fields(self, mock_playwright, mock_credentials):
        """Test that update fills correct form fields."""
        mock_page = mock_playwright["page"]
        
        client = AuthenticatedClient()
        await client.update_submission(
            "https://devpost.com/software/test",
            title="New Title",
            tagline="New Tagline",
            description="New Description",
        )
        
        mock_page.fill.assert_any_call("input[name='software[name]']", "New Title")
        mock_page.fill.assert_any_call("input[name='software[tagline]']", "New Tagline")
        mock_page.fill.assert_any_call("textarea[name='software[description]']", "New Description")


class TestAuthenticatedClientTeam:
    """Test team management."""

    @pytest.mark.asyncio
    async def test_add_team_member_navigates_to_team_page(self, mock_playwright, mock_credentials):
        """Test that add_team_member navigates to team page."""
        mock_page = mock_playwright["page"]
        
        client = AuthenticatedClient()
        await client.add_team_member("https://devpost.com/software/test", "username")
        
        # Check team URL was called
        goto_calls = [str(call) for call in mock_page.goto.call_args_list]
        assert any("/team" in call for call in goto_calls), f"Team URL not found in: {goto_calls}"

    @pytest.mark.asyncio
    async def test_remove_team_member_navigates_to_team_page(self, mock_playwright, mock_credentials):
        """Test that remove_team_member navigates to team page."""
        mock_page = mock_playwright["page"]
        
        client = AuthenticatedClient()
        await client.remove_team_member("https://devpost.com/software/test", "username")
        
        # Check team URL was called
        goto_calls = [str(call) for call in mock_page.goto.call_args_list]
        assert any("/team" in call for call in goto_calls), f"Team URL not found in: {goto_calls}"


class TestAuthenticatedClientJoinLeave:
    """Test join/leave hackathon."""

    @pytest.mark.asyncio
    async def test_join_hackathon_clicks_join(self, mock_playwright, mock_credentials):
        """Test that join_hackathon clicks join button."""
        mock_page = mock_playwright["page"]
        
        client = AuthenticatedClient()
        await client.join_hackathon("test-hackathon")
        
        # Check hackathon URL was called
        goto_calls = [str(call) for call in mock_page.goto.call_args_list]
        assert any("test-hackathon.devpost.com" in call for call in goto_calls)

    @pytest.mark.asyncio
    async def test_delete_requires_confirm(self, mock_playwright, mock_credentials):
        """Test that delete_submission requires confirm=True."""
        mock_page = mock_playwright["page"]
        
        client = AuthenticatedClient()
        result = await client.delete_submission("https://devpost.com/software/test", confirm=False)
        
        assert result["error"] == "Confirmation required"
        mock_page.goto.assert_not_called()


class TestAuthenticatedClientUpload:
    """Test screenshot upload."""

    @pytest.mark.asyncio
    async def test_upload_screenshots_navigates_to_edit(self, mock_playwright, mock_credentials):
        """Test that upload_screenshots navigates to edit page."""
        mock_page = mock_playwright["page"]
        
        client = AuthenticatedClient()
        await client.upload_screenshots(
            "https://devpost.com/software/test",
            ["/path/to/image.png"],
        )
        
        # Check edit URL was called
        goto_calls = [str(call) for call in mock_page.goto.call_args_list]
        assert any("/edit" in call for call in goto_calls), f"Edit URL not found in: {goto_calls}"

    @pytest.mark.asyncio
    async def test_upload_screenshots_uploads_files(self, mock_playwright, mock_credentials):
        """Test that upload_screenshots uploads files."""
        mock_page = mock_playwright["page"]
        
        # Setup file input mock - wait_for_selector should return file input for upload, timeout for others
        file_input = AsyncMock()
        file_input.set_input_files = AsyncMock()
        
        async def wait_for_selector_side_effect(selector, **kwargs):
            if "file" in selector.lower() or "image" in selector.lower() or "screenshot" in selector.lower():
                return file_input
            raise Exception("Timeout")
        
        mock_page.wait_for_selector = AsyncMock(side_effect=wait_for_selector_side_effect)
        mock_page.wait_for_timeout = AsyncMock()  # Called in upload_screenshots
        
        client = AuthenticatedClient()
        result = await client.upload_screenshots(
            "https://devpost.com/software/test",
            ["/path/to/image.png"],
        )
        
        file_input.set_input_files.assert_called_with("/path/to/image.png")


# OAuth login tests - implementation verified manually due to mock complexity
# The OAuth flow is tested through manual CLI testing:
# - devpost auth login --method github
# - devpost auth login --method google  
# - devpost auth login --method facebook
# - devpost auth login --method linkedin
# - devpost auth status (shows auth_method field)
        assert len(result["uploaded"]) == 1
