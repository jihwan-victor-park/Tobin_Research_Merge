
"""
AI Startup Tracker - Pipeline Dashboard

Full-page layout with top navigation bar, US geography map,
company table, trends, pipeline health, and scraper controls.
No sidebar — everything lives in the main content area.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
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
from backend.utils.ai_filter import ai_filter_sql
from backend.utils.country import normalize_country, GLOBE_COUNTRIES
from backend.utils.denylist import BIG_TECH_DENYLIST

load_dotenv()

# ── Design tokens — modern data platform ─────────────────────────────
# Public-facing research platform: near-white ground, white cards with
# hairline borders and 8–10px radii, one grotesk (Inter) for everything,
# tabular numerals for figures, a single blue accent. Navy survives only
# as the brand ink (logo lockup, primary buttons, active nav).
YALE_BLUE = "#14325e"   # brand ink: lockup, primary buttons, active nav
YALE_MID = "#1d4379"
YALE_LIGHT = "#2a5c9e"
ACCENT = "#2a78d6"      # primary data series + interactive accent (validated)
BG = "#fafbfc"          # app ground
BG_OFF = "#f2f4f7"      # wells, filter strips, table heads
BG_CARD = "#ffffff"     # cards, inputs, chart surfaces
BORDER = "#e4e8ee"      # card + input hairline
BORDER_LIGHT = "#eef1f5"  # row separators, chart grids
TXT = "#101828"         # primary ink
TXT2 = "#475467"        # secondary ink
TXT3 = "#98a2b3"        # muted ink / captions
GREEN = "#0e9f6e"       # status: working / healthy
AMBER = "#d97706"       # status: pending / degraded
RED = "#dc2626"         # status: broken / failed

MONO = "'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace"

# Chart palette (dataviz reference slots, validated on light surface:
# lightness band, chroma, CVD ΔE 73.6 worst-adjacent; aqua + yellow are
# sub-3:1 on white → always pair with direct labels or a table view):
#   CAT        — blue / aqua / yellow / violet, fixed order, never cycled
#   BLUE_RAMP  — single-hue ordinal ramp (light→dark), ordered series
#   SEQ_SCALE  — continuous sequential scale (choropleth, heatmaps)
#   GRAY_CTX   — context / "everything else" marks (never carries identity)
BLUE_RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab"]
CAT = ["#2a78d6", "#1baf7a", "#eda100", "#4a3aa7"]
TEAL = CAT[1]
GOLD = CAT[2]
SEQ_SCALE = [[0, "#e7f0fc"], [0.5, "#5598e7"], [1, "#184f95"]]
GRAY_CTX = "#d9dee5"

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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    html, body, .stApp {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        -webkit-font-smoothing: antialiased;
        text-rendering: optimizeLegibility;
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

    /* Hide streamlit chrome */
    #MainMenu, footer {{ visibility: hidden; }}
    header {{ display: none !important; }}

    .main, [data-testid="stAppViewContainer"],
    [data-testid="stMain"] {{ background: {BG} !important; }}
    /* Centered app column */
    .block-container {{
        padding-top: 0 !important;
        padding-bottom: 4rem;
        max-width: 1280px !important;
        margin: 0 auto;
        padding-left: 32px !important;
        padding-right: 32px !important;
    }}
    .block-container > div[data-testid="stVerticalBlock"] {{
        gap: 0 !important;
    }}

    /* Sidebar retired — the top bar is the nav */
    section[data-testid="stSidebar"],
    [data-testid="stSidebarCollapsedControl"] {{ display: none !important; }}

    /* ── Header row: brand left, nav right, one hairline under both ── */
    .st-key-header {{
        padding: 16px 0 0 0;
    }}
    .st-key-header [data-testid="stHorizontalBlock"] {{
        align-items: center;
    }}
    .brand {{
        display: flex;
        align-items: center;
        gap: 11px;
        white-space: nowrap;
    }}
    .brand-mark {{
        width: 32px; height: 32px;
        border-radius: 9px;
        background: linear-gradient(135deg, {YALE_BLUE} 0%, {YALE_MID} 100%);
        color: #ffffff;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: 0.02em;
        flex-shrink: 0;
        box-shadow: 0 1px 2px rgba(16,24,40,0.12);
    }}
    .brand-text {{ line-height: 1.15; }}
    .brand-name {{
        display: block;
        font-size: 0.98rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: {TXT};
    }}
    .brand-sub {{
        display: block;
        font-size: 0.66rem;
        font-weight: 500;
        letter-spacing: 0.04em;
        color: {TXT3};
        margin-top: 1px;
    }}
    .header-rule {{
        border-bottom: 1px solid {BORDER};
        margin: 12px 0 0 0;
    }}

    /* ── Primary nav: quiet text links, active gets a soft pill ── */
    .st-key-lnav [role="radiogroup"] {{
        display: flex;
        flex-wrap: wrap;
        justify-content: flex-end;
        gap: 2px;
        row-gap: 4px;
    }}
    .st-key-lnav [role="radiogroup"] label {{
        margin: 0 !important;
        padding: 7px 13px;
        border-radius: 8px;
        background: transparent !important;
        transition: background 0.12s;
        position: relative;
    }}
    /* hairline divider before the last item (Internal) */
    .st-key-lnav [role="radiogroup"] label:last-child {{
        margin-left: 16px !important;
    }}
    .st-key-lnav [role="radiogroup"] label:last-child::before {{
        content: "";
        position: absolute;
        left: -9px;
        top: 22%;
        height: 56%;
        border-left: 1px solid {BORDER};
    }}
    .st-key-lnav [role="radiogroup"] label > div:first-child {{
        display: none;
    }}
    .st-key-lnav [role="radiogroup"] label p {{
        font-size: 0.84rem;
        font-weight: 500;
        color: {TXT2};
        white-space: nowrap;
        line-height: 1.2;
    }}
    .st-key-lnav [role="radiogroup"] label:hover {{ background: {BG_OFF} !important; }}
    .st-key-lnav [role="radiogroup"] label:hover p {{ color: {TXT}; }}
    .st-key-lnav [role="radiogroup"] label:has(input:checked) {{
        background: {BG_OFF} !important;
    }}
    .st-key-lnav [role="radiogroup"] label:has(input:checked) p {{
        color: {YALE_BLUE};
        font-weight: 650;
    }}

    /* Secondary nav (internal pages) — quieter pills */
    .st-key-subnav [role="radiogroup"] {{
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        padding: 12px 0 0 0;
    }}
    .st-key-subnav [role="radiogroup"] label {{
        margin: 0 !important;
        padding: 4px 11px;
        border-radius: 999px;
        background: transparent !important;
        border: 1px solid transparent;
    }}
    .st-key-subnav [role="radiogroup"] label > div:first-child {{ display: none; }}
    .st-key-subnav [role="radiogroup"] label p {{
        font-size: 0.76rem;
        font-weight: 500;
        color: {TXT2};
        white-space: nowrap;
    }}
    .st-key-subnav [role="radiogroup"] label:has(input:checked) {{
        background: {BG_OFF} !important;
        border-color: {BORDER};
    }}
    .st-key-subnav [role="radiogroup"] label:has(input:checked) p {{
        color: {TXT};
        font-weight: 600;
    }}

    /* Page content wrapper */
    .st-key-page {{
        padding: 26px 0 0 0;
    }}

    /* ── Inner tabs — segmented underline ── */
    .stTabs {{ margin-top: 0; }}
    .stTabs [data-baseweb="tab-list"] {{
        gap: 18px;
        background: transparent;
        border-bottom: 1px solid {BORDER};
        padding: 0;
    }}
    .stTabs [data-baseweb="tab"] {{
        border-radius: 0;
        padding: 9px 2px;
        font-size: 0.82rem;
        font-weight: 500;
        color: {TXT2};
        background: transparent;
        border-bottom: 2px solid transparent;
        margin-bottom: -1px;
        white-space: nowrap;
    }}
    .stTabs [data-baseweb="tab"]:hover {{
        color: {TXT};
    }}
    .stTabs [data-baseweb="tab-highlight"],
    .stTabs [data-baseweb="tab-border"] {{ display: none; }}
    .stTabs [aria-selected="true"] {{
        color: {TXT} !important;
        background: transparent !important;
        border-bottom: 2px solid {ACCENT} !important;
        font-weight: 600;
    }}
    .stTabs [data-baseweb="tab-panel"] {{
        padding: 1rem 0 0 0;
    }}

    /* ── Headings ── */
    h1 {{ color: {TXT}; font-weight: 700; font-size: 1.4rem !important;
         letter-spacing: -0.02em; margin-bottom: 0.2rem !important; }}
    h2 {{ color: {TXT}; font-weight: 600; font-size: 1.08rem !important;
         letter-spacing: -0.01em; }}
    h3 {{ color: {TXT2}; font-weight: 600; font-size: 0.78rem !important;
         text-transform: uppercase; letter-spacing: 0.06em; }}
    p {{ color: {TXT2}; font-size: 0.87rem; }}
    .stCaption, [data-testid="stCaptionContainer"] {{ color: {TXT3}; font-size: 0.76rem; }}

    .section-header {{
        color: {TXT};
        font-size: 1.06rem;
        font-weight: 650;
        letter-spacing: -0.015em;
        margin: 0 0 3px 0;
    }}
    .section-sub {{
        color: {TXT3};
        font-size: 0.8rem;
        line-height: 1.5;
        margin: 0 0 16px 0;
    }}
    .eyebrow {{
        font-size: 0.66rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: {ACCENT};
        margin: 0 0 6px 0;
    }}

    /* ── Hero: headline left, lede right, full width ── */
    .hero-eyebrow {{
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.68rem;
        font-weight: 600;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: {TXT3};
        margin: 0 0 14px 0;
        font-variant-numeric: tabular-nums;
    }}
    .hero-eyebrow .live-dot {{
        width: 7px; height: 7px;
        border-radius: 999px;
        background: {GREEN};
        box-shadow: 0 0 0 3px rgba(14,159,110,0.15);
        flex-shrink: 0;
    }}
    .hero-title {{
        font-size: clamp(1.6rem, 3vw, 2.15rem);
        font-weight: 750;
        letter-spacing: -0.03em;
        line-height: 1.12;
        color: {TXT};
        text-wrap: balance;
        margin: 0;
    }}
    .hero-lede {{
        font-size: 0.95rem;
        line-height: 1.65;
        color: {TXT2};
        margin: 0;
    }}
    .hero-lede b {{ color: {TXT}; font-weight: 600; }}

    /* ── Stat band: one connected strip, divided columns ── */
    .statband {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        background: {BG_CARD};
        border: 1px solid {BORDER};
        border-radius: 12px;
        box-shadow: 0 1px 2px rgba(16,24,40,0.04);
        overflow: hidden;
    }}
    .statband .stat {{
        padding: 18px 22px 16px 22px;
    }}
    .statband .stat + .stat {{
        border-left: 1px solid {BORDER_LIGHT};
    }}
    .statband .stat-label {{
        display: block;
        font-size: 0.64rem;
        font-weight: 650;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: {TXT3};
        margin-bottom: 7px;
    }}
    .statband .stat-value {{
        display: block;
        font-size: 1.72rem;
        font-weight: 700;
        letter-spacing: -0.025em;
        line-height: 1.1;
        color: {TXT};
        font-variant-numeric: tabular-nums;
    }}
    .statband .stat-sub {{
        display: block;
        font-size: 0.72rem;
        color: {TXT3};
        margin-top: 5px;
        font-variant-numeric: tabular-nums;
    }}
    .statband .stat-sub b {{ color: {ACCENT}; font-weight: 650; }}
    @media (max-width: 900px) {{
        .statband {{ grid-template-columns: repeat(2, 1fr); }}
        .statband .stat:nth-child(3) {{ border-left: none; }}
        .statband .stat:nth-child(n+3) {{ border-top: 1px solid {BORDER_LIGHT}; }}
    }}

    /* ── KPI cards ── */
    [data-testid="stMetric"] {{
        background: {BG_CARD};
        padding: 16px 18px 14px 18px;
        border-radius: 10px;
        border: 1px solid {BORDER};
        box-shadow: 0 1px 2px rgba(16,24,40,0.04);
    }}
    [data-testid="stMetricValue"] {{
        font-size: 1.55rem;
        font-weight: 700;
        color: {TXT};
        font-variant-numeric: tabular-nums;
        letter-spacing: -0.02em;
        line-height: 1.15;
    }}
    [data-testid="stMetricLabel"] {{
        text-transform: uppercase;
        letter-spacing: 0.07em;
    }}
    [data-testid="stMetricLabel"] p {{
        font-size: 0.64rem !important;
        color: {TXT3} !important;
        font-weight: 600;
    }}
    [data-testid="stMetricDelta"] {{
        font-size: 0.74rem;
        font-variant-numeric: tabular-nums;
    }}

    /* ── Cards ── */
    .card {{
        background: {BG_CARD};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 20px 24px;
        box-shadow: 0 1px 2px rgba(16,24,40,0.04);
    }}
    .card-muted {{
        background: {BG_OFF};
        border: 1px solid {BORDER_LIGHT};
        border-radius: 10px;
        padding: 20px 24px;
    }}

    /* ── Filter bar ── */
    .filter-bar {{
        background: {BG_OFF};
        border: 1px solid {BORDER_LIGHT};
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 16px;
    }}
    .filter-bar-label {{
        color: {TXT3};
        font-size: 0.66rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 6px;
    }}

    /* ── Inputs ── */
    .stTextInput input, .stNumberInput input,
    .stSelectbox > div > div, .stMultiSelect > div > div {{
        background: {BG_CARD} !important;
        border: 1px solid {BORDER} !important;
        color: {TXT} !important;
        font-size: 0.84rem !important;
        border-radius: 8px !important;
    }}
    .stTextInput input::placeholder {{ color: {TXT3} !important; }}
    .stTextInput input:focus {{
        border-color: {ACCENT} !important;
        box-shadow: 0 0 0 3px rgba(42,120,214,0.12) !important;
    }}
    .stCheckbox label {{ color: {TXT2} !important; font-size: 0.82rem !important; }}
    .stMultiSelect span[data-baseweb="tag"] {{
        background: #e7f0fc !important;
        color: {YALE_BLUE} !important;
        border-radius: 6px !important;
        font-size: 0.76rem !important;
    }}
    .stMultiSelect span[data-baseweb="tag"] span {{ color: {YALE_BLUE} !important; }}
    label[data-testid="stWidgetLabel"] p {{
        font-size: 0.72rem !important;
        font-weight: 500;
        color: {TXT2} !important;
    }}

    /* ── Data table ── */
    [data-testid="stDataFrame"] {{
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid {BORDER};
        box-shadow: 0 1px 2px rgba(16,24,40,0.04);
    }}

    /* ── Buttons ── */
    .stButton > button {{
        border-radius: 8px;
        font-size: 0.82rem;
        font-weight: 500;
        border: 1px solid {BORDER};
        background: {BG_CARD};
        color: {TXT};
        transition: border-color 0.15s, color 0.15s, box-shadow 0.15s;
    }}
    .stButton > button:hover {{
        border-color: {ACCENT};
        color: {YALE_BLUE};
        box-shadow: 0 1px 4px rgba(42,120,214,0.15);
    }}
    .stButton > button[kind="primary"] {{
        background: {YALE_BLUE} !important;
        border-color: {YALE_BLUE} !important;
        color: #ffffff !important;
    }}
    .stButton > button[kind="primary"]:hover {{
        background: {YALE_MID} !important;
    }}

    .stDownloadButton > button {{
        background: {BG_CARD} !important;
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
        background: {BG_CARD};
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
        background: {BG_CARD};
        overflow: hidden;
    }}
    [data-testid="stExpander"] summary {{
        font-size: 0.82rem;
        padding: 10px 14px !important;
        color: {TXT};
        background: {BG_CARD};
    }}
    [data-testid="stExpander"] summary:hover {{
        background: {BG_OFF};
    }}

    hr {{ border: none; border-top: 1px solid {BORDER_LIGHT}; margin: 24px 0 20px 0; }}
</style>
""", unsafe_allow_html=True)


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
            c.cb_ai_tagged, c.ai_mentioned, c.llm_ai_verified, c.founded_year, c.categories,
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

        # Inclusive "is AI" flag: CB's own AI taxonomy OR model score OR any AI tag.
        has_tags = df["ai_tags"].apply(lambda x: isinstance(x, list) and len(x) > 0)
        cb_tagged = df["cb_ai_tagged"].fillna(False).astype(bool) if "cb_ai_tagged" in df.columns else pd.Series(False, index=df.index)
        ai_mentioned = df["ai_mentioned"].fillna(False).astype(bool) if "ai_mentioned" in df.columns else pd.Series(False, index=df.index)
        llm_verified = df["llm_ai_verified"].fillna(False).astype(bool) if "llm_ai_verified" in df.columns else pd.Series(False, index=df.index)
        df["is_ai"] = cb_tagged | (df["ai_score"].fillna(0) >= 0.3) | has_tags | ai_mentioned | llm_verified
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


