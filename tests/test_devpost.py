"""Legacy tests for Devpost CLI and core module."""

import pytest
from click.testing import CliRunner

from devpost_cli.cli import cli
from devpost_cli.core import DevpostClient


class TestDevpostClientLegacy:
    """Legacy HTTP client tests - these hit the real Devpost API.
    
    Marked as integration tests to skip during normal test runs.
    Run with: pytest -m integration
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_list_hackathons(self):
        """Test listing hackathons (real API)."""
        async with DevpostClient() as client:
            hackathons = await client.list_hackathons(limit=5)
            assert isinstance(hackathons, list)
            assert len(hackathons) > 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_hackathon_by_slug(self):
        """Test getting hackathon by slug (real API)."""
        async with DevpostClient() as client:
            hackathon = await client.get_hackathon_by_slug("zervehack")
            if hackathon:
                assert "title" in hackathon
                assert "url" in hackathon

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_search_hackathons(self):
        """Test searching hackathons (real API)."""
        async with DevpostClient() as client:
            hackathons = await client.list_hackathons(query="AI", limit=5)
            assert isinstance(hackathons, list)


class TestCLILegacy:
    """Legacy CLI tests."""

    def test_help(self):
        """Test CLI help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Devpost CLI" in result.output

    def test_list_help(self):
        """Test list command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--help"])
        assert result.exit_code == 0
        assert "List hackathons" in result.output

    def test_info_help(self):
        """Test info command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["info", "--help"])
        assert result.exit_code == 0
        assert "Get hackathon details" in result.output

    def test_search_help(self):
        """Test search command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert result.exit_code == 0
        assert "Search hackathons" in result.output

    def test_auth_help(self):
        """Test auth commands help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["auth", "--help"])
        assert result.exit_code == 0
        assert "Authentication commands" in result.output

    def test_team_help(self):
        """Test team commands help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["team", "--help"])
        assert result.exit_code == 0
        assert "Team management commands" in result.output

    def test_submit_help(self):
        """Test submit commands help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["submit", "--help"])
        assert result.exit_code == 0
        assert "Submit and manage projects" in result.output
