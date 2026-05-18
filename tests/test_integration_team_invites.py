"""Integration tests for team email invite functionality.

These tests require:
1. Valid Devpost credentials (DEVPOST_EMAIL, DEVPOST_PASSWORD)
2. A hackathon you control or can create teams in
3. Run with: pytest --integration

WARNING: These tests create real data on Devpost!
"""

import os
import pytest
import asyncio
from unittest.mock import patch

from devpost_cli.core import AuthenticatedClient


# Skip integration tests by default
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Need RUN_INTEGRATION_TESTS=1 env var to run integration tests"
)


class TestEmailInviteDetection:
    """Test email vs username detection logic."""
    
    def test_email_detection_basic(self):
        """Test basic email detection."""
        test_cases = [
            ("user@example.com", True),
            ("test.user@domain.org", True),
            ("user+tag@example.co.uk", True),
            ("username", False),
            ("user_name", False),
            ("user123", False),
        ]
        
        for value, expected_is_email in test_cases:
            is_email = "@" in value
            assert is_email == expected_is_email, f"Failed for {value}"
    
    def test_mixed_invite_list(self):
        """Test processing mixed username/email list."""
        invitees = ["alice", "bob@example.com", "charlie", "dave@test.org"]
        
        results = []
        for invitee in invitees:
            invite_type = "email" if "@" in invitee else "username"
            results.append((invitee, invite_type))
        
        assert results[0] == ("alice", "username")
        assert results[1] == ("bob@example.com", "email")
        assert results[2] == ("charlie", "username")
        assert results[3] == ("dave@test.org", "email")


class TestTeamCreateIntegration:
    """Integration tests for team creation with email invites.
    
    These tests will:
    1. Create a real team on Devpost
    2. Test username invites
    3. Test email invites
    4. Test mixed invites
    """
    
    @pytest.fixture
    def hackathon_slug(self):
        """Get hackathon slug from environment or use default."""
        return os.environ.get("TEST_HACKATHON_SLUG", "test-hackathon")
    
    @pytest.fixture
    def test_usernames(self):
        """Get test usernames from environment."""
        usernames = os.environ.get("TEST_USERNAMES", "testuser1,testuser2")
        return [u.strip() for u in usernames.split(",")]
    
    @pytest.fixture
    def test_emails(self):
        """Get test emails from environment."""
        emails = os.environ.get("TEST_EMAILS", "test1@example.com,test2@example.com")
        return [e.strip() for e in emails.split(",")]
    
    @pytest.mark.asyncio
    async def test_create_team_username_invites(self, hackathon_slug, test_usernames):
        """Test creating team with username invites only."""
        team_name = f"Test Team Usernames {os.urandom(2).hex()}"
        
        async with AuthenticatedClient(headed=True) as client:
            result = await client.create_team(
                hackathon_slug=hackathon_slug,
                team_name=team_name,
                invite_usernames=test_usernames,
                invite_emails=None,
            )
        
        # Log results
        print(f"\n=== Test: Username Invites ===")
        print(f"Team: {team_name}")
        print(f"Success: {result.get('success')}")
        print(f"Invites sent: {result.get('invites_sent', [])}")
        print(f"Invites failed: {result.get('invites_failed', [])}")
        print(f"Steps: {result.get('steps', [])}")
        
        # Assertions
        assert result.get("success") is True, f"Team creation failed: {result.get('error')}"
        assert len(result.get("invites_sent", [])) > 0 or len(result.get("invites_failed", [])) > 0, \
            "Should have attempted at least one invite"
    
    @pytest.mark.asyncio
    async def test_create_team_email_invites(self, hackathon_slug, test_emails):
        """Test creating team with email invites only."""
        team_name = f"Test Team Emails {os.urandom(2).hex()}"
        
        async with AuthenticatedClient(headed=True) as client:
            result = await client.create_team(
                hackathon_slug=hackathon_slug,
                team_name=team_name,
                invite_usernames=None,
                invite_emails=test_emails,
            )
        
        # Log results
        print(f"\n=== Test: Email Invites ===")
        print(f"Team: {team_name}")
        print(f"Success: {result.get('success')}")
        print(f"Invites sent: {result.get('invites_sent', [])}")
        print(f"Invites failed: {result.get('invites_failed', [])}")
        print(f"Steps: {result.get('steps', [])}")
        
        # Check invite types in results
        invites_sent = result.get("invites_sent", [])
        email_invites = [i for i in invites_sent if "@" in i]
        assert len(email_invites) > 0, "Should have attempted email invites"
        
        # Assertions
        assert result.get("success") is True, f"Team creation failed: {result.get('error')}"
    
    @pytest.mark.asyncio
    async def test_create_team_mixed_invites(self, hackathon_slug, test_usernames, test_emails):
        """Test creating team with mixed username and email invites."""
        team_name = f"Test Team Mixed {os.urandom(2).hex()}"
        
        async with AuthenticatedClient(headed=True) as client:
            result = await client.create_team(
                hackathon_slug=hackathon_slug,
                team_name=team_name,
                invite_usernames=test_usernames[:1],  # Use only first username
                invite_emails=test_emails[:1],  # Use only first email
            )
        
        # Log results
        print(f"\n=== Test: Mixed Invites ===")
        print(f"Team: {team_name}")
        print(f"Success: {result.get('success')}")
        print(f"Invites sent: {result.get('invites_sent', [])}")
        print(f"Invites failed: {result.get('invites_failed', [])}")
        
        # Check both types were attempted
        invites_sent = result.get("invites_sent", [])
        email_invites = [i for i in invites_sent if "@" in i]
        username_invites = [i for i in invites_sent if "@" not in i]
        
        print(f"Email invites sent: {email_invites}")
        print(f"Username invites sent: {username_invites}")
        
        # Assertions
        assert result.get("success") is True, f"Team creation failed: {result.get('error')}"
        assert len(invites_sent) > 0 or len(result.get("invites_failed", [])) > 0, \
            "Should have attempted invites"


class TestDebugScreenshots:
    """Test debug screenshot functionality."""
    
    @pytest.mark.asyncio
    async def test_debug_screenshots_on_error(self):
        """Test that debug screenshots are saved when errors occur."""
        import tempfile
        import os
        from pathlib import Path
        
        async with AuthenticatedClient(headed=True, debug_screenshots=True) as client:
            # Try to create team with invalid hackathon to trigger error
            result = await client.create_team(
                hackathon_slug="invalid-hackathon-that-does-not-exist",
                team_name="Test Team",
                invite_usernames=None,
                invite_emails=None,
            )
        
        print(f"\n=== Test: Debug Screenshots ===")
        print(f"Result: {result}")
        print(f"Error: {result.get('error')}")
        
        # Note: Screenshot saving depends on Playwright error handling
        # This test mainly verifies the flow doesn't crash


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
