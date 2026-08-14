"""Natural-language questions answered from the company dataset.

The rule this module is built around: **the model never supplies a number.**

A question is resolved to a scope (a category, a place, a discovery channel),
the scope is turned into ordinary SQL aggregates, and only then is a language
model asked to write two to four sentences *about figures that are already
computed*. If no model is configured the same figures render under a
deterministic summary, so the feature degrades to plain analytics rather than
to nothing — and never to invention.

Scope resolution is likewise constrained: the model may only choose from the
tag vocabulary that exists in the database, so it cannot invent a category the
tracker does not actually cover.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st
from sqlalchemy import text

from backend.db.connection import get_engine
from backend.utils.ai_filter import ai_filter_sql

from . import data as D

log = logging.getLogger("v2.intelligence")

AI = ai_filter_sql()
_FALLBACK_MODEL = "claude-haiku-4-5-20251001"

EXAMPLES = [
    "Which AI sectors are growing fastest?",
    "Where are new AI companies forming outside the U.S.?",
    "Which companies are missing from Crunchbase?",
    "What is happening in AI robotics?",
]


# ── Scope ────────────────────────────────────────────────────────────────

@dataclass
class Scope:
    """What a question turned out to be about."""
    kind: str = "overview"        # overview | category | place | hidden | momentum
    tag: str | None = None        # an ai_tags value
    tag_label: str | None = None
    country: str | None = None    # normalized country name
    city: str | None = None
    non_us: bool = False
    hidden_only: bool = False
    ranking_question: bool = False   # asks across categories, not about one
    resolved_by: str = "keyword"     # keyword | model


@dataclass
class Metric:
    label: str
    value: str
    delta: str | None = None
    direction: str | None = None  # up | down | flat


@dataclass
class Answer:
    question: str
    headline: str
    narrative: str
    scope: Scope
    metrics: list[Metric] = field(default_factory=list)
    series: pd.DataFrame = field(default_factory=pd.DataFrame)     # year, n
    ranking: pd.DataFrame = field(default_factory=pd.DataFrame)    # label, value, sub
    ranking_title: str = ""
    ranking_unit: str = "%"
    companies: pd.DataFrame = field(default_factory=pd.DataFrame)
    basis: str = ""               # how the figures were computed
    sources: list[tuple[str, str]] = field(default_factory=list)
    # "model"    — written by Claude, every figure verified against the facts
    # "computed" — deterministic summary; no model configured or it returned nothing
    # "rejected" — a model reply contained a figure not in the facts and was dropped
    narrative_source: str = "computed"
    empty: bool = False


# ── Vocabulary the resolver is allowed to choose from ────────────────────

@st.cache_data(ttl=900, show_spinner=False)
def _tag_vocabulary(min_n: int = 60) -> list[str]:
    df = D._frame(f"""
        SELECT t AS tag, COUNT(*) AS n
        FROM companies c, unnest(c.ai_tags) t
        WHERE {ai_filter_sql('c')}
        GROUP BY 1 HAVING COUNT(*) >= :n ORDER BY 2 DESC
    """, n=min_n)
    if df.empty:
        return []
    return [t for t in df["tag"].tolist() if t not in D._TAG_SKIP]


@st.cache_data(ttl=900, show_spinner=False)
def _place_vocabulary() -> tuple[list[str], list[str]]:
    countries = D.country_totals(min_companies=20)
    cities = D._frame(f"""
        SELECT city, COUNT(*) AS n FROM companies
        WHERE {AI} AND city IS NOT NULL AND city <> ''
        GROUP BY 1 HAVING COUNT(*) >= 40 ORDER BY 2 DESC LIMIT 120
    """)
    return (
        sorted(countries["country"].tolist()) if not countries.empty else [],
        sorted(cities["city"].astype(str).str.strip().tolist()) if not cities.empty else [],
    )


# Words a reader uses that are not literally the tag string.
_SYNONYMS = {
    "agents": ["agent", "agentic", "ai agents", "autonomous agents"],
    "generative-ai": ["generative", "genai", "gen ai", "image generation", "text to image"],
    "llm": ["language model", "language models", "foundation model", "gpt"],
    "nlp": ["natural language", "text analysis"],
    "computer-vision": ["vision", "image recognition", "visual"],
    "robotics": ["robot", "robots", "robotic", "humanoid"],
    "autonomous-vehicles": ["self driving", "self-driving", "autonomous driving", "av"],
    "rag": ["retrieval augmented", "retrieval-augmented", "vector search"],
    "predictive-analytics": ["forecasting", "prediction"],
    "speech-recognition": ["speech", "voice", "audio"],
    "rpa": ["process automation", "workflow automation"],
    "big-data": ["data infrastructure", "data platform"],
}

_HIDDEN_WORDS = ("hidden", "crunchbase", "pitchbook", "commercial database",
                 "not in", "before they", "undiscovered", "invisible", "unregistered")
_MOMENTUM_WORDS = ("fastest", "growing", "growth", "accelerat", "rising", "momentum",
                   "trend", "hot", "emerging", "this week", "this month", "changed")
_NON_US_WORDS = ("outside the us", "outside the u.s", "outside the united states",
                 "non-us", "outside america", "rest of the world", "internationally")

# "Which sectors are growing?" asks across categories; pinning it to a single
# tag answers a question nobody asked. These stay at ranking scope, and the
# model is not consulted for a tag.
_RANKING_PATTERNS = (
    r"\bwhich\s+(?:ai\s+)?(?:categor|sector|vertical|area|space|industr|field)",
    r"\bwhat\s+(?:ai\s+)?(?:categor|sector|vertical|area|space|industr|field)",
    r"\bfastest[- ]growing\b",
    r"\btop\s+\d*\s*(?:categor|sector|vertical|industr)",
)


def _is_ranking_question(ql: str) -> bool:
    return any(re.search(p, ql) for p in _RANKING_PATTERNS)


def _resolve_keyword(q: str) -> Scope:
    ql = f" {q.lower().strip()} "
    scope = Scope()
    ranking = _is_ranking_question(ql)

    if not ranking:
        for tag in _tag_vocabulary():
            needles = [tag.replace("-", " "), tag] + _SYNONYMS.get(tag, [])
            if any(re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", ql)
                   for n in needles):
                scope.tag, scope.tag_label, scope.kind = tag, D.tag_label(tag), "category"
                break

    countries, cities = _place_vocabulary()
    for city in cities:
        if re.search(rf"(?<![a-z0-9]){re.escape(city.lower())}(?![a-z0-9])", ql):
            scope.city, scope.kind = city, "place"
            break
    if not scope.city:
        for country in countries:
            if re.search(rf"(?<![a-z0-9]){re.escape(country.lower())}(?![a-z0-9])", ql):
                scope.country, scope.kind = country, "place"
                break

    if any(w in ql for w in _NON_US_WORDS):
        scope.non_us, scope.kind = True, "place"
        scope.country = None
    if any(w in ql for w in _HIDDEN_WORDS):
        scope.hidden_only = True
        if scope.kind == "overview":
            scope.kind = "hidden"
    if ranking or (scope.kind == "overview" and any(w in ql for w in _MOMENTUM_WORDS)):
        scope.kind = "momentum"
    scope.ranking_question = ranking
    return scope


def _resolve_with_model(q: str, scope: Scope) -> Scope:
    """Let the model pick a category, but only from tags that exist."""
    vocab = _tag_vocabulary()
    if not vocab or not _model_available():
        return scope
    reply = _ask_model(
        system=("You map a question to at most one category from a fixed list. "
                "Reply with JSON only: {\"tag\": \"<exact list value>\"} or {\"tag\": null}. "
                "Choose null unless the question is clearly about that category."),
        user=f"Question: {q}\n\nAllowed values:\n" + "\n".join(vocab),
        max_tokens=100,
    )
    if not reply:
        return scope
    try:
        m = re.search(r"\{.*\}", reply, re.S)
        tag = json.loads(m.group(0)).get("tag") if m else None
    except Exception:                              # noqa: BLE001
        return scope
    if tag in vocab:
        scope.tag, scope.tag_label = tag, D.tag_label(tag)
        scope.kind = "category"
        scope.resolved_by = "model"
    return scope


def resolve(q: str) -> Scope:
    scope = _resolve_keyword(q)
    if (scope.kind in ("overview", "momentum") and not scope.tag
            and not scope.ranking_question):
        scope = _resolve_with_model(q, scope)
    return scope


# ── Aggregates ───────────────────────────────────────────────────────────

def _where(scope: Scope, alias: str = "c") -> tuple[str, dict]:
    """SQL predicate + params for a scope. Always AI-filtered."""
    a = f"{alias}."
    clauses = [ai_filter_sql(alias)]
    params: dict = {}
    if scope.tag:
        clauses.append(f":tag = ANY({a}ai_tags)")
        params["tag"] = scope.tag
    if scope.hidden_only:
        clauses.append(f"{a}verification_status = :hidden")
        params["hidden"] = D.HIDDEN
    if scope.city:
        clauses.append(f"lower(trim({a}city)) = :city")
        params["city"] = scope.city.lower()
    return " AND ".join(clauses), params


def _country_filtered(df: pd.DataFrame, scope: Scope) -> pd.DataFrame:
    """Country and non-US filters run in pandas — the raw column is too messy for SQL."""
    if df.empty or "country" not in df.columns:
        return df
    out = df.copy()
    out["country"] = out["country"].map(D.clean_country)
    if scope.country:
        out = out[out["country"] == scope.country]
    if scope.non_us:
        out = out[out["country"].notna() & (out["country"] != "United States")]
    return out


def _scope_series(scope: Scope) -> pd.DataFrame:
    """Formation by founding year within the scope."""
    where, params = _where(scope)
    df = D._frame(f"""
        SELECT c.founded_year AS year, c.country, COUNT(*) AS n
        FROM companies c
        WHERE {where} AND c.founded_year BETWEEN 2012 AND EXTRACT(YEAR FROM NOW())::int
        GROUP BY 1, 2
    """, **params)
    if df.empty:
        return df
    df = _country_filtered(df, scope)
    if df.empty:
        return df
    return (df.groupby("year", as_index=False)["n"].sum()
              .astype({"year": int, "n": int}).sort_values("year"))


def _scope_totals(scope: Scope) -> dict:
    """Headline counts for the scope, plus its share-of-cohort movement."""
    where, params = _where(scope)
    (r0, r1), (p0, p1) = D.cohorts()
    df = D._frame(f"""
        SELECT c.country,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE c.verification_status = :h) AS hidden,
               COUNT(*) FILTER (WHERE c.founded_year BETWEEN :r0 AND :r1) AS recent,
               COUNT(*) FILTER (WHERE c.founded_year BETWEEN :p0 AND :p1) AS prior
        FROM companies c WHERE {where}
        GROUP BY 1
    """, h=D.HIDDEN, r0=r0, r1=r1, p0=p0, p1=p1, **params)
    if df.empty:
        return {}
    df = _country_filtered(df, scope)
    if df.empty:
        return {}

    total = int(df["total"].sum())
    recent, prior = int(df["recent"].sum()), int(df["prior"].sum())
    rt = int(D._scalar(f"SELECT COUNT(*) FROM companies WHERE {AI} "
                       "AND founded_year BETWEEN :a AND :b", a=r0, b=r1))
    pt = int(D._scalar(f"SELECT COUNT(*) FROM companies WHERE {AI} "
                       "AND founded_year BETWEEN :a AND :b", a=p0, b=p1))
    growth = None
    if rt and pt and prior:
        growth = ((recent / rt) / (prior / pt) - 1) * 100

    return {
        "total": total,
        "hidden": int(df["hidden"].sum()),
        "countries": int(df["country"].nunique()),
        "recent": recent,
        "prior": prior,
        "share_recent": (recent / rt * 100) if rt else None,
        "share_prior": (prior / pt * 100) if pt else None,
        "growth": growth,
        "recent_range": (r0, r1),
        "prior_range": (p0, p1),
        "top_countries": (df.sort_values("total", ascending=False)
                            .head(5)[["country", "total"]]
                            .dropna(subset=["country"])),
    }


def _scope_companies(scope: Scope, limit: int = 6) -> pd.DataFrame:
    """Named examples — hidden companies only, so nothing licensed is republished."""
    s = Scope(**{**scope.__dict__, "hidden_only": True})
    where, params = _where(s)
    df = D._frame(f"""
        SELECT c.name, c.domain, c.country, c.city, c.founded_year,
               LEFT(c.description, 260) AS description,
               c.source_domain, c.incubator_source
        FROM companies c
        WHERE {where}
          AND c.name IS NOT NULL AND c.name <> ''
          AND c.description IS NOT NULL AND length(c.description) > 60
          AND c.description NOT ILIKE 'Hugging Face organization%%'
        ORDER BY c.first_seen_at DESC NULLS LAST
        LIMIT :lim
    """, lim=limit * 5, **params)
    if df.empty:
        return df
    df = _country_filtered(df, scope)
    return D.drop_non_startups(df).head(limit).reset_index(drop=True)


# ── Narrative ────────────────────────────────────────────────────────────

def _model_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def _ask_model(system: str, user: str, max_tokens: int = 400) -> str | None:
    try:
        import anthropic
    except ImportError:
        return None
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    model = (os.getenv("ANTHROPIC_MODEL") or _FALLBACK_MODEL).strip()
    client = anthropic.Anthropic(api_key=key)
    for candidate in (model, _FALLBACK_MODEL):
        try:
            msg = client.messages.create(
                model=candidate, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}],
            )
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        except Exception as exc:                   # noqa: BLE001
            log.warning("v2 model call failed on %s: %s", candidate, exc)
    return None


_NARRATIVE_SYSTEM = (
    "You write two to four sentences of analyst commentary for a company-formation "
    "dataset covering AI startups.\n"
    "Absolute rule: every number you write must appear verbatim in the FACTS block. "
    "Never estimate, extrapolate, round differently, or introduce a figure that is "
    "not given. If the facts do not support a claim, leave the claim out.\n"
    "Do not assert timing, causation or sequence — that one thing happened before "
    "another, or caused it — unless a fact states it. The facts are counts and "
    "shares, not a chronology.\n"
    "Quote figures exactly as given. Do not round to a nicer number: write "
    "'5,161', never 'more than 5,000'. Do not compute new figures from the ones "
    "you are given.\n"
    "Say what the figures show and what limits them. Plain English, no hype, no "
    "bullet points, no headings, no markdown. Do not open with 'The data shows'."
)


_NUM_IN_TEXT = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _allowed_numbers(facts) -> set[float]:
    """Every number the narrative is permitted to contain.

    Walks the facts recursively and admits each numeric value plus the roundings
    a writer would legitimately produce from it (nearest integer, one decimal).
    """
    allowed: set[float] = set()

    def add(v: float) -> None:
        allowed.add(float(v))
        allowed.add(float(round(v)))
        allowed.add(float(round(v, 1)))
        allowed.add(float(abs(v)))
        allowed.add(float(round(abs(v), 1)))
        allowed.add(float(round(abs(v))))

    def walk(node) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            add(node)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)

    walk(facts)
    return allowed


def _numbers_check_out(text: str, facts) -> bool:
    """True when every figure in the narrative traces back to the facts.

    The prompt already forbids inventing numbers; models still occasionally slip
    a digit. Since the whole product claim is that figures are computed rather
    than generated, the prose is checked rather than trusted, and a narrative
    that fails is dropped for the deterministic one.
    """
    allowed = _allowed_numbers(facts)
    for token in _NUM_IN_TEXT.findall(text):
        try:
            value = float(token.replace(",", ""))
        except ValueError:
            continue
        # Bare years are prose, not claims drawn from the aggregates.
        if value.is_integer() and 1900 <= value <= 2100:
            continue
        if not any(abs(value - a) < 0.051 for a in allowed):
            log.warning("v2 narrative rejected: %r is not in the facts", token)
            return False
    return True


def _narrate(question: str, scope: Scope, facts: dict) -> tuple[str, str]:
    """Return (narrative, source) where source is how the prose was produced."""
    fallback = _template_narrative(scope, facts)
    if not _model_available():
        return fallback, "computed"
    reply = _ask_model(
        system=_NARRATIVE_SYSTEM,
        user=(f"QUESTION: {question}\n\nFACTS (the only numbers you may use):\n"
              f"{json.dumps(facts, indent=2, default=str)}"),
        max_tokens=350,
    )
    if not reply or not reply.strip():
        return fallback, "computed"
    reply = reply.strip()
    if not _numbers_check_out(reply, facts):
        return fallback, "rejected"
    return reply, "model"


def _fmt_pct(v) -> str:
    return "—" if v is None else f"{v:+.1f}%"


def _template_narrative(scope: Scope, facts: dict) -> str:
    """Deterministic prose for when no model is configured."""
    subject = facts.get("subject", "AI companies")
    total = facts.get("total")
    if not total:
        return (f"The dataset holds nothing under {subject} yet. "
                "Coverage grows as new sources are ingested.")

    cats = facts.get("category_share_change") or []
    if scope.ranking_question and cats:
        rr, pr = facts.get("recent_range"), facts.get("prior_range")
        lead = cats[0]
        others = ", ".join(
            f"{c['category']} ({c['share_change_pct']:+.1f}%)" for c in cats[1:3])
        return (
            f"{lead['category']} is taking share fastest: it accounts for "
            f"{lead['share_of_recent_cohort_pct']:.2f}% of AI companies founded in "
            f"{rr[0]}–{rr[1]}, against {lead['share_of_prior_cohort_pct']:.2f}% in "
            f"{pr[0]}–{pr[1]} — a {lead['share_change_pct']:+.1f}% move on "
            f"{lead['companies_in_recent_cohort']:,} companies. "
            + (f"{others} follow. " if others else "")
            + "Shares are used rather than raw counts because the most recent "
              "founding years are still filling in."
        )

    # `subject` is a display label ("Generative AI", "London", "AI companies
    # outside the United States"), so it is used as written — case-folding it
    # produced "the united states".
    opening = (f"The tracker holds {total:,} AI companies" if subject == "AI companies"
               else f"The tracker holds {total:,} companies under {subject}")
    bits = [opening]
    if facts.get("countries"):
        bits.append(f"across {facts['countries']:,} countries")
    first = " ".join(bits) + "."

    second = ""
    if facts.get("hidden"):
        pct = facts["hidden"] / total * 100
        second = (f" Of those, {facts['hidden']:,} ({pct:.1f}%) appear in neither "
                  "Crunchbase nor PitchBook.")

    third = ""
    g, rr, pr = facts.get("growth"), facts.get("recent_range"), facts.get("prior_range")
    if g is not None and rr and pr:
        direction = "gained" if g >= 0 else "lost"
        third = (f" Measured as a share of all AI company formation, the {rr[0]}–{rr[1]} "
                 f"founding cohort {direction} {abs(g):.1f}% against {pr[0]}–{pr[1]}.")

    fourth = ""
    if facts.get("provisional_note"):
        fourth = f" {facts['provisional_note']}"
    return first + second + third + fourth


# ── Coverage links ───────────────────────────────────────────────────────

# No newsroom feed is wired into the database yet, so the page does not claim to
# have found specific articles. These are the outlets' own search endpoints for
# the subject of the answer: real destinations, honestly labelled, and easy to
# swap for true headlines once a coverage table exists.
_OUTLETS = [
    ("Reuters", "https://www.reuters.com/site-search/?query={q}"),
    ("Financial Times", "https://www.ft.com/search?q={q}"),
    ("TechCrunch", "https://techcrunch.com/?s={q}"),
    ("The Verge", "https://www.theverge.com/search?q={q}"),
]


def coverage_links(subject: str) -> list[tuple[str, str]]:
    q = quote_plus(f"{subject} AI startups".strip())
    return [(name, tmpl.format(q=q)) for name, tmpl in _OUTLETS]


# ── Entry point ──────────────────────────────────────────────────────────

def _subject(scope: Scope) -> str:
    if scope.tag_label:
        return scope.tag_label
    if scope.city:
        return scope.city
    if scope.country:
        return scope.country
    if scope.non_us:
        return "AI companies outside the United States"
    if scope.hidden_only:
        return "companies missing from commercial databases"
    return "AI companies"


def _metrics_for(scope: Scope, totals: dict, cats: pd.DataFrame) -> list[Metric]:
    """The strip that sits under the narrative, matched to what was asked.

    A ranking question is about the leaders, not about the dataset as a whole,
    so quoting the full-dataset totals there would answer a different question.
    """
    r0, r1 = totals["recent_range"]
    p0, p1 = totals["prior_range"]

    if scope.ranking_question and not cats.empty:
        lead = cats.iloc[0]
        g = float(lead["growth"])
        return [
            Metric(f"{lead['label']} share Δ", _fmt_pct(g),
                   delta=f"{r0}–{r1} vs {p0}–{p1}",
                   direction="up" if g > 0.5 else "down" if g < -0.5 else "flat"),
            Metric("Leader share now", f"{float(lead['share']):.2f}%",
                   delta=f"of AI formation in {r0}–{r1}"),
            Metric("Companies", f"{int(lead['recent']):,}", delta="in that cohort"),
            Metric("Categories ranked", f"{len(cats):,}"),
        ]

    metrics = [
        Metric("Companies", f"{totals['total']:,}"),
        Metric("Hidden", f"{totals['hidden']:,}",
               delta=f"{totals['hidden'] / totals['total'] * 100:.0f}% of scope"),
    ]
    g = totals.get("growth")
    if g is not None:
        metrics.insert(0, Metric(
            "Share of formation", _fmt_pct(g), delta=f"{r0}–{r1} vs {p0}–{p1}",
            direction="up" if g > 0.5 else "down" if g < -0.5 else "flat",
        ))

    # A city name can occur in several countries, so "countries" for a city
    # scope reads as a coverage claim it does not make. Name the main one.
    if scope.city and not totals["top_countries"].empty:
        top = totals["top_countries"].iloc[0]
        metrics.append(Metric("Primary country", str(top["country"]),
                              delta=f"{int(top['total']):,} companies"))
    else:
        metrics.append(Metric("Countries", f"{totals['countries']:,}"))
    return metrics


def _headline(scope: Scope, totals: dict, cats: pd.DataFrame) -> str:
    subject = _subject(scope)
    g = totals.get("growth")
    if scope.ranking_question and not cats.empty:
        lead = cats.iloc[0]
        return f"{lead['label']} is taking share fastest"
    if scope.kind == "category" and g is not None:
        verb = "gains share of new AI company formation" if g >= 0 else \
               "loses share of new AI company formation"
        return f"{subject} {verb}"
    if scope.kind == "place" and totals.get("total"):
        return f"{subject}: {totals['total']:,} AI companies tracked"
    if scope.hidden_only:
        return "Companies the commercial databases have not registered"
    if scope.kind == "momentum":
        return "Where AI company formation is shifting"
    return f"{subject} across the tracked ecosystem"


def answer(question: str) -> Answer:
    """Resolve a question to real aggregates, then narrate them."""
    question = (question or "").strip()
    scope = resolve(question)
    subject = _subject(scope)

    totals = _scope_totals(scope)
    if not totals or not totals.get("total"):
        return Answer(
            question=question, scope=scope, empty=True,
            headline="No companies match that scope yet",
            narrative=("The tracker has no records for that combination. Coverage is "
                       "strongest for AI categories, and for countries and cities that "
                       "already carry a location in the dataset."),
            basis="Searched the full company table with the standard AI filter.",
        )

    series = _scope_series(scope)
    f = D.formation()
    provisional_note = ""
    if f.last_complete and not series.empty and int(series["year"].max()) > f.last_complete:
        provisional_note = (f"Founding years after {f.last_complete} are still filling in, "
                            "so the final points understate formation.")

    # Build the ranking before narrating so its rows can go into the facts —
    # otherwise a "which categories are growing?" answer has no leaders to name.
    ranking, ranking_title, unit = pd.DataFrame(), "", "%"
    cats = pd.DataFrame()
    if scope.kind in ("momentum", "overview") and not scope.tag:
        cats = D.category_momentum(limit=6)
        if not cats.empty:
            ranking = pd.DataFrame({
                "label": cats["label"],
                "value": cats["growth"].astype(float),
                "sub": cats["recent"].map(lambda n: f"{int(n):,} cos"),
            })
            ranking_title = "Categories by share change"
    elif not totals["top_countries"].empty:
        tc = totals["top_countries"]
        ranking = pd.DataFrame({
            "label": tc["country"],
            "value": (tc["total"] / totals["total"] * 100).astype(float),
            "sub": tc["total"].map(lambda n: f"{int(n):,}"),
        })
        ranking_title = "Share of this scope"

    facts = {
        "subject": subject,
        "total": totals["total"],
        "hidden_not_in_crunchbase_or_pitchbook": totals["hidden"],
        "countries": totals["countries"],
        "recent_cohort_years": totals["recent_range"],
        "recent_cohort_companies": totals["recent"],
        "prior_cohort_years": totals["prior_range"],
        "prior_cohort_companies": totals["prior"],
        "share_of_all_ai_formation_recent_pct": (
            round(totals["share_recent"], 2) if totals["share_recent"] is not None else None),
        "share_of_all_ai_formation_prior_pct": (
            round(totals["share_prior"], 2) if totals["share_prior"] is not None else None),
        "share_change_pct": round(totals["growth"], 1) if totals["growth"] is not None else None,
        "top_countries": (totals["top_countries"].to_dict("records")
                          if not totals["top_countries"].empty else []),
        "provisional_note": provisional_note,
        "recent_range": totals["recent_range"],
        "prior_range": totals["prior_range"],
        "hidden": totals["hidden"],
        "growth": round(totals["growth"], 1) if totals["growth"] is not None else None,
    }
    # A question about what commercial databases miss needs the discovery
    # channels in front of the model, or it correctly refuses for lack of facts.
    if scope.hidden_only or scope.kind == "hidden":
        ch = D.channel_facts()
        facts["how_hidden_companies_were_discovered_counts"] = {
            "carry_a_public_code_repository": ch.get("github_native"),
            "listed_in_an_accelerator_or_vc_portfolio": ch.get("portfolio"),
            "named_in_a_government_grant_award": ch.get("grant_backed"),
        }
        facts["hidden_companies_with_a_live_website"] = ch.get("with_domain")

    if not cats.empty:
        facts["category_share_change"] = [
            {"category": r["label"],
             "share_of_recent_cohort_pct": round(float(r["share"]), 2),
             "share_of_prior_cohort_pct": round(float(r["share_prior"]), 2),
             "share_change_pct": round(float(r["growth"]), 1),
             "companies_in_recent_cohort": int(r["recent"])}
            for _, r in cats.iterrows()
        ]

    narrative, narrative_source = _narrate(question, scope, facts)

    metrics = _metrics_for(scope, totals, cats)

    (r0, r1), (p0, p1) = D.cohorts()
    basis = (f"Counts run against the live company table with the tracker's standard AI "
             f"filter. Growth compares the {r0}–{r1} founding cohort's share of all AI "
             f"company formation with {p0}–{p1}, which removes the effect of recent years "
             f"still being incomplete."
             + (f" {provisional_note}" if provisional_note else ""))

    return Answer(
        question=question,
        headline=_headline(scope, totals, cats),
        narrative=narrative,
        scope=scope,
        metrics=metrics,
        series=series,
        ranking=ranking,
        ranking_title=ranking_title,
        ranking_unit=unit,
        companies=_scope_companies(scope),
        basis=basis,
        sources=coverage_links(subject),
        narrative_source=narrative_source,
    )