@st.cache_data(ttl=120)
def _load_overview_stats() -> dict:
    """Live aggregate stats for the Overview metric cards."""
    engine = get_engine()
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM companies")).scalar() or 0
        ai = conn.execute(text(
            f"SELECT COUNT(*) FROM companies WHERE {ai_filter_sql()}"
        )).scalar() or 0
        funded = conn.execute(text(
            "SELECT COUNT(DISTINCT company_id) FROM funding_signals"
        )).scalar() or 0
        countries = conn.execute(text(
            "SELECT COUNT(DISTINCT country) FROM companies "
            "WHERE country IS NOT NULL AND country != ''"
        )).scalar() or 0
    return {"total": total, "ai": ai, "funded": funded, "countries": countries}


@st.cache_data(ttl=300)
def _load_ai_adoption_curve() -> pd.DataFrame:
    """Aggregate AI adoption by founding year across all companies."""
    engine = get_engine()
    query = f"""
        SELECT
            founded_year,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE {ai_filter_sql()}) AS ai
        FROM companies
        WHERE founded_year BETWEEN 2000 AND 2026
        GROUP BY founded_year
        ORDER BY founded_year
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query)).mappings().all()
    df = pd.DataFrame(rows)
    if not df.empty:
        df["ai_pct"] = (df["ai"] / df["total"] * 100).round(1)
    return df


@st.cache_data(ttl=300)
def _load_country_ai_stats(min_companies: int = 100) -> pd.DataFrame:
    """Per-country totals and AI counts across all companies."""
    engine = get_engine()
    query = f"""
        SELECT country,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE {ai_filter_sql()}) AS ai
        FROM companies
        WHERE country IS NOT NULL AND country != ''
        GROUP BY country
        HAVING COUNT(*) >= {min_companies}
        ORDER BY ai DESC
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query)).mappings().all()
    df = pd.DataFrame(rows)
    if not df.empty:
        df["ai_pct"] = (df["ai"] / df["total"] * 100).round(1)
    return df


@st.cache_data(ttl=300)
def _load_source_ai_stats() -> pd.DataFrame:
    """Per-source AI counts across all companies (full DB)."""
    engine = get_engine()
    query = f"""
        SELECT
            COALESCE(incubator_source::text, '(no source)') AS incubator_source,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE {ai_filter_sql()}) AS ai_count
        FROM companies
        GROUP BY incubator_source
        HAVING COUNT(*) >= 5
        ORDER BY ai_count DESC
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query)).mappings().all()
    df = pd.DataFrame(rows)
    if not df.empty:
        df["ai_pct"] = (df["ai_count"] / df["total"] * 100).round(1)
    return df


@st.cache_data(ttl=300)
def _load_country_year_matrix(top_n: int = 25) -> pd.DataFrame:
    """AI% per country per founding year for the top N countries by total size."""
    engine = get_engine()
    query = f"""
        WITH top_countries AS (
            SELECT country FROM companies
            WHERE country IS NOT NULL AND country != ''
            GROUP BY country ORDER BY COUNT(*) DESC LIMIT {top_n}
        )
        SELECT c.country, c.founded_year,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE {ai_filter_sql("c")}) AS ai
        FROM companies c
        JOIN top_countries tc ON c.country = tc.country
        WHERE c.founded_year BETWEEN 2010 AND 2026
        GROUP BY c.country, c.founded_year
        ORDER BY c.country, c.founded_year
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query)).mappings().all()
    df = pd.DataFrame(rows)
    if not df.empty:
        df["ai_pct"] = (df["ai"] / df["total"] * 100).round(1)
    return df


@st.cache_data(ttl=300)
def _load_research_export() -> pd.DataFrame:
    """All AI companies per the canonical filter (see backend/utils/ai_filter.py) with key research fields."""
    engine = get_engine()
    query = f"""
        SELECT name, domain, country, city, founded_year,
               ai_score, cb_ai_tagged, ai_mentioned, llm_ai_verified, total_raised,
               team_size, stage, categories, verification_status
        FROM companies
        WHERE {ai_filter_sql()}
        ORDER BY founded_year DESC NULLS LAST, country
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query)).mappings().all()
    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def _load_company_filter_options() -> tuple:
    """Distinct countries, stages, and verticals for the Company Explorer filters."""
    engine = get_engine()
    with engine.connect() as conn:
        countries = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT country FROM companies WHERE country IS NOT NULL ORDER BY country"
        )).all()]
        stages = [r[0] for r in conn.execute(text(
            "SELECT stage FROM companies WHERE stage IS NOT NULL GROUP BY stage ORDER BY COUNT(*) DESC"
        )).all()]
        verticals = sorted({r[0] for r in conn.execute(text(
            "SELECT DISTINCT unnest(categories) AS v FROM companies WHERE categories IS NOT NULL"
        )).all()})
    return countries, stages, verticals


@st.cache_data(ttl=300)
def _load_filtered_companies(
    countries_t: tuple,
    year_min: int,
    year_max: int,
    stages_t: tuple,
    min_raised_m: float,
    ai_only: bool,
    verticals_t: tuple,
    limit: int = 1000,
) -> pd.DataFrame:
    engine = get_engine()
    conditions = ["founded_year BETWEEN :year_min AND :year_max"]
    params: dict = {"year_min": year_min, "year_max": year_max, "limit": limit}

    if countries_t:
        conditions.append("country = ANY(:countries)")
        params["countries"] = list(countries_t)
    if stages_t:
        conditions.append("stage = ANY(:stages)")
        params["stages"] = list(stages_t)
    if min_raised_m > 0:
        conditions.append("total_raised >= :min_raised")
        params["min_raised"] = min_raised_m
    if ai_only:
        conditions.append(ai_filter_sql())
    if verticals_t:
        conditions.append("categories && :verticals")
        params["verticals"] = list(verticals_t)

    where = " AND ".join(conditions)
    query = f"""
        SELECT
            name, domain, country, city, founded_year, stage,
            ROUND(total_raised::numeric, 1) AS total_raised_m,
            ai_score,
            cb_ai_tagged,
            ai_mentioned,
            llm_ai_verified,
            COALESCE(array_to_string(categories, ', '), '') AS verticals,
            verification_status
        FROM companies
        WHERE {where}
        ORDER BY total_raised DESC NULLS LAST, founded_year DESC NULLS LAST
        LIMIT :limit
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()
    df = pd.DataFrame(rows)
    if not df.empty:
        df["ai_score"] = df["ai_score"].round(2)
    return df


