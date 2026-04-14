"""Tests for AI scoring and startup scoring."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.utils.scoring import compute_ai_score, compute_startup_score, extract_ai_tags


class TestComputeAiScore:
    def test_strong_topic(self):
        score = compute_ai_score(topics=["llm", "python"])
        assert score >= 0.3

    def test_moderate_topic(self):
        score = compute_ai_score(topics=["machine-learning"])
        assert score >= 0.2

    def test_strong_plus_moderate(self):
        score = compute_ai_score(topics=["llm", "ai", "machine-learning"])
        assert score >= 0.5

    def test_text_keywords(self):
        score = compute_ai_score(
            description="We provide transformer-based inference for fine-tuning LLMs."
        )
        assert score >= 0.2

    def test_cb_flag(self):
        score = compute_ai_score(cb_ai_flag=True)
        assert score >= 0.2

    def test_max_cap(self):
        score = compute_ai_score(
            topics=["llm", "ai", "machine-learning"],
            description="transformer inference fine-tuning deep learning neural network",
            cb_ai_flag=True,
        )
        assert score <= 1.0

    def test_no_signals(self):
        score = compute_ai_score(topics=[], description="A web framework for building apps")
        assert score == 0.0

    def test_none_inputs(self):
        score = compute_ai_score()
        assert score == 0.0


class TestComputeStartupScore:
    def test_product_domain(self):
        score = compute_startup_score(domain="mycompany.com")
        assert score >= 0.4

    def test_github_domain_excluded(self):
        score = compute_startup_score(domain="github.com")
        assert score < 0.4

    def test_org_owner(self):
        score = compute_startup_score(owner_type="Organization")
        assert score >= 0.2

    def test_startup_signals_in_text(self):
        score = compute_startup_score(
            readme_snippet="Sign up for early access. Book a demo today. Enterprise pricing."
        )
        assert score >= 0.2

    def test_funding(self):
        score = compute_startup_score(has_funding=True)
        assert score >= 0.2

    def test_combined(self):
        score = compute_startup_score(
            domain="myai.com",
            owner_type="Organization",
            readme_snippet="Pricing and enterprise plans available.",
            has_funding=True,
        )
        assert score >= 0.8

    def test_no_signals(self):
        score = compute_startup_score()
        assert score == 0.0


class TestExtractAiTags:
    def test_from_topics(self):
        tags = extract_ai_tags(topics=["llm", "python", "ai"])
        assert "llm" in tags
        assert "ai" in tags
        assert "python" not in tags

    def test_from_text(self):
        tags = extract_ai_tags(description="Uses transformer models for inference.")
        assert any("transformer" in t for t in tags)

    def test_empty(self):
        assert extract_ai_tags() == []
