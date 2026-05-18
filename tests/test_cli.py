"""Tests for CLI commands."""

import pytest
import respx
from unittest.mock import patch, AsyncMock
from click.testing import CliRunner
from httpx import Response

from devpost_cli.cli import cli
from devpost_cli import session


class TestCLIPublicCommands:
    """Test public (no-auth) CLI commands."""

    def test_hackathons_json_output(self, mock_devpost_api):
        """Test that hackathons --json outputs valid JSON."""
        runner = CliRunner()
        result = runner.invoke(cli, ["hackathons", "--limit", "2", "--json"])
        
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert isinstance(data, dict)  # Now returns dict with 'hackathons' and 'meta'

    def test_hackathons_state_filter(self, mock_devpost_api):
        """Test hackathons --state filter."""
        runner = CliRunner()
        result = runner.invoke(cli, ["hackathons", "--state", "open", "--limit", "2"])
        
        assert result.exit_code == 0

    def test_overview_slug(self, mock_hackathon_api_response):
        """Test overview command with slug."""
        with patch("devpost_cli.core.DevpostClient.get_hackathon_by_slug") as mock_get:
            mock_get.return_value = {"title": "Test", "url": "https://test.devpost.com/"}
            
            runner = CliRunner()
            result = runner.invoke(cli, ["overview", "test-hackathon"])
            
            assert result.exit_code == 0
            assert "Test" in result.output

    def test_details_command(self, mock_hackathon_api_response):
        """Test consolidated details command."""
        with patch("devpost_cli.core.DevpostClient.get_hackathon_by_slug") as mock_get:
            mock_get.return_value = {"title": "Test", "url": "https://test.devpost.com/", "submission_period_dates": "Jan 1 - Jan 31"}
            
            runner = CliRunner()
            result = runner.invoke(cli, ["details", "test-hackathon", "-s", "dates"])
            
            assert result.exit_code == 0
            assert "dates" in result.output.lower()

    def test_get_command_participants(self):
        """Test get -t participants command."""
        with patch("devpost_cli.core.DevpostClient.get_participants") as mock_get:
            mock_get.return_value = {"success": True, "count": 2, "participants": [{"username": "alice", "name": "Alice", "url": "..."}]}
            
            runner = CliRunner()
            result = runner.invoke(cli, ["get", "test-hackathon", "-t", "participants"])
            
            assert result.exit_code == 0
            assert "alice" in result.output.lower()

    def test_get_command_winners(self):
        """Test get -t winners command."""
        with patch("devpost_cli.core.DevpostClient.get_winners") as mock_get:
            mock_get.return_value = {"success": True, "count": 1, "winners": [{"title": "Winner Project", "prize": "1st Place", "url": "..."}]}
            
            runner = CliRunner()
            result = runner.invoke(cli, ["get", "test-hackathon", "-t", "winners"])
            
            assert result.exit_code == 0
            assert "Winner" in result.output

    def test_search(self, mock_devpost_api):
        """Test search command - now searches projects."""
        with respx.mock:
            respx.get("https://devpost.com/software/search").mock(
                return_value=Response(200, text="<html><body><article class='software-entry'><a href='/software/test'><h2>Test Project</h2></a></article></body></html>")
            )
            
            runner = CliRunner()
            result = runner.invoke(cli, ["search", "AI", "--limit", "2"])
            
            assert result.exit_code == 0

    def test_gallery_winners_only(self, mock_gallery_html):
        """Test gallery --winners flag (formerly projects command)."""
        with respx.mock:
            respx.get("https://test.devpost.com/project-gallery").mock(
                return_value=Response(200, text=mock_gallery_html)
            )
            
            runner = CliRunner()
            result = runner.invoke(cli, ["gallery", "test", "--winners"])
            
            assert result.exit_code == 0
            assert "Project One" in result.output


