
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
from backend.utils.country import count_distinct_countries, normalize_country, GLOBE_COUNTRIES
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
    _raw_countries = _conn.execute(text(
        "SELECT DISTINCT country FROM companies"
        " WHERE country IS NOT NULL AND country != '' AND country NOT ILIKE '%remote%'"
    )).scalars().all()
    _countries = count_distinct_countries(_raw_countries)

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
    """Load companies for the dashboard.

    Memory-tuned for Railway's container limit. Two changes keep us under the
    OOM ceiling on a 125K+ row DB:
      - LEFT(description, 240) — descriptions can be multi-KB blobs.
      - LIMIT 15000 — newest 15K covers the visible UI; the rare "I want
        everything" path can re-query separately.
    """
    engine = get_engine()
    query = """
        SELECT
            c.id, c.name, c.domain,
            LEFT(c.description, 240) AS description,
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
        LIMIT 15000
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

        # Inclusive "is AI" flag: any model-scored signal OR any AI tag attached.
        # Captures companies with even a slight AI signal, not only high-confidence ones.
        has_tags = df["ai_tags"].apply(lambda x: isinstance(x, list) and len(x) > 0)
        df["is_ai"] = (df["ai_score"].fillna(0) >= 0.3) | has_tags
    return df


@st.cache_data(ttl=60)
def load_site_health() -> pd.DataFrame:
    # Make sure every registered scraper has a row, so newly added scrapers
    # show up even before their first run.
    try:
        from backend.orchestrator.health import HealthMonitor
        HealthMonitor().seed_registry()
    except Exception:
        pass

    engine = get_engine()
    q = """SELECT domain, url, difficulty, scraper_name, status, worker_state,
                  category, pending_reason, pending_reason_at,
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


@st.cache_data(ttl=300)
def _load_site_countries() -> dict[str, str]:
    """Returns domain → canonical country mapping.

    Priority: companies.incubator_source match > TLD inference > None.
    """
    engine = get_engine()
    mapping: dict[str, str] = {}

    # Pull country from already-scraped sites via companies table
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT DISTINCT incubator_source, country FROM companies "
            "WHERE incubator_source IS NOT NULL AND country IS NOT NULL AND country != ''"
        )).mappings().all()
    for row in rows:
        norm = normalize_country(row["country"])
        if norm and norm in GLOBE_COUNTRIES:
            mapping[row["incubator_source"]] = norm

    # For remaining domains, infer from TLD (longer patterns first)
    with engine.connect() as conn:
        domain_rows = conn.execute(text("SELECT DISTINCT domain FROM site_health")).mappings().all()
    _TLD_MAP = [
        (".co.kr", "South Korea"), (".com.au", "Australia"), (".co.uk", "United Kingdom"),
        (".com.br", "Brazil"), (".co.il", "Israel"), (".co.in", "India"),
        (".kr", "South Korea"), (".jp", "Japan"), (".de", "Germany"),
        (".fr", "France"), (".il", "Israel"), (".sg", "Singapore"),
        (".au", "Australia"), (".se", "Sweden"), (".nl", "Netherlands"),
        (".in", "India"), (".ae", "United Arab Emirates"), (".cn", "China"),
        (".tw", "Taiwan"), (".br", "Brazil"), (".ca", "Canada"),
        (".uk", "United Kingdom"), (".dk", "Denmark"), (".fi", "Finland"),
        (".no", "Norway"), (".ch", "Switzerland"), (".be", "Belgium"),
        (".es", "Spain"), (".it", "Italy"), (".pl", "Poland"), (".ee", "Estonia"),
    ]
    for row in domain_rows:
        domain = row["domain"]
        if domain not in mapping:
            for suffix, country in _TLD_MAP:
                if domain.endswith(suffix):
                    mapping[domain] = country
                    break

    return mapping


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