@st.cache_data(ttl=300)
def _load_vertical_ai_stats() -> pd.DataFrame:
    """AI share per industry vertical (canonical categories)."""
    engine = get_engine()
    query = f"""
        SELECT
            unnest(categories) AS vertical,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE {ai_filter_sql()}) AS ai
        FROM companies
        WHERE categories IS NOT NULL AND array_length(categories, 1) > 0
        GROUP BY vertical
        ORDER BY total DESC
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query)).mappings().all()
    df = pd.DataFrame(rows)
    if not df.empty:
        df["ai_pct"] = (df["ai"] / df["total"] * 100).round(1)
    return df


@st.cache_data(ttl=300)
def _load_vc_deal_volume() -> pd.DataFrame:
    """Deal count by stage bucket × year (2010-2024)."""
    engine = get_engine()
    query = """
        SELECT
            EXTRACT(year FROM deal_date)::int AS year,
            CASE round_type
                WHEN 'Accelerator/Incubator' THEN 'Pre-Seed / Accel'
                WHEN 'Grant'                 THEN 'Pre-Seed / Accel'
                WHEN 'Seed Round'            THEN 'Seed'
                WHEN 'Angel (individual)'    THEN 'Seed'
                WHEN 'Equity Crowdfunding'   THEN 'Seed'
                WHEN 'Early Stage VC'        THEN 'Early VC'
                WHEN 'Later Stage VC'        THEN 'Growth'
                WHEN 'PE Growth/Expansion'   THEN 'Growth'
                WHEN 'Corporate'             THEN 'Corporate / Other'
                WHEN 'PIPE'                  THEN 'Corporate / Other'
            END AS stage_bucket,
            COUNT(*) AS deals
        FROM funding_signals
        WHERE deal_date IS NOT NULL
          AND EXTRACT(year FROM deal_date) BETWEEN 2010 AND 2024
          AND round_type IN (
              'Accelerator/Incubator', 'Grant',
              'Seed Round', 'Angel (individual)', 'Equity Crowdfunding',
              'Early Stage VC', 'Later Stage VC', 'PE Growth/Expansion',
              'Corporate', 'PIPE'
          )
        GROUP BY year, stage_bucket
        ORDER BY year, stage_bucket
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query)).mappings().all()
    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def _load_deal_size_trend() -> pd.DataFrame:
    """Median deal size ($M) by year and stage bucket (2010-2024)."""
    engine = get_engine()
    query = """
        SELECT
            EXTRACT(year FROM deal_date)::int AS year,
            CASE round_type
                WHEN 'Seed Round'         THEN 'Seed'
                WHEN 'Angel (individual)' THEN 'Seed'
                WHEN 'Early Stage VC'     THEN 'Early VC'
                WHEN 'Later Stage VC'     THEN 'Growth'
                WHEN 'PE Growth/Expansion' THEN 'Growth'
            END AS stage_bucket,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deal_size / 1e6) AS median_m
        FROM funding_signals
        WHERE deal_date IS NOT NULL
          AND deal_size > 0
          AND EXTRACT(year FROM deal_date) BETWEEN 2010 AND 2024
          AND round_type IN (
              'Seed Round', 'Angel (individual)',
              'Early Stage VC', 'Later Stage VC', 'PE Growth/Expansion'
          )
        GROUP BY year, stage_bucket
        ORDER BY year, stage_bucket
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query)).mappings().all()
    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def _load_ai_first_financing() -> pd.DataFrame:
    """First financing year distribution for AI vs non-AI companies (2010-2024)."""
    engine = get_engine()
    query = f"""
        SELECT first_year, company_type, COUNT(*) AS companies
        FROM (
            SELECT
                EXTRACT(year FROM MIN(fs.deal_date))::int AS first_year,
                CASE WHEN {ai_filter_sql("c")}
                     THEN 'AI' ELSE 'Non-AI' END AS company_type
            FROM funding_signals fs
            JOIN companies c ON c.id = fs.company_id
            WHERE fs.deal_date IS NOT NULL
            GROUP BY c.id, c.cb_ai_tagged, c.ai_score, c.ai_mentioned, c.llm_ai_verified
        ) sub
        WHERE first_year BETWEEN 2010 AND 2024
        GROUP BY first_year, company_type
        ORDER BY first_year, company_type
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query)).mappings().all()
    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def _load_site_countries() -> dict[str, str]:
    """Returns domain → canonical country mapping.

    Priority: source_domain cross-ref > incubator_source cross-ref > TLD inference.
    """
    engine = get_engine()
    mapping: dict[str, str] = {}

    # Primary: source_domain set by agentic scraper (arbitrary sites)
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT source_domain, country FROM companies "
            "WHERE source_domain IS NOT NULL AND country IS NOT NULL AND country != '' "
            "GROUP BY source_domain, country ORDER BY COUNT(*) DESC"
        )).mappings().all()
    for row in rows:
        domain = row["source_domain"]
        if domain and domain not in mapping:
            norm = normalize_country(row["country"])
            if norm and norm in GLOBE_COUNTRIES:
                mapping[domain] = norm

    # Fallback: incubator_source enum for legacy hard-coded sources
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT DISTINCT incubator_source::text, country FROM companies "
            "WHERE incubator_source IS NOT NULL AND country IS NOT NULL AND country != ''"
        )).mappings().all()
    for row in rows:
        src = row["incubator_source"]
        if src and src not in mapping:
            norm = normalize_country(row["country"])
            if norm and norm in GLOBE_COUNTRIES:
                mapping[src] = norm

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

_PLOT_CFG = {"displayModeBar": False}


def _layout(**kw):
    base = dict(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family="Inter", color=TXT3, size=11.5),
        title=dict(text="", font=dict(color=TXT, size=13.5, family="Inter"),
                   x=0, xanchor="left"),
        colorway=[ACCENT] + CAT[1:],
        xaxis=dict(showgrid=False, zeroline=False,
                   linecolor=BORDER, ticks="outside", tickcolor=BORDER,
                   ticklen=4, tickfont=dict(size=11)),
        yaxis=dict(gridcolor=BORDER_LIGHT, zeroline=False,
                   linecolor="rgba(0,0,0,0)", tickfont=dict(size=11)),
        legend=dict(font=dict(size=11, color=TXT2), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=BG_CARD, bordercolor=BORDER,
                        font=dict(family="Inter", size=12, color=TXT)),
        bargap=0.35,
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


# ── Public-page loaders ──────────────────────────────────────────────

_HIDDEN_STATUS = "emerging_github"   # verification bucket: not in CB/PB


