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

from . import briefing as B
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

    # ── Opening band: headline, ask panel and coverage map as one block ───
    with st.container(key="v2opening"):
        left, right = st.columns([1.42, 1], gap="large")
        with left:
            C.hero()
            question = C.ask_panel(I.EXAMPLES)
        with right:
            C.hero_map(D.country_totals(), p)

    active = question or st.session_state.get("v2_last_question")
    if active:
        C.answer_panel(_answer_for(active), p)
    C.spacer(26)

    # ── Dataset scale ────────────────────────────────────────────────────
    trends = D.metric_trends()
    ai_share = f'{snap.ai_share:.1f}<span style="font-size:0.55em">%</span>'
    as_of = snap.as_of.strftime("%b %d") if snap.as_of else "—"
    C.metrics_strip([
        ("Companies tracked", f"{snap.total:,}",
         # Ingestion, not formation — bulk imports land in single days, so this
         # is deliberately labelled as records added rather than growth.
         f"+{snap.added_30d:,} records in the 30 days to {as_of}"
         if snap.added_30d else "no additions recorded",
         C.sparkline(trends.get("total", []), p)),
        ("Not in Crunchbase or PitchBook", f"{snap.hidden:,}",
         f"{snap.hidden_share:.1f}% of the dataset",
         C.sparkline(trends.get("hidden", []), p)),
        ("AI share", ai_share, "of all tracked companies",
         C.sparkline(trends.get("ai_share", []), p)),
        ("Countries", f"{snap.countries:,}", "with at least one headquarters",
         C.sparkline(trends.get("countries", []), p)),
    ])
    C.spacer(44)

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
        C.briefing(B.build(week, snap, facts, cats, geo))
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
        if not week.top_countries.empty:
            C.section_head("This week by country", "COMPANIES", soft=True, top=36)
            wk_total = int(week.top_countries["n"].sum()) or 1
            C.rank_rows(
                week.top_countries.head(6).assign(
                    label=week.top_countries["country"],
                    value=week.top_countries["n"] / wk_total * 100,
                    sub=week.top_countries["n"].map(lambda n: f"{int(n):,}"),
                )[["label", "value", "sub"]],
                unit="%", show_bar=True,
            )
    C.spacer(46)

    # ── Formation analysis ───────────────────────────────────────────────
    f = D.formation()
    meta = ""
    if f.recent_range and f.cohort_total:
        meta = f"{f.cohort_total:,} FOUNDED {f.recent_range[0]}–{f.recent_range[1]}"
        if f.peak_year:
            meta += f" · PEAK {f.peak_year}"
    C.section_head("AI company formation", meta)

    # Chart and the two rankings that read off it, on one row — the analysis
    # sits together instead of being split across two scrolls.
    cohort = f"{f.recent_range[0]}–{f.recent_range[1]}" if f.recent_range else ""
    chart, categories, places = st.columns([1.62, 1, 1], gap="large")
    with chart:
        C.formation_chart(f, p)
    with categories:
        C.section_head("Fastest-growing categories", "SHARE Δ", soft=True)
        C.category_ranking(cats)
    with places:
        C.section_head("Top headquarters", f"NEW {cohort}".strip(), soft=True)
        C.headquarters(geo)
        regions = D.region_totals()
        if not regions.empty:
            C.section_head("Hidden companies by region", "SHARE", soft=True, top=36)
            total = int(regions["n"].sum()) or 1
            C.rank_rows(
                regions.head(5).assign(
                    label=regions["region"],
                    value=regions["n"] / total * 100,
                    sub=regions["n"].map(lambda n: f"{int(n):,}"),
                )[["label", "value", "sub"]],
                unit="%", show_bar=True,
            )
    C.spacer(46)

    # ── Latest additions ─────────────────────────────────────────────────
    C.section_head("Latest hidden discoveries",
                   "NOT IN CRUNCHBASE OR PITCHBOOK")
    C.latest_additions(D.recent_hidden(limit=8))

    C.footer(snap, f)
