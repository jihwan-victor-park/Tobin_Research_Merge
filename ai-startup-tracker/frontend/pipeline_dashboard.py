
"""
AI Startup Tracker - Pipeline Dashboard

Full-page layout with top navigation bar, US geography map,
company table, trends, pipeline health, and scraper controls.
No sidebar — everything lives in the main content area.
"""
from __future__ import annotations

import base64
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.db.connection import get_engine
from backend.orchestrator.orchestrator import Orchestrator
from backend.scrapers.registry import SCRAPER_REGISTRY
from backend.utils.denylist import BIG_TECH_DENYLIST

load_dotenv()

# ── Design tokens ────────────────────────────────────────────────────
YALE_BLUE = "#00356b"
YALE_MID = "#1a4f8a"
YALE_LIGHT = "#2a6cb5"
ACCENT = "#286dc0"
BG = "#ffffff"
BG_OFF = "#f7f8fb"
BG_CARD = "#f9fafb"
BORDER = "#e3e7ee"
BORDER_LIGHT = "#eef1f6"
TXT = "#1a1f2e"
TXT2 = "#4a5568"
TXT3 = "#8492a6"
GREEN = "#0d9668"
AMBER = "#d97706"
RED = "#dc2626"

# ── US city coordinates (for geography map) ──────────────────────────
US_CITIES = {
    "new york": (40.71, -74.01), "nyc": (40.71, -74.01),
    "los angeles": (34.05, -118.24), "la": (34.05, -118.24),
    "chicago": (41.88, -87.63),
    "houston": (29.76, -95.37),
    "phoenix": (33.45, -112.07),
    "philadelphia": (39.95, -75.17),
    "san antonio": (29.42, -98.49),
    "san diego": (32.72, -117.16),
    "dallas": (32.78, -96.80),
    "san jose": (37.34, -121.89),
    "austin": (30.27, -97.74),
    "san francisco": (37.77, -122.42), "sf": (37.77, -122.42),
    "seattle": (47.61, -122.33),
    "denver": (39.74, -104.99),
    "washington": (38.91, -77.04), "washington dc": (38.91, -77.04),
    "dc": (38.91, -77.04), "washington d.c.": (38.91, -77.04),
    "nashville": (36.16, -86.78),
    "boston": (42.36, -71.06),
    "portland": (45.52, -122.68),
    "las vegas": (36.17, -115.14),
    "atlanta": (33.75, -84.39),
    "miami": (25.76, -80.19),
    "minneapolis": (44.98, -93.27),
    "tampa": (27.95, -82.46),
    "charlotte": (35.23, -80.84),
    "raleigh": (35.78, -78.64),
    "salt lake city": (40.76, -111.89),
    "pittsburgh": (40.44, -79.99),
    "st. louis": (38.63, -90.20), "saint louis": (38.63, -90.20),
    "detroit": (42.33, -83.05),
    "columbus": (39.96, -82.99),
    "indianapolis": (39.77, -86.16),
    "kansas city": (39.10, -94.58),
    "cincinnati": (39.10, -84.51),
    "cleveland": (41.50, -81.69),
    "oakland": (37.80, -122.27),
    "palo alto": (37.44, -122.14),
    "mountain view": (37.39, -122.08),
    "menlo park": (37.45, -122.18),
    "cupertino": (37.32, -122.03),
    "sunnyvale": (37.37, -122.04),
    "santa clara": (37.35, -121.96),
    "redwood city": (37.49, -122.24),
    "cambridge": (42.37, -71.11),
    "boulder": (40.01, -105.27),
    "ann arbor": (42.28, -83.74),
    "madison": (43.07, -89.40),
    "durham": (35.99, -78.90),
    "irvine": (33.68, -117.83),
    "santa monica": (34.02, -118.49),
    "bellevue": (47.61, -122.20),
    "pasadena": (34.15, -118.14),
    "new haven": (41.31, -72.93),
    "princeton": (40.36, -74.67),
    "ithaca": (42.44, -76.50),
    "provo": (40.23, -111.66),
    "richmond": (37.54, -77.44),
    "baltimore": (39.29, -76.61),
    "sacramento": (38.58, -121.49),
    "orlando": (28.54, -81.38),
    "omaha": (41.26, -95.93),
    "tucson": (32.22, -110.97),
    "albuquerque": (35.08, -106.65),
    "new orleans": (29.95, -90.07),
    "chattanooga": (35.05, -85.31),
    "scottsdale": (33.49, -111.93),
    "stamford": (41.05, -73.54),
    "arlington": (38.88, -77.10),
    "plano": (33.02, -96.70),
    "santa barbara": (34.42, -119.70),
    "honolulu": (21.31, -157.86),
    "des moines": (41.59, -93.62),
    "milwaukee": (43.04, -87.91),
    "jacksonville": (30.33, -81.66),
}

# ── Page config ──────────────────────────────────────────────────────