@st.cache_data(ttl=300)
def _load_bucket_stats() -> pd.DataFrame:
    """Company totals + AI counts per verification bucket (hidden / cb / pb)."""
    engine = get_engine()
    query = f"""
        SELECT verification_status AS bucket,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE {ai_filter_sql()}) AS ai
        FROM companies
        WHERE verification_status IS NOT NULL
        GROUP BY verification_status
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query)).mappings().all()
    df = pd.DataFrame(rows)
    if not df.empty:
        df["ai_pct"] = (df["ai"] / df["total"] * 100).round(1)
    return df


@st.cache_data(ttl=300)
def _load_country_counts() -> pd.DataFrame:
    """Per-country company totals for the world map (aggregates only)."""
    engine = get_engine()
    query = f"""
        SELECT country,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE {ai_filter_sql()}) AS ai
        FROM companies
        WHERE country IS NOT NULL AND country != ''
        GROUP BY country
        HAVING COUNT(*) >= 5
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query)).mappings().all()
    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def _load_hidden_companies(search: str, country: str, ai_only: bool,
                           limit: int = 5000) -> pd.DataFrame:
    """Hidden companies only (not in Crunchbase/PitchBook) — the public list.

    CB/PB-derived rows stay out of the public explorer for license reasons;
    they appear on the site only as aggregate statistics.
    """
    engine = get_engine()
    conditions = ["verification_status = :status"]
    params: dict = {"status": _HIDDEN_STATUS, "limit": limit}
    if search:
        conditions.append("(name ILIKE :q OR description ILIKE :q)")
        params["q"] = f"%{search}%"
    if country and country != "All countries":
        conditions.append("country = :country")
        params["country"] = country
    if ai_only:
        conditions.append(ai_filter_sql())
    where = " AND ".join(conditions)
    query = f"""
        SELECT name, domain, country, city, founded_year,
               LEFT(description, 180) AS description,
               ai_score, source_domain, incubator_source,
               first_seen_at::date AS first_seen
        FROM companies
        WHERE {where}
        ORDER BY first_seen_at DESC NULLS LAST
        LIMIT :limit
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()
    df = pd.DataFrame(rows)
    if not df.empty:
        df["ai_score"] = df["ai_score"].astype(float).round(2)
    return df


@st.cache_data(ttl=300)
def _load_hidden_country_options() -> list[str]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT country FROM companies "
            "WHERE verification_status = :status AND country IS NOT NULL AND country != '' "
            "GROUP BY country ORDER BY COUNT(*) DESC LIMIT 60"
        ), {"status": _HIDDEN_STATUS}).all()
    return [r[0] for r in rows]


_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


@st.cache_data(ttl=3600)
def _read_output_csv(name: str) -> pd.DataFrame:
    """Read a paper-ready analysis CSV from output/ (committed by research runs)."""
    path = _OUTPUT_DIR / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _source_label(row) -> str:
    """Human label for how a hidden company was discovered."""
    src = (row.get("source_domain") or "")
    if src in ("nih.gov", "nsf.gov"):
        return "US grant (SBIR/STTR)"
    if row.get("incubator_source"):
        return "Portfolio scrape"
    if src:
        return f"Web · {src}"
    return "GitHub"


# ── Page: Home (public overview) ─────────────────────────────────────

def page_home():
    stats = _load_overview_stats()
    buckets = _load_bucket_stats()
    curve = _load_ai_adoption_curve()

    hidden_total, hidden_ai_pct, cb_ai_pct = 0, None, None
    if not buckets.empty:
        b = buckets.set_index("bucket")
        if _HIDDEN_STATUS in b.index:
            hidden_total = int(b.loc[_HIDDEN_STATUS, "total"])
            hidden_ai_pct = float(b.loc[_HIDDEN_STATUS, "ai_pct"])
        if "verified_cb" in b.index:
            cb_ai_pct = float(b.loc["verified_cb", "ai_pct"])

    # ── Hero: headline left, lede right, stat band across ────────────
    st.markdown(
        f'<div class="hero-eyebrow"><span class="live-dot"></span>'
        f'Live dataset &middot; {stats["total"]:,} companies &middot; updated '
        f'{datetime.now().strftime("%b %d, %Y")}</div>',
        unsafe_allow_html=True,
    )
    h1col, h2col = st.columns([1.15, 1], gap="large", vertical_alignment="bottom")
    h1col.markdown(
        '<div class="hero-title">Where new AI companies actually come from</div>',
        unsafe_allow_html=True,
    )
    h2col.markdown(
        '<p class="hero-lede">We track company formation across GitHub, accelerator '
        'and VC portfolios, government grant awards, and startup media — including '
        '<b>tens of thousands of young firms that commercial databases have not '
        'registered yet</b>.</p>',
        unsafe_allow_html=True,
    )

    ai_stat = (
        f'<span class="stat-value">{hidden_ai_pct:.1f}%</span>'
        f'<span class="stat-sub">vs <b>{cb_ai_pct:.1f}%</b> in Crunchbase</span>'
        if hidden_ai_pct is not None and cb_ai_pct is not None
        else f'<span class="stat-value">{stats["ai"]:,}</span>'
             f'<span class="stat-sub">across all sources</span>'
    )
    st.markdown(
        f'<div style="height:22px"></div>'
        f'<div class="statband">'
        f'<div class="stat"><span class="stat-label">Companies tracked</span>'
        f'<span class="stat-value">{stats["total"]:,}</span>'
        f'<span class="stat-sub">all discovery channels</span></div>'
        f'<div class="stat"><span class="stat-label">Hidden companies</span>'
        f'<span class="stat-value">{hidden_total:,}</span>'
        f'<span class="stat-sub">in neither Crunchbase nor PitchBook</span></div>'
        f'<div class="stat"><span class="stat-label">AI share of hidden firms</span>'
        f'{ai_stat}</div>'
        f'<div class="stat"><span class="stat-label">Countries</span>'
        f'<span class="stat-value">{stats["countries"]:,}</span>'
        f'<span class="stat-sub">headquarters coverage</span></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Key findings ─────────────────────────────────────────────────
    st.markdown('<div style="height:26px"></div>', unsafe_allow_html=True)
    f1, f2 = st.columns([1.25, 1])

    with f1:
        st.markdown(
            '<div class="section-header">AI share of new companies is climbing</div>'
            '<div class="section-sub">Share of companies founded each year that are AI-focused</div>',
            unsafe_allow_html=True,
        )
        if not curve.empty:
            c = curve[curve["founded_year"] <= 2025]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=c["founded_year"], y=c["ai_pct"], mode="lines",
                line=dict(color=ACCENT, width=2.5),
                fill="tozeroy", fillcolor="rgba(42,120,214,0.08)",
                hovertemplate="%{x}: %{y:.1f}%<extra></extra>", name="AI share",
            ))
            last = c.iloc[-1]
            fig.add_trace(go.Scatter(
                x=[last["founded_year"]], y=[last["ai_pct"]], mode="markers+text",
                marker=dict(color=ACCENT, size=9),
                text=[f"{last['ai_pct']:.0f}%"], textposition="top left",
                textfont=dict(color=TXT, size=12), showlegend=False,
                hoverinfo="skip",
            ))
            fig.update_layout(**_layout(
                height=290, showlegend=False,
                yaxis=dict(ticksuffix="%", gridcolor=BORDER_LIGHT, zeroline=False,
                           linecolor="rgba(0,0,0,0)", rangemode="tozero"),
                margin=dict(l=0, r=8, t=8, b=0),
            ))
            st.plotly_chart(fig, use_container_width=True, config=_PLOT_CFG)

    with f2:
        st.markdown(
            '<div class="section-header">Hidden companies skew AI</div>'
            '<div class="section-sub">AI share by data source — firms invisible to '
            'commercial databases are the most AI-dense</div>',
            unsafe_allow_html=True,
        )
        if not buckets.empty:
            order = [(_HIDDEN_STATUS, "Hidden (this tracker)"),
                     ("verified_cb", "Crunchbase"),
                     ("verified_pb", "PitchBook")]
            rows = [(label, float(buckets.set_index("bucket").loc[key, "ai_pct"]))
                    for key, label in order
                    if key in buckets["bucket"].values]
            labels = [r[0] for r in rows][::-1]
            vals = [r[1] for r in rows][::-1]
            colors = [ACCENT if l.startswith("Hidden") else GRAY_CTX for l in labels]
            fig = go.Figure(go.Bar(
                x=vals, y=labels, orientation="h",
                marker=dict(color=colors),
                text=[f"{v:.1f}%" for v in vals], textposition="outside",
                textfont=dict(color=TXT, size=12),
                hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
            ))
            fig.update_layout(**_layout(
                height=290, showlegend=False, bargap=0.45,
                xaxis=dict(ticksuffix="%", showgrid=False, zeroline=False,
                           linecolor=BORDER, range=[0, max(vals) * 1.3]),
                yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=12, color=TXT2)),
                margin=dict(l=0, r=8, t=8, b=0),
            ))
            st.plotly_chart(fig, use_container_width=True, config=_PLOT_CFG)

    # ── World map ────────────────────────────────────────────────────
    st.markdown(
        '<div style="height:10px"></div>'
        '<div class="section-header">Global footprint</div>'
        '<div class="section-sub">Tracked companies by headquarters country (log scale)</div>',
        unsafe_allow_html=True,
    )
    geo = _load_country_counts()
    gcol, tcol = st.columns([2.6, 1])
    if not geo.empty:
        import numpy as np
        gm = geo.copy()
        gm["log_total"] = np.log10(gm["total"].clip(lower=1))
        fig = go.Figure(go.Choropleth(
            locations=gm["country"], locationmode="country names",
            z=gm["log_total"],
            customdata=gm[["total", "ai"]],
            colorscale=[[s, c] for s, c in SEQ_SCALE],
            marker_line_color="#ffffff", marker_line_width=0.4,
            colorbar=dict(
                title=dict(text="Companies", font=dict(size=11, color=TXT3)),
                tickvals=[0, 1, 2, 3, 4, 5],
                ticktext=["1", "10", "100", "1k", "10k", "100k"],
                thickness=10, len=0.7, outlinewidth=0,
                tickfont=dict(size=10.5, color=TXT3),
            ),
            hovertemplate="<b>%{location}</b><br>%{customdata[0]:,} companies · "
                          "%{customdata[1]:,} AI<extra></extra>",
        ))
        fig.update_geos(
            showframe=False, showcoastlines=False,
            landcolor=BG_OFF, bgcolor="rgba(0,0,0,0)",
            projection_type="natural earth",
        )
        fig.update_layout(
            height=420, margin=dict(l=0, r=0, t=6, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter", color=TXT3),
            hoverlabel=dict(bgcolor=BG_CARD, bordercolor=BORDER,
                            font=dict(family="Inter", size=12, color=TXT)),
        )
        with gcol:
            st.plotly_chart(fig, use_container_width=True, config=_PLOT_CFG)
        with tcol:
            top = geo.nlargest(10, "total")[["country", "total"]].rename(
                columns={"country": "Country", "total": "Companies"})
            st.markdown(
                f'<div style="color:{TXT3};font-size:0.8rem;margin:6px 0 6px 0;">'
                'Top 10 countries</div>', unsafe_allow_html=True)
            st.dataframe(top, hide_index=True, width="stretch", height=384)

    # ── Latest hidden discoveries ────────────────────────────────────
    st.markdown(
        '<div style="height:14px"></div>'
        '<div class="section-header">Latest hidden discoveries</div>'
        '<div class="section-sub">Recently found AI companies that are not in '
        'Crunchbase or PitchBook — browse and export the full list on the '
        '<b>Companies</b> page</div>',
        unsafe_allow_html=True,
    )
    recent = _load_hidden_companies(search="", country="All countries",
                                    ai_only=True, limit=12)
    if recent.empty:
        st.caption("No hidden companies loaded yet.")
    else:
        view = recent.copy()
        view["Discovered via"] = view.apply(_source_label, axis=1)
        view = view[["name", "country", "founded_year", "Discovered via", "first_seen"]]
        view.columns = ["Company", "Country", "Founded", "Discovered via", "First seen"]
        st.dataframe(view, hide_index=True, width="stretch",
                     column_config={
                         "Founded": st.column_config.NumberColumn(format="%d"),
                     })


# ── Page: Companies (hidden-only public explorer) ────────────────────

def page_companies():
    st.markdown(
        '<div class="section-header">Hidden companies</div>'
        '<div class="section-sub" style="max-width:74ch;">Companies discovered by this '
        'tracker that do not appear in Crunchbase or PitchBook — surfaced from GitHub '
        'activity, accelerator/VC portfolio pages, US SBIR/STTR grant awards, and '
        'startup media. Companies from commercial databases are shown on this site '
        'only as aggregate statistics.</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([2.2, 1.2, 1])
    search = c1.text_input("Search", placeholder="Search by name or description…",
                           label_visibility="collapsed")
    country = c2.selectbox("Country", ["All countries"] + _load_hidden_country_options(),
                           label_visibility="collapsed")
    ai_only = c3.checkbox("AI companies only", value=True)

    df = _load_hidden_companies(search=search.strip(), country=country,
                                ai_only=ai_only, limit=5000)
    if df.empty:
        st.caption("No companies match these filters.")
        return

    view = df.copy()
    view["Discovered via"] = view.apply(_source_label, axis=1)
    view["domain"] = view["domain"].map(
        lambda d: f"https://{d}" if isinstance(d, str) and d and not d.startswith("http") else d)
    view = view[["name", "domain", "country", "city", "founded_year",
                 "Discovered via", "ai_score", "first_seen", "description"]]
    view.columns = ["Company", "Website", "Country", "City", "Founded",
                    "Discovered via", "AI score", "First seen", "Description"]

    st.markdown(
        f'<div style="color:{TXT3};font-size:0.78rem;margin:2px 0 8px 0;">'
        f'{len(df):,} companies shown (newest first, capped at 5,000)</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(
        view, hide_index=True, width="stretch", height=560,
        column_config={
            "Website": st.column_config.LinkColumn(display_text=r"https?://(.*)"),
            "Founded": st.column_config.NumberColumn(format="%d"),
            "AI score": st.column_config.ProgressColumn(
                min_value=0.0, max_value=1.0, format="%.2f"),
            "Description": st.column_config.TextColumn(width="large"),
        },
    )
    st.download_button(
        "Export CSV", df.to_csv(index=False).encode(),
        file_name="hidden_companies.csv", mime="text/csv",
    )


# ── Page: About & methodology ────────────────────────────────────────

def page_about():
    stats = _load_overview_stats()
    buckets = _load_bucket_stats()
    hidden_total = 0
    if not buckets.empty and _HIDDEN_STATUS in buckets["bucket"].values:
        hidden_total = int(buckets.set_index("bucket").loc[_HIDDEN_STATUS, "total"])

    st.markdown(
        '<div class="section-header">About this tracker</div>'
        f'<div class="section-sub" style="max-width:76ch;">A research project of the '
        f'Tobin Center for Economic Policy at Yale University. We measure where and '
        f'when new AI companies form — including the young firms that commercial '
        f'databases miss. The tracker currently covers <b>{stats["total"]:,}</b> '
        f'companies across <b>{stats["countries"]}</b> countries, of which '
        f'<b>{hidden_total:,}</b> appear in neither Crunchbase nor PitchBook.</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div style="height:8px"></div>'
        '<div class="section-header">How companies enter the tracker</div>',
        unsafe_allow_html=True,
    )
    sources = pd.DataFrame([
        ["GitHub discovery", "Weekly scan of new AI repositories and organizations; "
         "signals like stars, contributor velocity, and org metadata identify "
         "companies before any register lists them."],
        ["Portfolio scraping", "400+ accelerator, incubator, university, and VC "
         "portfolio pages, scraped by an agentic engine that adapts per site."],
        ["Government grants", "NIH and NSF SBIR/STTR award APIs — US firms that won "
         "federal R&D grants, often years before commercial visibility."],
        ["Startup media", "18 regional startup news feeds worldwide, mined for "
         "funding announcements and company launches."],
        ["Commercial registers", "Crunchbase and PitchBook imports verify overlap "
         "and provide the institutional baseline (shown as aggregates only)."],
    ], columns=["Source", "What it contributes"])
    st.dataframe(sources, hide_index=True, width="stretch",
                 column_config={
                     "What it contributes": st.column_config.TextColumn(width="large")})

    st.markdown(
        '<div style="height:8px"></div>'
        '<div class="section-header">Reading the numbers</div>'
        '<div class="section-sub" style="max-width:76ch;">'
        '<b>Hidden companies</b> are firms in this tracker absent from both Crunchbase '
        'and PitchBook at match time. <b>AI classification</b> combines keyword rules, '
        'register tags, and an LLM verifier. Two caveats: recent-year counts are '
        'incomplete (young firms take time to surface — we estimate the lag on the '
        'Findings page), and the grant-sourced subset is 100% US by construction, '
        'which pulls the hidden bucket\'s geography toward the United States. '
        'Company-level data from commercial databases is not republished here; those '
        'sources appear only in aggregate comparisons.</div>',
        unsafe_allow_html=True,
    )
    st.caption("Contact: Tobin Center for Economic Policy, Yale University.")


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

    # Live aggregate stats (full DB, not limited to the 15K loaded rows)
    stats = _load_overview_stats()
    total = stats["total"]

    st.markdown(
        '<div class="section-header" style="margin-top:24px;">Companies</div>'
        '<div class="section-sub">AI-startup totals across all tracked sources (inclusive: any AI signal)</div>',
        unsafe_allow_html=True,
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Companies", f"{stats['total']:,}")
    m2.metric("AI Startups", f"{stats['ai']:,}")
    m3.metric("With Funding", f"{stats['funded']:,}")
    m4.metric("Countries", f"{stats['countries']:,}")

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
                   color="#1f3a5f", zoom=3, width="stretch")
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
    # (raw-HTML wrappers can't enclose Streamlit widgets, so this is a
    # labeled divider rather than a boxed container)
    st.markdown('<hr/><div class="filter-bar-label">Filters</div>', unsafe_allow_html=True)

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

    ff1, ff2, ff3, ff4, ff5 = st.columns(5)
    stages = sorted(df["stage"].dropna().unique().tolist())
    sel_stages = ff1.multiselect("Stage", options=stages, placeholder="All stages")
    ctries = sorted(df["country"].dropna().unique().tolist())
    sel_ctries = ff2.multiselect("Country", options=ctries, placeholder="All countries")
    incs = sorted(df["incubator_source"].dropna().astype(str).unique().tolist())
    sel_incs = ff3.multiselect("Incubator", options=incs, placeholder="All incubators")
    sel_cats = ff4.multiselect("Source type", options=list(_CAT_LABELS.keys()),
                                format_func=lambda x: _CAT_LABELS.get(x, x),
                                placeholder="All types")
    from backend.utils.industry import CANONICAL_VERTICALS
    sel_verticals = ff5.multiselect("Vertical", options=CANONICAL_VERTICALS, placeholder="All verticals")

    if "founded_year" in df.columns and df["founded_year"].notna().any():
        valid_yrs = df["founded_year"].dropna().astype(int)
        yr_min, yr_max = int(valid_yrs.min()), int(valid_yrs.max())
        yr_min = max(yr_min, 2000)
        yr_range = st.slider("Founded year", yr_min, yr_max, (2015, yr_max), key="yr_range")
    else:
        yr_range = None

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
    if sel_verticals and "categories" in f.columns:
        f = f[f["categories"].apply(
            lambda cats: isinstance(cats, list) and any(v in cats for v in sel_verticals)
        )]
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
        f'<b style="color:{TXT};">{len(f):,}</b> matching '
        f'(of {len(df):,} loaded) &middot; <b style="color:{TXT};">{total:,}</b> total in DB '
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
        fig.update_traces(marker_color=ACCENT)
        fig.update_layout(**_layout(height=260))
        st.plotly_chart(fig, width="stretch", config=_PLOT_CFG)

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

    is_ai_sig = (df["ai_score"].fillna(0) >= 0.5) | df.get("cb_ai_tagged", pd.Series(False, index=df.index)).fillna(False)
    ai_df = df[is_ai_sig & df["ai_tags"].notna()].copy()
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
        fig1.update_traces(marker_color=ACCENT)
        fig1.update_layout(**_layout(height=420,
            xaxis=dict(showgrid=True, gridcolor=BORDER_LIGHT, zeroline=False,
                       linecolor="rgba(0,0,0,0)", tickfont=dict(size=11)),
            yaxis=dict(autorange="reversed", showgrid=False),
            showlegend=False))
        st.plotly_chart(fig1, width="stretch", config=_PLOT_CFG)

    with t2:
        gs = mg.sort_values("growth_pct", ascending=False)
        fig2 = px.bar(gs, x="growth_pct", y="subdomain", orientation="h",
                      title="Growth rate (vs prior 30d)",
                      labels={"growth_pct": "% Growth", "subdomain": ""})
        fig2.update_traces(marker_color=TEAL)
        fig2.update_layout(**_layout(height=420,
            xaxis=dict(showgrid=True, gridcolor=BORDER_LIGHT, zeroline=False,
                       linecolor="rgba(0,0,0,0)", tickfont=dict(size=11)),
            yaxis=dict(autorange="reversed", showgrid=False),
            showlegend=False))
        st.plotly_chart(fig2, width="stretch", config=_PLOT_CFG)

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
                color_discrete_map={"working": GREEN, "pending": AMBER},
                category_orders={"category": [
                    "university_incubator", "accelerator", "vc_portfolio",
                    "discovery_aggregator", "government_program", "other",
                ]},
                barmode="stack",
            )
            fig.update_layout(**_layout(height=260, legend_title_text=""))
            st.plotly_chart(fig, width="stretch", config=_PLOT_CFG)
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
        for state, color in [("pending", AMBER), ("healthy", GREEN), ("broken", RED)]:
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
        st.plotly_chart(fig, use_container_width=True, config=_PLOT_CFG)

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
    st.markdown('<hr/><div class="filter-bar-label">Filters</div>', unsafe_allow_html=True)
    search = st.text_input("Search GitHub", placeholder="Search by repo, owner, description...",
                           label_visibility="collapsed", key="gh_search")
    gc1, gc2, gc3 = st.columns(3)
    min_stars = gc1.number_input("Min stars", min_value=0, value=0, step=100, key="gh_minstars")
    min_conf = gc2.slider("Min LLM confidence", 0.0, 1.0, 0.6, 0.05, key="gh_minconf")
    recent_only = gc3.checkbox("Last 30 days", key="gh_recent")

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
    "university_incubator": CAT[0],
    "accelerator":          CAT[1],
    "vc_portfolio":         CAT[3],
    "government_program":   CAT[2],
    "discovery_aggregator": BLUE_RAMP[0],
    "other":                "#9aa5b3",
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

    scrape_colors = {"easy": GREEN, "agentic": ACCENT, "challenging": RED}

    present_tiers = [t for t in ["easy", "agentic", "challenging"] if t in cat_counts["scrapeability"].values]
    fig_cat = px.bar(
        cat_counts,
        x="category_label",
        y="count",
        color="scrapeability",
        color_discrete_map=scrape_colors,
        category_orders={
            "category_label": [_CATEGORY_LABELS[c] for c in _CATEGORY_ORDER],
            "scrapeability": present_tiers,
        },
        barmode="stack",
        labels={"category_label": "", "count": "Sites", "scrapeability": ""},
        title="Sites by Type & Scrapeability",
    )
    fig_cat.update_layout(**_layout(height=320))
    st.plotly_chart(fig_cat, use_container_width=True, config=_PLOT_CFG)

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
        st.plotly_chart(fig_d, use_container_width=True, config=_PLOT_CFG)

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


def page_ai_analysis(df: pd.DataFrame, stats: dict | None = None,
                     source_stats: pd.DataFrame | None = None,
                     country_stats: pd.DataFrame | None = None):
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
    cb_tagged = df["cb_ai_tagged"].fillna(False).astype(bool) if "cb_ai_tagged" in df.columns else pd.Series(False, index=df.index)
    ai_mentioned = df["ai_mentioned"].fillna(False).astype(bool) if "ai_mentioned" in df.columns else pd.Series(False, index=df.index)
    llm_verified = df["llm_ai_verified"].fillna(False).astype(bool) if "llm_ai_verified" in df.columns else pd.Series(False, index=df.index)
    is_ai = cb_tagged | ((df["ai_score"].fillna(0) >= 0.3) | has_tags | ai_mentioned | llm_verified) if "ai_score" in df.columns else has_tags
    df = df.copy()
    df["is_ai"] = is_ai

    # Use full-DB stats for headline numbers; fall back to df sample if not provided
    total = stats["total"] if stats else len(df)
    ai_cos = stats["ai"] if stats else int(is_ai.sum())
    non_ai = total - ai_cos
    ai_pct = round(ai_cos * 100.0 / total, 1) if total else 0
    unclassified = int(df["ai_score"].isna().sum()) if "ai_score" in df.columns else 0

    # ── Headline metrics ─────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total companies", f"{total:,}")
    m2.metric("AI companies", f"{ai_cos:,}", help="cb_ai_tagged OR ai_score ≥ 0.5 OR ai_mentioned OR llm_ai_verified")
    m3.metric("AI share", f"{ai_pct}%")
    m4.metric("Unclassified", f"{unclassified:,}", help="ai_score is NULL")

    st.markdown("<br/>", unsafe_allow_html=True)

    # ── AI % by source program ───────────────────────────────────────
    if source_stats is not None and not source_stats.empty:
        prog = source_stats.sort_values("ai_count", ascending=True).tail(20)
    elif "incubator_source" in df.columns:
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
    else:
        prog = pd.DataFrame()
    if not prog.empty:

        fig_src = px.bar(
            prog,
            x="ai_count",
            y="incubator_source",
            orientation="h",
            color="ai_pct",
            color_continuous_scale=SEQ_SCALE,
            labels={"ai_count": "AI Companies", "incubator_source": "", "ai_pct": "AI %"},
            title="AI Companies by Source",
            text="ai_count",
        )
        fig_src.update_traces(textposition="outside")
        fig_src.update_layout(**_layout(height=max(300, len(prog) * 26 + 80)))
        st.plotly_chart(fig_src, use_container_width=True, config=_PLOT_CFG)

    # ── Country distribution ─────────────────────────────────────────
    st.markdown("<br/>", unsafe_allow_html=True)
    col_left, col_right = st.columns([3, 2])

    with col_left:
        if country_stats is not None and not country_stats.empty:
            ctry = country_stats.sort_values("ai", ascending=False).head(15).sort_values("ai")
            fig_ctry = px.bar(
                ctry,
                x="ai",
                y="country",
                orientation="h",
                color="ai",
                color_continuous_scale=SEQ_SCALE,
                labels={"ai": "AI Startups", "country": ""},
                title="AI Startups by Country (top 15)",
                text="ai",
            )
            fig_ctry.update_traces(textposition="outside")
            fig_ctry.update_layout(**_layout(height=440))
            st.plotly_chart(fig_ctry, use_container_width=True, config=_PLOT_CFG)
        elif "country" in df.columns:
            ai_df = df[df["is_ai"]].copy()
            norm = {"USA": "United States", "US": "United States", "usa": "United States",
                    "U.S.A.": "United States", "U.S.": "United States"}
            ai_df["country_norm"] = ai_df["country"].replace(norm)
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
                color_continuous_scale=SEQ_SCALE,
                labels={"count": "AI Startups", "country_norm": ""},
                title="AI Startups by Country (top 15)",
                text="count",
            )
            fig_ctry.update_traces(textposition="outside")
            fig_ctry.update_layout(**_layout(height=440))
            st.plotly_chart(fig_ctry, use_container_width=True, config=_PLOT_CFG)

    with col_right:
        # AI vs non-AI donut
        fig_d = go.Figure(go.Pie(
            labels=["AI-focused", "Non-AI"],
            values=[ai_cos, non_ai],
            marker_colors=[ACCENT, GRAY_CTX],
            hole=0.55,
            textinfo="label+percent",
            hovertemplate="%{label}: %{value:,}<extra></extra>",
        ))
        fig_d.update_layout(**_layout(height=280, title_text="AI vs. Non-AI"))
        st.plotly_chart(fig_d, use_container_width=True, config=_PLOT_CFG)

        # Score histogram
        if "ai_score" in df.columns:
            score_df = df[df["ai_score"].notna()]
            fig_hist = px.histogram(
                score_df,
                x="ai_score",
                nbins=20,
                color_discrete_sequence=[ACCENT],
                labels={"ai_score": "AI Score", "count": "Companies"},
                title="AI Score Distribution",
            )
            fig_hist.add_vline(x=0.3, line_dash="dash", line_color=RED,
                               annotation_text="AI threshold (0.3)")
            fig_hist.update_layout(**_layout(height=240))
            st.plotly_chart(fig_hist, use_container_width=True, config=_PLOT_CFG)

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
        fig_time.add_bar(x=monthly["month"], y=monthly["total"], name="All", marker_color=GRAY_CTX)
        fig_time.add_bar(x=monthly["month"], y=monthly["ai"], name="AI", marker_color=ACCENT)
        fig_time.update_layout(
            barmode="overlay",
            title_text="Monthly Company Discovery (AI in blue, all in grey)",
            xaxis_title="",
            yaxis_title="Companies",
            **_layout(height=280),
        )
        st.plotly_chart(fig_time, use_container_width=True, config=_PLOT_CFG)

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


# ── Page: Research ───────────────────────────────────────────────────

def page_research():
    stats = _load_overview_stats()
    curve = _load_ai_adoption_curve()
    country_stats = _load_country_ai_stats(min_companies=100)
    matrix = _load_country_year_matrix(top_n=25)
    vertical_stats = _load_vertical_ai_stats()
    deal_volume = _load_vc_deal_volume()
    deal_sizes = _load_deal_size_trend()
    first_fin = _load_ai_first_financing()

    total_cos = stats["total"]
    total_ai = stats["ai"]
    countries_n = stats["countries"]

    st.markdown(
        f'<div class="eyebrow">Findings</div>'
        f'<h1>Global AI startup formation</h1>'
        f'<div class="section-sub">{total_cos:,} companies across {countries_n} '
        f'countries, 2000–2026 — including the hidden layer commercial databases miss</div>',
        unsafe_allow_html=True,
    )

    # ── Summary stats ────────────────────────────────────────────────
    if not curve.empty:
        # Peak year: only consider years with at least 1,000 companies (avoid sparse recent years)
        stable = curve[curve["total"] >= 1000]
        peak_year = int(stable.loc[stable["ai_pct"].idxmax(), "founded_year"]) if not stable.empty else "—"
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total companies", f"{total_cos:,}")
        c2.metric("AI companies", f"{total_ai:,}", f"{100*total_ai/total_cos:.1f}% of total")
        c3.metric("Countries", f"{countries_n}")
        c4.metric("Peak AI year", str(peak_year))

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Section 1: AI Formation Timeline ────────────────────────────
    st.markdown(
        '<div class="section-header">AI Startup Formation Timeline</div>'
        '<div class="section-sub">Total tech companies (bars) vs AI share % (line) by founding year</div>',
        unsafe_allow_html=True,
    )

    if not curve.empty:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=curve["founded_year"], y=curve["total"],
            name="All tech companies",
            marker_color=GRAY_CTX,
            yaxis="y2",
        ))
        fig.add_trace(go.Scatter(
            x=curve["founded_year"], y=curve["ai_pct"],
            name="AI share (%)",
            mode="lines+markers",
            line=dict(color=TEAL, width=2.5),
            marker=dict(size=6),
        ))
        fig.update_layout(
            **_layout(
                height=380,
                yaxis=dict(title="AI share (%)", ticksuffix="%", rangemode="tozero", gridcolor=BORDER_LIGHT),
                yaxis2=dict(title="Total companies", overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", y=1.08, font=dict(size=11, color=TXT2),
                            bgcolor="rgba(0,0,0,0)"),
            ),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, config=_PLOT_CFG)

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Section 2: Geographic AI Concentration ───────────────────────
    st.markdown(
        '<div class="section-header">Geographic AI Concentration</div>'
        '<div class="section-sub">Countries ranked by AI share of tech startup formation (min 100 companies)</div>',
        unsafe_allow_html=True,
    )

    if not country_stats.empty:
        col_left, col_right = st.columns([3, 2])

        with col_left:
            top30 = country_stats.head(30).sort_values("ai_pct")
            fig_geo = px.bar(
                top30, x="ai_pct", y="country", orientation="h",
                labels={"ai_pct": "AI share (%)", "country": ""},
                color="ai_pct",
                color_continuous_scale=SEQ_SCALE,
            )
            fig_geo.update_coloraxes(showscale=False)
            fig_geo.update_layout(**_layout(height=max(400, len(top30) * 22)))
            st.plotly_chart(fig_geo, use_container_width=True, config=_PLOT_CFG)

        with col_right:
            tbl = country_stats.head(30)[["country", "total", "ai", "ai_pct"]].copy()
            tbl.columns = ["Country", "Total", "AI", "AI %"]
            tbl["AI %"] = tbl["AI %"].apply(lambda v: f"{v:.1f}%")
            st.dataframe(tbl, hide_index=True, use_container_width=True, height=680)

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Section 3: AI Adoption by Industry Vertical ──────────────────
    st.markdown(
        '<div class="section-header">AI Adoption by Industry Vertical</div>'
        '<div class="section-sub">AI share of startup formation per industry — unified taxonomy across Crunchbase and PitchBook (98% coverage)</div>',
        unsafe_allow_html=True,
    )

    if not vertical_stats.empty:
        col_vl, col_vr = st.columns([3, 2])
        with col_vl:
            sorted_v = vertical_stats.sort_values("ai_pct")
            fig_vert = px.bar(
                sorted_v, x="ai_pct", y="vertical", orientation="h",
                labels={"ai_pct": "AI share (%)", "vertical": ""},
                color="ai_pct",
                color_continuous_scale=SEQ_SCALE,
            )
            fig_vert.update_coloraxes(showscale=False)
            fig_vert.update_layout(**_layout(height=max(380, len(sorted_v) * 26)))
            st.plotly_chart(fig_vert, use_container_width=True, config=_PLOT_CFG)
        with col_vr:
            tbl_v = vertical_stats[["vertical", "total", "ai", "ai_pct"]].copy()
            tbl_v = tbl_v.sort_values("ai_pct", ascending=False)
            tbl_v.columns = ["Vertical", "Total", "AI", "AI %"]
            tbl_v["AI %"] = tbl_v["AI %"].apply(lambda v: f"{v:.1f}%")
            st.dataframe(tbl_v, hide_index=True, use_container_width=True, height=500)

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Section 4: Country × Year Heatmap ───────────────────────────
    st.markdown(
        '<div class="section-header">AI Adoption by Country × Year</div>'
        '<div class="section-sub">AI share (%) per country per founding year — top 25 countries by total size</div>',
        unsafe_allow_html=True,
    )

    if not matrix.empty:
        pivot = matrix.pivot(index="country", columns="founded_year", values="ai_pct").fillna(0)
        # Sort countries by their 2022-2024 average AI% descending
        recent_cols = [c for c in pivot.columns if c >= 2020]
        pivot["_sort"] = pivot[recent_cols].mean(axis=1) if recent_cols else 0
        pivot = pivot.sort_values("_sort", ascending=False).drop(columns=["_sort"])

        fig_heat = px.imshow(
            pivot,
            labels=dict(x="Founded Year", y="Country", color="AI share (%)"),
            color_continuous_scale=[[0, "#f4f7fb"], [0.5, "#4f8fd9"], [1, "#00356b"]],
            aspect="auto",
            zmin=0, zmax=50,
        )
        fig_heat.update_layout(**_layout(height=max(500, len(pivot) * 22)))
        fig_heat.update_xaxes(side="bottom")
        st.plotly_chart(fig_heat, use_container_width=True, config=_PLOT_CFG)

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Section 4: VC Deal Intelligence ─────────────────────────────
    st.markdown(
        '<div class="section-header">VC Deal Intelligence</div>'
        '<div class="section-sub">268K funding events from PitchBook — deal volume, size trends, and AI vs non-AI first financing</div>',
        unsafe_allow_html=True,
    )

    if not deal_volume.empty:
        col_vol, col_size = st.columns(2)

        with col_vol:
            st.markdown("**Deal volume by stage (2010–2024)**")
            # Ordered stages take the single-hue ordinal ramp (light→dark);
            # the unordered catch-all bucket stays neutral gray.
            STAGE_COLORS = {
                "Pre-Seed / Accel": BLUE_RAMP[0],
                "Seed":             BLUE_RAMP[1],
                "Early VC":         BLUE_RAMP[2],
                "Growth":           BLUE_RAMP[3],
                "Corporate / Other":"#9aa5b3",
            }
            bucket_order = ["Pre-Seed / Accel", "Seed", "Early VC", "Growth", "Corporate / Other"]
            fig_vol = go.Figure()
            for bucket in bucket_order:
                sub = deal_volume[deal_volume["stage_bucket"] == bucket]
                if sub.empty:
                    continue
                fig_vol.add_trace(go.Bar(
                    x=sub["year"], y=sub["deals"],
                    name=bucket,
                    marker_color=STAGE_COLORS.get(bucket, "#999"),
                ))
            fig_vol.update_layout(
                **_layout(
                    height=340,
                    xaxis=dict(title="", tickformat="d", showgrid=False, zeroline=False,
                               linecolor=BORDER, ticks="outside", tickcolor=BORDER, ticklen=4),
                    yaxis=dict(title="Deals", gridcolor=BORDER_LIGHT),
                    legend=dict(orientation="h", y=1.08, font=dict(size=11, color=TXT2),
                                bgcolor="rgba(0,0,0,0)"),
                ),
                barmode="stack",
                hovermode="x unified",
            )
            st.plotly_chart(fig_vol, use_container_width=True, config=_PLOT_CFG)

        with col_size:
            st.markdown("**Median deal size by stage ($M, 2010–2024)**")
            SIZE_COLORS = {"Seed": GOLD, "Early VC": TEAL, "Growth": ACCENT}
            fig_size = go.Figure()
            for bucket, color in SIZE_COLORS.items():
                sub = deal_sizes[deal_sizes["stage_bucket"] == bucket]
                if sub.empty:
                    continue
                fig_size.add_trace(go.Scatter(
                    x=sub["year"], y=sub["median_m"].round(1),
                    name=bucket, mode="lines+markers",
                    line=dict(color=color, width=2),
                    marker=dict(size=6),
                ))
            fig_size.update_layout(
                **_layout(
                    height=340,
                    xaxis=dict(title="", tickformat="d", showgrid=False, zeroline=False,
                               linecolor=BORDER, ticks="outside", tickcolor=BORDER, ticklen=4),
                    yaxis=dict(title="Median deal size ($M)", gridcolor=BORDER_LIGHT),
                    legend=dict(orientation="h", y=1.08, font=dict(size=11, color=TXT2),
                                bgcolor="rgba(0,0,0,0)"),
                ),
                hovermode="x unified",
            )
            st.plotly_chart(fig_size, use_container_width=True, config=_PLOT_CFG)

    if not first_fin.empty:
        st.markdown("**First financing year: AI vs non-AI companies**")
        ai_df = first_fin[first_fin["company_type"] == "AI"]
        non_df = first_fin[first_fin["company_type"] == "Non-AI"]
        # Normalise to % within each group so scale difference doesn't dominate
        ai_total = ai_df["companies"].sum()
        non_total = non_df["companies"].sum()
        fig_ff = go.Figure()
        fig_ff.add_trace(go.Scatter(
            x=ai_df["first_year"], y=(ai_df["companies"] / ai_total * 100).round(2),
            name="AI companies", mode="lines+markers",
            line=dict(color=ACCENT, width=2.5), marker=dict(size=6),
        ))
        fig_ff.add_trace(go.Scatter(
            x=non_df["first_year"], y=(non_df["companies"] / non_total * 100).round(2),
            name="Non-AI companies", mode="lines+markers",
            line=dict(color=TXT3, width=2, dash="dot"), marker=dict(size=5),
        ))
        fig_ff.update_layout(
            **_layout(
                height=300,
                xaxis=dict(title="Year of first financing", tickformat="d", showgrid=False,
                           zeroline=False, linecolor=BORDER, ticks="outside",
                           tickcolor=BORDER, ticklen=4),
                yaxis=dict(title="Share of cohort (%)", ticksuffix="%", gridcolor=BORDER_LIGHT),
                legend=dict(orientation="h", y=1.08, font=dict(size=11, color=TXT2),
                            bgcolor="rgba(0,0,0,0)"),
            ),
            hovermode="x unified",
        )
        st.plotly_chart(fig_ff, use_container_width=True, config=_PLOT_CFG)

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Section 5: The hidden startup layer ──────────────────────────
    st.markdown(
        '<div class="eyebrow">The hidden startup layer</div>'
        '<div class="section-header">Companies commercial databases miss</div>'
        '<div class="section-sub" style="max-width:76ch;">Firms in this tracker that '
        'appear in neither Crunchbase nor PitchBook — discovered through GitHub, '
        'portfolio pages, US SBIR/STTR grants, and startup media. This is the '
        'tracker\'s unique contribution to measuring AI entrepreneurship.</div>',
        unsafe_allow_html=True,
    )

    adoption = _read_output_csv("13_hidden_vs_institutional_ai_adoption.csv")
    if not adoption.empty:
        lbl = {"hidden": "Hidden (this tracker)", "cb": "Crunchbase", "pb": "PitchBook"}
        cols = st.columns(len(adoption))
        for col, (_, r) in zip(cols, adoption.iterrows()):
            col.metric(f"{lbl.get(r['bucket'], r['bucket'])} — {int(r['total']):,} cos",
                       f"{r['ai_pct']:.1f}% AI")

    # Formation of hidden companies by discovery channel
    h_form = _read_output_csv("09a_hidden_formation_timeline.csv")
    h_surv = _read_output_csv("09b_hidden_survival_proxy_by_cohort.csv")
    hc1, hc2 = st.columns(2)
    with hc1:
        st.markdown(
            '<div class="section-header" style="margin-top:20px;">Hidden-company formation</div>'
            '<div class="section-sub">Founding year of hidden companies, by discovery channel</div>',
            unsafe_allow_html=True,
        )
        if not h_form.empty:
            hf = h_form[h_form["founded_year"].between(2010, 2025)]
            fig = go.Figure()
            for src, color in [("github", ACCENT), ("scraper", TEAL)]:
                s = hf[hf["source"] == src]
                if not s.empty:
                    fig.add_trace(go.Bar(
                        x=s["founded_year"], y=s["total"], name=src.capitalize(),
                        marker=dict(color=color),
                        hovertemplate="%{x} · " + src + ": %{y:,}<extra></extra>",
                    ))
            fig.update_layout(**_layout(
                height=300, barmode="stack",
                legend=dict(orientation="h", y=1.12, font=dict(size=11, color=TXT2),
                            bgcolor="rgba(0,0,0,0)"),
                margin=dict(l=0, r=4, t=8, b=0),
            ))
            st.plotly_chart(fig, use_container_width=True, config=_PLOT_CFG)
        else:
            st.caption("Analysis file not available in this deployment.")
    with hc2:
        st.markdown(
            '<div class="section-header" style="margin-top:20px;">Do they survive?</div>'
            '<div class="section-sub">Share of each founding cohort with a live website today</div>',
            unsafe_allow_html=True,
        )
        if not h_surv.empty:
            hs = h_surv[h_surv["founded_year"].between(2010, 2024)]
            fig = go.Figure(go.Scatter(
                x=hs["founded_year"], y=hs["live_pct"], mode="lines+markers",
                line=dict(color=ACCENT, width=2.5), marker=dict(size=7),
                customdata=hs["total_checked"],
                hovertemplate="%{x}: %{y:.1f}% live · n=%{customdata:,}<extra></extra>",
            ))
            fig.update_layout(**_layout(
                height=300, showlegend=False,
                yaxis=dict(ticksuffix="%", gridcolor=BORDER_LIGHT, zeroline=False,
                           linecolor="rgba(0,0,0,0)", range=[0, 105]),
                margin=dict(l=0, r=4, t=8, b=0),
            ))
            st.plotly_chart(fig, use_container_width=True, config=_PLOT_CFG)
            st.caption("Survival proxy: company website resolves as of the last check.")
        else:
            st.caption("Analysis file not available in this deployment.")

    # Hidden vs institutional: what they build
    h_vert = _read_output_csv("12_hidden_vs_institutional_verticals.csv")
    if not h_vert.empty:
        st.markdown(
            '<div class="section-header" style="margin-top:20px;">What hidden companies build</div>'
            '<div class="section-sub">Sector mix vs Crunchbase-registered firms (share of each group)</div>',
            unsafe_allow_html=True,
        )
        top_verts = (h_vert[h_vert["bucket"] == "hidden"]
                     .nlargest(8, "share_of_bucket_pct")["vertical"].tolist())
        hv = h_vert[h_vert["vertical"].isin(top_verts) & h_vert["bucket"].isin(["hidden", "cb"])]
        fig = go.Figure()
        for bucket, color, name in [("hidden", ACCENT, "Hidden (this tracker)"),
                                    ("cb", GRAY_CTX, "Crunchbase")]:
            s = (hv[hv["bucket"] == bucket].set_index("vertical")
                 .reindex(top_verts)["share_of_bucket_pct"])
            fig.add_trace(go.Bar(
                y=top_verts[::-1], x=s.reindex(top_verts[::-1]), orientation="h",
                name=name, marker=dict(color=color),
                text=[f"{v:.0f}%" if pd.notna(v) else "" for v in s.reindex(top_verts[::-1])],
                textposition="outside", textfont=dict(size=10.5, color=TXT2),
                hovertemplate="%{y} · " + name + ": %{x:.1f}%<extra></extra>",
            ))
        fig.update_layout(**_layout(
            height=380, barmode="group", bargap=0.25,
            xaxis=dict(ticksuffix="%", showgrid=False, zeroline=False, linecolor=BORDER),
            yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=11.5, color=TXT2)),
            legend=dict(orientation="h", y=1.08, font=dict(size=11, color=TXT2),
                        bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=0, r=24, t=8, b=0),
        ))
        st.plotly_chart(fig, use_container_width=True, config=_PLOT_CFG)

    st.caption(
        "Note: the grant-sourced subset of hidden companies (NIH/NSF SBIR/STTR) is "
        "US-only by construction and pulls the hidden bucket's geography toward the "
        "United States — read it as a distinct sub-population."
    )

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Section 6: Download aggregates ───────────────────────────────
    st.markdown(
        '<div class="section-header">Download the data</div>'
        '<div class="section-sub">Aggregate statistics only — company-level rows from '
        'commercial databases are not redistributed</div>',
        unsafe_allow_html=True,
    )

    dl1, dl2, dl3 = st.columns(3)
    with dl1:
        if not curve.empty:
            st.download_button(
                "Formation by year (CSV)", curve.to_csv(index=False),
                file_name="ai_formation_by_year.csv", mime="text/csv",
            )
    with dl2:
        if not country_stats.empty:
            st.download_button(
                "Country AI stats (CSV)", country_stats.to_csv(index=False),
                file_name="ai_concentration_by_country.csv", mime="text/csv",
            )
    with dl3:
        if not adoption.empty:
            st.download_button(
                "Hidden vs institutional (CSV)", adoption.to_csv(index=False),
                file_name="hidden_vs_institutional_ai.csv", mime="text/csv",
            )


# ── Info Sheet ───────────────────────────────────────────────────────

def _utcnow() -> datetime:
    """Naive UTC now — DB timestamps are timezone-naive UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@st.cache_data(ttl=1800)
