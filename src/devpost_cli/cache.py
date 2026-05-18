"""Disk-based cache for Devpost CLI with TTL support."""

import hashlib
import json
import os
import platform
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .logging_config import get_logger

logger = get_logger("cache")

CACHE_DIR = Path.home() / ".devpost" / "cache"
DEFAULT_TTL = int(os.getenv("DEVPOST_CACHE_TTL", "3600"))


def _ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(key: str) -> Path:
    safe_key = re.sub(r"[^a-zA-Z0-9_\-]", "_", key)
    if len(safe_key) > 200:
        digest = hashlib.sha256(safe_key.encode()).hexdigest()[:16]
        safe_key = safe_key[:184] + "_" + digest
    return CACHE_DIR / f"{safe_key}.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _acquire_lock(lock_path: Path, exclusive: bool = True) -> Optional[Any]:
    """Acquire a file lock (non-blocking). Returns lock file object or None if couldn't acquire."""
    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        if platform.system() == "Windows":
            import msvcrt
            try:
                os.lseek(lock_fd, 0, os.SEEK_SET)
                msvcrt.locking(lock_fd, msvcrt.LK_NBLCK, 1)
            except (OSError, IOError):
                os.close(lock_fd)
                return None
        else:
            import fcntl
            flags = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            try:
                fcntl.flock(lock_fd, flags | fcntl.LOCK_NB)
            except (OSError, IOError):
                os.close(lock_fd)
                return None
        return lock_fd
    except OSError:
        return None


def _release_lock(lock_fd: Any) -> None:
    """Release a file lock."""
    try:
        if platform.system() == "Windows":
            import msvcrt
            os.lseek(lock_fd, 0, os.SEEK_SET)
            msvcrt.locking(lock_fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
    except OSError:
        pass


class CacheManager:
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        default_ttl: int = DEFAULT_TTL,
    ) -> None:
        self.cache_dir = cache_dir or CACHE_DIR
        self.default_ttl = default_ttl
        self._disabled = default_ttl == 0

    def get(self, key: str) -> Optional[Any]:
        if self._disabled:
            return None
        path = self.cache_dir / _cache_path(key).name
        if not path.exists():
            return None
        lock_path = path.with_suffix(".lock")
        lock_fd = _acquire_lock(lock_path, exclusive=False)
        try:
            with open(path, "r", encoding="utf-8") as f:
                entry = json.load(f)
            stored = datetime.fromisoformat(entry["stored_at"])
            ttl = entry.get("ttl", self.default_ttl)
            if ttl == 0:
                return None
            age = (_now() - stored).total_seconds()
            if age > ttl:
                return None
            return entry["data"]
        except (json.JSONDecodeError, KeyError, ValueError, IOError):
            return None
        finally:
            if lock_fd is not None:
                _release_lock(lock_fd)

    def set(
        self,
        key: str,
        data: Any,
        ttl: Optional[int] = None,
    ) -> None:
        if self._disabled:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / _cache_path(key).name
        effective_ttl = ttl if ttl is not None else self.default_ttl
        if effective_ttl == 0:
            return
        entry = {
            "key": key,
            "stored_at": _now().isoformat(),
            "ttl": effective_ttl,
            "data": data,
        }
        lock_path = path.with_suffix(".lock")
        lock_fd = _acquire_lock(lock_path, exclusive=True)
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self.cache_dir),
                prefix=".cache_tmp_",
                suffix=".json",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(entry, f, indent=2, default=str)
                os.replace(tmp_path, str(path))
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as e:
            logger.debug("Could not write cache entry %s: %s", key, e)
        finally:
            if lock_fd is not None:
                _release_lock(lock_fd)

    def delete(self, key: str) -> None:
        if self._disabled:
            return
        path = self.cache_dir / _cache_path(key).name
        if path.exists():
            path.unlink()

    def clear(self) -> int:
        if not self.cache_dir.exists():
            return 0
        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
            count += 1
        for f in self.cache_dir.glob("*.lock"):
            try:
                f.unlink()
            except OSError:
                pass
        return count

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    def status(self) -> dict:
        if not self.cache_dir.exists():
            return {"entries": 0, "size_bytes": 0, "keys": [], "oldest": None, "newest": None}
        entries = []
        total_size = 0
        oldest = None
        newest = None
        for f in self.cache_dir.glob("*.json"):
            total_size += f.stat().st_size
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    entry = json.load(fh)
                stored = datetime.fromisoformat(entry.get("stored_at", ""))
                key = entry.get("key", f.stem)
                entries.append({"key": key, "stored_at": stored, "size": f.stat().st_size})
                if oldest is None or stored < oldest:
                    oldest = stored
                if newest is None or stored > newest:
                    newest = stored
            except (json.JSONDecodeError, ValueError, IOError):
                pass
        return {
            "entries": len(entries),
            "size_bytes": total_size,
            "keys": [e["key"] for e in entries],
            "oldest": oldest.isoformat() if oldest else None,
            "newest": newest.isoformat() if newest else None,
        }

    def search(self, query: str) -> list[dict]:
        if self._disabled:
            return []
        results = []
        q = query.lower()
        if not self.cache_dir.exists():
            return results
        for f in self.cache_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    entry = json.load(fh)
                data = entry.get("data")
                key = entry.get("key", f.stem)
                if data is not None and _matches(data, q):
                    results.append({"cache_key": key, "data": data})
            except (json.JSONDecodeError, IOError):
                pass
        return results


