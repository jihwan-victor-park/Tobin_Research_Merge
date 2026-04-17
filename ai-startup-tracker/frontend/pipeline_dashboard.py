"""
AI Startup Tracker - Pipeline Dashboard

Main page: scraped startup list (sorted by most recently funded).
Sidebar: scraper agents grouped by tier (Easy / Hard / Discovery).
Trends tab: what appeared this week + fastest-growing AI subdomains.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.db.connection import get_engine
from backend.orchestrator.orchestrator import Orchestrator
from backend.scrapers.registry import SCRAPER_REGISTRY

load_dotenv()

# ── Page config ───────────────────────────────────────────────────────

st.set_page_config(
    page_title="AI Startup Tracker",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    /* Import professional font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }

    /* Apply Inter only to text elements — never touch icon spans */
    p, span:not([data-testid*="Icon"]):not([class*="icon"]):not([class*="Icon"]),
    div, h1, h2, h3, h4, h5, h6, label, button, input, textarea, select,
    .stMarkdown, .stText, [data-testid="stMarkdownContainer"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }

    /* Preserve Material Icons / Streamlit icon fonts */
    [data-testid*="Icon"], [class*="material-icons"], [class*="Icon"],
    [data-testid="stIconMaterial"], .material-symbols-outlined,
    span[aria-hidden="true"][class*="st-emotion"] {
        font-family: "Material Symbols Rounded", "Material Icons", "Material Icons Outlined" !important;
    }

    code, pre, kbd {
        font-family: 'JetBrains Mono', 'SF Mono', Menlo, monospace;
    }

    /* Main background */
    .main { background-color: #0b0d12; }
    .block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1600px; }

    /* Title */
    h1 {
        color: #e5e7eb;
        font-weight: 700;
        letter-spacing: -0.025em;
        font-size: 1.85rem !important;
        margin-bottom: 0.2rem !important;
    }
    h2 {
        color: #d1d5db;
        font-weight: 600;
        font-size: 1.25rem !important;
        letter-spacing: -0.015em;
    }
    h3 {
        color: #9ca3af;
        font-weight: 600;
        font-size: 0.95rem !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .stCaption, p { color: #9ca3af; font-size: 0.85rem; }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: #151821;
        padding: 14px 18px;
        border-radius: 8px;
        border: 1px solid rgba(255,255,255,0.05);
    }
    [data-testid="stMetricValue"] {
        font-size: 1.5rem;
        font-weight: 700;
        color: #f3f4f6;
        font-family: 'Inter', sans-serif;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #6b7280;
        font-weight: 500;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: #0f1116;
        border-right: 1px solid rgba(255,255,255,0.05);
        width: 340px !important;
    }
    section[data-testid="stSidebar"] > div { padding-top: 0.5rem; }
    section[data-testid="stSidebar"] h2 {
        font-size: 0.95rem !important;
        color: #e5e7eb;
        margin-bottom: 0.2rem;
    }
    section[data-testid="stSidebar"] .tier-label {
        color: #9ca3af;
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        margin: 18px 0 6px 0;
        padding-bottom: 4px;
        border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    section[data-testid="stSidebar"] .tier-sub {
        color: #6b7280;
        font-size: 0.72rem;
        margin-bottom: 8px;
    }
    section[data-testid="stSidebar"] .stButton > button {
        width: 100%;
        border-radius: 6px;
        font-size: 0.82rem;
        font-weight: 500;
        height: 34px;
        background: #1a1e28;
        border: 1px solid rgba(255,255,255,0.08);
        color: #e5e7eb;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: #242938;
        border-color: rgba(96,165,250,0.4);
    }
    section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: #2563eb;
        border-color: #2563eb;
        color: #ffffff;
    }
    section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
        background: #1d4ed8;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
        border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px 6px 0 0;
        padding: 10px 18px;
        font-size: 0.88rem;
        font-weight: 500;
        color: #9ca3af;
        background: transparent;
    }
    .stTabs [aria-selected="true"] {
        color: #e5e7eb !important;
        background: #151821 !important;
    }

    /* Filter card */
    .filter-card {
        background: #12151d;
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 16px;
    }
    .filter-label {
        color: #6b7280;
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 6px;
    }

    /* Inputs */
    .stTextInput input, .stSelectbox > div > div, .stMultiSelect > div > div {
        background: #1a1e28 !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        color: #e5e7eb !important;
        font-size: 0.85rem !important;
    }
    .stCheckbox label {
        color: #d1d5db !important;
        font-size: 0.82rem !important;
    }

    /* DataFrame */
    [data-testid="stDataFrame"] {
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid rgba(255,255,255,0.06);
    }

    /* Subtle "show more" link-style button */
    .show-more-wrap .stButton > button {
        background: transparent !important;
        border: none !important;
        color: #4b5563 !important;
        font-size: 0.72rem !important;
        font-weight: 400 !important;
        height: 26px !important;
        padding: 0 !important;
        text-align: center !important;
        letter-spacing: 0.02em;
        box-shadow: none !important;
    }
    .show-more-wrap .stButton > button:hover {
        background: transparent !important;
        color: #9ca3af !important;
        border: none !important;
    }
    .show-more-wrap .stButton > button:focus {
        box-shadow: none !important;
        outline: none !important;
    }
    .show-more-wrap { margin: 2px 0 8px 0; }

    /* Expander inside sidebar compact */
    section[data-testid="stSidebar"] [data-testid="stExpander"] {
        border: 1px solid rgba(255,255,255,0.05) !important;
        border-radius: 5px;
        background: #131620;
        margin-bottom: 4px;
    }
    section[data-testid="stSidebar"] [data-testid="stExpander"] summary {
        font-size: 0.78rem;
        padding: 6px 10px !important;
    }

    /* Hide streamlit branding but keep sidebar controls */
    #MainMenu, footer { visibility: hidden; }
    header [data-testid="stToolbar"] { display: none; }

    /* Sidebar always expanded */
    section[data-testid="stSidebar"] {
        min-width: 340px !important;
        max-width: 340px !important;
    }

    /* Status dots */
    .dot-healthy { color: #10b981; }
    .dot-pending { color: #6b7280; }
    .dot-degraded { color: #f59e0b; }
    .dot-broken { color: #ef4444; }
    .dot-excluded { color: #6366f1; }

    hr { border-color: rgba(255,255,255,0.06); margin: 12px 0; }
</style>
""", unsafe_allow_html=True)


