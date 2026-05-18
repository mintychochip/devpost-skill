"""Tests for the SearchIndex module."""

import pytest
from pathlib import Path
import tempfile
import shutil

from devpost_cli.search_index import SearchIndex, _normalize_text, _extract_words


class TestNormalizeText:
    """Test text normalization."""

    def test_lowercase(self):
        assert _normalize_text("Hello WORLD") == "hello world"

    def test_remove_punctuation(self):
        assert _normalize_text("Hello, World!") == "hello world"

    def test_multiple_spaces(self):
        assert _normalize_text("hello   world") == "hello world"

    def test_empty(self):
        assert _normalize_text("") == ""

    def test_none(self):
        assert _normalize_text(None) == ""


class TestExtractWords:
    """Test word extraction."""

    def test_basic(self):
        words = _extract_words("hello world foo")
        assert words == {"hello", "world", "foo"}

    def test_removes_short_words(self):
        words = _extract_words("a I be hello AI")
        assert "a" not in words  # 1 char
        assert "i" not in words  # 1 char (lowercased)
        assert "be" in words  # 2 chars included
        assert "ai" in words  # 2 chars included (lowercased)
        assert "hello" in words

    def test_empty(self):
        assert _extract_words("") == set()


class TestSearchIndex:
    """Test the SearchIndex class."""

    @pytest.fixture
    def temp_index(self):
        """Create a temporary index directory."""
        temp_dir = tempfile.mkdtemp()
        original_index_dir = Path.home() / ".devpost" / "index"
        
        import devpost_cli.search_index as si
        si.INDEX_DIR = Path(temp_dir)
        si.INDEX_FILE = si.INDEX_DIR / "search_index.json"
        
        idx = SearchIndex()
        yield idx
        
        shutil.rmtree(temp_dir)

    def test_init_empty(self, temp_index):
        """Test that index starts empty."""
        assert len(temp_index.index["hackathons"]) == 0
        assert len(temp_index.index["projects"]) == 0
        assert len(temp_index.index["users"]) == 0

    def test_add_hackathon(self, temp_index):
        """Test adding a hackathon."""
        hackathon = {
            "url": "https://test-hack.devpost.com/",
            "title": "Test Hackathon",
            "tagline": "A test hackathon",
            "description": "This is a test hackathon for AI and ML",
            "themes": [{"name": "Machine Learning"}, {"name": "AI"}],
            "organization_name": "Test Org",
        }
        temp_index.add_hackathon(hackathon)
        
        assert "test-hack" in temp_index.index["hackathons"]
        data = temp_index.index["hackathons"]["test-hack"]
        assert data["title"] == "Test Hackathon"
        assert len(data["search_words"]) > 0

    def test_add_project(self, temp_index):
        """Test adding a project."""
        project = {
            "url": "https://devpost.com/software/test-project",
            "title": "Test Project",
            "tagline": "A cool project",
            "description": "Built with Python and AI",
            "built_with": ["Python", "TensorFlow"],
            "is_winner": True,
        }
        temp_index.add_project(project, hackathon_slug="test-hack")
        
        assert len(temp_index.index["projects"]) == 1
        project_id = list(temp_index.index["projects"].keys())[0]
        data = temp_index.index["projects"][project_id]
        assert data["title"] == "Test Project"
        assert data["hackathon_slug"] == "test-hack"
        assert data["is_winner"] is True

    def test_add_user(self, temp_index):
        """Test adding a user."""
        user = {
            "username": "testuser",
            "name": "Test User",
            "bio": "Python developer interested in AI",
            "skills": ["Python", "Machine Learning", "AI"],
            "location": "San Francisco",
        }
        temp_index.add_user(user)
        
        assert "testuser" in temp_index.index["users"]
        data = temp_index.index["users"]["testuser"]
        assert data["name"] == "Test User"
        assert len(data["search_words"]) > 0

    def test_search_hackathons(self, temp_index):
        """Test searching hackathons."""
        hackathon1 = {
            "url": "https://ai-hack.devpost.com/",
            "title": "AI Hackathon",
            "tagline": "Build AI projects",
            "description": "Machine learning and deep learning",
            "themes": [],
            "organization_name": "",
        }
        hackathon2 = {
            "url": "https://web-hack.devpost.com/",
            "title": "Web Hackathon",
            "tagline": "Build web projects",
            "description": "Frontend and backend development",
            "themes": [],
            "organization_name": "",
        }
        
        temp_index.add_hackathon(hackathon1)
        temp_index.add_hackathon(hackathon2)
        
        results = temp_index.search_hackathons("AI", limit=10)
        assert len(results) == 1
        assert results[0]["slug"] == "ai-hack"

    def test_search_projects(self, temp_index):
        """Test searching projects."""
        project1 = {
            "url": "https://devpost.com/software/ai-chatbot",
            "title": "AI Chatbot",
            "tagline": "Chat with AI",
            "built_with": ["Python", "OpenAI"],
            "is_winner": False,
        }
        project2 = {
            "url": "https://devpost.com/software/web-app",
            "title": "Web App",
            "tagline": "A web application",
            "built_with": ["React", "Node.js"],
            "is_winner": True,
        }
        
        temp_index.add_project(project1, "ai-hack")
        temp_index.add_project(project2, "web-hack")
        
        results = temp_index.search_projects("AI", limit=10)
        assert len(results) == 1
        assert results[0]["title"] == "AI Chatbot"

    def test_search_projects_with_filters(self, temp_index):
        """Test searching projects with filters."""
        project1 = {
            "url": "https://devpost.com/software/ai-chatbot",
            "title": "AI Chatbot",
            "tagline": "Chat with AI",
            "built_with": ["Python", "OpenAI"],
            "is_winner": False,
        }
        project2 = {
            "url": "https://devpost.com/software/winning-ai",
            "title": "Winning AI Project",
            "tagline": "Award winning AI",
            "built_with": ["Python", "TensorFlow"],
            "is_winner": True,
        }
        
        temp_index.add_project(project1, "ai-hack")
        temp_index.add_project(project2, "ai-hack")
        
        results = temp_index.search_projects("AI", limit=10, filters={"is_winner": True})
        assert len(results) == 1
        assert results[0]["title"] == "Winning AI Project"

    def test_search_users(self, temp_index):
        """Test searching users."""
        user1 = {
            "username": "alice",
            "name": "Alice Smith",
            "bio": "Python developer",
            "skills": ["Python", "AI"],
            "location": "NYC",
        }
        user2 = {
            "username": "bob",
            "name": "Bob Jones",
            "bio": "Web developer",
            "skills": ["JavaScript", "React"],
            "location": "LA",
        }
        
        temp_index.add_user(user1)
        temp_index.add_user(user2)
        
        results = temp_index.search_users("Python", limit=10)
        assert len(results) == 1
        assert results[0]["username"] == "alice"

    def test_save_and_load(self, temp_index):
        """Test saving and loading index."""
        hackathon = {
            "url": "https://test.devpost.com/",
            "title": "Test Hackathon",
            "tagline": "Test",
            "description": "Testing",
            "themes": [],
            "organization_name": "",
        }
        temp_index.add_hackathon(hackathon)
        temp_index.save()
        
        new_idx = SearchIndex()
        assert new_idx.load() is True
        assert "test" in new_idx.index["hackathons"]

    def test_get_stats(self, temp_index):
        """Test getting index statistics."""
        hackathon = {
            "url": "https://test.devpost.com/",
            "title": "Test",
            "tagline": "Test",
            "description": "Test",
            "themes": [],
            "organization_name": "",
        }
        temp_index.add_hackathon(hackathon)
        
        stats = temp_index.get_stats()
        assert stats["hackathon_count"] == 1
        assert stats["project_count"] == 0
        assert stats["user_count"] == 0

    def test_clear(self, temp_index):
        """Test clearing index."""
        hackathon = {
            "url": "https://test.devpost.com/",
            "title": "Test",
            "tagline": "Test",
            "description": "Test",
            "themes": [],
            "organization_name": "",
        }
        temp_index.add_hackathon(hackathon)
        temp_index.save()
        
        temp_index.clear()
        assert len(temp_index.index["hackathons"]) == 0
        assert not temp_index.index_path.exists()

    def test_bulk_index(self, temp_index):
        """Test bulk indexing."""
        hackathons = [
            {
                "url": f"https://hack{i}.devpost.com/",
                "title": f"Hackathon {i}",
                "tagline": f"Tagline {i}",
                "description": f"Description {i}",
                "themes": [],
                "organization_name": "",
            }
            for i in range(10)
        ]
        
        count = temp_index.bulk_index_hackathons(hackathons)
        assert count == 10
        assert len(temp_index.index["hackathons"]) == 10
