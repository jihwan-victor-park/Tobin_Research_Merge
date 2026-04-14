"""
Rule-based AI subdomain and stack layer classifier.

No LLM calls — uses keyword matching on topics, description, and README.

Outputs:
  ai_subdomain: one of SUBDOMAINS
  stack_layer:  one of LAYERS
"""
import re
from typing import List, Optional, Tuple


# ── Valid categories ──────────────────────────────────────────────────

SUBDOMAINS = [
    "Agents", "RAG/Retrieval", "Model/Training", "Inference/Serving",
    "Data/Scraping", "Vision/OCR", "Audio/Speech", "DevTools",
    "Eval/Observability", "Other",
]

LAYERS = [
    "Model", "Infra", "Data", "Framework", "Agent", "App", "Other",
]


# ── Keyword rules (order matters — first match wins) ─────────────────

# Each rule: (subdomain, compiled_regex)
_SUBDOMAIN_RULES: List[Tuple[str, re.Pattern]] = [
    ("Agents", re.compile(
        r"\b(agent|agents|agentic|multi.?agent|autonomous.?agent|"
        r"tool.?use|function.?call|crew.?ai|autogen|langgraph|"
        r"swarm|orchestrat|reason.?act)\b", re.I)),
    ("RAG/Retrieval", re.compile(
        r"\b(rag|retrieval.?augmented|vector.?database|vector.?store|"
        r"knowledge.?base|semantic.?search|embedding.?search|"
        r"chunk|retriev|llamaindex|langchain|rerank|"
        r"document.?qa|pdf.?chat)\b", re.I)),
    ("Model/Training", re.compile(
        r"\b(fine.?tun|pre.?train|train|lora|qlora|rlhf|dpo|"
        r"alignment|distill|quantiz|pruning|"
        r"foundation.?model|large.?language|"
        r"bert|gpt|llama|mistral|mixtral|gemma|phi|"
        r"checkpoint|hyperparameter)\b", re.I)),
    ("Inference/Serving", re.compile(
        r"\b(inference|serving|deploy|vllm|tgi|triton|"
        r"onnx|tensorrt|llm.?server|model.?server|"
        r"batch.?inference|streaming|token.?per.?sec|"
        r"endpoint|gpu.?optim)\b", re.I)),
    ("Vision/OCR", re.compile(
        r"\b(computer.?vision|image|object.?detect|segmentat|"
        r"ocr|optical.?character|yolo|diffusion|"
        r"stable.?diffusion|text.?to.?image|image.?gen|"
        r"visual|multimodal|vlm)\b", re.I)),
    ("Audio/Speech", re.compile(
        r"\b(speech|audio|voice|asr|tts|text.?to.?speech|"
        r"speech.?to.?text|whisper|transcri|"
        r"music|sound|speaker)\b", re.I)),
    ("Data/Scraping", re.compile(
        r"\b(scrap|crawl|data.?pipeline|data.?extract|"
        r"dataset|data.?collect|etl|"
        r"synthetic.?data|annotation|label)\b", re.I)),
    ("Eval/Observability", re.compile(
        r"\b(eval|benchmark|observ|monitor|trac|"
        r"prompt.?engineer|guardrail|safety|"
        r"test|metric|leaderboard|"
        r"langfuse|langsmith|phoenix|arize)\b", re.I)),
    ("DevTools", re.compile(
        r"\b(sdk|cli|api|framework|library|toolkit|"
        r"plugin|extension|integration|wrapper|"
        r"developer|devtool|open.?source|"
        r"template|starter|boilerplate)\b", re.I)),
]

_LAYER_RULES: List[Tuple[str, re.Pattern]] = [
    ("Agent", re.compile(
        r"\b(agent|agentic|multi.?agent|autonomous|"
        r"orchestrat|crew.?ai|autogen|langgraph|swarm)\b", re.I)),
    ("Model", re.compile(
        r"\b(model|llm|bert|gpt|llama|mistral|mixtral|"
        r"foundation|pre.?train|fine.?tun|"
        r"transformer|diffusion|lora|qlora)\b", re.I)),
    ("Infra", re.compile(
        r"\b(infra|inference|serving|deploy|gpu|"
        r"cluster|kubernetes|docker|cloud|"
        r"vllm|triton|tensorrt|endpoint|scale)\b", re.I)),
    ("Data", re.compile(
        r"\b(data|dataset|pipeline|etl|scrap|crawl|"
        r"vector.?database|embedding.?store|"
        r"annotation|label|synthetic)\b", re.I)),
    ("Framework", re.compile(
        r"\b(framework|library|sdk|toolkit|"
        r"langchain|llamaindex|langfuse|"
        r"pytorch|tensorflow|jax|hugging.?face)\b", re.I)),
    ("App", re.compile(
        r"\b(app|application|platform|product|saas|"
        r"dashboard|frontend|demo|chatbot|"
        r"chat|assistant|copilot|ui)\b", re.I)),
]


def classify_repo(
    topics: Optional[List[str]] = None,
    description: Optional[str] = None,
    readme_snippet: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Classify a repo into (ai_subdomain, stack_layer).

    Uses keyword matching against topics, description, and README.
    First matching rule wins; defaults to "Other" if nothing matches.

    Returns:
        (subdomain, layer) tuple of strings
    """
    # Build a single text blob to match against
    parts = []
    if topics:
        parts.append(" ".join(topics))
    if description:
        parts.append(description)
    if readme_snippet:
        # Only use first 3000 chars of README for classification
        parts.append(readme_snippet[:3000])

    text = " ".join(parts)
    if not text.strip():
        return ("Other", "Other")

    # Classify subdomain
    subdomain = "Other"
    for name, pattern in _SUBDOMAIN_RULES:
        if pattern.search(text):
            subdomain = name
            break

    # Classify layer
    layer = "Other"
    for name, pattern in _LAYER_RULES:
        if pattern.search(text):
            layer = name
            break

    return (subdomain, layer)