# ── Data loaders ──────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_startups() -> pd.DataFrame:
    """Load companies with latest funding + top GitHub repo, sorted by most recent funding."""
    engine = get_engine()
    query = """
        SELECT
            c.id,
            c.name,
            c.domain,
            c.description,
            c.country,
            c.city,
            c.stage,
            c.ai_score,
            c.ai_tags,
            c.first_seen_at,
            c.incubator_source,
            c.verification_status,
            latest_funding.deal_date AS last_funding_date,
            latest_funding.deal_size AS last_funding_amount,
            latest_funding.round_type AS last_funding_round,
            top_repo.repo_full_name AS github_repo,
            top_repo.repo_url AS github_url,
            top_repo.stars AS github_stars,
            top_repo.forks AS github_forks
        FROM companies c
        LEFT JOIN LATERAL (
            SELECT deal_date, deal_size, round_type
            FROM funding_signals f
            WHERE f.company_id = c.id
            ORDER BY deal_date DESC NULLS LAST
            LIMIT 1
        ) latest_funding ON TRUE
        LEFT JOIN LATERAL (
            SELECT repo_full_name, repo_url, stars, forks
            FROM github_signals g
            WHERE g.company_id = c.id
            ORDER BY stars DESC NULLS LAST
            LIMIT 1
        ) top_repo ON TRUE
        ORDER BY latest_funding.deal_date DESC NULLS LAST, c.first_seen_at DESC NULLS LAST
    """
    with engine.connect() as conn:
        result = conn.execute(text(query))
        rows = result.mappings().all()
    df = pd.DataFrame(rows)
    if not df.empty:
        for col in ["first_seen_at", "last_funding_date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


@st.cache_data(ttl=60)
def load_site_health() -> pd.DataFrame:
    engine = get_engine()
    query = """
        SELECT domain, url, difficulty, scraper_name, status,
               consecutive_failures, last_success_at, last_failure_at,
               last_record_count, total_runs, total_successes
        FROM site_health
        ORDER BY domain
    """
    with engine.connect() as conn:
        result = conn.execute(text(query))
        rows = result.mappings().all()
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def load_recent_runs(hours: int = 168) -> pd.DataFrame:
    engine = get_engine()
    query = f"""
        SELECT domain, difficulty, scraper_name, status, records_found,
               records_new, duration_seconds, started_at, finished_at
        FROM scrape_runs
        WHERE started_at >= NOW() - INTERVAL '{hours} hours'
        ORDER BY started_at DESC
    """
    with engine.connect() as conn:
        result = conn.execute(text(query))
        rows = result.mappings().all()
    return pd.DataFrame(rows)


# ── Sidebar: Scraper agents ───────────────────────────────────────────

def status_label(status: str) -> str:
    """Return a small colored dot + status text (no emoji)."""
    cls = {
        "healthy": "dot-healthy",
        "pending": "dot-pending",
        "degraded": "dot-degraded",
        "broken": "dot-broken",
        "excluded": "dot-excluded",
    }.get(status or "pending", "dot-pending")
    return f'<span class="{cls}">●</span> <span style="color:#d1d5db;font-size:0.78rem;">{(status or "pending").upper()}</span>'


def render_sidebar():
    st.sidebar.markdown("## Scraper Agents")
    st.sidebar.markdown(
        '<div style="color:#6b7280;font-size:0.75rem;margin-bottom:4px;">'
        'Trigger scrapes across three tiers</div>',
        unsafe_allow_html=True,
    )

    health_df = load_site_health()
    health_map = (
        {row["domain"]: row for _, row in health_df.iterrows()}
        if not health_df.empty else {}
    )

    # ── Tier 1: Easy ──────────────────────────────────────────────────
    st.sidebar.markdown(
        '<div class="tier-label">Tier 1 &nbsp;&middot;&nbsp; Hard-coded</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(
        f'<div class="tier-sub">{len(SCRAPER_REGISTRY)} deterministic scrapers</div>',
        unsafe_allow_html=True,
    )

    def _render_easy_scraper(domain: str, entry):
        health = health_map.get(domain, {})
        status = health.get("status", "pending")
        last_count = health.get("last_record_count")

        with st.sidebar.expander(domain, expanded=False):
            st.markdown(status_label(status), unsafe_allow_html=True)
            st.caption(f"Pattern: {entry.pattern}")
            if last_count is not None:
                st.caption(f"Last run: {last_count} records")
            last_success = health.get("last_success_at")
            if last_success is not None and pd.notna(last_success):
                st.caption(
                    f"Last success: {pd.to_datetime(last_success).strftime('%Y-%m-%d %H:%M')}"
                )

            if st.button("Run", key=f"easy_{domain}", use_container_width=True):
                url = health.get("url") or entry.cls().source_url
                with st.spinner(f"Running {domain}..."):
                    orch = Orchestrator()
                    result = orch.run(url, force=True)
                if result.success:
                    st.success(f"{result.records_found} records ({result.records_new} new)")
                else:
                    st.error(f"{result.status}: {result.error_message or ''}")
                st.cache_data.clear()

    # Show first 4 by default; hide rest behind a subtle expand link
    sorted_entries = sorted(SCRAPER_REGISTRY.items())
    visible_count = 4
    for domain, entry in sorted_entries[:visible_count]:
        _render_easy_scraper(domain, entry)

    if len(sorted_entries) > visible_count:
        if "show_all_easy" not in st.session_state:
            st.session_state.show_all_easy = False

        arrow = "⌄" if not st.session_state.show_all_easy else "⌃"
        label = (
            f"Show {len(sorted_entries) - visible_count} more"
            if not st.session_state.show_all_easy
            else "Show less"
        )

        # Faint text-only button styled as a chevron link
        with st.sidebar.container():
            st.markdown('<div class="show-more-wrap">', unsafe_allow_html=True)
            if st.button(
                f"{label}  {arrow}",
                key="show_all_easy_btn",
                use_container_width=True,
            ):
                st.session_state.show_all_easy = not st.session_state.show_all_easy
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.show_all_easy:
            for domain, entry in sorted_entries[visible_count:]:
                _render_easy_scraper(domain, entry)

    # ── Tier 2: Hard ──────────────────────────────────────────────────
    st.sidebar.markdown(
        '<div class="tier-label">Tier 2 &nbsp;&middot;&nbsp; Agentic</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(
        '<div class="tier-sub">Claude + Tavily for unknown sites</div>',
        unsafe_allow_html=True,
    )

    with st.sidebar.form("hard_scrape_form", clear_on_submit=False):
        hard_url = st.text_input(
            "URL",
            placeholder="https://example.com/portfolio",
            key="hard_url_input",
            label_visibility="collapsed",
        )
        force_hard = st.checkbox("Force (ignore cooldown)", value=True, key="force_hard")
        submitted = st.form_submit_button(
            "Run Agentic Scraper", use_container_width=True, type="primary"
        )

    if submitted and hard_url:
        with st.spinner("Agentic scraper running..."):
            orch = Orchestrator()
            result = orch.run(hard_url, force=force_hard)
        if result.success:
            st.sidebar.success(f"{result.records_found} records ({result.records_new} new)")
        else:
            st.sidebar.error(f"{result.status}: {result.error_message or ''}")
        st.cache_data.clear()

    # ── Tier 3: Discovery & Self-Healing ──────────────────────────────
    st.sidebar.markdown(
        '<div class="tier-label">Tier 3 &nbsp;&middot;&nbsp; Discovery &amp; Self-Healing</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(
        '<div class="tier-sub">Automated loops</div>',
        unsafe_allow_html=True,
    )

    if st.sidebar.button("Discover new sites", use_container_width=True, key="discover_btn"):
        from backend.discovery.feed_loader import register_new_sites
        with st.spinner("Loading feeds..."):
            register_new_sites()
        st.sidebar.success("New sites registered")
        st.cache_data.clear()

    if st.sidebar.button("Retry zero-result sites", use_container_width=True, key="retry_btn"):
        with st.spinner("Retrying via hard tier..."):
            orch = Orchestrator()
            results = orch.run_retries(hours=48)
        st.sidebar.success(f"Retried {len(results)} sites")
        st.cache_data.clear()

    if st.sidebar.button("Revisit excluded sites", use_container_width=True, key="revisit_btn"):
        from backend.orchestrator.health import HealthMonitor
        with st.spinner("Reactivating..."):
            HealthMonitor().reactivate_revisit_sites()
        st.sidebar.success("Excluded sites reactivated")
        st.cache_data.clear()

    if st.sidebar.button(
        "Run all due sites", use_container_width=True, key="batch_btn", type="primary"
    ):
        with st.spinner("Batch scraping..."):
            orch = Orchestrator()
            results = orch.run_all_due()
        success = sum(1 for r in results if r.success)
        st.sidebar.success(f"{success}/{len(results)} succeeded")
        st.cache_data.clear()


# ── Main: Startup list ────────────────────────────────────────────────

def render_startup_list(df: pd.DataFrame):
    if df.empty:
        st.info("No companies in database yet. Run a scraper from the sidebar to get started.")
        return

    # Top metrics
    total = len(df)
    ai_count = int((df["ai_score"].fillna(0) >= 0.5).sum())
    funded = int(df["last_funding_date"].notna().sum())
    github_count = int(df["github_repo"].notna().sum()) if "github_repo" in df.columns else 0
    countries = df["country"].dropna().nunique()

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Companies", f"{total:,}")
    m2.metric("AI Startups", f"{ai_count:,}")
    m3.metric("With Funding", f"{funded:,}")
    m4.metric("With GitHub", f"{github_count:,}")
    m5.metric("Countries", f"{countries:,}")

    # ── Congregated filter panel ─────────────────────────────────────
    st.markdown("<br/>", unsafe_allow_html=True)
    with st.container():
        st.markdown('<div class="filter-card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="filter-label">Filters</div>',
            unsafe_allow_html=True,
        )

        # Row 1: search takes full width
        search = st.text_input(
            "Search",
            placeholder="Search by company name or description...",
            label_visibility="collapsed",
        )

        # Row 2: checkboxes
        c1, c2, c3, c4, c5 = st.columns(5)
        ai_only = c1.checkbox("AI startups only", value=True)
        funded_only = c2.checkbox("Funded only", value=False)
        has_github = c3.checkbox("Has GitHub", value=False)
        has_location = c4.checkbox("Has location", value=False)
        recent_only = c5.checkbox("Last 30 days", value=False)

        # Row 3: multi-selects
        f1, f2, f3 = st.columns(3)

        stages = sorted([s for s in df["stage"].dropna().unique().tolist()])
        selected_stages = f1.multiselect("Funding stage", options=stages, placeholder="All stages")

        countries_list = sorted([c for c in df["country"].dropna().unique().tolist()])
        selected_countries = f2.multiselect("Country", options=countries_list, placeholder="All countries")

        incubators = sorted([i for i in df["incubator_source"].dropna().astype(str).unique().tolist()])
        selected_incs = f3.multiselect("Incubator", options=incubators, placeholder="All incubators")

        st.markdown('</div>', unsafe_allow_html=True)

    # Apply filters
    filtered = df.copy()
    if ai_only:
        filtered = filtered[filtered["ai_score"].fillna(0) >= 0.5]
    if funded_only:
        filtered = filtered[filtered["last_funding_date"].notna()]
    if has_github and "github_repo" in filtered.columns:
        filtered = filtered[filtered["github_repo"].notna()]
    if has_location:
        filtered = filtered[filtered["country"].notna()]
    if recent_only:
        cutoff = datetime.utcnow() - timedelta(days=30)
        filtered = filtered[filtered["first_seen_at"] >= cutoff]
    if selected_stages:
        filtered = filtered[filtered["stage"].isin(selected_stages)]
    if selected_countries:
        filtered = filtered[filtered["country"].isin(selected_countries)]
    if selected_incs:
        filtered = filtered[filtered["incubator_source"].astype(str).isin(selected_incs)]
    if search:
        s = search.lower()
        mask = (
            filtered["name"].str.lower().str.contains(s, na=False)
            | filtered["description"].fillna("").str.lower().str.contains(s, na=False)
        )
        filtered = filtered[mask]

    # Results header
    rc1, rc2 = st.columns([5, 1])
    with rc1:
        st.markdown(
            f'<div style="color:#9ca3af;font-size:0.85rem;margin-top:6px;">'
            f'Showing <span style="color:#e5e7eb;font-weight:600;">{len(filtered):,}</span> '
            f'of {total:,} companies &nbsp;&middot;&nbsp; sorted by most recent funding</div>',
            unsafe_allow_html=True,
        )
    with rc2:
        st.download_button(
            "Download CSV",
            data=filtered.to_csv(index=False).encode("utf-8"),
            file_name=f"startups_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # Display columns — GitHub moved near front so it's visible without scrolling
    display_cols = [
        "name",
        "github_repo", "github_stars", "github_url",
        "ai_tags", "country", "stage",
        "last_funding_date", "last_funding_amount", "last_funding_round",
        "city", "incubator_source", "first_seen_at", "domain", "description",
    ]
    display_cols = [c for c in display_cols if c in filtered.columns]

    display = filtered[display_cols].copy()
    if "ai_tags" in display.columns:
        display["ai_tags"] = display["ai_tags"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else (x or "")
        )
    if "last_funding_amount" in display.columns:
        display["last_funding_amount"] = display["last_funding_amount"].apply(
            lambda v: f"${v/1e6:.1f}M" if pd.notna(v) and v > 0 else ""
        )
    if "last_funding_date" in display.columns:
        display["last_funding_date"] = display["last_funding_date"].dt.strftime("%Y-%m-%d")
    if "first_seen_at" in display.columns:
        display["first_seen_at"] = display["first_seen_at"].dt.strftime("%Y-%m-%d")
    if "incubator_source" in display.columns:
        display["incubator_source"] = display["incubator_source"].astype(str).replace("None", "")
    if "github_stars" in display.columns:
        display["github_stars"] = display["github_stars"].apply(
            lambda v: int(v) if pd.notna(v) else None
        )

    display = display.rename(columns={
        "name": "Name",
        "ai_tags": "AI Category",
        "country": "Country",
        "city": "City",
        "stage": "Stage",
        "last_funding_date": "Last Funded",
        "last_funding_amount": "Amount",
        "last_funding_round": "Round",
        "github_repo": "GitHub",
        "github_stars": "Stars",
        "github_url": "Repo Link",
        "incubator_source": "Incubator",
        "first_seen_at": "First Seen",
        "domain": "Website",
        "description": "Description",
    })

    col_config = {}
    if "Website" in display.columns:
        col_config["Website"] = st.column_config.LinkColumn(
            "Website", display_text="visit"
        )
    if "Repo Link" in display.columns:
        col_config["Repo Link"] = st.column_config.LinkColumn(
            "Repo", display_text="view"
        )
    if "Stars" in display.columns:
        col_config["Stars"] = st.column_config.NumberColumn(
            "Stars", format="%d", help="GitHub stars on top repo",
        )
    if "Description" in display.columns:
        col_config["Description"] = st.column_config.TextColumn(
            "Description", width="large"
        )

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=620,
        column_config=col_config,
    )


# ── Trends tab ────────────────────────────────────────────────────────

def render_trends(df: pd.DataFrame):
    if df.empty:
        st.info("No data yet. Scrape some sites from the sidebar first.")
        return

    # ── Section 1: What appeared this week ───────────────────────────
    st.markdown("### New This Week")
    cutoff = datetime.utcnow() - timedelta(days=7)
    this_week = df[df["first_seen_at"] >= cutoff].copy()

    c1, c2, c3 = st.columns(3)
    c1.metric("New companies (7d)", f"{len(this_week):,}")
    ai_new = int((this_week["ai_score"].fillna(0) >= 0.5).sum()) if len(this_week) else 0
    c2.metric("AI startups (7d)", f"{ai_new:,}")
    funded_new = int(this_week["last_funding_date"].notna().sum()) if len(this_week) else 0
    c3.metric("With funding (7d)", f"{funded_new:,}")

    if this_week.empty:
        st.info("No new companies in the last 7 days.")
    else:
        daily = this_week.groupby(this_week["first_seen_at"].dt.date).size().reset_index(name="count")
        daily.columns = ["date", "count"]
        fig = px.bar(
            daily, x="date", y="count",
            labels={"count": "Companies", "date": "Date"},
        )
        fig.update_traces(marker_color="#3b82f6")
        fig.update_layout(
            height=280,
            margin=dict(l=0, r=0, t=20, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter", color="#9ca3af", size=12),
            xaxis=dict(gridcolor="rgba(255,255,255,0.04)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.04)"),
        )
        st.plotly_chart(fig, use_container_width=True)

        preview = this_week.head(50)[
            ["name", "country", "stage", "last_funding_date", "first_seen_at", "domain"]
        ].copy()
        preview["first_seen_at"] = preview["first_seen_at"].dt.strftime("%Y-%m-%d")
        preview["last_funding_date"] = preview["last_funding_date"].dt.strftime("%Y-%m-%d")
        preview = preview.rename(columns={
            "name": "Name", "country": "Country", "stage": "Stage",
            "last_funding_date": "Last Funded", "first_seen_at": "First Seen",
            "domain": "Website",
        })
        st.dataframe(preview, use_container_width=True, hide_index=True, height=300)

    st.markdown("<br/>", unsafe_allow_html=True)

    # ── Section 2: Fastest-growing AI subdomains ─────────────────────
    st.markdown("### Fastest-Growing AI Subdomains")

    ai_df = df[df["ai_score"].fillna(0) >= 0.5].copy()
    if ai_df.empty or "ai_tags" not in ai_df.columns:
        st.info("Not enough AI-tagged companies yet to compute subdomain trends.")
        return

    ai_df = ai_df[ai_df["ai_tags"].notna()]
    ai_df = ai_df[ai_df["ai_tags"].apply(lambda x: isinstance(x, list) and len(x) > 0)]

    if ai_df.empty:
        st.info("No AI tags available. Run the classifier on recent companies.")
        return

    exploded = ai_df.explode("ai_tags").rename(columns={"ai_tags": "subdomain"})
    exploded = exploded[exploded["subdomain"].notna() & (exploded["subdomain"] != "")]

    totals = exploded.groupby("subdomain").size().reset_index(name="total")

    cutoff_30 = datetime.utcnow() - timedelta(days=30)
    recent_30 = exploded[exploded["first_seen_at"] >= cutoff_30]
    recent_counts = recent_30.groupby("subdomain").size().reset_index(name="new_30d")

    cutoff_60 = datetime.utcnow() - timedelta(days=60)
    prev_30 = exploded[
        (exploded["first_seen_at"] >= cutoff_60)
        & (exploded["first_seen_at"] < cutoff_30)
    ]
    prev_counts = prev_30.groupby("subdomain").size().reset_index(name="prev_30d")

    merged = totals.merge(recent_counts, on="subdomain", how="left").merge(
        prev_counts, on="subdomain", how="left"
    )
    merged["new_30d"] = merged["new_30d"].fillna(0).astype(int)
    merged["prev_30d"] = merged["prev_30d"].fillna(0).astype(int)
    merged["growth_pct"] = merged.apply(
        lambda r: ((r["new_30d"] - r["prev_30d"]) / r["prev_30d"] * 100) if r["prev_30d"] > 0 else (100.0 if r["new_30d"] > 0 else 0.0),
        axis=1,
    )
    merged = merged.sort_values("new_30d", ascending=False).head(15)

    tc1, tc2 = st.columns(2)
    with tc1:
        fig1 = px.bar(
            merged, x="new_30d", y="subdomain",
            orientation="h",
            title="New companies (last 30 days)",
            labels={"new_30d": "Companies", "subdomain": ""},
        )
        fig1.update_traces(marker_color="#3b82f6")
        fig1.update_layout(
            height=440,
            margin=dict(l=0, r=0, t=40, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(autorange="reversed", gridcolor="rgba(255,255,255,0.04)"),
            xaxis=dict(gridcolor="rgba(255,255,255,0.04)"),
            font=dict(family="Inter", color="#9ca3af", size=12),
            title_font=dict(color="#d1d5db", size=14),
            showlegend=False,
        )
        st.plotly_chart(fig1, use_container_width=True)

    with tc2:
        growth_sorted = merged.sort_values("growth_pct", ascending=False)
        fig2 = px.bar(
            growth_sorted, x="growth_pct", y="subdomain",
            orientation="h",
            title="Growth rate (vs previous 30d)",
            labels={"growth_pct": "% Growth", "subdomain": ""},
        )
        fig2.update_traces(marker_color="#10b981")
        fig2.update_layout(
            height=440,
            margin=dict(l=0, r=0, t=40, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(autorange="reversed", gridcolor="rgba(255,255,255,0.04)"),
            xaxis=dict(gridcolor="rgba(255,255,255,0.04)"),
            font=dict(family="Inter", color="#9ca3af", size=12),
            title_font=dict(color="#d1d5db", size=14),
            showlegend=False,
        )
        st.plotly_chart(fig2, use_container_width=True)

    merged_display = merged[["subdomain", "total", "new_30d", "prev_30d", "growth_pct"]].copy()
    merged_display["growth_pct"] = merged_display["growth_pct"].apply(lambda v: f"{v:+.1f}%")
    merged_display = merged_display.rename(columns={
        "subdomain": "Subdomain",
        "total": "Total",
        "new_30d": "New (30d)",
        "prev_30d": "Prev 30d",
        "growth_pct": "Growth",
    })
    st.dataframe(merged_display, use_container_width=True, hide_index=True)


# ── Pipeline Health tab ───────────────────────────────────────────────

def render_health(health_df: pd.DataFrame, runs_df: pd.DataFrame):
    if health_df.empty:
        st.info("No sites registered. Click 'Discover new sites' in the sidebar.")
        return

    total = len(health_df)
    healthy = int((health_df["status"] == "healthy").sum())
    degraded = int((health_df["status"] == "degraded").sum())
    broken = int((health_df["status"] == "broken").sum())
    excluded = int((health_df["status"] == "excluded").sum())
    pending = int((health_df["status"] == "pending").sum())

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Healthy", healthy)
    m2.metric("Degraded", degraded)
    m3.metric("Broken", broken)
    m4.metric("Excluded", excluded)
    m5.metric("Pending", pending)

    st.markdown("<br/>", unsafe_allow_html=True)

    tier = health_df["difficulty"].value_counts().reset_index()
    tier.columns = ["Tier", "Count"]
    c1, c2 = st.columns([1, 2])
    with c1:
        fig = px.pie(
            tier, values="Count", names="Tier",
            title="Scrapers by Tier", hole=0.55,
            color_discrete_sequence=["#3b82f6", "#10b981", "#f59e0b"],
        )
        fig.update_layout(
            height=300,
            margin=dict(l=0, r=0, t=40, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter", color="#9ca3af"),
            title_font=dict(color="#d1d5db", size=14),
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        health_display = health_df[[
            "domain", "difficulty", "status", "consecutive_failures",
            "last_record_count", "total_runs", "total_successes", "last_success_at"
        ]].copy()
        if "last_success_at" in health_display.columns:
            health_display["last_success_at"] = pd.to_datetime(
                health_display["last_success_at"], errors="coerce"
            ).dt.strftime("%Y-%m-%d %H:%M")
        st.dataframe(health_display, use_container_width=True, hide_index=True, height=320)

    st.markdown("### Recent Scrape Runs (7 days)")
    if runs_df.empty:
        st.caption("No runs in the last 7 days.")
    else:
        runs_display = runs_df.copy()
        if "started_at" in runs_display.columns:
            runs_display["started_at"] = pd.to_datetime(
                runs_display["started_at"], errors="coerce"
            ).dt.strftime("%Y-%m-%d %H:%M")
        if "finished_at" in runs_display.columns:
            runs_display = runs_display.drop(columns=["finished_at"])
        if "duration_seconds" in runs_display.columns:
            runs_display["duration_seconds"] = runs_display["duration_seconds"].apply(
                lambda v: f"{v:.1f}s" if pd.notna(v) else ""
            )
        st.dataframe(runs_display, use_container_width=True, hide_index=True, height=360)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    render_sidebar()

    st.markdown("# AI Startup Tracker")
    st.markdown(
        '<div style="color:#6b7280;font-size:0.92rem;margin-top:-8px;margin-bottom:14px;">'
        'Automatic discovery and trend intelligence for the AI startup scene</div>',
        unsafe_allow_html=True,
    )

    df = load_startups()
    health_df = load_site_health()
    runs_df = load_recent_runs()

    tab_overview, tab_trends, tab_health = st.tabs([
        "Startup Overview",
        "Trends",
        "Pipeline Health",
    ])

    with tab_overview:
        render_startup_list(df)

    with tab_trends:
        render_trends(df)

    with tab_health:
        render_health(health_df, runs_df)


if __name__ == "__main__":
    main()
