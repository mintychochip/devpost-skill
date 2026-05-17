"""Tests for cache module."""

import json
import time
from pathlib import Path

import pytest

from devpost_cli.cache import (
    CacheManager,
    _matches,
    make_hackathon_key,
    make_list_key,
    make_project_key,
    make_projects_key,
    make_rules_key,
    make_evaluate_key,
    make_scrape_key,
    parse_days_left,
    parse_prize_amount,
)


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "cache"


@pytest.fixture
def cache(cache_dir):
    return CacheManager(cache_dir=cache_dir, default_ttl=3600)


class TestCacheManager:
    def test_set_and_get(self, cache):
        cache.set("test_key", {"hello": "world"})
        result = cache.get("test_key")
        assert result == {"hello": "world"}

    def test_get_missing_key(self, cache):
        assert cache.get("nonexistent") is None

    def test_has(self, cache):
        cache.set("exists", [1, 2, 3])
        assert cache.has("exists") is True
        assert cache.has("nope") is False

    def test_delete(self, cache):
        cache.set("del_me", "data")
        assert cache.has("del_me") is True
        cache.delete("del_me")
        assert cache.has("del_me") is False

    def test_clear(self, cache):
        cache.set("a", 1)
        cache.set("b", 2)
        count = cache.clear()
        assert count == 2
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_clear_empty(self, cache):
        assert cache.clear() == 0

    def test_ttl_expired(self, cache_dir):
        mgr = CacheManager(cache_dir=cache_dir, default_ttl=0)
        mgr.set("expire_fast", "gone", ttl=0)
        time.sleep(0.01)
        assert mgr.get("expire_fast") is None

    def test_custom_ttl(self, cache):
        cache.set("long_lived", "data", ttl=99999)
        assert cache.get("long_lived") == "data"

    def test_status_empty(self, cache):
        info = cache.status()
        assert info["entries"] == 0
        assert info["size_bytes"] == 0

    def test_status_with_entries(self, cache):
        cache.set("key1", {"a": 1})
        cache.set("key2", {"b": 2})
        info = cache.status()
        assert info["entries"] == 2
        assert info["size_bytes"] > 0
        assert "key1" in info["keys"]
        assert "key2" in info["keys"]

    def test_search_basic(self, cache):
        cache.set("h1", {"title": "AI Hackathon", "prize": "$10,000"})
        cache.set("h2", {"title": "Cybersecurity Fest", "prize": "$5,000"})
        results = cache.search("AI")
        assert len(results) == 1
        assert results[0]["data"]["title"] == "AI Hackathon"

    def test_search_nested(self, cache):
        cache.set("h1", {"title": "Hack", "themes": [{"name": "Machine Learning"}]})
        results = cache.search("machine learning")
        assert len(results) == 1

    def test_search_no_match(self, cache):
        cache.set("h1", {"title": "Hack"})
        results = cache.search("quantum")
        assert len(results) == 0

    def test_caches_list_data(self, cache):
        data = [{"id": 1, "title": "Test Hack"}]
        cache.set("hackathons_list", data)
        result = cache.get("hackathons_list")
        assert len(result) == 1

    def test_overwrite_existing_key(self, cache):
        cache.set("key", "first")
        cache.set("key", "second")
        assert cache.get("key") == "second"

    def test_no_cache_dir(self, cache_dir):
        nonexistent = cache_dir / "nope"
        mgr = CacheManager(cache_dir=nonexistent, default_ttl=3600)
        mgr.set("auto_creates", "yes")
        assert mgr.get("auto_creates") == "yes"

    def test_ttl_zero_disables_cache(self, cache_dir):
        mgr = CacheManager(cache_dir=cache_dir, default_ttl=0)
        mgr.set("disabled_key", "data")
        assert mgr.get("disabled_key") is None
        assert mgr.has("disabled_key") is False
        assert mgr.search("data") == []

    def test_ttl_zero_skips_set(self, cache_dir):
        mgr = CacheManager(cache_dir=cache_dir, default_ttl=0)
        mgr.set("ttl0", "value", ttl=0)
        path = cache_dir / "ttl0.json"
        assert not path.exists()

    def test_atomic_write_no_partial_files(self, cache_dir):
        mgr = CacheManager(cache_dir=cache_dir, default_ttl=3600)
        mgr.set("atomic", "data")
        json_files = list(cache_dir.glob("*.json"))
        tmp_files = list(cache_dir.glob(".cache_tmp_*"))
        assert len(json_files) == 1
        assert len(tmp_files) == 0
        assert mgr.get("atomic") == "data"

    def test_clear_removes_lock_files(self, cache_dir):
        mgr = CacheManager(cache_dir=cache_dir, default_ttl=3600)
        mgr.set("key", "data")
        lock_path = cache_dir / "key.lock"
        lock_path.write_text("lock")
        mgr.clear()
        assert not lock_path.exists()

    def test_datetime_serialization(self, cache_dir):
        from datetime import datetime, timezone
        mgr = CacheManager(cache_dir=cache_dir, default_ttl=3600)
        data = {"ts": datetime(2026, 1, 1, tzinfo=timezone.utc)}
        mgr.set("dt_key", data)
        result = mgr.get("dt_key")
        assert "ts" in result