class TestCLIAuthCommands:
    """Test authentication CLI commands."""

    def test_auth_status_no_creds(self, monkeypatch):
        """Test auth status when no credentials set."""
        monkeypatch.delenv("DEVPOST_EMAIL", raising=False)
        monkeypatch.delenv("DEVPOST_PASSWORD", raising=False)
        
        with patch("devpost_cli.cli.get_credentials", return_value=None):
            runner = CliRunner()
            result = runner.invoke(cli, ["auth", "status"])
            
            assert result.exit_code == 0
            import json
            data = json.loads(result.output)
            assert data == {"authenticated": False}

    def test_auth_login_saves_creds(self, monkeypatch, tmp_path):
        """Test auth login saves credentials."""
        session_dir = tmp_path / "test_login"
        env_file = session_dir / ".env"
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Mock save_credentials to use our temp paths
        with patch("devpost_cli.session.SESSION_DIR", session_dir):
            with patch("devpost_cli.session.ENV_FILE", env_file):
                with patch("devpost_cli.cli.save_credentials_interactive") as mock_save:
                    mock_save.return_value = {"success": True, "email": "test@example.com"}
                    
                    runner = CliRunner()
                    result = runner.invoke(
                        cli,
                        ["auth", "login"],
                        input="test@example.com\ntestpassword\n",
                    )
                    
                    assert result.exit_code == 0
                    # save_credentials_interactive should have been called
                    assert mock_save.called


class TestCLISubmitCommands:
    """Test submission CLI commands."""

    def test_submit_project_dry_run(self, monkeypatch):
        """Test submit project with --dry-run."""
        monkeypatch.setenv("DEVPOST_EMAIL", "test@example.com")
        monkeypatch.setenv("DEVPOST_PASSWORD", "testpass")
        
        with patch("devpost_cli.core.AuthenticatedClient.submit_project") as mock_submit:
            mock_submit.return_value = {
                "success": True,
                "dry_run": True,
                "hackathon_slug": "test",
                "project_title": "Test Project",
            }
            
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "submit", "project", "test-hackathon",
                    "--title", "Test Project",
                    "--tagline", "Test Tagline",
                    "--dry-run",
                ],
            )
            
            assert result.exit_code == 0
            assert "DRY RUN" in result.output

    def test_update_no_fields_error(self, monkeypatch):
        """Test update exits with error when no fields specified."""
        monkeypatch.setenv("DEVPOST_EMAIL", "test@example.com")
        monkeypatch.setenv("DEVPOST_PASSWORD", "testpass")
        
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["update", "https://devpost.com/software/test"],
        )
        
        assert result.exit_code == 1
        assert "No fields to update" in result.output

    def test_delete_no_confirm(self, monkeypatch):
        """Test delete shows warning without --confirm."""
        monkeypatch.setenv("DEVPOST_EMAIL", "test@example.com")
        monkeypatch.setenv("DEVPOST_PASSWORD", "testpass")
        
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["delete", "https://devpost.com/software/test"],
        )
        
        # Delete without confirm should show warning and exit 0
        assert result.exit_code == 0
        assert "Confirmation" in result.output or "confirm" in result.output.lower()


class TestCLITeamCommands:
    """Test team management CLI commands."""

    def test_team_add(self, monkeypatch):
        """Test team add command."""
        monkeypatch.setenv("DEVPOST_EMAIL", "test@example.com")
        monkeypatch.setenv("DEVPOST_PASSWORD", "testpass")
        
        with patch("devpost_cli.core.AuthenticatedClient.add_team_member") as mock_add:
            mock_add.return_value = {
                "success": True,
                "message": "Added user to project",
            }
            
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["team", "add", "https://devpost.com/software/test", "username"],
            )
            
            assert result.exit_code == 0
            assert "Added" in result.output

    def test_team_remove(self, monkeypatch):
        """Test team remove command."""
        monkeypatch.setenv("DEVPOST_EMAIL", "test@example.com")
        monkeypatch.setenv("DEVPOST_PASSWORD", "testpass")
        
        with patch("devpost_cli.core.AuthenticatedClient.remove_team_member") as mock_remove:
            mock_remove.return_value = {
                "success": True,
                "message": "Removed user from project",
            }
            
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["team", "remove", "https://devpost.com/software/test", "username"],
            )
            
            assert result.exit_code == 0
            assert "Removed" in result.output


