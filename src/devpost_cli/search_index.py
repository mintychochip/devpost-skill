"""Local search index for Devpost data.

Provides full-text search across cached hackathons, projects, and users.
Uses JSON-based index for simplicity (can be upgraded to SQLite later).
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .logging_config import get_logger

logger = get_logger("search_index")

INDEX_DIR = Path.home() / ".devpost" / "index"
INDEX_FILE = INDEX_DIR / "search_index.json"


def _ensure_index_dir() -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)


def _normalize_text(text: str) -> str:
    """Normalize text for indexing."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_words(text: str) -> set[str]:
    """Extract unique words from text for indexing."""
    normalized = _normalize_text(text)
    words = normalized.split()
    return {w for w in words if len(w) > 1}


class SearchIndex:
    """Local full-text search index for Devpost data."""

    def __init__(self) -> None:
        self.index_path = INDEX_FILE
        self.index: dict[str, Any] = {
            "hackathons": {},
            "projects": {},
            "users": {},
            "metadata": {
                "created_at": None,
                "updated_at": None,
                "hackathon_count": 0,
                "project_count": 0,
                "user_count": 0,
            },
        }
        self._dirty = False

    def load(self) -> bool:
        """Load index from disk. Returns True if loaded successfully."""
        if not self.index_path.exists():
            return False
        
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                self.index = json.load(f)
            return True
        except (json.JSONDecodeError, IOError) as e:
            logger.debug("Could not load index: %s", e)
            return False

    def save(self) -> None:
        """Save index to disk."""
        if not self._dirty:
            return
        
        _ensure_index_dir()
        self.index["metadata"]["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        tmp_path = self.index_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.index, f, indent=2, default=str)
            tmp_path.replace(self.index_path)
            self._dirty = False
        except IOError as e:
            logger.debug("Could not save index: %s", e)

    def add_hackathon(self, hackathon: dict) -> None:
        """Add or update a hackathon in the index."""
        url = hackathon.get("url", "")
        if not url:
            return
        
        import re
        match = re.search(r'https?://([a-z0-9-]+)\.devpost\.com', url, re.IGNORECASE)
        slug = match.group(1) if match else url.rstrip("/").split("/")[-1]
        if not slug:
            return
        
        words = set()
        words.update(_extract_words(hackathon.get("title", "")))
        words.update(_extract_words(hackathon.get("tagline", "")))
        words.update(_extract_words(hackathon.get("description", "")))
        
        themes = hackathon.get("themes", [])
        for t in themes:
            words.update(_extract_words(t.get("name", "") if isinstance(t, dict) else t))
        
        org = hackathon.get("organization_name", "")
        if org:
            words.update(_extract_words(org))
        
        self.index["hackathons"][slug] = {
            "slug": slug,
            "title": hackathon.get("title", ""),
            "url": hackathon.get("url", ""),
            "tagline": hackathon.get("tagline", ""),
            "prize_amount": hackathon.get("prize_amount", ""),
            "open_state": hackathon.get("open_state", ""),
            "ends_at": hackathon.get("ends_at", ""),
            "search_words": list(words),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._dirty = True

    def add_project(self, project: dict, hackathon_slug: str = "") -> None:
        """Add or update a project in the index."""
        url = project.get("url", "")
        if not url:
            return
        
        project_id = hashlib.sha256(url.encode()).hexdigest()[:16]
        
        words = set()
        words.update(_extract_words(project.get("title", "")))
        words.update(_extract_words(project.get("tagline", "")))
        words.update(_extract_words(project.get("description", "")))
        
        tech_stack = project.get("built_with", [])
        for tech in tech_stack:
            words.update(_extract_words(tech))
        
        self.index["projects"][project_id] = {
            "project_id": project_id,
            "title": project.get("title", ""),
            "url": url,
            "tagline": project.get("tagline", ""),
            "built_with": tech_stack if isinstance(tech_stack, list) else [],
            "is_winner": project.get("is_winner", False),
            "hackathon_slug": hackathon_slug,
            "search_words": list(words),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._dirty = True

    def add_user(self, user: dict) -> None:
        """Add or update a user in the index."""
        username = user.get("username", "")
        if not username:
            return
        
        words = set()
        words.update(_extract_words(username))
        words.update(_extract_words(user.get("name", "")))
        words.update(_extract_words(user.get("bio", "")))
        
        skills = user.get("skills", [])
        for skill in skills:
            words.update(_extract_words(skill))
        
        self.index["users"][username] = {
            "username": username,
            "name": user.get("name", ""),
            "url": f"https://devpost.com/users/{username}",
            "bio": user.get("bio", ""),
            "skills": skills if isinstance(skills, list) else [],
            "location": user.get("location", ""),
            "search_words": list(words),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._dirty = True

    def remove_hackathon(self, slug: str) -> None:
        """Remove a hackathon from the index."""
        if slug in self.index["hackathons"]:
            del self.index["hackathons"][slug]
            self._dirty = True

    def remove_project(self, url: str) -> None:
        """Remove a project from the index."""
        project_id = hashlib.sha256(url.encode()).hexdigest()[:16]
        if project_id in self.index["projects"]:
            del self.index["projects"][project_id]
            self._dirty = True

    def remove_user(self, username: str) -> None:
        """Remove a user from the index."""
        if username in self.index["users"]:
            del self.index["users"][username]
            self._dirty = True

    def search_hackathons(self, query: str, limit: int = 20) -> list[dict]:
        """Search hackathons by query."""
        q = _normalize_text(query)
        q_words = set(q.split())
        
        results = []
        for slug, data in self.index["hackathons"].items():
            score = 0
            search_words = set(data.get("search_words", []))
            
            for qw in q_words:
                if len(qw) < 2:
                    continue
                if qw in search_words:
                    score += 1
            
            if score > 0:
                results.append((score, data))
        
        results.sort(key=lambda x: x[0], reverse=True)
        return [data for score, data in results[:limit]]

    def search_projects(self, query: str, limit: int = 50, filters: Optional[dict] = None) -> list[dict]:
        """Search projects by query with optional filters.
        
        Args:
            query: Search query
            limit: Max results
            filters: Optional filters (is_winner, built_with, hackathon_slug)
        
        Returns:
            List of matching projects
        """
        q = _normalize_text(query)
        q_words = set(q.split())
        
        results = []
        for project_id, data in self.index["projects"].items():
            score = 0
            search_words = set(data.get("search_words", []))
            
            for qw in q_words:
                if len(qw) < 2:
                    continue
                if qw in search_words:
                    score += 1
            
            if score > 0:
                if filters:
                    if filters.get("is_winner") and not data.get("is_winner"):
                        continue
                    if filters.get("built_with"):
                        tech_lower = [t.lower() for t in data.get("built_with", [])]
                        if filters["built_with"].lower() not in tech_lower:
                            continue
                    if filters.get("hackathon_slug") and data.get("hackathon_slug") != filters["hackathon_slug"]:
                        continue
                
                results.append((score, data))
        
        results.sort(key=lambda x: x[0], reverse=True)
        return [data for score, data in results[:limit]]

    def search_users(self, query: str, limit: int = 20) -> list[dict]:
        """Search users by query."""
        q = _normalize_text(query)
        q_words = set(q.split())
        
        results = []
        for username, data in self.index["users"].items():
            score = 0
            search_words = set(data.get("search_words", []))
            
            for qw in q_words:
                if len(qw) < 2:
                    continue
                if qw in search_words:
                    score += 1
            
            if score > 0:
                results.append((score, data))
        
        results.sort(key=lambda x: x[0], reverse=True)
        return [data for score, data in results[:limit]]

    def get_stats(self) -> dict:
        """Get index statistics."""
        return {
            "hackathon_count": len(self.index["hackathons"]),
            "project_count": len(self.index["projects"]),
            "user_count": len(self.index["users"]),
            "created_at": self.index["metadata"].get("created_at"),
            "updated_at": self.index["metadata"].get("updated_at"),
        }

    def clear(self) -> None:
        """Clear all indexed data."""
        self.index = {
            "hackathons": {},
            "projects": {},
            "users": {},
            "metadata": {
                "created_at": None,
                "updated_at": None,
                "hackathon_count": 0,
                "project_count": 0,
                "user_count": 0,
            },
        }
        self._dirty = True
        if self.index_path.exists():
            self.index_path.unlink()

    def bulk_index_hackathons(self, hackathons: list[dict]) -> int:
        """Bulk index multiple hackathons. Returns count indexed."""
        count = 0
        for h in hackathons:
            self.add_hackathon(h)
            count += 1
        return count

    def bulk_index_projects(self, projects: list[dict], hackathon_slug: str = "") -> int:
        """Bulk index multiple projects. Returns count indexed."""
        count = 0
        for p in projects:
            self.add_project(p, hackathon_slug)
            count += 1
        return count

    def bulk_index_users(self, users: list[dict]) -> int:
        """Bulk index multiple users. Returns count indexed."""
        count = 0
        for u in users:
            self.add_user(u)
            count += 1
        return count