def _load_contribution_stats() -> dict:
    """Non-overlapping source buckets + scraper detail for the Info Sheet.

    Bucket priority: CB / PB first (standard databases), then companies our
    scrapers found (has an incubator_signal), then GitHub-only. Buckets are
    mutually exclusive and sum exactly to the companies total.
    """
    engine = get_engine()
    with engine.connect() as conn:
        buckets = dict(conn.execute(text("""
            SELECT CASE
                     WHEN c.verification_status = 'verified_cb' THEN 'cb'
                     WHEN c.verification_status = 'verified_pb' THEN 'pb'
                     WHEN s.company_id IS NOT NULL THEN 'scraper'
                     ELSE 'github'
                   END AS bucket,
                   COUNT(*) AS n
            FROM companies c
            LEFT JOIN (SELECT DISTINCT company_id FROM incubator_signals) s
                   ON s.company_id = c.id
            GROUP BY 1
        """)).fetchall())

        overlap = dict(conn.execute(text("""
            SELECT c.verification_status::text, COUNT(DISTINCT s.company_id)
            FROM incubator_signals s
            JOIN companies c ON c.id = s.company_id
            WHERE c.verification_status IN ('verified_cb', 'verified_pb')
            GROUP BY 1
        """)).fetchall())

        scraper_sources = conn.execute(text("""
            SELECT s.source::text, COUNT(DISTINCT c.id)
            FROM companies c
            JOIN incubator_signals s ON s.company_id = c.id
            WHERE c.verification_status = 'emerging_github'
            GROUP BY 1 ORDER BY 2 DESC
        """)).fetchall()

        funding = conn.execute(text("""
            SELECT COUNT(*),
                   (SELECT COUNT(DISTINCT company_id) FROM funding_signals)
            FROM funding_signals
        """)).fetchone()

    return {
        "buckets": buckets,
        "overlap": overlap,
        "scraper_sources": [(s, n) for s, n in scraper_sources],
        "funding_rows": funding[0] if funding else 0,
        "funded_companies": funding[1] if funding else 0,
    }