class TestCLINewCommands:
    """Test newly added CLI commands."""

    def test_join(self, monkeypatch):
        """Test join hackathon command."""
        monkeypatch.setenv("DEVPOST_EMAIL", "test@example.com")
        monkeypatch.setenv("DEVPOST_PASSWORD", "testpass")
        
        with patch("devpost_cli.core.AuthenticatedClient.join_hackathon") as mock_join:
            mock_join.return_value = {
                "success": True,
                "data": {
                    "hackathon_slug": "test-hackathon",
                    "message": "Successfully joined test-hackathon",
                },
            }
            
            runner = CliRunner()
            result = runner.invoke(cli, ["join", "test-hackathon"])
            
            assert result.exit_code == 0
            assert "joined" in result.output

    def test_leave_no_confirm(self, monkeypatch):
        """Test leave hackathon without --confirm."""
        monkeypatch.setenv("DEVPOST_EMAIL", "test@example.com")
        monkeypatch.setenv("DEVPOST_PASSWORD", "testpass")
        
        runner = CliRunner()
        result = runner.invoke(cli, ["leave", "test-hackathon"])
        
        # Leave without confirm should show warning and exit 0
        assert result.exit_code == 0
        assert "Confirmation" in result.output or "confirm" in result.output.lower()

    def test_like(self, monkeypatch):
        """Test like project command."""
        monkeypatch.setenv("DEVPOST_EMAIL", "test@example.com")
        monkeypatch.setenv("DEVPOST_PASSWORD", "testpass")
        
        with patch("devpost_cli.core.AuthenticatedClient.like_project") as mock_like:
            mock_like.return_value = {
                "success": True,
                "data": {
                    "project_url": "https://devpost.com/software/test",
                    "message": "Project liked successfully",
                },
            }
            
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["like", "https://devpost.com/software/test"],
            )
            
            assert result.exit_code == 0
            assert "liked" in result.output

    def test_links(self, monkeypatch):
        """Test links update command."""
        monkeypatch.setenv("DEVPOST_EMAIL", "test@example.com")
        monkeypatch.setenv("DEVPOST_PASSWORD", "testpass")
        
        with patch("devpost_cli.core.AuthenticatedClient.update_submission") as mock_update:
            mock_update.return_value = {
                "success": True,
                "updated_fields": ["github_link"],
            }
            
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "links", "https://devpost.com/software/test",
                    "--github", "https://github.com/user/repo",
                ],
            )
            
            assert result.exit_code == 0

    def test_upload(self):
        """Test upload screenshots command - basic invocation test."""
        # Just verify the command can be invoked without argument errors
        runner = CliRunner()
        result = runner.invoke(cli, ["upload", "--help"])
        assert result.exit_code == 0
        assert "Upload screenshots" in result.output or "IMAGE_PATHS" in result.output

    def test_submission(self, monkeypatch):
        """Test submission details command."""
        monkeypatch.setenv("DEVPOST_EMAIL", "test@example.com")
        monkeypatch.setenv("DEVPOST_PASSWORD", "testpass")
        
        with patch("devpost_cli.core.AuthenticatedClient.get_submission_details") as mock_get:
            mock_get.return_value = {
                "success": True,
                "url": "https://devpost.com/software/test",
                "details": {
                    "title": "Test Project",
                    "tagline": "Test tagline",
                    "description": "Test description",
                    "built_with": [],
                    "team_members": [],
                },
            }
            
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["submission", "https://devpost.com/software/test"],
            )
            
            assert result.exit_code == 0
            assert "Test Project" in result.output


