"""
Deterministic scoring for AI relevance and startup likelihood.
No embeddings, no LLM calls — pure rule-based.
"""
import re
from typing import List, Optional


# --- AI keywords grouped by strength ---

STRONG_AI_TOPICS = frozenset({
    "llm", "rag", "agents", "generative-ai", "generative_ai",
    "large-language-model", "large-language-models",
    "langchain", "llamaindex", "autogen",
})

MODERATE_AI_TOPICS = frozenset({
    "ai", "machine-learning", "deep-learning", "computer-vision",
    "nlp", "natural-language-processing", "neural-network",
    "reinforcement-learning", "speech-recognition",
    "transformer", "diffusion", "multimodal",
})

STRONG_AI_TEXT_KEYWORDS = re.compile(
    r"\b(fine[- ]?tun|inference|transformer|diffusion|multimodal|"
    r"large language model|retrieval.augmented|rag pipeline|"
    r"vector.?database|embedding.?model|llm.?agent|"
    r"text.?to.?image|speech.?to.?text|foundation model)\b",
    re.IGNORECASE,
)

MODERATE_AI_TEXT_KEYWORDS = re.compile(
    r"\b(machine learning|deep learning|neural net|computer vision|"
    r"natural language|object detection|image classification|"
    r"sentiment analysis|recommendation engine|"
    r"model training|model serving|mlops|"
    r"pytorch|tensorflow|jax|hugging\s?face)\b",
    re.IGNORECASE,
)


# --- Startup signal keywords ---

STARTUP_TEXT_SIGNALS = re.compile(
    r"\b(waitlist|pricing|book a demo|request demo|"
    r"customers|enterprise|saas|api key|free trial|"
    r"sign up|get started|early access|beta access|"
    r"backed by|funded by|raised|series [a-d]|seed round|"
    r"our platform|our product|we help|we build)\b",
    re.IGNORECASE,
)


def compute_ai_score(
    topics: Optional[List[str]] = None,
    description: Optional[str] = None,
    readme_snippet: Optional[str] = None,
    cb_ai_flag: bool = False,
) -> float:
    """
    Compute AI relevance score (0.0 to 1.0) using deterministic rules.

    Scoring:
    - +0.3 if topics include strong AI topics (llm, rag, agents, generative-ai)
    - +0.2 if topics include moderate AI topics (ai, machine-learning, etc.)
    - +0.2 if description/README contains strong AI text keywords
    - +0.1 if description/README contains moderate AI text keywords
    - +0.2 if Crunchbase AI flag is true
    """
    score = 0.0
    topics_set = set(t.lower().strip() for t in (topics or []))

    # Topics-based
    if topics_set & STRONG_AI_TOPICS:
        score += 0.3
    if topics_set & MODERATE_AI_TOPICS:
        score += 0.2

    # Text-based (combine description + readme)
    combined_text = " ".join(filter(None, [description, readme_snippet]))
    if combined_text:
        if STRONG_AI_TEXT_KEYWORDS.search(combined_text):
            score += 0.2
        if MODERATE_AI_TEXT_KEYWORDS.search(combined_text):
            score += 0.1

    # Crunchbase verification
    if cb_ai_flag:
        score += 0.2

    return min(score, 1.0)


def compute_startup_score(
    domain: Optional[str] = None,
    owner_type: Optional[str] = None,
    description: Optional[str] = None,
    readme_snippet: Optional[str] = None,
    has_funding: bool = False,
    has_cb_record: bool = False,
) -> float:
    """
    Compute startup likelihood score (0.0 to 1.0) using deterministic rules.

    Scoring:
    - +0.4 if domain exists and looks like a product site
    - +0.2 if repo owner is an organization
    - +0.2 if README/description contains startup signals
    - +0.2 if has PitchBook funding deal OR Crunchbase company record
    """
    from .domain import is_product_domain

    score = 0.0

    # Domain signal
    if domain and is_product_domain(domain):
        score += 0.4

    # Owner type
    if owner_type and owner_type.lower() == "organization":
        score += 0.2

    # Text signals
    combined_text = " ".join(filter(None, [description, readme_snippet]))
    if combined_text and STARTUP_TEXT_SIGNALS.search(combined_text):
        score += 0.2

    # External verification
    if has_funding or has_cb_record:
        score += 0.2

    return min(score, 1.0)


COMMERCIAL_KEYWORDS = re.compile(
    r"\b(pricing|contact us|enterprise|cloud|api|signup|sign up|"
    r"waitlist|book a demo|request demo|free trial|"
    r"get started|early access|beta access|"
    r"our platform|our product|we help|we build|"
    r"backed by|funded by|raised|series [a-d]|seed round|"
    r"customers|saas|managed service|hosted|on-prem)\b",
    re.IGNORECASE,
)


def compute_startup_likelihood(
    domain: Optional[str] = None,
    owner_type: Optional[str] = None,
    has_org_blog: bool = False,
    description: Optional[str] = None,
    readme_snippet: Optional[str] = None,
    pushed_at_recent: bool = False,
) -> float:
    """
    Compute startup likelihood for a single repo snapshot (0.0 to 1.0).

    Heuristic scoring:
      +0.30 valid external domain (not github.io/docs/social)
      +0.15 owner is an Organization
      +0.10 org has a website/blog field
      +0.25 README/desc contains commercial keywords (pricing, enterprise, etc.)
      +0.10 recently pushed (within last 14 days)
      +0.10 description mentions product/platform/API
    """
    from .domain import is_product_domain

    score = 0.0

    # External product domain
    if domain and is_product_domain(domain):
        score += 0.30

    # Organization owner
    if owner_type and owner_type.lower() == "organization":
        score += 0.15

    # Org has a website
    if has_org_blog:
        score += 0.10

    # Commercial language in text
    combined_text = " ".join(filter(None, [description, readme_snippet]))
    if combined_text:
        matches = COMMERCIAL_KEYWORDS.findall(combined_text)
        if len(matches) >= 3:
            score += 0.25
        elif len(matches) >= 1:
            score += 0.15

    # Recent activity
    if pushed_at_recent:
        score += 0.10

    # Description product signals
    if description:
        product_pattern = re.compile(
            r"\b(platform|product|api|service|tool|solution)\b", re.I
        )
        if product_pattern.search(description):
            score += 0.10

    return round(min(1.0, score), 4)


def extract_ai_tags(
    topics: Optional[List[str]] = None,
    description: Optional[str] = None,
    readme_snippet: Optional[str] = None,
) -> List[str]:
    """
    Extract AI-related tags from topics and text for the ai_tags field.
    Returns deduplicated, sorted list.
    """
    tags = set()
    topics_set = set(t.lower().strip() for t in (topics or []))

    # From topics
    for t in topics_set:
        if t in STRONG_AI_TOPICS or t in MODERATE_AI_TOPICS:
            tags.add(t)

    # From text: extract matched keyword groups
    combined_text = " ".join(filter(None, [description, readme_snippet]))
    if combined_text:
        for match in STRONG_AI_TEXT_KEYWORDS.finditer(combined_text):
            tag = match.group(0).lower().strip()
            tag = re.sub(r"\s+", "-", tag)
            tags.add(tag)

    return sorted(tags)