st.set_page_config(
    page_title="AI Startup Tracker",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ──────────────────────────────────────────────────────────────

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, .stApp {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        -webkit-font-smoothing: antialiased;
        background: {BG} !important;
    }}
    p, span:not([data-testid*="Icon"]):not([class*="icon"]):not([class*="Icon"]),
    div, h1, h2, h3, h4, h5, h6, label, button, input, textarea, select,
    .stMarkdown, .stText, [data-testid="stMarkdownContainer"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }}
    [data-testid*="Icon"], [class*="material-icons"], [class*="Icon"],
    .material-symbols-outlined, span[aria-hidden="true"][class*="st-emotion"] {{
        font-family: "Material Symbols Rounded","Material Icons" !important;
    }}

    /* Hide sidebar + streamlit chrome */
    section[data-testid="stSidebar"] {{ display: none !important; }}
    #MainMenu, footer {{ visibility: hidden; }}
    header {{ display: none !important; }}

    .main, [data-testid="stAppViewContainer"],
    [data-testid="stMain"] {{ background: {BG} !important; }}
    .block-container {{
        padding-top: 0 !important;
        padding-bottom: 2rem;
        max-width: 100% !important;
        padding-left: 0 !important;
        padding-right: 0 !important;
    }}

    /* ── Top nav bar (white, with logo + tabs) ── */
    .topnav {{
        background: {BG};
        border-bottom: 1px solid {BORDER};
        padding: 0 40px;
        display: flex;
        align-items: center;
        gap: 0;
        position: sticky;
        top: 0;
        z-index: 999;
    }}
    .topnav-brand {{
        display: flex;
        align-items: center;
        gap: 14px;
        padding: 10px 0;
        margin-right: 36px;
        flex-shrink: 0;
    }}
    .topnav-logo {{
        height: 34px;
    }}
    .topnav-sep {{
        width: 1px;
        height: 26px;
        background: {BORDER};
    }}
    .topnav-title {{
        font-size: 0.95rem;
        font-weight: 700;
        color: {YALE_BLUE};
        letter-spacing: -0.02em;
        white-space: nowrap;
    }}
    .topnav-right {{
        margin-left: auto;
        color: {TXT3};
        font-size: 0.72rem;
        white-space: nowrap;
    }}

    /* Hero banner */
    .hero {{
        background: linear-gradient(135deg, {YALE_BLUE} 0%, {YALE_MID} 60%, {YALE_LIGHT} 100%);
        padding: 26px 40px 22px 40px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }}
    .hero-title {{
        color: #fff;
        font-size: 1.5rem;
        font-weight: 700;
        letter-spacing: -0.025em;
    }}
    .hero-sub {{
        color: rgba(255,255,255,0.55);
        font-size: 0.82rem;
        margin-top: 2px;
    }}
    .hero-stats {{
        display: flex;
        gap: 32px;
    }}
    .hero-stat {{
        text-align: center;
    }}
    .hero-stat-val {{
        color: #fff;
        font-size: 1.35rem;
        font-weight: 700;
        line-height: 1.2;
    }}
    .hero-stat-label {{
        color: rgba(255,255,255,0.45);
        font-size: 0.58rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }}

    /* ── Nav tabs (flush under hero, act as page nav) ── */
    .stTabs {{ margin-top: 0; }}
    .stTabs [data-baseweb="tab-list"] {{
        gap: 0;
        background: {BG};
        border-bottom: 1px solid {BORDER};
        padding: 0 40px;
    }}
    .stTabs [data-baseweb="tab"] {{
        border-radius: 0;
        padding: 13px 24px;
        font-size: 0.88rem;
        font-weight: 500;
        color: {TXT3};
        background: transparent;
        border-bottom: 2px solid transparent;
        margin-bottom: -1px;
        white-space: nowrap;
    }}
    .stTabs [data-baseweb="tab"]:hover {{
        color: {TXT2};
    }}
    .stTabs [aria-selected="true"] {{
        color: {YALE_BLUE} !important;
        background: transparent !important;
        border-bottom: 2px solid {YALE_BLUE} !important;
        font-weight: 600;
    }}
    .stTabs [data-baseweb="tab-panel"] {{
        padding: 1.5rem 40px 0 40px;
    }}

    /* ── Section headers ── */
    h1 {{ color: {YALE_BLUE}; font-weight: 700; font-size: 1.4rem !important;
         letter-spacing: -0.02em; margin-bottom: 0.2rem !important; }}
    h2 {{ color: {TXT}; font-weight: 600; font-size: 1.1rem !important; }}
    h3 {{ color: {TXT2}; font-weight: 600; font-size: 0.8rem !important;
         text-transform: uppercase; letter-spacing: 0.06em; }}
    p {{ color: {TXT2}; font-size: 0.85rem; }}
    .stCaption {{ color: {TXT3}; }}

    .section-header {{
        color: {TXT};
        font-size: 1.05rem;
        font-weight: 600;
        letter-spacing: -0.01em;
        margin: 0 0 4px 0;
    }}
    .section-sub {{
        color: {TXT3};
        font-size: 0.82rem;
        margin: 0 0 16px 0;
    }}

    /* ── Metric cards ── */
    [data-testid="stMetric"] {{
        background: {BG};
        padding: 18px 20px;
        border-radius: 10px;
        border: 1px solid {BORDER};
    }}
    [data-testid="stMetricValue"] {{
        font-size: 1.5rem;
        font-weight: 700;
        color: {YALE_BLUE};
        font-family: 'Inter', sans-serif;
    }}
    [data-testid="stMetricLabel"] {{
        font-size: 0.66rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: {TXT3};
        font-weight: 500;
    }}

    /* ── Cards ── */
    .card {{
        background: {BG};
        border: 1px solid {BORDER};
        border-radius: 12px;
        padding: 20px 24px;
    }}
    .card-muted {{
        background: {BG_OFF};
        border: 1px solid {BORDER_LIGHT};
        border-radius: 12px;
        padding: 20px 24px;
    }}

    /* ── Filter bar ── */
    .filter-bar {{
        background: {BG_OFF};
        border: 1px solid {BORDER_LIGHT};
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 16px;
    }}
    .filter-bar-label {{
        color: {TXT3};
        font-size: 0.68rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        margin-bottom: 6px;
    }}

    /* ── Inputs ── */
    .stTextInput input, .stSelectbox > div > div, .stMultiSelect > div > div {{
        background: {BG} !important;
        border: 1px solid {BORDER} !important;
        color: {TXT} !important;
        font-size: 0.85rem !important;
        border-radius: 8px !important;
    }}
    .stTextInput input:focus {{
        border-color: {ACCENT} !important;
        box-shadow: 0 0 0 2px rgba(0,53,107,0.08) !important;
    }}
    .stCheckbox label {{ color: {TXT2} !important; font-size: 0.82rem !important; }}

    /* ── Data table ── */
    [data-testid="stDataFrame"] {{
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid {BORDER};
    }}

    /* ── Buttons ── */
    .stButton > button {{
        border-radius: 8px;
        font-size: 0.84rem;
        font-weight: 500;
        border: 1px solid {BORDER};
        background: {BG};
        color: {TXT};
        transition: all 0.15s;
    }}
    .stButton > button:hover {{
        border-color: {ACCENT};
        color: {YALE_BLUE};
        box-shadow: 0 1px 4px rgba(0,53,107,0.08);
    }}
    .stButton > button[kind="primary"] {{
        background: {YALE_BLUE} !important;
        border-color: {YALE_BLUE} !important;
        color: #fff !important;
    }}
    .stButton > button[kind="primary"]:hover {{
        background: {YALE_MID} !important;
        box-shadow: 0 2px 8px rgba(0,53,107,0.18);
    }}

    .stDownloadButton > button {{
        background: {BG} !important;
        border: 1px solid {BORDER} !important;
        color: {TXT2} !important;
        font-size: 0.8rem !important;
        border-radius: 8px !important;
    }}
    .stDownloadButton > button:hover {{
        border-color: {ACCENT} !important;
        color: {YALE_BLUE} !important;
    }}

    /* ── Scraper cards grid ── */
    .scraper-card {{
        background: {BG};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 14px 16px;
        height: 100%;
    }}
    .scraper-domain {{
        font-size: 0.82rem;
        font-weight: 600;
        color: {TXT};
        margin-bottom: 4px;
    }}
    .scraper-meta {{
        font-size: 0.72rem;
        color: {TXT3};
    }}

    /* Status dots */
    .dot-healthy {{ color: {GREEN}; }}
    .dot-pending {{ color: {TXT3}; }}
    .dot-degraded {{ color: {AMBER}; }}
    .dot-broken {{ color: {RED}; }}
    .dot-excluded {{ color: #7c3aed; }}

    /* Expander */
    [data-testid="stExpander"] {{
        border: 1px solid {BORDER} !important;
        border-radius: 10px;
        background: {BG};
    }}
    [data-testid="stExpander"] summary {{
        font-size: 0.85rem;
        padding: 10px 14px !important;
        color: {TXT};
    }}

    hr {{ border-color: {BORDER_LIGHT}; margin: 16px 0; }}
</style>
""", unsafe_allow_html=True)


# ── Header ───────────────────────────────────────────────────────────

# Encode logo as base64 for inline HTML
_logo_path = Path(__file__).resolve().parent.parent / "yalesom.png"
_logo_b64 = ""
if _logo_path.exists():
    _logo_b64 = base64.b64encode(_logo_path.read_bytes()).decode()

# Quick stats for hero
_engine = get_engine()
with _engine.connect() as _conn:
    _total = _conn.execute(text("SELECT COUNT(*) FROM companies")).scalar() or 0
    _sources = _conn.execute(text("SELECT COUNT(*) FROM site_health")).scalar() or 0
    _countries = _conn.execute(text(
        "SELECT COUNT(DISTINCT country) FROM companies WHERE country IS NOT NULL"
    )).scalar() or 0

_logo_img = (
    f'<img src="data:image/png;base64,{_logo_b64}" class="topnav-logo" alt="Yale SOM"/>'
    if _logo_b64 else '<span class="topnav-title">Yale SOM</span>'
)

# 1) White navigation bar with logo
st.markdown(
    f'<div class="topnav">'
    f'<div class="topnav-brand">'
    f'{_logo_img}'
    f'<div class="topnav-sep"></div>'
    f'<span class="topnav-title">AI Startup Tracker</span>'
    f'</div>'
    f'<div class="topnav-right">Tobin Center for Economic Policy &middot; Yale University</div>'
    f'</div>',
    unsafe_allow_html=True,
)

# 2) Blue hero strip with live stats
st.markdown(
    f'<div class="hero">'
    f'<div>'
    f'<div class="hero-title">Tracking the AI startup ecosystem</div>'
    f'<div class="hero-sub">Automated discovery and trend intelligence</div>'
    f'</div>'
    f'<div class="hero-stats">'
    f'<div class="hero-stat"><div class="hero-stat-val">{_total:,}</div>'
    f'<div class="hero-stat-label">Companies</div></div>'
    f'<div class="hero-stat"><div class="hero-stat-val">{_sources:,}</div>'
    f'<div class="hero-stat-label">Sources</div></div>'
    f'<div class="hero-stat"><div class="hero-stat-val">{_countries:,}</div>'
    f'<div class="hero-stat-label">Countries</div></div>'
    f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)


# ── Data loaders ─────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_startups() -> pd.DataFrame:
    engine = get_engine()
    query = """
        SELECT
            c.id, c.name, c.domain, c.description,
            c.country, c.city, c.stage, c.ai_score, c.ai_tags,
            c.first_seen_at, c.incubator_source, c.verification_status,
            lf.deal_date AS last_funding_date,
            lf.deal_size AS last_funding_amount,
            lf.round_type AS last_funding_round,
            tr.repo_full_name AS github_repo,
            tr.repo_url AS github_url,
            tr.stars AS github_stars,
            tr.forks AS github_forks,
            ls.llm_classification,
            ls.llm_confidence,
            ls.startup_likelihood
        FROM companies c
        LEFT JOIN LATERAL (
            SELECT deal_date, deal_size, round_type
            FROM funding_signals f WHERE f.company_id = c.id
            ORDER BY deal_date DESC NULLS LAST LIMIT 1
        ) lf ON TRUE
        LEFT JOIN LATERAL (
            SELECT repo_full_name, repo_url, stars, forks
            FROM github_signals g WHERE g.company_id = c.id
            ORDER BY stars DESC NULLS LAST LIMIT 1
        ) tr ON TRUE
        LEFT JOIN LATERAL (
            SELECT s.llm_classification, s.llm_confidence, s.startup_likelihood
            FROM github_repo_snapshots s
            WHERE s.repo_full_name = tr.repo_full_name
            ORDER BY s.collected_at DESC LIMIT 1
        ) ls ON TRUE
        ORDER BY lf.deal_date DESC NULLS LAST, c.first_seen_at DESC NULLS LAST
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query)).mappings().all()
    df = pd.DataFrame(rows)
    if not df.empty:
        for col in ["first_seen_at", "last_funding_date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        # Drop big-tech / incumbents that slipped in via Crunchbase / PitchBook /
        # HN Who is Hiring imports. Match on name OR domain root label.
        name_l = df["name"].fillna("").str.strip().str.lower()
        dom = df["domain"].fillna("").str.strip().str.lower().str.replace(r"^www\.", "", regex=True)
        dom_root = dom.str.split(".").str[0]
        is_big = name_l.isin(BIG_TECH_DENYLIST) | dom_root.isin(BIG_TECH_DENYLIST)
        df = df[~is_big].reset_index(drop=True)
    return df


@st.cache_data(ttl=60)
def load_site_health() -> pd.DataFrame:
    engine = get_engine()
    q = """SELECT domain, url, difficulty, scraper_name, status,
                  consecutive_failures, last_success_at, last_failure_at,
                  last_record_count, total_runs, total_successes
           FROM site_health ORDER BY domain"""
    with engine.connect() as conn:
        rows = conn.execute(text(q)).mappings().all()
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def load_recent_runs(hours: int = 168) -> pd.DataFrame:
    engine = get_engine()
    q = f"""SELECT domain, difficulty, scraper_name, status, records_found,
                   records_new, duration_seconds, started_at, finished_at
            FROM scrape_runs
            WHERE started_at >= NOW() - INTERVAL '{hours} hours'
            ORDER BY started_at DESC"""
    with engine.connect() as conn:
        rows = conn.execute(text(q)).mappings().all()
    return pd.DataFrame(rows)


# ── Plotly helpers ───────────────────────────────────────────────────

def _layout(**kw):
    base = dict(
        paper_bgcolor=BG, plot_bgcolor=BG_OFF,
        font=dict(family="Inter", color=TXT2, size=12),
        title_font=dict(color=TXT, size=14, family="Inter"),
        xaxis=dict(gridcolor=BORDER_LIGHT, zerolinecolor=BORDER),
        yaxis=dict(gridcolor=BORDER_LIGHT, zerolinecolor=BORDER),
        margin=dict(l=0, r=0, t=36, b=0),
    )
    base.update(kw)
    return base


def _geocode_us(df: pd.DataFrame) -> pd.DataFrame:
    """Geocode US companies by city name lookup."""
    us_mask = df["country"].fillna("").str.lower().str.contains(
        r"united states|usa|^us$", regex=True
    )
    us = df[us_mask & df["city"].notna()].copy()
    if us.empty:
        return pd.DataFrame()

    us["city_key"] = us["city"].str.lower().str.strip()
    us["lat"] = us["city_key"].map(lambda c: US_CITIES.get(c, (None,))[0])
    us["lon"] = us["city_key"].map(lambda c: US_CITIES.get(c, (None, None))[1])
    return us[us["lat"].notna()].copy()


# ── Page: Overview ───────────────────────────────────────────────────

def page_overview(df: pd.DataFrame):
    if df.empty:
        st.info("No companies in database. Go to the Scraper tab to get started.")
        return

    # Metrics
    total = len(df)
    ai_n = int((df["ai_score"].fillna(0) >= 0.5).sum())
    funded = int(df["last_funding_date"].notna().sum())
    countries = df["country"].dropna().nunique()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Companies", f"{total:,}")
    m2.metric("AI Startups", f"{ai_n:,}")
    m3.metric("With Funding", f"{funded:,}")
    m4.metric("Countries", f"{countries:,}")

    # ── US Geography Map ─────────────────────────────────────────────
    st.markdown(
        f'<div class="section-header" style="margin-top:24px;">US Startup Geography</div>'
        f'<div class="section-sub">Distribution of tracked companies across the United States</div>',
        unsafe_allow_html=True,
    )

    geo = _geocode_us(df)
    if geo.empty:
        st.caption("No US companies with recognized city data to map yet.")
    else:
        city_agg = (
            geo.groupby(["city", "lat", "lon"])
            .agg(count=("id", "size"), ai_pct=("ai_score", lambda s: (s.fillna(0) >= 0.5).mean()))
            .reset_index()
        )
        fig = px.scatter_geo(
            city_agg,
            lat="lat", lon="lon",
            size="count",
            color="count",
            hover_name="city",
            hover_data={"count": True, "lat": False, "lon": False, "ai_pct": ":.0%"},
            color_continuous_scale=[[0, "#a8c8f0"], [0.5, ACCENT], [1, YALE_BLUE]],
            size_max=32,
            labels={"count": "Companies", "ai_pct": "AI %"},
        )
        fig.update_geos(
            scope="usa",
            showland=True, landcolor="#f0f2f6",
            showlakes=True, lakecolor="#e8ecf4",
            showcountries=False,
            showsubunits=True, subunitcolor="#dde1ea",
            bgcolor=BG,
        )
        fig.update_layout(
            height=420,
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor=BG,
            coloraxis_colorbar=dict(
                title="Count",
                thickness=14,
                len=0.5,
                tickfont=dict(size=10, color=TXT3),
                title_font=dict(size=11, color=TXT2),
            ),
            font=dict(family="Inter"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Filters ──────────────────────────────────────────────────────
    st.markdown('<div class="filter-bar">', unsafe_allow_html=True)
    st.markdown('<div class="filter-bar-label">Filters</div>', unsafe_allow_html=True)

    search = st.text_input("Search", placeholder="Search by name or description...",
                           label_visibility="collapsed")

    fc1, fc2, fc3, fc4 = st.columns(4)
    ai_only = fc1.checkbox("AI startups only", value=True)
    funded_only = fc2.checkbox("Funded only")
    has_loc = fc3.checkbox("Has location")
    recent = fc4.checkbox("Last 30 days")

    ff1, ff2, ff3 = st.columns(3)
    stages = sorted(df["stage"].dropna().unique().tolist())
    sel_stages = ff1.multiselect("Stage", options=stages, placeholder="All stages")
    ctries = sorted(df["country"].dropna().unique().tolist())
    sel_ctries = ff2.multiselect("Country", options=ctries, placeholder="All countries")
    incs = sorted(df["incubator_source"].dropna().astype(str).unique().tolist())
    sel_incs = ff3.multiselect("Incubator", options=incs, placeholder="All incubators")
    st.markdown('</div>', unsafe_allow_html=True)

    # Apply
    f = df.copy()
    if ai_only:
        f = f[f["ai_score"].fillna(0) >= 0.5]
    if funded_only:
        f = f[f["last_funding_date"].notna()]
    if has_loc:
        f = f[f["country"].notna()]
    if recent:
        f = f[f["first_seen_at"] >= datetime.utcnow() - timedelta(days=30)]
    if sel_stages:
        f = f[f["stage"].isin(sel_stages)]
    if sel_ctries:
        f = f[f["country"].isin(sel_ctries)]
    if sel_incs:
        f = f[f["incubator_source"].astype(str).isin(sel_incs)]
    if search:
        s = search.lower()
        f = f[
            f["name"].str.lower().str.contains(s, na=False)
            | f["description"].fillna("").str.lower().str.contains(s, na=False)
        ]

    # Results header
    r1, r2 = st.columns([5, 1])
    r1.markdown(
        f'<span style="color:{TXT3};font-size:0.84rem;">'
        f'<b style="color:{TXT};">{len(f):,}</b> of {total:,} companies '
        f'&middot; sorted by most recent funding</span>',
        unsafe_allow_html=True,
    )
    r2.download_button(
        "Export CSV",
        data=f.to_csv(index=False).encode("utf-8"),
        file_name=f"startups_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    # Table
    cols = [c for c in [
        "name", "ai_tags", "country", "stage",
        "last_funding_date", "last_funding_amount", "last_funding_round",
        "city", "incubator_source", "first_seen_at", "domain", "description",
    ] if c in f.columns]

    disp = f[cols].copy()
    if "ai_tags" in disp.columns:
        disp["ai_tags"] = disp["ai_tags"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else (x or ""))
    if "last_funding_amount" in disp.columns:
        disp["last_funding_amount"] = disp["last_funding_amount"].apply(
            lambda v: f"${v/1e6:.1f}M" if pd.notna(v) and v > 0 else "")
    if "last_funding_date" in disp.columns:
        disp["last_funding_date"] = disp["last_funding_date"].dt.strftime("%Y-%m-%d")
    if "first_seen_at" in disp.columns:
        disp["first_seen_at"] = disp["first_seen_at"].dt.strftime("%Y-%m-%d")
    if "incubator_source" in disp.columns:
        disp["incubator_source"] = disp["incubator_source"].astype(str).replace("None", "")

    disp = disp.rename(columns={
        "name": "Name", "ai_tags": "AI Category", "country": "Country",
        "city": "City", "stage": "Stage",
        "last_funding_date": "Last Funded", "last_funding_amount": "Amount",
        "last_funding_round": "Round",
        "incubator_source": "Incubator", "first_seen_at": "First Seen",
        "domain": "Website", "description": "Description",
    })

    col_cfg = {}
    if "Website" in disp.columns:
        col_cfg["Website"] = st.column_config.LinkColumn("Website", display_text="visit")
    if "Description" in disp.columns:
        col_cfg["Description"] = st.column_config.TextColumn("Description", width="large")

    st.dataframe(disp, use_container_width=True, hide_index=True, height=560,
                 column_config=col_cfg)


# ── Page: Trends ─────────────────────────────────────────────────────

def page_trends(df: pd.DataFrame):
    if df.empty:
        st.info("No data yet.")
        return

    st.markdown(
        f'<div class="section-header">New This Week</div>'
        f'<div class="section-sub">Companies first seen in the last 7 days</div>',
        unsafe_allow_html=True,
    )

    cutoff = datetime.utcnow() - timedelta(days=7)
    week = df[df["first_seen_at"] >= cutoff].copy()

    c1, c2, c3 = st.columns(3)
    c1.metric("New companies (7d)", f"{len(week):,}")
    ai_new = int((week["ai_score"].fillna(0) >= 0.5).sum()) if len(week) else 0
    c2.metric("AI startups (7d)", f"{ai_new:,}")
    funded_new = int(week["last_funding_date"].notna().sum()) if len(week) else 0
    c3.metric("With funding (7d)", f"{funded_new:,}")

    if week.empty:
        st.caption("No new companies in the last 7 days.")
    else:
        daily = week.groupby(week["first_seen_at"].dt.date).size().reset_index(name="count")
        daily.columns = ["date", "count"]
        fig = px.bar(daily, x="date", y="count",
                     labels={"count": "Companies", "date": "Date"})
        fig.update_traces(marker_color=YALE_BLUE)
        fig.update_layout(**_layout(height=260))
        st.plotly_chart(fig, use_container_width=True)

        preview = week.head(50)[
            ["name", "country", "stage", "last_funding_date", "first_seen_at", "domain"]
        ].copy()
        preview["first_seen_at"] = preview["first_seen_at"].dt.strftime("%Y-%m-%d")
        preview["last_funding_date"] = preview["last_funding_date"].dt.strftime("%Y-%m-%d")
        preview = preview.rename(columns={
            "name": "Name", "country": "Country", "stage": "Stage",
            "last_funding_date": "Last Funded", "first_seen_at": "First Seen",
            "domain": "Website",
        })
        st.dataframe(preview, use_container_width=True, hide_index=True, height=280)

    st.markdown("<hr/>", unsafe_allow_html=True)

    # AI subdomain growth
    st.markdown(
        f'<div class="section-header">Fastest-Growing AI Subdomains</div>'
        f'<div class="section-sub">Company counts by AI category over last 30 days vs prior 30 days</div>',
        unsafe_allow_html=True,
    )

    ai_df = df[(df["ai_score"].fillna(0) >= 0.5) & df["ai_tags"].notna()].copy()
    ai_df = ai_df[ai_df["ai_tags"].apply(lambda x: isinstance(x, list) and len(x) > 0)]

    if ai_df.empty:
        st.caption("Not enough AI-tagged companies yet.")
        return

    exploded = ai_df.explode("ai_tags").rename(columns={"ai_tags": "subdomain"})
    exploded = exploded[exploded["subdomain"].notna() & (exploded["subdomain"] != "")]

    totals = exploded.groupby("subdomain").size().reset_index(name="total")
    c30 = datetime.utcnow() - timedelta(days=30)
    c60 = datetime.utcnow() - timedelta(days=60)
    new_30 = exploded[exploded["first_seen_at"] >= c30].groupby("subdomain").size().reset_index(name="new_30d")
    prev_30 = exploded[(exploded["first_seen_at"] >= c60) & (exploded["first_seen_at"] < c30)].groupby("subdomain").size().reset_index(name="prev_30d")

    mg = totals.merge(new_30, on="subdomain", how="left").merge(prev_30, on="subdomain", how="left")
    mg["new_30d"] = mg["new_30d"].fillna(0).astype(int)
    mg["prev_30d"] = mg["prev_30d"].fillna(0).astype(int)
    mg["growth_pct"] = mg.apply(
        lambda r: ((r["new_30d"] - r["prev_30d"]) / r["prev_30d"] * 100)
        if r["prev_30d"] > 0 else (100.0 if r["new_30d"] > 0 else 0.0), axis=1)
    mg = mg.sort_values("new_30d", ascending=False).head(15)

    t1, t2 = st.columns(2)
    with t1:
        fig1 = px.bar(mg, x="new_30d", y="subdomain", orientation="h",
                      title="New companies (last 30 days)",
                      labels={"new_30d": "Companies", "subdomain": ""})
        fig1.update_traces(marker_color=YALE_BLUE)
        fig1.update_layout(**_layout(height=420,
            yaxis=dict(autorange="reversed", gridcolor=BORDER_LIGHT),
            showlegend=False))
        st.plotly_chart(fig1, use_container_width=True)

    with t2:
        gs = mg.sort_values("growth_pct", ascending=False)
        fig2 = px.bar(gs, x="growth_pct", y="subdomain", orientation="h",
                      title="Growth rate (vs prior 30d)",
                      labels={"growth_pct": "% Growth", "subdomain": ""})
        fig2.update_traces(marker_color=GREEN)
        fig2.update_layout(**_layout(height=420,
            yaxis=dict(autorange="reversed", gridcolor=BORDER_LIGHT),
            showlegend=False))
        st.plotly_chart(fig2, use_container_width=True)

    md = mg[["subdomain", "total", "new_30d", "prev_30d", "growth_pct"]].copy()
    md["growth_pct"] = md["growth_pct"].apply(lambda v: f"{v:+.1f}%")
    md = md.rename(columns={"subdomain": "Subdomain", "total": "Total",
                             "new_30d": "New (30d)", "prev_30d": "Prev 30d", "growth_pct": "Growth"})
    st.dataframe(md, use_container_width=True, hide_index=True)


# ── Page: Pipeline Health ────────────────────────────────────────────

def page_health(health_df: pd.DataFrame, runs_df: pd.DataFrame):
    if health_df.empty:
        st.info("No sites registered yet.")
        return

    st.markdown(
        f'<div class="section-header">Pipeline Health</div>'
        f'<div class="section-sub">Per-domain status from the <code>site_health</code> table. '
        f'Any URL you run under <b>Scraper → Run Agentic Scraper</b> registers/updates that domain '
        f"here (seed URL, last counts, next batch due). Hard-coded easy scrapers are only part of the list.</div>",
        unsafe_allow_html=True,
    )

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
    h1, h2 = st.columns([1, 2])
    with h1:
        fig = px.pie(tier, values="Count", names="Tier", title="By Tier",
                     hole=0.55, color_discrete_sequence=[YALE_BLUE, GREEN, AMBER])
        fig.update_layout(**_layout(height=280))
        st.plotly_chart(fig, use_container_width=True)

    with h2:
        hd = health_df[["domain", "difficulty", "status", "consecutive_failures",
                         "last_record_count", "total_runs", "total_successes", "last_success_at"]].copy()
        if "last_success_at" in hd.columns:
            hd["last_success_at"] = pd.to_datetime(hd["last_success_at"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
        st.dataframe(hd, use_container_width=True, hide_index=True, height=300)

    st.markdown("### Recent Runs (7 days)")
    if runs_df.empty:
        st.caption("No runs in the last 7 days.")
    else:
        rd = runs_df.copy()
        if "started_at" in rd.columns:
            rd["started_at"] = pd.to_datetime(rd["started_at"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
        if "finished_at" in rd.columns:
            rd = rd.drop(columns=["finished_at"])
        if "duration_seconds" in rd.columns:
            rd["duration_seconds"] = rd["duration_seconds"].apply(
                lambda v: f"{v:.1f}s" if pd.notna(v) else "")
        st.dataframe(rd, use_container_width=True, hide_index=True, height=340)


# ── Page: GitHub Discovery ───────────────────────────────────────────

def page_github(df: pd.DataFrame, df_all: pd.DataFrame):
    """GitHub-sourced companies only, filtered by LLM = 'startup'."""
    st.markdown(
        f'<div class="section-header">GitHub Discovery</div>'
        f'<div class="section-sub">Repos found via GitHub scan and classified as startups by the LLM filter</div>',
        unsafe_allow_html=True,
    )

    total_all = len(df_all)
    total_kept = len(df)

    cls_counts = (
        df_all["llm_classification"].fillna("unclassified").value_counts().to_dict()
        if not df_all.empty and "llm_classification" in df_all.columns
        else {}
    )

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("GitHub repos (raw)", f"{total_all:,}")
    m2.metric("Classified as startup", f"{total_kept:,}")
    m3.metric("Personal projects", f"{cls_counts.get('personal_project', 0):,}")
    m4.metric("Research", f"{cls_counts.get('research', 0):,}")
    m5.metric("Community tools", f"{cls_counts.get('community_tool', 0):,}")

    if df.empty:
        st.info("No GitHub repos pass the LLM startup filter yet. "
                "Run `python scripts/github_weekly_discover.py` or `scripts/run_llm_classify.py`.")
        return

    # Filters
    st.markdown('<div class="filter-bar">', unsafe_allow_html=True)
    st.markdown('<div class="filter-bar-label">Filters</div>', unsafe_allow_html=True)
    search = st.text_input("Search GitHub", placeholder="Search by repo, owner, description...",
                           label_visibility="collapsed", key="gh_search")
    gc1, gc2, gc3 = st.columns(3)
    min_stars = gc1.number_input("Min stars", min_value=0, value=0, step=100, key="gh_minstars")
    min_conf = gc2.slider("Min LLM confidence", 0.0, 1.0, 0.6, 0.05, key="gh_minconf")
    recent_only = gc3.checkbox("Last 30 days", key="gh_recent")
    st.markdown('</div>', unsafe_allow_html=True)

    f = df.copy()
    if min_stars > 0:
        f = f[f["github_stars"].fillna(0) >= min_stars]
    if min_conf > 0 and "llm_confidence" in f.columns:
        # auto-accepted rows have NULL confidence — keep them
        f = f[f["llm_confidence"].isna() | (f["llm_confidence"] >= min_conf)]
    if recent_only:
        f = f[f["first_seen_at"] >= datetime.utcnow() - timedelta(days=30)]
    if search:
        s = search.lower()
        f = f[
            f["name"].str.lower().str.contains(s, na=False)
            | f["github_repo"].fillna("").str.lower().str.contains(s, na=False)
            | f["description"].fillna("").str.lower().str.contains(s, na=False)
        ]

    # Results header + export
    r1, r2 = st.columns([5, 1])
    r1.markdown(
        f'<span style="color:{TXT3};font-size:0.84rem;">'
        f'<b style="color:{TXT};">{len(f):,}</b> of {total_kept:,} GitHub startups '
        f'&middot; sorted by stars</span>',
        unsafe_allow_html=True,
    )
    r2.download_button(
        "Export CSV",
        data=f.to_csv(index=False).encode("utf-8"),
        file_name=f"github_startups_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True,
        key="gh_export",
    )

    disp = f.sort_values("github_stars", ascending=False, na_position="last").copy()
    cols = [c for c in [
        "name", "github_repo", "github_stars", "github_forks", "github_url",
        "ai_tags", "llm_confidence", "country", "city",
        "first_seen_at", "domain", "description",
    ] if c in disp.columns]
    disp = disp[cols]

    if "ai_tags" in disp.columns:
        disp["ai_tags"] = disp["ai_tags"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else (x or ""))
    if "first_seen_at" in disp.columns:
        disp["first_seen_at"] = disp["first_seen_at"].dt.strftime("%Y-%m-%d")
    if "github_stars" in disp.columns:
        disp["github_stars"] = disp["github_stars"].apply(
            lambda v: int(v) if pd.notna(v) else None)
    if "github_forks" in disp.columns:
        disp["github_forks"] = disp["github_forks"].apply(
            lambda v: int(v) if pd.notna(v) else None)
    if "llm_confidence" in disp.columns:
        disp["llm_confidence"] = disp["llm_confidence"].apply(
            lambda v: f"{v:.2f}" if pd.notna(v) else "auto")

    disp = disp.rename(columns={
        "name": "Owner", "github_repo": "Repo", "github_stars": "Stars",
        "github_forks": "Forks", "github_url": "Link",
        "ai_tags": "AI Category", "llm_confidence": "LLM Conf",
        "country": "Country", "city": "City",
        "first_seen_at": "First Seen", "domain": "Website", "description": "Description",
    })

    col_cfg = {}
    if "Link" in disp.columns:
        col_cfg["Link"] = st.column_config.LinkColumn("Link", display_text="view")
    if "Website" in disp.columns:
        col_cfg["Website"] = st.column_config.LinkColumn("Website", display_text="visit")
    if "Stars" in disp.columns:
        col_cfg["Stars"] = st.column_config.NumberColumn("Stars", format="%d")
    if "Forks" in disp.columns:
        col_cfg["Forks"] = st.column_config.NumberColumn("Forks", format="%d")
    if "Description" in disp.columns:
        col_cfg["Description"] = st.column_config.TextColumn("Description", width="large")

    st.dataframe(disp, use_container_width=True, hide_index=True, height=560,
                 column_config=col_cfg)


# ── Page: Scraper ────────────────────────────────────────────────────

def page_scraper():
    health_df = load_site_health()
    health_map = ({r["domain"]: r for _, r in health_df.iterrows()} if not health_df.empty else {})

    # ── Agentic scraper (top, prominent) ─────────────────────────────
    st.markdown(
        f'<div class="section-header">Run Scraper</div>'
        f'<div class="section-sub">Enter any URL to scrape using the agentic engine (Claude + Tavily)</div>',
        unsafe_allow_html=True,
    )

    with st.form("agentic_form", clear_on_submit=False):
        ac1, ac2 = st.columns([4, 1])
        with ac1:
            url = st.text_input("URL", placeholder="https://example.com/portfolio",
                                label_visibility="collapsed")
        with ac2:
            force = st.checkbox("Force", value=True, help="Ignore cooldown")
        submitted = st.form_submit_button("Run Agentic Scraper", type="primary",
                                          use_container_width=True)
    if submitted and url:
        with st.spinner("Running agentic scraper..."):
            result = Orchestrator().run(url, force=force)
        if result.success:
            st.success(f"{result.records_found} records ({result.records_new} new)")
        else:
            st.error(f"{result.status}: {result.error_message or ''}")
        st.cache_data.clear()

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Easy scrapers grid ───────────────────────────────────────────
    st.markdown(
        f'<div class="section-header">Deterministic Scrapers</div>'
        f'<div class="section-sub">{len(SCRAPER_REGISTRY)} hard-coded scrapers for known sites</div>',
        unsafe_allow_html=True,
    )

    sorted_scrapers = sorted(SCRAPER_REGISTRY.items())
    cols_per_row = 4
    for i in range(0, len(sorted_scrapers), cols_per_row):
        batch = sorted_scrapers[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for j, (domain, entry) in enumerate(batch):
            with cols[j]:
                health = health_map.get(domain, {})
                status = health.get("status", "pending")
                dot_cls = {"healthy": "dot-healthy", "degraded": "dot-degraded",
                           "broken": "dot-broken", "excluded": "dot-excluded"
                           }.get(status, "dot-pending")
                last_ct = health.get("last_record_count")
                ct_text = f" &middot; {last_ct} records" if last_ct else ""

                st.markdown(
                    f'<div class="scraper-card">'
                    f'<div class="scraper-domain">'
                    f'<span class="{dot_cls}">&#9679;</span> {domain}</div>'
                    f'<div class="scraper-meta">{entry.pattern}{ct_text}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button("Run", key=f"easy_{domain}", use_container_width=True):
                    src_url = health.get("url") or entry.cls().source_url
                    with st.spinner(f"Running {domain}..."):
                        result = Orchestrator().run(src_url, force=True)
                    if result.success:
                        st.success(f"{result.records_found} ({result.records_new} new)")
                    else:
                        st.error(f"{result.status}")
                    st.cache_data.clear()

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Discovery & self-healing ─────────────────────────────────────
    st.markdown(
        f'<div class="section-header">Discovery &amp; Self-Healing</div>'
        f'<div class="section-sub">Automated loops for finding new sites and recovering broken ones</div>',
        unsafe_allow_html=True,
    )

    d1, d2, d3, d4 = st.columns(4)
    with d1:
        if st.button("Discover new sites", use_container_width=True):
            from backend.discovery.feed_loader import register_new_sites
            with st.spinner("Loading feeds..."):
                register_new_sites()
            st.success("New sites registered")
            st.cache_data.clear()
    with d2:
        if st.button("Retry zero-result sites", use_container_width=True):
            with st.spinner("Retrying..."):
                results = Orchestrator().run_retries(hours=48)
            st.success(f"Retried {len(results)} sites")
            st.cache_data.clear()
    with d3:
        if st.button("Revisit excluded sites", use_container_width=True):
            from backend.orchestrator.health import HealthMonitor
            with st.spinner("Reactivating..."):
                HealthMonitor().reactivate_revisit_sites()
            st.success("Excluded sites reactivated")
            st.cache_data.clear()
    with d4:
        if st.button("Run all due sites", use_container_width=True, type="primary"):
            with st.spinner("Batch scraping..."):
                results = Orchestrator().run_all_due()
            ok = sum(1 for r in results if r.success)
            st.success(f"{ok}/{len(results)} succeeded")
            st.cache_data.clear()


# ── Main ─────────────────────────────────────────────────────────────

def main():
    df = load_startups()
    health_df = load_site_health()
    runs_df = load_recent_runs()

    # Split companies by source.
    #   GitHub Discovery: came in via GitHub scan (no incubator_source, has a repo)
    #   Scraper:          came in via accelerator/incubator scrapers
    if not df.empty:
        inc = df["incubator_source"].astype("string")
        has_repo = df["github_repo"].notna() if "github_repo" in df.columns else pd.Series([False] * len(df))
        is_gh = inc.isna() & has_repo
    else:
        is_gh = pd.Series([], dtype=bool)

    scraper_df = df[~is_gh].copy() if not df.empty else df
    github_df_all = df[is_gh].copy() if not df.empty else df

    # LLM filter: only keep repos classified as 'startup' by the LLM
    if "llm_classification" in github_df_all.columns:
        github_df = github_df_all[github_df_all["llm_classification"] == "startup"].copy()
    else:
        github_df = github_df_all.iloc[0:0].copy()

    tab_overview, tab_github, tab_trends, tab_health, tab_scraper = st.tabs([
        "Overview", "GitHub Discovery", "Trends", "Pipeline Health", "Scraper",
    ])

    with tab_overview:
        page_overview(scraper_df)
    with tab_github:
        page_github(github_df, github_df_all)
    with tab_trends:
        page_trends(scraper_df)
    with tab_health:
        page_health(health_df, runs_df)
    with tab_scraper:
        page_scraper()


if __name__ == "__main__":
    main()