class TestCLINewFeatureCommands:
    """Test evaluate CLI command."""

    def test_get_command_rules_json(self):
        """Test devpost get -t rules command with JSON output."""
        rules_result = {
            "success": True, "slug": "test-hack",
            "url": "https://test-hack.devpost.com/rules",
            "eligibility": ["Must be 18+"],
            "requirements": ["Use sponsorAPI"],
            "judging_criteria": ["Innovation 40%"],
            "prize_categories": ["Grand Prize $10,000"],
            "key_dates": [], "sponsor_apis": [],
        }
        with patch("devpost_cli.core.DevpostClient.parse_rules_page", new_callable=AsyncMock) as mock_rules:
            mock_rules.return_value = rules_result
            runner = CliRunner()
            result = runner.invoke(cli, ["get", "test-hack", "-t", "rules", "--json"])
            assert result.exit_code == 0
            import json
            data = json.loads(result.output)
            assert data["success"] is True
            assert data["eligibility"] == ["Must be 18+"]

    def test_get_command_winners_json(self):
        """Test devpost get -t winners command with JSON output."""
        winners_result = {
            "success": True, "slug": "test-hack",
            "winners": [
                {"title": "Winner", "url": "https://devpost.com/software/w", "prize": "1st", "is_winner": True}
            ],
            "count": 1,
        }
        with patch("devpost_cli.core.DevpostClient.get_winners", new_callable=AsyncMock) as mock_winners:
            mock_winners.return_value = winners_result
            runner = CliRunner()
            result = runner.invoke(cli, ["get", "test-hack", "-t", "winners", "--json"])
            assert result.exit_code == 0
            import json
            data = json.loads(result.output)
            assert data["count"] == 1

    def test_get_command_winners_no_winners(self):
        """Test get -t winners command when no winners found."""
        winners_result = {
            "success": True, "slug": "test-hack",
            "winners": [], "count": 0,
            "message": "No winners found",
        }
        with patch("devpost_cli.core.DevpostClient.get_winners", new_callable=AsyncMock) as mock_winners:
            mock_winners.return_value = winners_result
            runner = CliRunner()
            result = runner.invoke(cli, ["get", "test-hack", "-t", "winners"])
            assert result.exit_code == 0
            assert "No winners" in result.output

    def test_get_command_invalid_type(self):
        """Test get command with invalid type."""
        runner = CliRunner()
        result = runner.invoke(cli, ["get", "test-hack", "-t", "invalid"])
        assert result.exit_code == 2
        assert "Invalid value" in result.output

    def test_evaluate_command_json(self):
        """Test devpost evaluate command with JSON output."""
        eval_result = {
            "success": True, "slug": "test-hack",
            "verdict": "Enter", "verdict_reason": "Favorable",
            "basics": {"title": "Test", "prize": "$50,000", "status": "open", "dates": "", "url": "", "organization": "", "featured": False, "themes": []},
            "competition": {"registrants": 1000, "submissions": 10, "prize_per_project": 5000, "registrants_per_prize": 200, "prize_categories": 5},
            "eligibility": [], "requirements": [], "judging_criteria": [],
            "prize_categories": [], "key_dates": [], "sponsor_apis": [],
            "signals": {
                "time_pressure": {"level": "low", "days_left": 30, "detail": "30 days left"},
                "prize_density": {"level": "high", "per_project": 5000, "detail": "$5,000 per project"},
                "competition_density": {"level": "low", "registrants_per_prize": 200, "detail": "less crowded"},
                "submission_gap": {"level": "wide_open", "detail": "wide open"},
                "theme_fit": {"level": "unknown", "detail": "No skills provided"},
            },
            "errors": [],
        }
        with patch("devpost_cli.core.DevpostClient.evaluate_hackathon", new_callable=AsyncMock) as mock_eval:
            mock_eval.return_value = eval_result
            runner = CliRunner()
            result = runner.invoke(cli, ["evaluate", "test-hack", "--json"])
            assert result.exit_code == 0
            import json
            data = json.loads(result.output)
            assert data["verdict"] == "Enter"

    def test_evaluate_command_with_skills(self):
        """Test evaluate command with --skills flag."""
        eval_result = {
            "success": True, "slug": "test-hack",
            "verdict": "Enter", "verdict_reason": "Good fit",
            "basics": {"title": "Test", "prize": "$10,000", "status": "open", "dates": "", "url": "", "organization": "", "featured": False, "themes": ["AI"]},
            "competition": {"registrants": 500, "submissions": 20, "prize_per_project": 500, "registrants_per_prize": 100, "prize_categories": 5},
            "eligibility": [], "requirements": [], "judging_criteria": [],
            "prize_categories": [], "key_dates": [], "sponsor_apis": [],
            "signals": {
                "time_pressure": {"level": "low"},
                "prize_density": {"level": "medium"},
                "competition_density": {"level": "medium"},
                "submission_gap": {"level": "moderate"},
                "theme_fit": {"level": "high", "matched_skills": ["python"]},
            },
            "errors": [],
        }
        with patch("devpost_cli.core.DevpostClient.evaluate_hackathon", new_callable=AsyncMock) as mock_eval:
            mock_eval.return_value = eval_result
            runner = CliRunner()
            result = runner.invoke(cli, ["evaluate", "test-hack", "--skills", "Python,AI", "--json"])
            assert result.exit_code == 0
            mock_eval.assert_called_once_with("test-hack", skills=["Python", "AI"])

    def test_evaluate_command_help(self):
        """Test evaluate command help text."""
        runner = CliRunner()
        result = runner.invoke(cli, ["evaluate", "--help"])
        assert result.exit_code == 0
        assert "evaluate" in result.output.lower() or "Evaluate" in result.output

    def test_hackathons_state_closed(self, mock_devpost_api):
        """Test that hackathons --state closed is a valid choice."""
        runner = CliRunner()
        result = runner.invoke(cli, ["hackathons", "--state", "closed", "--json"])
        assert result.exit_code == 0

    def test_hackathons_state_ended(self, mock_devpost_api):
        """Test that hackathons --state ended is a valid choice."""
        runner = CliRunner()
        result = runner.invoke(cli, ["hackathons", "--state", "ended", "--json"])
        assert result.exit_code == 0