_SCRAPER_SOURCE_LABELS = {
    "agentic_scrape": "Agentic scraper (Claude+Tavily over registered VC/accelerator/university sites)",
    "yc": "Y Combinator",
    "techstars": "Techstars",
    "harvard_ilabs": "Harvard Innovation Labs",
    "stanford_startx": "Stanford StartX",
    "entrepreneur_first": "Entrepreneur First",
    "mit_engine": "MIT The Engine",
    "berkeley_skydeck": "Berkeley SkyDeck",
    "princeton_elab": "Princeton eLab",
    "rice_owlspark": "Rice OwlSpark",
    "seedcamp": "Seedcamp",
    "antler": "Antler",
}


@st.cache_data(ttl=1800)
def _load_scraping_ops() -> dict:
    """Site inventory, run outcomes and error taxonomy for the Info Sheet."""
    engine = get_engine()
    with engine.connect() as conn:
        site_status = dict(conn.execute(text(
            "SELECT status, COUNT(*) FROM site_health GROUP BY 1"
        )).fetchall())

        cat_rows = conn.execute(text("""
            SELECT COALESCE(category, 'other') AS cat,
                   COUNT(*) AS sites,
                   COUNT(*) FILTER (WHERE status = 'healthy') AS healthy
            FROM site_health GROUP BY 1 ORDER BY 2 DESC
        """)).fetchall()

        run_stats = conn.execute(text("""
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE status = 'success'),
                   COALESCE(SUM(records_new) FILTER (WHERE status = 'success'), 0),
                   MAX(started_at)
            FROM scrape_runs
            WHERE started_at > NOW() - INTERVAL '30 days'
        """)).fetchone()

        lifetime = conn.execute(text("""
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE status = 'success'),
                   MAX(started_at)
            FROM scrape_runs
        """)).fetchone()

        errors = conn.execute(text("""
            SELECT CASE
                     WHEN error_message ILIKE '%tavily%' THEN 'Tavily API unreachable / timeout'
                     WHEN error_message ILIKE '%429%' THEN 'Anthropic rate limit (429)'
                     WHEN error_message ILIKE '%together%' THEN 'Together.ai auth (401)'
                     WHEN error_message ILIKE '%timed out%' OR error_message ILIKE '%timeout%' THEN 'Site timeout'
                     ELSE 'Other'
                   END AS kind, COUNT(*)
            FROM scrape_runs
            WHERE status = 'error' AND started_at > NOW() - INTERVAL '60 days'
            GROUP BY 1 ORDER BY 2 DESC
        """)).fetchall()

        struggling = pd.DataFrame(conn.execute(text("""
            SELECT domain, COALESCE(category, 'other') AS category, status,
                   consecutive_failures, last_success_at,
                   total_successes, total_runs,
                   COALESCE(pending_reason, LEFT(last_error, 90)) AS diagnosis
            FROM site_health
            WHERE status IN ('broken', 'degraded')
            ORDER BY total_successes DESC, consecutive_failures DESC
        """)).mappings().all())

    return {
        "site_status": site_status,
        "categories": [tuple(r) for r in cat_rows],
        "runs_30d": tuple(run_stats),
        "lifetime": tuple(lifetime),
        "errors_60d": [tuple(r) for r in errors],
        "struggling": struggling,
    }