def _matches(obj: Any, query: str) -> bool:
    if isinstance(obj, str):
        return query in obj.lower()
    if isinstance(obj, dict):
        for v in obj.values():
            if _matches(v, query):
                return True
    if isinstance(obj, list):
        for item in obj:
            if _matches(item, query):
                return True
    return False


def make_list_key(
    state: Optional[str] = None,
    order_by: str = "recently-added",
    search: Optional[str] = None,
    challenge_type: Optional[list[str]] = None,
    length: Optional[list[str]] = None,
    themes: Optional[list[str]] = None,
    organization: Optional[str] = None,
    open_to: Optional[list[str]] = None,
    managed_by_devpost_badge: bool = False,
    eligibility: bool = False,
    page: int = 1,
    per_page: int = 9,
    limit: Optional[int] = None,  # for backward compat with old calls
) -> str:
    parts = ["hackathons"]
    parts.append(state or "all")
    parts.append(order_by)
    parts.append(search or "noquery")
    if challenge_type:
        parts.append("ct:" + "-".join(sorted(challenge_type)))
    if length:
        parts.append("len:" + "-".join(sorted(length)))
    if themes:
        parts.append("themes:" + "-".join(sorted(themes)))
    if organization:
        parts.append("org:" + organization.replace(" ", ""))
    if open_to:
        parts.append("access:" + "-".join(sorted(open_to)))
    if managed_by_devpost_badge:
        parts.append("devpost-managed")
    if eligibility:
        parts.append("eligible")
    parts.append(f"p{page}")
    parts.append(f"pp{per_page}")
    if limit:
        parts.append(f"l{limit}")
    return "_".join(parts)


def make_hackathon_key(slug: str) -> str:
    return f"hackathon_{slug}"


def make_scrape_key(url: str) -> str:
    digest = hashlib.sha256(url.encode()).hexdigest()[:16]
    return f"scrape_{digest}"


def make_projects_key(hackathon_url: str, page: int = 1) -> str:
    digest = hashlib.sha256(hackathon_url.encode()).hexdigest()[:16]
    return f"projects_{digest}_p{page}"


def make_project_key(project_url: str) -> str:
    digest = hashlib.sha256(project_url.encode()).hexdigest()[:16]
    return f"project_{digest}"


def make_rules_key(slug: str) -> str:
    return f"rules_{slug}"


def make_evaluate_key(slug: str) -> str:
    return f"evaluate_{slug}"


def make_search_projects_key(query: str, limit: int = 20, order_by: Optional[str] = None) -> str:
    parts = ["search_projects", query.replace(" ", "_"), f"l{limit}"]
    if order_by:
        parts.append(order_by)
    return "_".join(parts)


def make_popular_projects_key(limit: int = 20) -> str:
    return f"popular_projects_{limit}"


def make_built_with_key(tech: str, limit: int = 20) -> str:
    tech_slug = tech.lower().replace(" ", "-").replace("+", "plus")
    return f"built_with_{tech_slug}_{limit}"


def make_featured_projects_key(limit: int = 20) -> str:
    return f"featured_projects_{limit}"


def make_participants_key(slug: str, limit: int = 50) -> str:
    return f"participants_{slug}_{limit}"


def make_resources_key(slug: str) -> str:
    return f"resources_{slug}"


def make_updates_key(slug: str, limit: int = 20) -> str:
    return f"updates_{slug}_{limit}"


def make_discussions_key(slug: str, limit: int = 20) -> str:
    return f"discussions_{slug}_{limit}"


def parse_days_left(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    text_lower = text.lower().strip()
    m = re.match(r"(\d+)\s+day", text_lower)
    if m:
        return float(m.group(1))
    m = re.match(r"(\d+)\s+hour", text_lower)
    if m:
        return float(m.group(1)) / 24.0
    m = re.match(r"about\s+(\d+)\s+month", text_lower)
    if m:
        return float(m.group(1)) * 30.0
    if "month" in text_lower:
        return 30.0
    if "today" in text_lower or "tomorrow" in text_lower:
        return 0.0 if "today" in text_lower else 1.0
    return None


def parse_prize_amount(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"\$([\d,]+)", text)
    if m:
        return int(m.group(1).replace(",", ""))
    return None
