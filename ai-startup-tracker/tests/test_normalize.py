"""Tests for company name normalization and fuzzy matching."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.utils.normalize import normalize_company_name, fuzzy_name_match


class TestNormalizeCompanyName:
    def test_basic(self):
        assert normalize_company_name("OpenAI") == "openai"

    def test_strip_inc(self):
        result = normalize_company_name("Anthropic Inc.")
        assert "inc" not in result
        assert "anthropic" in result

    def test_strip_llc(self):
        result = normalize_company_name("My Company LLC")
        assert "llc" not in result

    def test_strip_labs(self):
        result = normalize_company_name("DeepMind Labs")
        assert "labs" not in result
        assert "deepmind" in result

    def test_strip_ai_suffix(self):
        result = normalize_company_name("Cohere AI")
        assert "cohere" in result

    def test_punctuation_removed(self):
        result = normalize_company_name("My.Company! (Test)")
        assert "." not in result
        assert "!" not in result

    def test_whitespace_collapsed(self):
        result = normalize_company_name("  My   Company  ")
        assert "  " not in result

    def test_empty(self):
        assert normalize_company_name("") is None
        assert normalize_company_name(None) is None

    def test_only_suffix(self):
        # If name is only a suffix, should return None
        result = normalize_company_name("Inc.")
        assert result is None or result == ""


class TestFuzzyNameMatch:
    def test_exact(self):
        assert fuzzy_name_match("OpenAI", "OpenAI") == 1.0

    def test_case_insensitive(self):
        score = fuzzy_name_match("openai", "OpenAI")
        assert score == 1.0

    def test_with_suffix(self):
        score = fuzzy_name_match("Anthropic", "Anthropic Inc.")
        assert score >= 0.9

    def test_different_names(self):
        score = fuzzy_name_match("Google", "Microsoft")
        assert score < 0.5

    def test_similar_names(self):
        score = fuzzy_name_match("DeepMind", "Deep Mind Labs")
        assert score >= 0.8

    def test_empty(self):
        assert fuzzy_name_match("", "OpenAI") == 0.0
        assert fuzzy_name_match("OpenAI", "") == 0.0
