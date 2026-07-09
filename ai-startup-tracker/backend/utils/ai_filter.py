"""Canonical "is this company AI" SQL predicate — single source of truth.

Combines four independent signals, each catching companies the others miss:
  - cb_ai_tagged   — Crunchbase's own AI taxonomy
  - ai_score >= 0.5 — keyword/LLM-derived score (ceiling ~0.3 for PitchBook
    rows on keyword text alone, so this alone under-counts PB companies)
  - ai_mentioned   — broad free-text AI mention flag
  - llm_ai_verified — Haiku batch classifier verdict for PitchBook companies
    the keyword cascade couldn't decide (scripts/classify_pb_ai_with_llm.py)

Previously this predicate was duplicated ~15 times across the dashboard and
research export script with inconsistent syntax (some included ai_mentioned,
some didn't; some used a 0.3 threshold, most used 0.5). Import this instead
of hand-writing the SQL so every count in the app agrees.
"""


def ai_filter_sql(alias: str = "") -> str:
    """Return the AI predicate as a SQL fragment, optionally table-aliased.

    ai_filter_sql()    -> "(cb_ai_tagged = TRUE OR ...)"
    ai_filter_sql("c") -> "(c.cb_ai_tagged = TRUE OR c.ai_score >= 0.5 OR ...)"
    """
    p = f"{alias}." if alias else ""
    return (
        f"({p}cb_ai_tagged = TRUE OR {p}ai_score >= 0.5 "
        f"OR {p}ai_mentioned = TRUE OR {p}llm_ai_verified = TRUE)"
    )


# Bare (unaliased) fragment for the common case — most dashboard queries
# select directly from `companies` with no alias.
AI_FILTER_SQL = ai_filter_sql()
