"""Session persistence for Devpost authentication."""

import json
import os
import platform
import stat
import subprocess
from pathlib import Path
from typing import Optional

from .logging_config import get_logger

logger = get_logger("session")

SESSION_DIR = Path.home() / ".devpost"
SESSION_FILE = SESSION_DIR / "session.json"
ENV_FILE = SESSION_DIR / ".env"


def _restrict_file(path: Path) -> None:
    """Restrict file permissions to owner-only.

    On POSIX: chmod 0600.
    On Windows: use icacls to remove inherited ACEs and grant only current user.
    """
    try:
        if platform.system() != "Windows":
            os.chmod(str(path), stat.S_IRUSR | stat.S_IWUSR)
        else:
            subprocess.run(
                [
                    "icacls", str(path),
                    "/inheritance:r",
                    "/grant:r", f"{os.getenv('USERNAME', '%USERNAME%')}:(R,W)",
                ],
                check=True,
                capture_output=True,
                timeout=10,
            )
    except Exception:
        logger.debug("Could not restrict file permissions for %s", path)


def ensure_session_dir() -> None:
    """Ensure the session directory exists with restricted permissions."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if platform.system() != "Windows":
            os.chmod(str(SESSION_DIR), stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    except Exception:
        logger.debug("Could not restrict session directory permissions")


def save_session(cookies: list[dict], email: str, auth_method: str = "password") -> None:
    """Save session cookies and email to disk.
    
    Args:
        cookies: List of browser cookies from the authenticated session
        email: User email (or auth method identifier for OAuth)
        auth_method: Authentication method used: "password", "github", "google", "facebook", "linkedin"
    """
    ensure_session_dir()
    session_data = {
        "email": email,
        "cookies": cookies,
        "auth_method": auth_method,
    }
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=2)
    _restrict_file(SESSION_FILE)


def load_session() -> Optional[dict]:
    """Load session from disk if it exists.
    
    Returns:
        Dict with keys: email, cookies, auth_method (or None if no session)
    """
    if not SESSION_FILE.exists():
        return None
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            session = json.load(f)
            # Backwards compatibility: default to "password" if auth_method not present
            if "auth_method" not in session:
                session["auth_method"] = "password"
            return session
    except (json.JSONDecodeError, IOError):
        return None


def get_auth_method() -> Optional[str]:
    """Get the authentication method from the current session.
    
    Returns:
        Auth method string ("password", "github", "google", "facebook", "linkedin") or None
    """
    session = load_session()
    if session:
        return session.get("auth_method", "password")
    return None


def clear_session() -> None:
    """Clear saved session."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def save_credentials(email: str, password: str) -> None:
    """Save credentials to .env file with restricted permissions."""
    ensure_session_dir()
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(f"DEVPOST_EMAIL={email}\n")
        f.write(f"DEVPOST_PASSWORD={password}\n")
    _restrict_file(ENV_FILE)


def load_credentials() -> Optional[tuple[str, str]]:
    """Load credentials from .env file if it exists."""
    if not ENV_FILE.exists():
        return None
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            email = None
            password = None
            for line in f:
                line = line.strip()
                if line.startswith("DEVPOST_EMAIL="):
                    email = line.split("=", 1)[1]
                elif line.startswith("DEVPOST_PASSWORD="):
                    password = line.split("=", 1)[1]
            if email and password:
                return email, password
    except IOError:
        logger.debug("Could not read credentials file")
    return None


def load_credentials_from_env() -> Optional[tuple[str, str]]:
    """Load credentials from environment variables."""
    email = os.getenv("DEVPOST_EMAIL")
    password = os.getenv("DEVPOST_PASSWORD")
    if email and password:
        return email, password
    return None


def get_credentials() -> Optional[tuple[str, str]]:
    """Get credentials from .env file or environment variables."""
    creds = load_credentials()
    if creds:
        return creds
    return load_credentials_from_env()


def is_session_file(path: str) -> bool:
    """Check if a path is the session file."""
    return str(path) == str(SESSION_FILE)
