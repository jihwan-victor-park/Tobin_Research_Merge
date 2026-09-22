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

from .. import vocabulary as V
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
    # The two figures the research programme reports, on one definition so they
    # can be read together, plus the geographic reach. Non-AI companies are not
    # counted here at all -- the strip used to open with every tracked record.
    trends = D.metric_trends()
    h = D.headline_counts()
    total, hidden = h.get("ai_total", 0), h.get("ai_hidden", 0)
    C.metrics_strip([
        ("AI companies tracked", f"{total:,}",
         "artificial intelligence and data",
         C.sparkline(trends.get("total", []), p)),
        ("In no commercial database", f"{hidden:,}",
         f"{hidden / max(total, 1) * 100:.0f}% of the companies tracked",
         C.sparkline(trends.get("hidden", []), p)),
        ("Countries", f"{h.get('countries', 0):,}",
         "with an AI headquarters",
         C.sparkline(trends.get("countries", []), p)),
    ])
    C.spacer(44)

    # ── The last 30 days of intake ───────────────────────────────────────
    week = D.recent_activity()
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
        # The briefing read as a news column -- kicker, headline, paragraph --
        # and the meeting asked for this slot to carry our own quarterly
        # research signal instead. Same layout, our scrapers as the source.
        C.quarterly_update(D.quarterly_discovery())
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
                # No bar: narrow column, the label needs the room.
                unit="%", total=100.0,
                note=(f"Share of the {total:,} companies outside "
                      f"{V.THE_DATASETS} that resolve to a region, across "
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
    C.section_head("Latest discoveries", V.KICKER)
    C.latest_additions(D.recent_hidden(limit=8))

    C.footer(snap, f)
