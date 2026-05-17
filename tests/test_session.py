"""Tests for session persistence module."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from devpost_cli import session


class TestSessionPersistence:
    """Test session cookie persistence."""

    def test_ensure_session_dir_creates_directory(self, tmp_path):
        """Test that ensure_session_dir creates the directory."""
        session_dir = tmp_path / "test_session"
        with patch.object(session, 'SESSION_DIR', session_dir):
            session.ensure_session_dir()
            assert session_dir.exists()
            assert session_dir.is_dir()

    def test_save_session_writes_file(self, tmp_path):
        """Test that save_session writes cookies to file."""
        session_dir = tmp_path / "test_session"
        session_file = session_dir / "session.json"
        
        session_dir.mkdir(parents=True, exist_ok=True)
        
        with patch.object(session, 'SESSION_DIR', session_dir):
            with patch.object(session, 'SESSION_FILE', session_file):
                cookies = [{"name": "test", "value": "abc123"}]
                session.save_session(cookies, "test@example.com")
                
                assert session_file.exists()
                with open(session_file) as f:
                    data = json.load(f)
                    assert data["email"] == "test@example.com"
                    assert data["cookies"] == cookies

    def test_load_session_returns_none_if_missing(self, tmp_path):
        """Test that load_session returns None when file doesn't exist."""
        session_dir = tmp_path / "test_session"
        session_file = session_dir / "session.json"
        
        session_dir.mkdir(parents=True, exist_ok=True)
        
        with patch.object(session, 'SESSION_DIR', session_dir):
            with patch.object(session, 'SESSION_FILE', session_file):
                result = session.load_session()
                assert result is None

    def test_load_session_roundtrip(self, tmp_path):
        """Test save and load roundtrip."""
        session_dir = tmp_path / "test_session"
        session_file = session_dir / "session.json"
        
        session_dir.mkdir(parents=True, exist_ok=True)
        
        with patch.object(session, 'SESSION_DIR', session_dir):
            with patch.object(session, 'SESSION_FILE', session_file):
                cookies = [{"name": "session", "value": "xyz789"}]
                session.save_session(cookies, "user@example.com")
                
                loaded = session.load_session()
                assert loaded is not None
                assert loaded["email"] == "user@example.com"
                assert loaded["cookies"] == cookies

    def test_clear_session_removes_file(self, tmp_path):
        """Test that clear_session removes the session file."""
        session_dir = tmp_path / "test_session"
        session_file = session_dir / "session.json"
        
        session_dir.mkdir(parents=True, exist_ok=True)
        
        with patch.object(session, 'SESSION_DIR', session_dir):
            with patch.object(session, 'SESSION_FILE', session_file):
                session.save_session([], "test@example.com")
                assert session_file.exists()
                
                session.clear_session()
                assert not session_file.exists()


class TestCredentialsPersistence:
    """Test credentials persistence."""

    def test_save_credentials_writes_env_file(self, tmp_path):
        """Test that save_credentials writes to .env file."""
        session_dir = tmp_path / "test_creds"
        env_file = session_dir / ".env"
        
        session_dir.mkdir(parents=True, exist_ok=True)
        
        with patch.object(session, 'SESSION_DIR', session_dir):
            with patch.object(session, 'ENV_FILE', env_file):
                session.save_credentials("test@example.com", "password123")
                
                assert env_file.exists()
                content = env_file.read_text()
                assert "DEVPOST_EMAIL=test@example.com" in content
                assert "DEVPOST_PASSWORD=password123" in content

    def test_load_credentials_returns_none_if_missing(self, tmp_path):
        """Test that load_credentials returns None when file doesn't exist."""
        session_dir = tmp_path / "test_creds"
        env_file = session_dir / ".env"
        
        session_dir.mkdir(parents=True, exist_ok=True)
        
        with patch.object(session, 'SESSION_DIR', session_dir):
            with patch.object(session, 'ENV_FILE', env_file):
                result = session.load_credentials()
                assert result is None

    def test_load_credentials_roundtrip(self, tmp_path):
        """Test save and load credentials roundtrip."""
        session_dir = tmp_path / "test_creds"
        env_file = session_dir / ".env"
        
        session_dir.mkdir(parents=True, exist_ok=True)
        
        with patch.object(session, 'SESSION_DIR', session_dir):
            with patch.object(session, 'ENV_FILE', env_file):
                session.save_credentials("user@test.com", "secret")
                
                loaded = session.load_credentials()
                assert loaded is not None
                assert loaded[0] == "user@test.com"
                assert loaded[1] == "secret"

    def test_load_credentials_from_env_vars(self, monkeypatch):
        """Test loading credentials from environment variables."""
        monkeypatch.setenv("DEVPOST_EMAIL", "env@test.com")
        monkeypatch.setenv("DEVPOST_PASSWORD", "envpass")
        
        result = session.load_credentials_from_env()
        assert result is not None
        assert result[0] == "env@test.com"
        assert result[1] == "envpass"

    def test_load_credentials_from_env_vars_missing(self, monkeypatch):
        """Test loading credentials when env vars are missing."""
        monkeypatch.delenv("DEVPOST_EMAIL", raising=False)
        monkeypatch.delenv("DEVPOST_PASSWORD", raising=False)
        
        result = session.load_credentials_from_env()
        assert result is None

    def test_get_credentials_prefers_file(self, tmp_path, monkeypatch):
        """Test that get_credentials prefers .env file over env vars."""
        session_dir = tmp_path / "test_creds"
        env_file = session_dir / ".env"
        
        session_dir.mkdir(parents=True, exist_ok=True)
        
        monkeypatch.setenv("DEVPOST_EMAIL", "env@test.com")
        monkeypatch.setenv("DEVPOST_PASSWORD", "envpass")
        
        with patch.object(session, 'SESSION_DIR', session_dir):
            with patch.object(session, 'ENV_FILE', env_file):
                session.save_credentials("file@test.com", "filepass")
                
                result = session.get_credentials()
                assert result is not None
                assert result[0] == "file@test.com"
                assert result[1] == "filepass"

    def test_get_credentials_falls_back_to_env(self, tmp_path, monkeypatch):
        """Test that get_credentials falls back to env vars."""
        session_dir = tmp_path / "test_creds"
        env_file = session_dir / ".env"
        
        session_dir.mkdir(parents=True, exist_ok=True)
        
        monkeypatch.setenv("DEVPOST_EMAIL", "env@test.com")
        monkeypatch.setenv("DEVPOST_PASSWORD", "envpass")
        
        with patch.object(session, 'SESSION_DIR', session_dir):
            with patch.object(session, 'ENV_FILE', env_file):
                result = session.get_credentials()
                assert result is not None
                assert result[0] == "env@test.com"
                assert result[1] == "envpass"