def page_overview(df: pd.DataFrame, health_df: pd.DataFrame | None = None):
    if df.empty:
        st.info("No companies in database. Go to the Scraper tab to get started.")
        return

    # ── Sources analyzed (site_health inventory) ─────────────────────
    if health_df is not None and not health_df.empty:
        st.markdown(
            '<div class="section-header">Sources Analyzed</div>'
            '<div class="section-sub">Portfolio sites in the tracker — click to expand category and scraping-state breakdown</div>',
            unsafe_allow_html=True,
        )

        cat = health_df.get("category")
        if cat is None:
            cat = pd.Series([None] * len(health_df))
        cat = cat.fillna("other")
        state = (
            health_df.get("worker_state").fillna("pending")
            if "worker_state" in health_df.columns
            else pd.Series(["pending"] * len(health_df))
        )

        # Top-level summary: just total sites.
        st.metric("Total Sites", f"{len(health_df):,}")

        # Detailed breakdown collapsed by default.
        with st.expander("View detailed breakdown", expanded=False):
            s1, s2, s3, s4, s5 = st.columns(5)
            s1.metric("Universities", f"{int((cat == 'university_incubator').sum()):,}")
            s2.metric("Accelerators", f"{int((cat == 'accelerator').sum()):,}")
            s3.metric("VC Portfolios", f"{int((cat == 'vc_portfolio').sum()):,}")
            s4.metric("Discovery", f"{int((cat == 'discovery_aggregator').sum()):,}")
            s5.metric("Gov Programs", f"{int((cat == 'government_program').sum()):,}")

            working_n = int((state == "working").sum())
            pending_n = int((state == "pending").sum())
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Scrapable (working)", f"{working_n:,}")
            sc2.metric("Challenging (pending)", f"{pending_n:,}")
            if "pending_reason" in health_df.columns:
                diagnosed_n = int(health_df["pending_reason"].notna().sum())
                sc3.metric("With AI diagnosis", f"{diagnosed_n:,}")

    # Metrics
    total = len(df)
    # Inclusive: any model-scored AI signal OR any AI tag attached.
    is_ai_col = df["is_ai"] if "is_ai" in df.columns else (df["ai_score"].fillna(0) >= 0.3)
    ai_n = int(is_ai_col.sum())
    funded = int(df["last_funding_date"].notna().sum())
    countries = count_distinct_countries(df["country"].dropna().tolist())

    st.markdown(
        '<div class="section-header" style="margin-top:24px;">Companies</div>'
        '<div class="section-sub">AI-startup totals across all tracked sources (inclusive: any AI signal)</div>',
        unsafe_allow_html=True,
    )
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
            .agg(count=("id", "size"), ai_pct=("is_ai", "mean"))
            .reset_index()
        )
        if len(city_agg) > 100:
            city_agg = city_agg.nlargest(100, "count")

        # Streamlit's native pydeck map. plotly's scatter_geo (with scope="usa"
        # + showsubunits) ships US state geojson chunks that get truncated by
        # Railway's response buffering and surface as "Unexpected end of input"
        # in the browser. pydeck only sends lat/lon/size — a few KB payload.
        map_df = city_agg.rename(columns={"count": "size"})[["lat", "lon", "size"]].copy()
        # Scale marker size for visibility on a continental zoom.
        map_df["size"] = (map_df["size"].astype(float) ** 0.5) * 4000
        mc1, mc2 = st.columns([3, 1])
        with mc1:
            st.map(map_df, latitude="lat", longitude="lon", size="size",
                   color="#0F4D92", zoom=3, width="stretch")
        with mc2:
            top_cities = (
                city_agg.nlargest(10, "count")[["city", "count"]]
                .rename(columns={"city": "City", "count": "Companies"})
            )
            st.markdown(
                f'<div style="color:{TXT3};font-size:0.82rem;margin-bottom:4px;">Top 10 cities</div>',
                unsafe_allow_html=True,
            )
            st.dataframe(top_cities, width="stretch", hide_index=True, height=380)

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

    _SOURCE_CATEGORY = {
        "yc": "accelerator", "techstars": "accelerator", "alchemist": "accelerator",
        "antler": "accelerator", "entrepreneur_first": "accelerator", "seedcamp": "accelerator",
        "era_nyc": "accelerator", "capital_factory": "accelerator", "dreamit": "accelerator",
        "sosv": "accelerator", "masschallenge": "accelerator", "plug_and_play": "accelerator",
        "five_hundred_global": "accelerator", "station_f": "accelerator",
        "startupbootcamp": "accelerator", "h_farm": "accelerator", "rockstart": "accelerator",
        "wayra": "accelerator", "surge": "accelerator", "brinc": "accelerator",
        "hax": "accelerator", "flat6labs": "accelerator", "astrolabs": "accelerator",
        "parallel18": "accelerator", "nxtp_ventures": "accelerator",
        "sequoia": "vc_portfolio", "greylock": "vc_portfolio", "balderton": "vc_portfolio",
        "foundersfund": "vc_portfolio", "usv": "vc_portfolio", "bvp": "vc_portfolio",
        "generalcatalyst": "vc_portfolio", "village_global": "vc_portfolio",
        "pioneer_fund": "vc_portfolio", "beenext": "vc_portfolio", "allvp": "vc_portfolio",
        "lux_capital": "vc_portfolio", "ventures_platform": "vc_portfolio",
        "berkeley_skydeck": "university_incubator", "stanford_startx": "university_incubator",
        "harvard_ilabs": "university_incubator", "mit_engine": "university_incubator",
        "princeton_elab": "university_incubator", "rice_owlspark": "university_incubator",
        "uiuc_enterpriseworks": "university_incubator", "cmu_swartz": "university_incubator",
        "georgia_tech_atdc": "university_incubator", "michigan_zell_lurie": "university_incubator",
        "grindstone": "government_program", "seedstars": "government_program",
        "sting_stockholm": "government_program", "startup_chile": "government_program",
        "sparklabs": "government_program",
        "agentic_scrape": "discovery_aggregator", "betalist": "discovery_aggregator",
        "wellfound": "discovery_aggregator", "f6s": "discovery_aggregator",
    }
    _CAT_LABELS = {
        "accelerator": "Accelerator", "vc_portfolio": "VC Portfolio",
        "university_incubator": "University Incubator",
        "government_program": "Government Program", "discovery_aggregator": "Discovery Aggregator",
    }

    ff1, ff2, ff3, ff4 = st.columns(4)
    stages = sorted(df["stage"].dropna().unique().tolist())
    sel_stages = ff1.multiselect("Stage", options=stages, placeholder="All stages")
    ctries = sorted(df["country"].dropna().unique().tolist())
    sel_ctries = ff2.multiselect("Country", options=ctries, placeholder="All countries")
    incs = sorted(df["incubator_source"].dropna().astype(str).unique().tolist())
    sel_incs = ff3.multiselect("Incubator", options=incs, placeholder="All incubators")
    sel_cats = ff4.multiselect("Source type", options=list(_CAT_LABELS.keys()),
                                format_func=lambda x: _CAT_LABELS.get(x, x),
                                placeholder="All types")

    if "founded_year" in df.columns and df["founded_year"].notna().any():
        valid_yrs = df["founded_year"].dropna().astype(int)
        yr_min, yr_max = int(valid_yrs.min()), int(valid_yrs.max())
        yr_min = max(yr_min, 2000)
        yr_range = st.slider("Founded year", yr_min, yr_max, (2015, yr_max), key="yr_range")
    else:
        yr_range = None

    st.markdown('</div>', unsafe_allow_html=True)

    # Apply
    f = df.copy()
    if ai_only:
        f = f[f["is_ai"]] if "is_ai" in f.columns else f[f["ai_score"].fillna(0) >= 0.3]
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
    if sel_cats:
        src_cat = f["incubator_source"].astype(str).map(_SOURCE_CATEGORY).fillna("discovery_aggregator")
        f = f[src_cat.isin(sel_cats)]
    if yr_range and "founded_year" in f.columns:
        f = f[f["founded_year"].isna() | f["founded_year"].between(yr_range[0], yr_range[1])]
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
        width="stretch",
    )

    # Table — sort so AI startups appear first (by is_ai DESC, then by funding date).
    if "is_ai" in f.columns:
        f = f.sort_values(
            by=["is_ai", "last_funding_date", "first_seen_at"],
            ascending=[False, False, False],
            na_position="last",
        )

    cols = [c for c in [
        "is_ai", "name", "ai_tags", "country", "stage",
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
    if "is_ai" in disp.columns:
        disp["is_ai"] = disp["is_ai"].astype(bool)

    disp = disp.rename(columns={
        "is_ai": "AI",
        "name": "Name", "ai_tags": "AI Category", "country": "Country",
        "city": "City", "stage": "Stage",
        "last_funding_date": "Last Funded", "last_funding_amount": "Amount",
        "last_funding_round": "Round",
        "incubator_source": "Incubator", "first_seen_at": "First Seen",
        "domain": "Website", "description": "Description",
    })

    col_cfg = {}
    if "AI" in disp.columns:
        col_cfg["AI"] = st.column_config.CheckboxColumn(
            "AI", help="AI signal detected (model score or AI tag)", width="small"
        )
    if "Website" in disp.columns:
        col_cfg["Website"] = st.column_config.LinkColumn("Website", display_text="visit")
    if "Description" in disp.columns:
        col_cfg["Description"] = st.column_config.TextColumn("Description", width="large")

    # Paginate the in-browser table. Sending tens of thousands of rows in a
    # single response trips Railway's proxy buffer (shows up as
    # "Unexpected end of input" + the page's plotly charts breaking too).
    # Full data remains downloadable via the Export CSV button above.
    PAGE_SIZE = 100
    total_rows = len(disp)
    total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)

    pc1, pc2, pc3 = st.columns([1, 2, 1])
    with pc2:
        page = st.number_input(
            "Page",
            min_value=1,
            max_value=total_pages,
            value=1,
            step=1,
            label_visibility="collapsed",
            help=f"{total_rows:,} rows across {total_pages:,} pages of {PAGE_SIZE}",
        )
    with pc1:
        st.markdown(
            f'<div style="color:{TXT3};font-size:0.82rem;padding-top:6px;">'
            f"Page <b style=\"color:{TXT};\">{page:,}</b> of {total_pages:,}"
            f"</div>",
            unsafe_allow_html=True,
        )
    with pc3:
        start_row = (page - 1) * PAGE_SIZE + 1
        end_row = min(page * PAGE_SIZE, total_rows)
        st.markdown(
            f'<div style="color:{TXT3};font-size:0.82rem;padding-top:6px;text-align:right;">'
            f"Rows <b style=\"color:{TXT};\">{start_row:,}–{end_row:,}</b> of {total_rows:,}"
            f"</div>",
            unsafe_allow_html=True,
        )

    start = (page - 1) * PAGE_SIZE
    disp_view = disp.iloc[start:start + PAGE_SIZE]

    st.dataframe(disp_view, width="stretch", hide_index=True, height=560,
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
    if len(week) and "is_ai" in week.columns:
        ai_new = int(week["is_ai"].sum())
    elif len(week):
        ai_new = int((week["ai_score"].fillna(0) >= 0.3).sum())
    else:
        ai_new = 0
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
        st.plotly_chart(fig, width="stretch")

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
        st.dataframe(preview, width="stretch", hide_index=True, height=280)

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
        st.plotly_chart(fig1, width="stretch")

    with t2:
        gs = mg.sort_values("growth_pct", ascending=False)
        fig2 = px.bar(gs, x="growth_pct", y="subdomain", orientation="h",
                      title="Growth rate (vs prior 30d)",
                      labels={"growth_pct": "% Growth", "subdomain": ""})
        fig2.update_traces(marker_color=GREEN)
        fig2.update_layout(**_layout(height=420,
            yaxis=dict(autorange="reversed", gridcolor=BORDER_LIGHT),
            showlegend=False))
        st.plotly_chart(fig2, width="stretch")

    md = mg[["subdomain", "total", "new_30d", "prev_30d", "growth_pct"]].copy()
    md["growth_pct"] = md["growth_pct"].apply(lambda v: f"{v:+.1f}%")
    md = md.rename(columns={"subdomain": "Subdomain", "total": "Total",
                             "new_30d": "New (30d)", "prev_30d": "Prev 30d", "growth_pct": "Growth"})
    st.dataframe(md, width="stretch", hide_index=True)


# ── Page: Pipeline Health ────────────────────────────────────────────

def page_health(health_df: pd.DataFrame, runs_df: pd.DataFrame):
    if health_df.empty:
        st.info("No sites registered yet.")
        return

    st.markdown(
        f'<div class="section-header">Pipeline Health</div>'
        f'<div class="section-sub">Each scraper is classified <b>Working</b> (last attempt produced valid records) '
        f'or <b>Pending</b> (last attempt failed, returned zero, or was never tried). '
        f'Detailed status (degraded / broken / excluded) is shown alongside.</div>',
        unsafe_allow_html=True,
    )

    # Backward compat: if older rows don't yet have worker_state, derive it from status.
    if "worker_state" not in health_df.columns:
        health_df = health_df.copy()
        health_df["worker_state"] = health_df["status"].apply(
            lambda s: "working" if s == "healthy" else "pending"
        )

    working_df = health_df[health_df["worker_state"] == "working"].copy()
    pending_df = health_df[health_df["worker_state"] != "working"].copy()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Master Working", len(working_df))
    m2.metric("Master Pending", len(pending_df))
    m3.metric("Easy tier", int((health_df["difficulty"] == "easy").sum()))
    m4.metric("Hard tier", int((health_df["difficulty"] == "hard").sum()))

    st.markdown("<br/>", unsafe_allow_html=True)

    # ── Inventory by category ───────────────────────────────────────────
    st.markdown("### Inventory by category")
    if "category" in health_df.columns and health_df["category"].notna().any():
        inv = (
            health_df.assign(category=health_df["category"].fillna("other"))
            .groupby(["category", "worker_state"]).size()
            .reset_index(name="count")
        )
        try:
            import plotly.express as px
            fig = px.bar(
                inv, x="category", y="count", color="worker_state",
                color_discrete_map={"working": "#1aab68", "pending": "#d97706"},
                category_orders={"category": [
                    "university_incubator", "accelerator", "vc_portfolio",
                    "discovery_aggregator", "government_program", "other",
                ]},
                barmode="stack",
            )
            fig.update_layout(**_layout(height=260, legend_title_text=""))
            st.plotly_chart(fig, width="stretch")
        except Exception:
            st.dataframe(inv, hide_index=True, width="stretch")
    else:
        st.caption("No category tags yet — run `python scripts/backfill_site_health_from_companies.py`.")

    # ── Scout button ────────────────────────────────────────────────────
    sc_col, _ = st.columns([1, 5])
    if sc_col.button("Scout 5 new US sites", key="scout_btn"):
        with st.spinner("Scouting…"):
            import subprocess
            from pathlib import Path
            project_root = Path(__file__).resolve().parent.parent
            try:
                out = subprocess.run(
                    [sys.executable, "scripts/run_scout.py", "--country", "US", "--limit", "5"],
                    cwd=project_root, capture_output=True, text=True, timeout=600,
                )
                st.code((out.stdout or "") + (out.stderr or ""), language="text")
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Scout failed: {e}")

    cols_to_show_working = ["domain", "category", "difficulty", "scraper_name", "status",
                            "consecutive_failures", "last_record_count",
                            "total_runs", "total_successes", "last_success_at"]
    cols_to_show_pending = ["domain", "category", "difficulty", "scraper_name", "status",
                            "consecutive_failures", "pending_reason",
                            "last_record_count", "total_runs", "last_failure_at"]

    def _fmt(df, cols):
        d = df[[c for c in cols if c in df.columns]].copy()
        for tcol in ("last_success_at", "last_failure_at"):
            if tcol in d.columns:
                d[tcol] = pd.to_datetime(d[tcol], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
        return d

    w_tab, p_tab = st.tabs([f"Master Working ({len(working_df)})",
                             f"Master Pending ({len(pending_df)})"])
    with w_tab:
        if working_df.empty:
            st.caption("No scrapers have produced records yet.")
        else:
            st.dataframe(_fmt(working_df.sort_values("last_success_at", ascending=False, na_position="last"),
                              cols_to_show_working),
                         width="stretch", hide_index=True, height=320)

    with p_tab:
        if pending_df.empty:
            st.caption("All scrapers are currently working.")
        else:
            st.dataframe(_fmt(pending_df.sort_values(["consecutive_failures", "domain"], ascending=[False, True]),
                              cols_to_show_pending),
                         width="stretch", hide_index=True, height=320)

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
        st.dataframe(rd, width="stretch", hide_index=True, height=340)

    # ── Coverage by Country ──────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Coverage by Country")

    country_map = _load_site_countries()
    hdf = health_df.copy()
    hdf["country"] = hdf["domain"].map(country_map)
    intl_df = hdf[hdf["country"].notna()].copy()

    if intl_df.empty:
        st.info("No country data available yet — scrape some sites or check TLD coverage.")
    else:
        by_country = (
            intl_df.groupby("country")
            .agg(
                total=("domain", "count"),
                healthy=("status", lambda x: (x == "healthy").sum()),
                pending=("status", lambda x: (x == "pending").sum()),
                broken=("status", lambda x: (x == "broken").sum()),
                last_scraped=("last_success_at", "max"),
            )
            .reset_index()
            .sort_values("total", ascending=False)
        )

        fig = go.Figure()
        for state, color in [("pending", "#f59e0b"), ("healthy", "#22c55e"), ("broken", "#ef4444")]:
            fig.add_bar(
                y=by_country["country"],
                x=by_country[state],
                name=state.capitalize(),
                marker_color=color,
                orientation="h",
            )
        fig.update_layout(
            barmode="stack",
            height=max(300, len(by_country) * 28),
            xaxis_title="Sites",
            legend_title_text="Status",
            title_text="",
            **_layout(),
        )
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)

        display = by_country.copy()
        display["last_scraped"] = pd.to_datetime(display["last_scraped"], errors="coerce").dt.strftime("%Y-%m-%d")
        st.dataframe(
            display.rename(columns={
                "country": "Country", "total": "Total",
                "healthy": "Healthy", "pending": "Pending", "broken": "Broken",
                "last_scraped": "Last Scraped",
            }),
            use_container_width=True,
            hide_index=True,
        )


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
        width="stretch",
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

    st.dataframe(disp, width="stretch", hide_index=True, height=560,
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
                                          width="stretch")
    if submitted and url:
        with st.spinner("Running agentic scraper..."):
            result = Orchestrator().run(url, force=force)
        if result.success:
            st.success(f"{result.records_found} records ({result.records_new} new)")
        else:
            st.error(f"{result.status}: {result.error_message or ''}")
        st.cache_data.clear()

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Easy scrapers (collapsed list) ───────────────────────────────
    sorted_scrapers = sorted(SCRAPER_REGISTRY.items())
    working_n = sum(
        1 for d, _ in sorted_scrapers
        if (health_map.get(d, {}).get("worker_state") or
            ("working" if health_map.get(d, {}).get("status") == "healthy" else "pending")) == "working"
    )

    with st.expander(
        f"Deterministic Scrapers — {len(sorted_scrapers)} sites "
        f"({working_n} working / {len(sorted_scrapers) - working_n} pending)",
        expanded=False,
    ):
        for domain, entry in sorted_scrapers:
            health = health_map.get(domain, {})
            worker_state = health.get("worker_state") or (
                "working" if health.get("status") == "healthy" else "pending"
            )
            dot = "🟢" if worker_state == "working" else "🟡"
            last_ct = health.get("last_record_count")
            ct_text = f" · {last_ct} records" if last_ct else ""
            row1, row2 = st.columns([5, 1])
            row1.markdown(
                f"{dot}&nbsp; **{domain}** "
                f"<span style='color:{TXT3};font-size:0.82rem;'>"
                f"&middot; {entry.pattern}{ct_text}</span>",
                unsafe_allow_html=True,
            )
            if row2.button("Run", key=f"easy_{domain}", width="stretch"):
                src_url = health.get("url") or entry.cls().source_url
                with st.spinner(f"Running {domain}..."):
                    result = Orchestrator().run(src_url, force=True)
                if result.success:
                    st.success(f"{domain}: {result.records_found} ({result.records_new} new)")
                else:
                    st.error(f"{domain}: {result.status}")
                st.cache_data.clear()

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Batch: run all pending ────────────────────────────────────────
    st.markdown(
        f'<div class="section-header">Batch: Run Pending Sites</div>'
        f'<div class="section-sub">Run the agentic engine on all hard-tier pending sites. '
        f'Budget cap stops the run before cost overruns. Progress prints to server logs.</div>',
        unsafe_allow_html=True,
    )

    _ALL_CATS = ["university_incubator", "accelerator", "vc_portfolio",
                 "discovery_aggregator", "government_program", "other"]

    # Pending counts per category
    pending_by_cat: dict[str, int] = {}
    if not health_df.empty and "category" in health_df.columns:
        ws = health_df["worker_state"] if "worker_state" in health_df.columns else pd.Series("pending", index=health_df.index)
        diff = health_df["difficulty"] if "difficulty" in health_df.columns else pd.Series("hard", index=health_df.index)
        pend = health_df[(ws.fillna("pending") != "working") & (diff.fillna("hard") == "hard")]
        for cat, grp in pend.groupby(pend["category"].fillna("other")):
            pending_by_cat[cat] = len(grp)

    total_pending_hard = sum(pending_by_cat.values())
    st.caption(
        f"**{total_pending_hard}** hard-tier pending sites across all categories  ·  "
        + "  ".join(f"{c}: {pending_by_cat.get(c, 0)}" for c in _ALL_CATS if pending_by_cat.get(c, 0))
    )

    with st.form("batch_pending_form"):
        bc1, bc2, bc3 = st.columns([3, 1, 1])
        with bc1:
            sel_cats = st.multiselect(
                "Categories",
                options=_ALL_CATS,
                default=_ALL_CATS,
                label_visibility="collapsed",
            )
        with bc2:
            batch_budget = st.number_input("Budget (USD)", min_value=0.5, max_value=50.0,
                                           value=5.0, step=0.5)
        with bc3:
            batch_max = st.number_input("Max sites", min_value=1, max_value=500,
                                        value=100, step=10)
        run_batch = st.form_submit_button("Run Batch", type="primary", use_container_width=True)

    if run_batch and sel_cats:
        import subprocess
        from pathlib import Path
        project_root = Path(__file__).resolve().parent.parent
        cmd = [
            sys.executable, "scripts/run_batch_by_category.py",
            "--categories", *sel_cats,
            "--max-sites", str(int(batch_max)),
            "--budget", str(batch_budget),
        ]
        st.info(f"Launching batch: `{' '.join(cmd[2:])}`  — output goes to server logs.")
        try:
            proc = subprocess.Popen(
                cmd, cwd=project_root,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            with st.status("Running batch…", expanded=True) as status_widget:
                log_box = st.empty()
                lines: list[str] = []
                assert proc.stdout is not None
                for line in proc.stdout:
                    lines.append(line.rstrip())
                    log_box.code("\n".join(lines[-40:]), language="text")
                proc.wait()
                if proc.returncode == 0:
                    status_widget.update(label="Batch complete ✓", state="complete")
                else:
                    status_widget.update(label=f"Batch exited {proc.returncode}", state="error")
        except Exception as exc:
            st.error(f"Failed to launch batch: {exc}")
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
        if st.button("Discover new sites", width="stretch"):
            from backend.discovery.feed_loader import register_new_sites
            with st.spinner("Loading feeds..."):
                register_new_sites()
            st.success("New sites registered")
            st.cache_data.clear()
    with d2:
        if st.button("Retry zero-result sites", width="stretch"):
            with st.spinner("Retrying..."):
                results = Orchestrator().run_retries(hours=48)
            st.success(f"Retried {len(results)} sites")
            st.cache_data.clear()
    with d3:
        if st.button("Revisit excluded sites", width="stretch"):
            from backend.orchestrator.health import HealthMonitor
            with st.spinner("Reactivating..."):
                HealthMonitor().reactivate_revisit_sites()
            st.success("Excluded sites reactivated")
            st.cache_data.clear()
    with d4:
        if st.button("Run all due sites", width="stretch", type="primary"):
            with st.spinner("Batch scraping..."):
                results = Orchestrator().run_all_due()
            ok = sum(1 for r in results if r.success)
            st.success(f"{ok}/{len(results)} succeeded")
            st.cache_data.clear()


# ── Page: Inventory ──────────────────────────────────────────────────

_DOMAIN_CATEGORIES: dict[str, str] = {
    # University / research incubators
    "berkeley.edu": "university_incubator",
    "skydeck.berkeley.edu": "university_incubator",
    "startx.com": "university_incubator",
    "web.startx.com": "university_incubator",
    "innovationlabs.harvard.edu": "university_incubator",
    "kellercenter.princeton.edu": "university_incubator",
    "alliance.rice.edu": "university_incubator",
    "entrepreneurship.mit.edu": "university_incubator",
    "startups.columbia.edu": "university_incubator",
    # Accelerators
    "500.co": "accelerator",
    "alchemistaccelerator.com": "accelerator",
    "antler.co": "accelerator",
    "astrolabs.com": "accelerator",
    "beondeck.com": "accelerator",
    "brinc.io": "accelerator",
    "capitalfactory.com": "accelerator",
    "dreamit.com": "accelerator",
    "eranyc.com": "accelerator",
    "fi.co": "accelerator",
    "flat6labs.com": "accelerator",
    "gener8tor.com": "accelerator",
    "h-farm.com": "accelerator",
    "hax.co": "accelerator",
    "jfdi.asia": "accelerator",
    "joinef.com": "accelerator",
    "masschallenge.org": "accelerator",
    "neo.com": "accelerator",
    "plugandplaytechcenter.com": "accelerator",
    "rockstart.com": "accelerator",
    "seedcamp.com": "accelerator",
    "seedstars.com": "accelerator",
    "sosv.com": "accelerator",
    "sparklabs.co.kr": "accelerator",
    "startupbootcamp.org": "accelerator",
    "stationf.co": "accelerator",
    "sting.co": "accelerator",
    "surgeahead.com": "accelerator",
    "techstars.com": "accelerator",
    "turn8.co": "accelerator",
    "wayra.com": "accelerator",
    "ycombinator.com": "accelerator",
    # VC portfolios
    "8vc.com": "vc_portfolio",
    "a16z.com": "vc_portfolio",
    "accel.com": "vc_portfolio",
    "allvp.vc": "vc_portfolio",
    "beenext.com": "vc_portfolio",
    "bvp.com": "vc_portfolio",
    "foundersfund.com": "vc_portfolio",
    "generalcatalyst.com": "vc_portfolio",
    "greylock.com": "vc_portfolio",
    "lsvp.com": "vc_portfolio",
    "nea.com": "vc_portfolio",
    "nxtp.vc": "vc_portfolio",
    "pioneerfund.vc": "vc_portfolio",
    "sequoiacap.com": "vc_portfolio",
    "venturesplatform.com": "vc_portfolio",
    "villageglobal.com": "vc_portfolio",
    # Government programs
    "parallel18.com": "government_program",
    "startupchile.org": "government_program",
    # Discovery aggregators
    "ai-startups.org": "discovery_aggregator",
    "aitoolhunt.com": "discovery_aggregator",
    "aitools.fyi": "discovery_aggregator",
    "alternativeto.net": "discovery_aggregator",
    "appsruntheworld.com": "discovery_aggregator",
    "betalist.com": "discovery_aggregator",
    "cbinsights.com": "discovery_aggregator",
    "crozdesk.com": "discovery_aggregator",
    "crunchbase.com": "discovery_aggregator",
    "dang.ai": "discovery_aggregator",
    "dealroom.co": "discovery_aggregator",
    "futurepedia.io": "discovery_aggregator",
    "g2.com": "discovery_aggregator",
    "getapp.com": "discovery_aggregator",
    "insidr.ai": "discovery_aggregator",
    "killerstartups.com": "discovery_aggregator",
    "launched.io": "discovery_aggregator",
    "launchingnext.com": "discovery_aggregator",
    "lmarks.com": "discovery_aggregator",
    "microlaunch.net": "discovery_aggregator",
    "nationalstartupsdirectory.com": "discovery_aggregator",
    "openvc.app": "discovery_aggregator",
    "pitchbook.com": "discovery_aggregator",
    "saasaitools.com": "discovery_aggregator",
    "saasworthy.com": "discovery_aggregator",
    "softwareworld.co": "discovery_aggregator",
    "sourceforge.net": "discovery_aggregator",
    "stackshare.io": "discovery_aggregator",
    "startup88.com": "discovery_aggregator",
    "startupbase.io": "discovery_aggregator",
    "startupguys.net": "discovery_aggregator",
    "startupinspire.com": "discovery_aggregator",
    "startupjohn.com": "discovery_aggregator",
    "startupranking.com": "discovery_aggregator",
    "startups.gallery": "discovery_aggregator",
    "startupstash.com": "discovery_aggregator",
    "startuptabs.com": "discovery_aggregator",
    "thehub.io": "discovery_aggregator",
    "theresanaiforthat.com": "discovery_aggregator",
    "toolify.ai": "discovery_aggregator",
    "topai.tools": "discovery_aggregator",
    "topstartups.io": "discovery_aggregator",
    "tracxn.com": "discovery_aggregator",
    "wellfound.com": "discovery_aggregator",
    "producthunt.com": "discovery_aggregator",
    "f6s.com": "discovery_aggregator",
    "growjo.com": "discovery_aggregator",
    "signal.nfx.com": "discovery_aggregator",
    "techcrunch.com": "discovery_aggregator",
    # VC Portfolios (new)
    "benchmark.com": "vc_portfolio",
    "firstround.com": "vc_portfolio",
    "kleinerperkins.com": "vc_portfolio",
    "indexventures.com": "vc_portfolio",
    "sparkcapital.com": "vc_portfolio",
    "usv.com": "vc_portfolio",
    "insightpartners.com": "vc_portfolio",
    "ivp.com": "vc_portfolio",
    "battery.com": "vc_portfolio",
    "balderton.com": "vc_portfolio",
    "atomico.com": "vc_portfolio",
    "khoslaventures.com": "vc_portfolio",
    "redpoint.com": "vc_portfolio",
    "gv.com": "vc_portfolio",
    "crv.com": "vc_portfolio",
    "felicis.com": "vc_portfolio",
    "initialized.com": "vc_portfolio",
    "svangel.com": "vc_portfolio",
    # University Incubators (new)
    "atdc.org": "university_incubator",
    "zli.umich.edu": "university_incubator",
    "tech.cornell.edu": "university_incubator",
    "polskycenter.uchicago.edu": "university_incubator",
    "entrepreneurship.duke.edu": "university_incubator",
    "engine.xyz": "university_incubator",
    "enterprise.cam.ac.uk": "university_incubator",
    "oxfordsciencesinnovation.com": "university_incubator",
    "imperialenterprises.co.uk": "university_incubator",
    "whartonentrepreneurship.org": "university_incubator",
    # Accelerators (new)
    "angelpad.com": "accelerator",
    "boost.vc": "accelerator",
    "vilcap.com": "accelerator",
    "village-capital.com": "accelerator",
    "rockhealth.com": "accelerator",
    "betaworks.com": "accelerator",
    "indiebio.co": "accelerator",
    "mattervc.com": "accelerator",
    "launchaccelerator.co": "accelerator",
    # Government Programs (new)
    "sbir.gov": "government_program",
    "eic.ec.europa.eu": "government_program",
    "enterprise.gov.sg": "government_program",
    "startupindia.gov.in": "government_program",
    "nzte.govt.nz": "government_program",
    # International VCs — Europe
    "earlybird.com": "vc_portfolio",
    "northzone.com": "vc_portfolio",
    "partech.vc": "vc_portfolio",
    "speedinvest.com": "vc_portfolio",
    "localglobe.vc": "vc_portfolio",
    "creandum.com": "vc_portfolio",
    "targetglobal.vc": "vc_portfolio",
    # International VCs — India
    "nexusvp.com": "vc_portfolio",
    "kalaari.com": "vc_portfolio",
    "blume.vc": "vc_portfolio",
    # International VCs — Israel
    "tlvpartners.com": "vc_portfolio",
    "jvp.co.il": "vc_portfolio",
    "lool.vc": "vc_portfolio",
    # International VCs — APAC & Americas
    "blackbird.vc": "vc_portfolio",
    "startmate.com": "accelerator",
    "marsdd.com": "university_incubator",
    "cdl.utoronto.ca": "university_incubator",
    # Additional US VCs
    "lightspeedvp.com": "vc_portfolio",
    "foundation.capital": "vc_portfolio",
    "venrock.com": "vc_portfolio",
    # International VCs — Germany
    "hv.capital": "vc_portfolio",
}

_EASY_DOMAINS = {
    # Original easy scrapers
    "ycombinator.com", "techstars.com", "alchemistaccelerator.com",
    "seedcamp.com", "capitalfactory.com", "eranyc.com", "villageglobal.com",
    "antler.co", "innovationlabs.harvard.edu", "web.startx.com",
    "kellercenter.princeton.edu", "alliance.rice.edu", "joinef.com",
    "skydeck.berkeley.edu", "startups.columbia.edu", "entrepreneurship.mit.edu",
    "crunchbase.com",
    # VC portfolios added (session 2)
    "sequoiacap.com", "greylock.com", "balderton.com",
    # VC portfolios added (session 3)
    "foundersfund.com", "usv.com", "bvp.com", "generalcatalyst.com",
}

_CATEGORY_LABELS = {
    "university_incubator": "University / Incubator",
    "accelerator":          "Accelerator",
    "vc_portfolio":         "VC Portfolio",
    "government_program":   "Government Program",
    "discovery_aggregator": "Discovery Aggregator",
    "other":                "Other",
}

_CATEGORY_ORDER = [
    "university_incubator", "accelerator", "vc_portfolio",
    "government_program", "discovery_aggregator", "other",
]

_CAT_COLORS = {
    "university_incubator": "#286dc0",
    "accelerator":          "#1aab68",
    "vc_portfolio":         "#a855f7",
    "government_program":   "#d97706",
    "discovery_aggregator": "#06b6d4",
    "other":                "#94a3b8",
}


@st.cache_data(ttl=300)
def _load_yaml_inventory() -> pd.DataFrame:
    yaml_dir = Path(__file__).resolve().parent.parent / "data" / "scrape_instructions"
    rows = []
    seen = set()
    try:
        import yaml as _yaml
        for f in sorted(yaml_dir.glob("*.yaml")):
            d = _yaml.safe_load(f.read_text())
            domain = d.get("domain", f.stem)
            ls = d.get("last_success") or {}
            rc = ls.get("record_count", 0) if ls else 0
            seen.add(domain)
            rows.append({
                "domain": domain, "record_count": rc, "source": "yaml",
                "probe_result": d.get("probe_result"),
            })
    except Exception:
        pass
    # registry-only entries (have scraper but no YAML)
    for d in _EASY_DOMAINS:
        if d not in seen:
            rows.append({"domain": d, "record_count": -1, "source": "registry", "probe_result": None})
    df = pd.DataFrame(rows)
    df["category"] = df["domain"].map(_DOMAIN_CATEGORIES).fillna("other")

    def _scrape_tier(r):
        if r["domain"] in _EASY_DOMAINS:
            return "easy"
        if r["record_count"] > 5:
            return "agentic"
        if r["record_count"] > 0:
            return "challenging"
        if r.get("probe_result") == "easy_candidate":
            return "agentic"  # accessible but not yet run
        return "challenging"

    df["scrapeability"] = df.apply(_scrape_tier, axis=1)
    return df


def page_inventory():
    st.markdown(
        '<div class="section-header">Site Inventory</div>'
        '<div class="section-sub">Every website we have analysed — categorised by type '
        'and rated for scrapeability.</div>',
        unsafe_allow_html=True,
    )

    inv = _load_yaml_inventory()
    total = len(inv)
    easy = int((inv["scrapeability"] == "easy").sum())
    agentic = int((inv["scrapeability"] == "agentic").sum())
    challenging = int((inv["scrapeability"] == "challenging").sum())

    # ── Top metrics ────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total sites analysed", total)
    m2.metric("Easy scraper", easy, help="Dedicated scraper — reliable, high-volume")
    m3.metric("AI agent worked", agentic, help="Agentic engine extracted >5 records")
    m4.metric("Challenging", challenging, help="AI struggled — JS-heavy or paywalled")

    st.markdown("<br/>", unsafe_allow_html=True)

    # ── By-category bar chart ──────────────────────────────────────────
    cat_counts = (
        inv.groupby(["category", "scrapeability"])
        .size()
        .reset_index(name="count")
    )
    cat_counts["category_label"] = cat_counts["category"].map(_CATEGORY_LABELS)

    scrape_colors = {"easy": "#1aab68", "agentic": "#286dc0", "challenging": "#dc2626"}

    fig_cat = px.bar(
        cat_counts,
        x="category_label",
        y="count",
        color="scrapeability",
        color_discrete_map=scrape_colors,
        category_orders={
            "category_label": [_CATEGORY_LABELS[c] for c in _CATEGORY_ORDER],
            "scrapeability": ["easy", "agentic", "challenging"],
        },
        barmode="stack",
        labels={"category_label": "", "count": "Sites", "scrapeability": ""},
        title="Sites by Type & Scrapeability",
    )
    fig_cat.update_layout(**_layout(height=320))
    st.plotly_chart(fig_cat, use_container_width=True)

    # ── Scrapeability donut ────────────────────────────────────────────
    col_donut, col_table = st.columns([1, 2])
    with col_donut:
        fig_d = go.Figure(go.Pie(
            labels=["Easy scraper", "AI agent worked", "Challenging"],
            values=[easy, agentic, challenging],
            marker_colors=[scrape_colors["easy"], scrape_colors["agentic"], scrape_colors["challenging"]],
            hole=0.55,
            textinfo="label+value",
            hovertemplate="%{label}: %{value}<extra></extra>",
        ))
        fig_d.update_layout(**_layout(height=280, title_text="Scrapeability split"))
        st.plotly_chart(fig_d, use_container_width=True)

    # ── Challenging sites table ────────────────────────────────────────
    with col_table:
        st.markdown("**Challenging sites — AI struggled**")
        hard = inv[inv["scrapeability"] == "challenging"][["domain", "category", "record_count"]].copy()
        hard["category"] = hard["category"].map(_CATEGORY_LABELS)
        hard = hard.rename(columns={
            "domain": "Domain",
            "category": "Type",
            "record_count": "AI records extracted",
        }).sort_values("Domain")
        st.dataframe(hard, hide_index=True, use_container_width=True, height=260)

    st.markdown("<br/>", unsafe_allow_html=True)

    # ── Full site list ─────────────────────────────────────────────────
    st.markdown("### All sites")
    badge_map = {"easy": "✓ easy", "agentic": "~ AI", "challenging": "✗ hard"}
    display = inv[["domain", "category", "scrapeability", "record_count"]].copy()
    display["type"] = display["category"].map(_CATEGORY_LABELS)
    display["scraper"] = display["scrapeability"].map(badge_map)
    display["AI records"] = display["record_count"].apply(
        lambda x: "—" if x < 0 else str(x)
    )
    display = display[["domain", "type", "scraper", "AI records"]].sort_values(
        ["type", "domain"]
    )
    st.dataframe(display, hide_index=True, use_container_width=True, height=480)


def page_ai_analysis(df: pd.DataFrame):
    st.markdown(
        '<div class="section-header">AI Startup Analysis</div>'
        '<div class="section-sub">Classification of all tracked companies — AI-focused vs. non-AI, '
        'broken down by source, geography, and discovery date.</div>',
        unsafe_allow_html=True,
    )

    if df.empty:
        st.info("No company data available.")
        return

    # Align with overview: is_ai = score >= 0.3 OR any ai_tag present
    # Use apply() to handle both list and string storage ([] is falsy but [] != "" is True)
    has_tags = df["ai_tags"].apply(lambda x: bool(x)) if "ai_tags" in df.columns else pd.Series(False, index=df.index)
    is_ai = ((df["ai_score"].fillna(0) >= 0.3) | has_tags) if "ai_score" in df.columns else has_tags
    df = df.copy()
    df["is_ai"] = is_ai

    total = len(df)
    ai_cos = int(is_ai.sum())
    non_ai = total - ai_cos
    ai_pct = round(ai_cos * 100.0 / total, 1) if total else 0
    unclassified = int(df["ai_score"].isna().sum()) if "ai_score" in df.columns else 0

    # ── Headline metrics ─────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total companies", f"{total:,}")
    m2.metric("AI companies", f"{ai_cos:,}", help="ai_score ≥ 0.3 or has AI tag")
    m3.metric("AI share", f"{ai_pct}%")
    m4.metric("Unclassified", f"{unclassified:,}", help="ai_score is NULL")

    st.markdown("<br/>", unsafe_allow_html=True)

    # ── AI % by source program ───────────────────────────────────────
    if "incubator_source" in df.columns:
        src = df.copy()
        src["incubator_source"] = src["incubator_source"].fillna("(no source)")
        prog = (
            src.groupby("incubator_source")
            .agg(
                total=("id", "size"),
                ai_count=("is_ai", "sum"),
            )
            .reset_index()
        )
        prog = prog[prog["total"] >= 5].copy()
        prog["ai_pct"] = (prog["ai_count"] / prog["total"] * 100).round(1)
        prog = prog.sort_values("ai_count", ascending=True).tail(20)

        fig_src = px.bar(
            prog,
            x="ai_count",
            y="incubator_source",
            orientation="h",
            color="ai_pct",
            color_continuous_scale=[[0, "#cce3ff"], [1, "#286dc0"]],
            labels={"ai_count": "AI Companies", "incubator_source": "", "ai_pct": "AI %"},
            title="AI Companies by Source",
            text="ai_count",
        )
        fig_src.update_traces(textposition="outside")
        fig_src.update_layout(**_layout(height=max(300, len(prog) * 26 + 80)))
        st.plotly_chart(fig_src, use_container_width=True)

    # ── Country distribution ─────────────────────────────────────────
    st.markdown("<br/>", unsafe_allow_html=True)
    col_left, col_right = st.columns([3, 2])

    with col_left:
        if "country" in df.columns:
            ai_df = df[df["is_ai"]].copy()
            # Normalise messy country strings: "USA", "United States", "US" → "United States"
            norm = {"USA": "United States", "US": "United States", "usa": "United States",
                    "U.S.A.": "United States", "U.S.": "United States"}
            ai_df["country_norm"] = ai_df["country"].replace(norm)
            # Strip trailing semicolon fields like "USA; Remote"
            ai_df["country_norm"] = ai_df["country_norm"].str.split(";").str[0].str.strip()

            ctry = (
                ai_df[ai_df["country_norm"].notna()]
                .groupby("country_norm")
                .size()
                .reset_index(name="count")
                .sort_values("count", ascending=False)
                .head(15)
            )
            fig_ctry = px.bar(
                ctry,
                x="count",
                y="country_norm",
                orientation="h",
                color="count",
                color_continuous_scale=[[0, "#cce3ff"], [1, "#00356b"]],
                labels={"count": "AI Startups", "country_norm": ""},
                title="AI Startups by Country (top 15)",
                text="count",
            )
            fig_ctry.update_traces(textposition="outside")
            fig_ctry.update_layout(**_layout(height=440))
            st.plotly_chart(fig_ctry, use_container_width=True)

    with col_right:
        # AI vs non-AI donut
        fig_d = go.Figure(go.Pie(
            labels=["AI-focused", "Non-AI"],
            values=[ai_cos, non_ai],
            marker_colors=["#286dc0", "#e3e7ee"],
            hole=0.55,
            textinfo="label+percent",
            hovertemplate="%{label}: %{value:,}<extra></extra>",
        ))
        fig_d.update_layout(**_layout(height=280, title_text="AI vs. Non-AI"))
        st.plotly_chart(fig_d, use_container_width=True)

        # Score histogram
        if "ai_score" in df.columns:
            score_df = df[df["ai_score"].notna()]
            fig_hist = px.histogram(
                score_df,
                x="ai_score",
                nbins=20,
                color_discrete_sequence=["#286dc0"],
                labels={"ai_score": "AI Score", "count": "Companies"},
                title="AI Score Distribution",
            )
            fig_hist.add_vline(x=0.3, line_dash="dash", line_color=RED,
                               annotation_text="AI threshold (0.3)")
            fig_hist.update_layout(**_layout(height=240))
            st.plotly_chart(fig_hist, use_container_width=True)

    # ── Discovery over time ──────────────────────────────────────────
    st.markdown("<br/>", unsafe_allow_html=True)
    if "first_seen_at" in df.columns and "ai_score" in df.columns:
        time_df = df[df["first_seen_at"].notna()].copy()
        time_df["month"] = pd.to_datetime(time_df["first_seen_at"]).dt.to_period("M").astype(str)
        monthly = (
            time_df.groupby("month")
            .agg(
                total=("id", "size"),
                ai=("is_ai", "sum"),
            )
            .reset_index()
            .tail(24)
        )
        fig_time = go.Figure()
        fig_time.add_bar(x=monthly["month"], y=monthly["total"], name="All", marker_color="#e3e7ee")
        fig_time.add_bar(x=monthly["month"], y=monthly["ai"], name="AI", marker_color="#286dc0")
        fig_time.update_layout(
            barmode="overlay",
            title_text="Monthly Company Discovery (AI in blue, all in grey)",
            xaxis_title="",
            yaxis_title="Companies",
            **_layout(height=280),
        )
        st.plotly_chart(fig_time, use_container_width=True)

    # ── Recently discovered AI companies ────────────────────────────
    st.markdown("<br/>", unsafe_allow_html=True)
    st.markdown("### Recently Discovered AI Companies")
    if "first_seen_at" in df.columns:
        cols = [c for c in ["name", "country", "description", "ai_score", "incubator_source", "first_seen_at"] if c in df.columns]
        recent = (
            df[df["is_ai"]]
            .sort_values("first_seen_at", ascending=False)
            .head(30)
            [cols]
            .copy()
        )
        if "ai_score" in recent.columns:
            recent["ai_score"] = recent["ai_score"].round(2)
        recent["first_seen_at"] = pd.to_datetime(recent["first_seen_at"]).dt.date
        col_rename = {"name": "Name", "country": "Country", "description": "Description",
                      "ai_score": "AI Score", "incubator_source": "Source", "first_seen_at": "First Seen"}
        recent.rename(columns=col_rename, inplace=True)
        st.dataframe(recent, hide_index=True, use_container_width=True, height=480)


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

    tab_overview, tab_ai, tab_github, tab_trends, tab_health, tab_inventory, tab_scraper = st.tabs([
        "Overview", "AI Analysis", "GitHub Discovery", "Trends", "Pipeline Health", "Inventory", "Scraper",
    ])

    with tab_overview:
        page_overview(scraper_df, health_df)
    with tab_ai:
        page_ai_analysis(scraper_df)
    with tab_github:
        page_github(github_df, github_df_all)
    with tab_trends:
        page_trends(scraper_df)
    with tab_health:
        page_health(health_df, runs_df)
    with tab_inventory:
        page_inventory()
    with tab_scraper:
        page_scraper()


if __name__ == "__main__":
    main()