class TestCLINewAPICommands:
    """Test new API-based CLI commands."""

    def test_featured_command_json(self, mock_devpost_api):
        """Test featured --json outputs valid JSON."""
        runner = CliRunner()
        result = runner.invoke(cli, ["featured", "--json"])
        
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert "hackathons" in data
        assert "count" in data

    def test_featured_command_type_filter(self, mock_devpost_api):
        """Test featured --type in-person."""
        runner = CliRunner()
        result = runner.invoke(cli, ["featured", "--type", "in-person"])
        
        assert result.exit_code == 0

    def test_recommended_command_json(self, mock_devpost_api):
        """Test recommended --json outputs valid JSON."""
        runner = CliRunner()
        result = runner.invoke(cli, ["recommended", "--json"])
        
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert "hackathons" in data

    def test_nearby_command_json(self, mock_devpost_api):
        """Test nearby --json outputs valid JSON."""
        runner = CliRunner()
        result = runner.invoke(cli, ["nearby", "--json"])
        
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert "hackathons" in data

    def test_organizations_command_json(self, mock_devpost_api):
        """Test organizations --json outputs valid JSON."""
        runner = CliRunner()
        result = runner.invoke(cli, ["organizations", "--json"])
        
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert "organizations" in data
        assert "count" in data

    def test_organizations_command_query(self, mock_devpost_api):
        """Test organizations -q filter."""
        runner = CliRunner()
        result = runner.invoke(cli, ["organizations", "-q", "Google"])
        
        assert result.exit_code == 0