_INFO_CATEGORY_LABELS = {
    "vc_portfolio": "VC portfolios",
    "university_incubator": "University incubators",
    "accelerator": "Accelerators",
    "government_program": "Government programs",
    "discovery_aggregator": "Discovery aggregators",
    "other": "Other / uncategorized",
}


@st.cache_data(ttl=1800)
def _load_pipeline_status() -> dict:
    """Live activity signals for every pipeline component (Info Sheet §3)."""
    engine = get_engine()
    with engine.connect() as conn:
        tier_last = dict(conn.execute(text(
            "SELECT difficulty, MAX(started_at) FROM scrape_runs GROUP BY 1"
        )).fetchall())
        gh_signals = conn.execute(text("SELECT COUNT(*) FROM github_signals")).scalar() or 0
        last_site_added = conn.execute(text("SELECT MAX(created_at) FROM site_health")).scalar()
        cov = conn.execute(text("""
            SELECT COUNT(*),
                   COUNT(founded_year),
                   COUNT(country),
                   COUNT(*) FILTER (WHERE categories IS NOT NULL
                                    AND array_length(categories, 1) > 0)
            FROM companies
        """)).fetchone()
        has_naics = bool(conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'companies' AND column_name = 'naics_code'
        """)).scalar())
    total = cov[0] or 1
    return {
        "last_easy": tier_last.get("easy"),
        "last_hard": tier_last.get("hard"),
        "gh_signals": gh_signals,
        "last_site_added": last_site_added,
        "founded_cov": cov[1] / total,
        "country_cov": cov[2] / total,
        "categories_cov": cov[3] / total,
        "has_naics": has_naics,
    }


def _activity_status(ts, active_days: int = 7):
    """(status label, last-activity string) from a timestamp."""
    if ts is None:
        return "⚪ Never ran", "—"
    days = (_utcnow() - ts).days
    if days <= active_days:
        return "🟢 Running", f"{ts:%b %d, %Y}"
    return "🔴 Stalled", f"{ts:%b %d, %Y} ({days}d ago)"


def _info_pipeline_section():
    try:
        ps = _load_pipeline_status()
    except Exception as e:
        st.error(f"Could not load pipeline status: {e}")
        return

    st.markdown(
        "How the database gets built: the **orchestrator** visits every registered "
        "site — site-specific *easy* scrapers first, and a Claude+Tavily *agentic* "
        "scraper for everything else. A **healer** watches outcomes (2 easy failures "
        "→ escalate to agentic; 3 agentic failures → exclude 90 days). **Discovery** "
        "agents add new sites, and **enrichment** scripts fill in missing fields."
    )

    easy_stat, easy_last = _activity_status(ps["last_easy"])
    hard_stat, hard_last = _activity_status(ps["last_hard"])
    scout_stat, scout_last = _activity_status(ps["last_site_added"], active_days=14)
    gh_stat = "⚪ Never ran" if ps["gh_signals"] == 0 else "🟢 Has data"
    revelio_stat = "🟢 Done" if ps["has_naics"] else "🟠 Incomplete"

    rows = [
        ("Easy-tier scrapers", "36 site-specific scrapers (YC, Techstars, HuggingFace, …)",
         easy_stat, easy_last, "scripts/run_orchestrator.py --batch"),
        ("Agentic scraper", "Claude+Tavily agent that can scrape any registered site",
         hard_stat, hard_last, "scripts/run_orchestrator.py --batch"),
        ("Healer / watchdog", "Escalates failing sites between tiers, writes diagnoses",
         hard_stat, hard_last, "runs inside the orchestrator"),
        ("International scout", "Finds new VC/accelerator sites to register (KR, IL, CN, …)",
         scout_stat, f"last new site {scout_last}", "scripts/run_international_scout.py"),
        ("GitHub discovery", "Weekly scan of GitHub orgs for emerging startups",
         gh_stat, f"{ps['gh_signals']:,} signals in DB", "scripts/github_weekly_discover.py"),
        ("LLM classifier", "Tags AI relevance + industry vertical (17-category taxonomy)",
         f"🟢 {ps['categories_cov']:.0%} coverage", "runs after imports", "scripts/run_llm_classify_failover.py"),
        ("Revelio enrichment", "LinkedIn workforce data → founded_year, NAICS codes",
         revelio_stat, "naics_code column present" if ps["has_naics"] else "naics_code column missing",
         "scripts/enrich_from_revelio.py"),
        ("Country fill / normalize", "TLD inference + normalizer after bulk imports",
         f"🟢 {ps['country_cov']:.0%} coverage", "maintenance script", "scripts/infer_country_from_tld.py"),
    ]
    comp_df = pd.DataFrame(rows, columns=["Component", "What it does", "Status", "Last activity", "How to run"])
    st.dataframe(comp_df, hide_index=True, use_container_width=True)

    # Auto-detected gaps — the professor's "want running but currently not running?"
    gaps = []
    if ps["last_easy"] is None or (_utcnow() - ps["last_easy"]).days > 7:
        gaps.append("**Scrapers are not running.** No scheduler is attached: Railway only "
                    "serves this dashboard, and the local launchd job is not loaded. "
                    "Scrapes happen only when someone runs the orchestrator manually.")
    if ps["gh_signals"] == 0:
        gaps.append("**GitHub discovery has never run** against this database "
                    "(`github_signals` is empty) — a planned weekly source that isn't wired up.")
    if not ps["has_naics"]:
        gaps.append("**Revelio enrichment is unfinished** — the NAICS-code backfill "
                    "(~292K companies) started Jun 21 but never landed here.")
    if gaps:
        st.warning("**Wanted running, but currently not:**\n\n" + "\n\n".join(f"- {g}" for g in gaps))
    else:
        st.success("All pipeline components show recent activity.")


def _info_scraping_section():
    try:
        ops = _load_scraping_ops()
    except Exception as e:
        st.error(f"Could not load scraping stats: {e}")
        return

    ss = ops["site_status"]
    total_sites = sum(ss.values())
    healthy = ss.get("healthy", 0)
    struggling_n = ss.get("broken", 0) + ss.get("degraded", 0)

    runs30, ok30, new30, last30 = ops["runs_30d"]
    runs_all, ok_all, last_run = ops["lifetime"]

    # Stall banner — the single most important operational fact on this page.
    if last_run is None:
        st.error("The scraping pipeline has never run.")
    else:
        days_idle = (_utcnow() - last_run).days
        if days_idle > 7:
            st.error(
                f"**Scraping pipeline is STALLED** — last run was {last_run:%b %d, %Y} "
                f"({days_idle} days ago). Nothing is scheduled to run it automatically; "
                "see section 3 below."
            )
        else:
            st.success(f"Scraping pipeline active — last run {last_run:%b %d, %Y}.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Websites registered", f"{total_sites:,}")
    m2.metric("Currently healthy", f"{healthy:,}",
              f"{healthy / total_sites:.0%} of sites" if total_sites else None, delta_color="off")
    m3.metric("Struggling (broken + degraded)", f"{struggling_n:,}")
    m4.metric("Lifetime success rate",
              f"{ok_all / runs_all:.0%}" if runs_all else "—",
              f"{ok_all:,} of {runs_all:,} runs", delta_color="off")

    col_status, col_cat = st.columns(2)
    with col_status:
        st.markdown("**Site status**")
        order = ["healthy", "degraded", "broken", "pending", "excluded"]
        desc = {
            "healthy": "producing records",
            "degraded": "partially failing",
            "broken": "failing — needs attention",
            "pending": "registered, never run",
            "excluded": "gave up (90-day exclusion)",
        }
        stat_df = pd.DataFrame(
            [(s, ss.get(s, 0), desc[s]) for s in order if ss.get(s, 0)],
            columns=["Status", "Sites", "Meaning"],
        )
        st.dataframe(stat_df, hide_index=True, use_container_width=True)
    with col_cat:
        st.markdown("**By site category**")
        cat_df = pd.DataFrame(
            [(_INFO_CATEGORY_LABELS.get(c, c), n, h, f"{h / n:.0%}" if n else "—")
             for c, n, h in ops["categories"]],
            columns=["Category", "Sites", "Healthy", "Healthy %"],
        )
        st.dataframe(cat_df, hide_index=True, use_container_width=True)

    st.markdown("**Recent activity (last 30 days)**")
    a1, a2, a3 = st.columns(3)
    a1.metric("Scrape runs", f"{runs30:,}")
    a2.metric("Successful", f"{ok30:,}",
              f"{ok30 / runs30:.0%} success rate" if runs30 else None, delta_color="off")
    a3.metric("New companies collected", f"{int(new30):,}")

    if ops["errors_60d"]:
        err_total = sum(n for _, n in ops["errors_60d"])
        st.markdown("**Why runs fail** (errors, last 60 days)")
        err_df = pd.DataFrame(ops["errors_60d"], columns=["Failure cause", "Runs"])
        err_df["Share"] = (err_df["Runs"] / err_total).map("{:.0%}".format)
        st.dataframe(err_df, hide_index=True, use_container_width=True)
        st.caption(
            "Nearly all failures are external-API issues (Tavily connectivity, "
            "Anthropic rate limits), not site problems — retry with backoff "
            "recovers most of these sites without any new code per site."
        )

    strug = ops["struggling"]
    if not strug.empty:
        with st.expander(f"Monitoring: all {len(strug)} struggling sites", expanded=False):
            view = strug.rename(columns={
                "domain": "Domain", "category": "Category", "status": "Status",
                "consecutive_failures": "Consecutive failures",
                "last_success_at": "Last success",
                "total_successes": "Lifetime successes",
                "total_runs": "Lifetime runs",
                "diagnosis": "Diagnosis / last error",
            })
            view["Category"] = view["Category"].map(lambda c: _INFO_CATEGORY_LABELS.get(c, c))
            view = view[["Domain", "Category", "Status", "Consecutive failures",
                         "Last success", "Lifetime successes", "Lifetime runs",
                         "Diagnosis / last error"]]
            st.dataframe(view, hide_index=True, use_container_width=True, height=420)


def _info_sources_section():
    try:
        stats = _load_contribution_stats()
    except Exception as e:
        st.error(f"Could not load contribution stats: {e}")
        return

    b = stats["buckets"]
    cb, pb = b.get("cb", 0), b.get("pb", 0)
    scraper, github = b.get("scraper", 0), b.get("github", 0)
    total = cb + pb + scraper + github
    unique_ours = scraper + github

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total companies", f"{total:,}")
    m2.metric("Covered by Crunchbase", f"{cb:,}", f"{cb / total:.1%} of total" if total else None, delta_color="off")
    m3.metric("Covered by PitchBook", f"{pb:,}", f"{pb / total:.1%} of total" if total else None, delta_color="off")
    m4.metric("Only we have", f"{unique_ours:,}", f"{unique_ours / total:.1%} of total" if total else None, delta_color="off")

    rows = [
        ("Crunchbase", cb, "Standard database — bulk import, used as the enrichment layer"),
        ("PitchBook", pb, "Standard database — bulk import; also the source of all funding-deal records"),
        ("Our scrapers", scraper, "NOT in CB/PB — found by our own scraping of accelerator, VC and university sites"),
        ("GitHub discovery", github, "NOT in CB/PB — emerging companies found via GitHub organization scans"),
    ]
    src_df = pd.DataFrame(rows, columns=["Source", "Companies", "What it is"])
    src_df["Share"] = (src_df["Companies"] / total).map("{:.1%}".format) if total else "—"

    chart_col, table_col = st.columns([2, 3])
    with chart_col:
        fig = go.Figure()
        colors = {"Crunchbase": BLUE_RAMP[2], "PitchBook": BLUE_RAMP[0],
                  "Our scrapers": CAT[1], "GitHub discovery": CAT[2]}
        for name, n, _ in rows:
            fig.add_trace(go.Bar(
                y=["Companies"], x=[n], name=name, orientation="h",
                marker_color=colors[name],
                hovertemplate=f"{name}: {n:,}<extra></extra>",
            ))
        fig.update_layout(
            barmode="stack", height=160, showlegend=True,
            legend=dict(orientation="h", y=-0.4),
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis=dict(title=None), yaxis=dict(visible=False),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.caption("Buckets are mutually exclusive and sum exactly to the total.")
    with table_col:
        st.dataframe(src_df[["Source", "Companies", "Share", "What it is"]],
                     hide_index=True, use_container_width=True)

    cb_overlap = stats["overlap"].get("verified_cb", 0)
    pb_overlap = stats["overlap"].get("verified_pb", 0)
    st.markdown(
        f"**Cross-validation:** our scrapers independently re-discovered "
        f"**{cb_overlap:,}** Crunchbase and **{pb_overlap:,}** PitchBook companies "
        f"(counted once, under CB/PB above). Funding data: "
        f"**{stats['funding_rows']:,}** deal records covering "
        f"**{stats['funded_companies']:,}** companies, all from PitchBook."
    )

    with st.expander(f"Where the {scraper:,} scraper-unique companies came from", expanded=False):
        det = pd.DataFrame(
            [(_SCRAPER_SOURCE_LABELS.get(s, s), n) for s, n in stats["scraper_sources"]],
            columns=["Scraper source", "Unique companies (not in CB/PB)"],
        )
        st.dataframe(det, hide_index=True, use_container_width=True)


def page_info_sheet():
    """One-page summary for collaborators: where the data comes from, what
    runs to build it, and how scraping is doing.

    Sections are filled in incrementally — see reports/INFO_SHEET_PLAN.md
    for the step plan and how to resume.
    """
    st.markdown(
        '<div class="section-header">Info Sheet</div>'
        '<div class="section-sub">Everything about this database on one page — '
        'data provenance, scraping operations, and pipeline status</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"Generated {_utcnow():%Y-%m-%d %H:%M} UTC — "
        "all numbers query the live production database"
    )

    st.markdown('<div class="section-header">1 · Where the data comes from</div>'
                '<div class="section-sub">How much is covered by standard databases '
                '(Crunchbase / PitchBook), and where the rest came from</div>',
                unsafe_allow_html=True)
    _info_sources_section()

    st.markdown('<div class="section-header">2 · Scraping operations</div>'
                '<div class="section-sub">How many websites we scrape, how many succeed, '
                'and which ones are struggling</div>',
                unsafe_allow_html=True)
    _info_scraping_section()

    st.markdown('<div class="section-header">3 · Pipeline components — running vs. not</div>'
                '<div class="section-sub">Every agent and script that builds this database, '
                'and whether it is currently running</div>',
                unsafe_allow_html=True)
    _info_pipeline_section()


# ── Main ─────────────────────────────────────────────────────────────

def _company_frames():
    """Load companies and split by source.

    GitHub Discovery: came in via GitHub scan (no incubator_source, has a repo)
    Scraper:          came in via accelerator/incubator scrapers
    """
    df = load_startups()
    if not df.empty:
        inc = df["incubator_source"].astype("string")
        has_repo = df["github_repo"].notna() if "github_repo" in df.columns else pd.Series([False] * len(df))
        is_gh = inc.isna() & has_repo
    else:
        is_gh = pd.Series([], dtype=bool)

    scraper_df = df[~is_gh].copy() if not df.empty else df
    github_df_all = df[is_gh].copy() if not df.empty else df
    return scraper_df, github_df_all


# Public pages lead; operations pages live behind the "Internal" tab.
_PUBLIC_PAGES = ["Overview", "Findings", "Companies", "GitHub Discovery", "About"]
_INTERNAL_PAGES = ["AI Analysis", "Trends", "Pipeline Health", "Inventory", "Scraper"]


def main():
    # ── Header: brand + primary nav on one row, hairline under both ──
    with st.container(key="header"):
        bcol, ncol = st.columns([1, 2.4], vertical_alignment="center")
        with bcol:
            st.markdown(
                '<div class="brand">'
                '<span class="brand-mark">AI</span>'
                '<span class="brand-text">'
                '<span class="brand-name">AI Startup Tracker</span>'
                '<span class="brand-sub">Tobin Center for Economic Policy &middot; Yale</span>'
                '</span>'
                '</div>',
                unsafe_allow_html=True,
            )
        with ncol:
            with st.container(key="lnav"):
                section = st.radio("Navigation", _PUBLIC_PAGES + ["Internal"],
                                   horizontal=True, label_visibility="collapsed")
        st.markdown('<div class="header-rule"></div>', unsafe_allow_html=True)

    page = section
    if section == "Internal":
        with st.container(key="subnav"):
            page = st.radio("Internal pages", _INTERNAL_PAGES,
                            horizontal=True, label_visibility="collapsed")

    # ── Main content: render only the selected page ──────────────────
    with st.container(key="page"):
        if page == "Overview":
            page_home()
        elif page == "Findings":
            page_research()
        elif page == "Companies":
            page_companies()
        elif page == "GitHub Discovery":
            _sc, github_df_all = _company_frames()
            # LLM filter: only keep repos classified as 'startup' by the LLM
            if "llm_classification" in github_df_all.columns:
                github_df = github_df_all[github_df_all["llm_classification"] == "startup"].copy()
            else:
                github_df = github_df_all.iloc[0:0].copy()
            page_github(github_df, github_df_all)
        elif page == "About":
            page_about()
        elif page == "AI Analysis":
            scraper_df, _gh = _company_frames()
            page_ai_analysis(scraper_df, _load_overview_stats(),
                             source_stats=_load_source_ai_stats(),
                             country_stats=_load_country_ai_stats(min_companies=1))
        elif page == "Trends":
            scraper_df, _gh = _company_frames()
            page_trends(scraper_df)
        elif page == "Pipeline Health":
            page_health(load_site_health(), load_recent_runs())
        elif page == "Inventory":
            page_inventory()
        elif page == "Scraper":
            page_scraper()


if __name__ == "__main__":
    main()