class TestMatches:
    def test_string_match(self):
        assert _matches("hello world", "world") is True

    def test_string_no_match(self):
        assert _matches("hello", "xyz") is False

    def test_case_insensitive(self):
        assert _matches("Hello World", "hello") is True

    def test_dict_match(self):
        assert _matches({"key": "AI Hackathon"}, "hack") is True

    def test_dict_no_match(self):
        assert _matches({"key": "foo"}, "bar") is False

    def test_list_match(self):
        assert _matches(["Python", "React"], "react") is True

    def test_nested_match(self):
        data = {"themes": [{"name": "Machine Learning"}]}
        assert _matches(data, "machine learning") is True

    def test_number_no_match(self):
        assert _matches(42, "foo") is False


class TestKeyGenerators:
    def test_make_list_key(self):
        key = make_list_key(state="open", sort_by="prize-amount", query="AI", limit=10)
        assert "open" in key
        assert "prize-amount" in key
        assert "AI" in key

    def test_make_hackathon_key(self):
        assert make_hackathon_key("medo") == "hackathon_medo"

    def test_make_scrape_key(self):
        key = make_scrape_key("https://medo.devpost.com/")
        assert key.startswith("scrape_")

    def test_make_projects_key(self):
        key = make_projects_key("https://medo.devpost.com/", page=1)
        assert key.startswith("projects_")

    def test_make_project_key(self):
        key = make_project_key("https://devpost.com/software/test")
        assert key.startswith("project_")

    def test_make_rules_key(self):
        key = make_rules_key("my-hackathon")
        assert key == "rules_my-hackathon"

    def test_make_evaluate_key(self):
        key = make_evaluate_key("my-hackathon")
        assert key == "evaluate_my-hackathon"


class TestParseDaysLeft:
    def test_days(self):
        assert parse_days_left("3 days left") == 3.0

    def test_single_day(self):
        assert parse_days_left("1 day left") == 1.0

    def test_hours(self):
        assert parse_days_left("12 hours left") == 0.5

    def test_about_month(self):
        assert parse_days_left("about 1 month left") == 30.0

    def test_months(self):
        assert parse_days_left("about 2 months left") == 60.0

    def test_today(self):
        assert parse_days_left("today") == 0.0

    def test_none(self):
        assert parse_days_left(None) is None

    def test_empty(self):
        assert parse_days_left("") is None


class TestParsePrizeAmount:
    def test_dollar_amount(self):
        assert parse_prize_amount("$50,000") == 50000

    def test_small_amount(self):
        assert parse_prize_amount("$1,000") == 1000

    def test_zero(self):
        assert parse_prize_amount("$0") == 0

    def test_none(self):
        assert parse_prize_amount(None) is None

    def test_empty(self):
        assert parse_prize_amount("") is None

    def test_no_dollar(self):
        assert parse_prize_amount("no prize") is None
