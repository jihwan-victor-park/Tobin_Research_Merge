"""Tests for entity resolution and deduplication."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.utils.dedup import entity_key, resolve_entity, deduplicate_candidates


class TestEntityKey:
    def test_domain_preferred(self):
        key = entity_key("example.com", "Example Inc")
        assert key.startswith("domain:")

    def test_name_fallback(self):
        key = entity_key(None, "My Company")
        assert key.startswith("name:")

    def test_none(self):
        assert entity_key(None, None) is None
        assert entity_key("", "") is None


class TestResolveEntity:
    def test_match_by_domain(self):
        existing = [
            {"id": 1, "domain": "example.com", "normalized_name": "example", "name": "Example"},
            {"id": 2, "domain": "other.com", "normalized_name": "other", "name": "Other"},
        ]
        result = resolve_entity("example.com", "Whatever", existing)
        assert result is not None
        assert result["id"] == 1

    def test_no_domain_match(self):
        existing = [
            {"id": 1, "domain": "example.com", "normalized_name": "example", "name": "Example"},
        ]
        result = resolve_entity("notfound.com", "NotFound", existing)
        assert result is None

    def test_name_match_fallback(self):
        existing = [
            {"id": 1, "domain": None, "normalized_name": "openai", "name": "OpenAI"},
        ]
        result = resolve_entity(None, "OpenAI", existing, require_shared_signal=False)
        assert result is not None
        assert result["id"] == 1

    def test_empty_existing(self):
        result = resolve_entity("example.com", "Example", [])
        assert result is None


class TestDeduplicateCandidates:
    def test_domain_dedup(self):
        candidates = [
            {"domain": "example.com", "name": "Example", "repo_url": "r1", "stars": 100},
            {"domain": "example.com", "name": "Example 2", "repo_url": "r2", "stars": 50},
            {"domain": "other.com", "name": "Other", "repo_url": "r3", "stars": 10},
        ]
        result = deduplicate_candidates(candidates)
        assert len(result) == 2

    def test_name_dedup(self):
        candidates = [
            {"domain": None, "name": "My Company", "repo_url": "r1", "stars": 5},
            {"domain": None, "name": "My Company", "repo_url": "r2", "stars": 10},
        ]
        result = deduplicate_candidates(candidates)
        assert len(result) == 1
        # Stars should be the higher value
        assert result[0]["stars"] == 10

    def test_no_duplicates(self):
        candidates = [
            {"domain": "a.com", "name": "A", "repo_url": "r1", "stars": 1},
            {"domain": "b.com", "name": "B", "repo_url": "r2", "stars": 2},
        ]
        result = deduplicate_candidates(candidates)
        assert len(result) == 2

    def test_empty(self):
        assert deduplicate_candidates([]) == []
