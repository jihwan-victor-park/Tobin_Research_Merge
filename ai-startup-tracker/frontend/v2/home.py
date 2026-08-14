"""The V2 homepage — page rhythm and composition.

Order: status rule → hero → ask bar → answer → market strip → weekly brief →
formation analysis → geography → latest additions → methodology footer. No
section owns a full screen; the reader should reach real data immediately and
keep meeting it on the way down.

`render()` draws only the page body. The host script owns navigation, so the
V1 pages are reachable exactly as before.
"""
from __future__ import annotations

import streamlit as st

from . import components as C
from . import data as D
from . import intelligence as I
from .theme import Palette


def _answer_for(question: str) -> I.Answer:
    """Cached per question so re-renders (theme flips, nav) do not re-query.

    The progress line is drawn into a placeholder and cleared when the answer
    lands, so it does not linger above the panel it was announcing.
    """
    cache: dict = st.session_state.setdefault("v2_answer_cache", {})
    if question not in cache:
        slot = st.empty()
        with slot:
            C.loading("Querying dataset")
        try:
            cache[question] = I.answer(question)
        finally:
            slot.empty()
    return cache[question]


def render(p: Palette) -> None:
    snap = D.snapshot()

    C.status_line(snap)
    C.hero()

    # ── Ask the ecosystem ────────────────────────────────────────────────
    question = C.ask_bar(I.EXAMPLES)
    active = question or st.session_state.get("v2_last_question")
    if active:
        C.answer_panel(_answer_for(active), p)
    C.spacer(46)

    # ── Dataset scale ────────────────────────────────────────────────────
    ai_share = f'{snap.ai_share:.1f}<span style="font-size:0.55em">%</span>'
    as_of = snap.as_of.strftime("%b %d") if snap.as_of else "—"
    C.metrics_strip([
        ("Companies tracked", f"{snap.total:,}",
         # Ingestion, not formation — bulk imports land in single days, so this
         # is deliberately labelled as records added rather than growth.
         f"+{snap.added_30d:,} records in the 30 days to {as_of}"
         if snap.added_30d else "no additions recorded"),
        ("Not in Crunchbase or PitchBook", f"{snap.hidden:,}",
         f"{snap.hidden_share:.1f}% of the dataset"),
        ("AI share", ai_share, "of all tracked companies"),
        ("Countries", f"{snap.countries:,}", "with at least one headquarters"),
    ])
    C.spacer(52)

    # ── This week in AI ──────────────────────────────────────────────────
    week = D.latest_week()
    facts = D.channel_facts()
    cats = D.category_momentum(limit=6)
    geo = D.geographic_momentum(limit=6)

    if week.start and week.end:
        window = (f"{week.start.strftime('%b %d')} — {week.end.strftime('%b %d, %Y')}"
                  .upper())
    else:
        window = "NO RECENT INTAKE"
    C.section_head("This week in AI", window)

    lead, signals = st.columns([1.62, 1], gap="large")
    with lead:
        C.lead_story(week, facts, snap)
        C.coverage(I.coverage_links("AI startups"))
        C.secondary_stories(week, facts, snap, cats, geo)
    with signals:
        C.section_head("Market signals", "SHARE Δ", soft=True)
        C.market_signals(cats)
        if not cats.empty:
            (r0, r1), (p0, p1) = D.cohorts()
            C._md(f'<p class="v2-small" style="margin-top:16px">Change in each '
                  f'category&rsquo;s share of AI company formation, {r0}&ndash;{r1} '
                  f'against {p0}&ndash;{p1}. The figures beside each name are its '
                  f'current share and company count.</p>')
        C.section_head("Where the week came from", "COMPANIES", soft=True, top=40)
        C.discovery_channels(week)
    C.spacer(56)

    # ── Formation analysis ───────────────────────────────────────────────
    f = D.formation()
    meta = ""
    if f.recent_range and f.cohort_total:
        meta = f"{f.cohort_total:,} FOUNDED {f.recent_range[0]}–{f.recent_range[1]}"
        if f.peak_year:
            meta += f" · PEAK {f.peak_year}"
    C.section_head("AI company formation", meta)

    chart, ranking = st.columns([1.75, 1], gap="large")
    with chart:
        C.formation_chart(f, p)
    with ranking:
        C.section_head("Fastest-growing categories", "SHARE Δ", soft=True)
        C.category_ranking(cats)
    C.spacer(52)

    # ── Geography ────────────────────────────────────────────────────────
    C.section_head("Geographic momentum",
                   f"SHARE OF {f.recent_range[0]}–{f.recent_range[1]} FORMATION"
                   if f.recent_range else "")
    cities, world = st.columns([1, 1.65], gap="large")
    with cities:
        C.geographic_momentum(geo)
        regions = D.region_totals()
        if not regions.empty:
            C.section_head("Hidden companies by region", "SHARE", soft=True, top=40)
            total = int(regions["n"].sum()) or 1
            C.rank_rows(
                regions.head(5).assign(
                    label=regions["region"],
                    value=regions["n"] / total * 100,
                    sub=regions["n"].map(lambda n: f"{int(n):,}"),
                )[["label", "value", "sub"]],
                unit="%", show_bar=True,
            )
    with world:
        C.world_map(D.country_totals(), p, height=414)
    C.spacer(52)

    # ── Latest additions ─────────────────────────────────────────────────
    C.section_head("Latest hidden discoveries",
                   "NOT IN CRUNCHBASE OR PITCHBOOK")
    C.latest_additions(D.recent_hidden(limit=8))

    C.footer(snap, f)
