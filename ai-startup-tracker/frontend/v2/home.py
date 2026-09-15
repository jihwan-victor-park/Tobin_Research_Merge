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
            C.hero_map(
                D.country_totals(), p,
                caption=(f"Every company in the dataset, shaded by how many each "
                         f"country holds — {snap.total:,} across "
                         f"{snap.countries:,} countries."),
            )

    active = question or st.session_state.get("v2_last_question")
    if active:
        C.answer_panel(_answer_for(active), p)
    C.spacer(26)

    # ── Dataset scale ────────────────────────────────────────────────────
    # Four figures that nest inside one another, so a reader can add them up:
    # 191,488 AI and data companies, of which 124,093 are core AI, of which
    # 13,579 appear in no commercial database. Each caption names the figure
    # directly above it as its base, rather than leaving the base implied.
    trends = D.metric_trends()
    h = D.headline_counts()
    broad, narrow = h.get("ai_broad", 0), h.get("ai_narrow", 0)
    hidden, tracked = h.get("ai_hidden", 0), h.get("all_companies", 0)
    C.metrics_strip([
        ("AI companies", f"{broad:,}",
         f"{broad / max(tracked, 1) * 100:.0f}% of {tracked:,} tracked",
         C.sparkline(trends.get("total", []), p)),
        ("Core AI only", f"{narrow:,}",
         f"{narrow / max(broad, 1) * 100:.0f}% of the above",
         C.sparkline(trends.get("ai_share", []), p)),
        ("In no commercial database", f"{hidden:,}",
         f"{hidden / max(narrow, 1) * 100:.0f}% of core AI",
         C.sparkline(trends.get("hidden", []), p)),
        ("Countries", f"{h.get('countries', 0):,}", "with an AI headquarters",
         C.sparkline(trends.get("countries", []), p)),
    ])
    C.spacer(44)

    # ── The last 30 days of intake ───────────────────────────────────────
    week = D.recent_activity()
    facts = D.channel_facts()
    cats = D.category_momentum(limit=6)
    geo = D.geographic_momentum(limit=6)

    if week.start and week.end:
        window = (f"{week.start.strftime('%b %d')} — {week.end.strftime('%b %d, %Y')}"
                  .upper())
    else:
        window = "NO INTAKE RECORDED"
    C.section_head("AI startup activity · last 30 days", window)
    # The window follows the newest record, not the calendar. When collection
    # pauses, that gap is the most important thing on the section.
    if week.is_stale and week.end:
        C.freshness_notice(week)

    lead, signals = st.columns([1.62, 1], gap="large")
    with lead:
        C.briefing(B.build(week, snap, facts, cats, geo))
    with signals:
        C.section_head("Market signals", "SHARE Δ", soft=True)
        C.market_signals(cats)
        # "Where these came from" -- the split by grant portal, portfolio page,
        # media feed and code host -- was the collection method drawn as a
        # chart. The geography of the intake is the part a reader can use.
        if not week.top_countries.empty:
            C.section_head("By country", "COMPANIES", soft=True, top=36)
            wk_total = int(week.top_countries["n"].sum()) or 1
            n_countries = len(week.top_countries)
            C.rank_rows(
                week.top_countries.head(6).assign(
                    label=week.top_countries["country"],
                    value=week.top_countries["n"] / wk_total * 100,
                    sub=week.top_countries["n"].map(lambda n: f"{int(n):,}"),
                )[["label", "value", "sub"]],
                unit="%", show_bar=True, total=100.0,
                note=(f"Share of the {wk_total:,} companies in this window that "
                      f"carry a country, across {n_countries:,}."),
            )
    C.spacer(46)

    # ── Formation analysis ───────────────────────────────────────────────
    f = D.formation()
    meta = ""
    if f.recent_range and f.cohort_total:
        # No "peak year" here. On counts it would read 2018, which is only
        # where our coverage peaks; on share it would read whatever the last
        # complete year happens to be, while the series is still climbing past
        # it. Either way the label asserts a turning point we cannot support.
        meta = f"{f.cohort_total:,} AI COMPANIES FOUNDED {f.recent_range[0]}–{f.recent_range[1]}"
    C.section_head("AI share of company formation", meta)

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
                unit="%", show_bar=True, total=100.0,
                note=(f"Share of the {total:,} companies outside Crunchbase and "
                      f"PitchBook that resolve to a region, across "
                      f"{len(regions):,}."),
            )
    C.spacer(46)

    # ── What these companies do ──────────────────────────────────────────
    # The Landscape page's headline read, brought forward: a reader should meet
    # the shape of the population here rather than having to go looking for it.
    domains, mapped_total = D.domain_totals(limit=6)
    if not domains.empty:
        C.section_head("What these companies do", f"{mapped_total:,} CLASSIFIED")
        left, right = st.columns([1.62, 1], gap="large")
        with left:
            C.domain_ranking(domains, mapped_total)
        with right:
            C.domain_note(domains, mapped_total)
        C.spacer(46)

    # ── Latest additions ─────────────────────────────────────────────────
    C.section_head("Latest discoveries", "NOT IN CRUNCHBASE OR PITCHBOOK")
    C.latest_additions(D.recent_hidden(limit=8))

    C.footer(snap, f)
