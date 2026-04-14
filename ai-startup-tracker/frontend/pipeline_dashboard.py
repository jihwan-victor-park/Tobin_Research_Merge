"""
AI Startup Tracker - GitHub-first Pipeline Dashboard
=====================================================
Streamlit dashboard for the new pipeline (companies, github_signals, funding_signals).
Includes trend analysis, category classification, and geographic breakdowns.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import sys
import os
import json
from datetime import datetime, timedelta
from glob import glob

from dotenv import load_dotenv
from sqlalchemy import text
import pandas.api.types as pdt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.db.connection import get_engine, session_scope
from backend.db.models import Company, GithubSignal, FundingSignal, SourceMatch, IncubatorSignal
from backend.agentic import run_agentic_scrape, load_registered_sites

# Page config
st.set_page_config(
    page_title="AI Startup Tracker",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    /* ── Base ─────────────────────────────── */
    .main { background-color: #0e1117; }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1f2e 0%, #1e2538 100%);
        padding: 16px 20px;
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.06);
    }
    [data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 700; }
    [data-testid="stMetricLabel"] { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; opacity: 0.6; }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #111827 0%, #0f1419 100%);
        border-right: 1px solid rgba(255,255,255,0.05);
    }
    section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
        width: 100%; border-radius: 8px; font-weight: 600;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 8px 16px;
        font-size: 0.85rem;
        font-weight: 500;
    }

    /* Tables */
    [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

    /* Expanders */
    [data-testid="stExpander"] {
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 10px;
    }

    /* Title */
    h1 { color: #60a5fa; font-weight: 800; letter-spacing: -0.02em; }
</style>
""", unsafe_allow_html=True)


# ── Data loading (cached) ─────────────────────────────────────────────

def _read_sql_df(query: str, engine) -> pd.DataFrame:
    """Load via SQLAlchemy 2.0 only — avoids pandas read_sql + Engine/Connection quirks."""
    with engine.connect() as conn:
        result = conn.execute(text(query))
        columns = list(result.keys())
        rows = result.mappings().all()
        if not rows:
            return pd.DataFrame(columns=columns)
        return pd.DataFrame([dict(row) for row in rows])


def _px_category_orders(
    df: pd.DataFrame,
    column: str,
    desired: list | tuple | None = None,
    *,
    strip_strings: bool = True,
) -> dict:
    """
    Plotly Express: category_orders must not list values missing from the frame, or
    internal groupby.get_group can raise KeyError.

    Returns empty dict (= let Plotly auto-detect) to avoid any KeyError.
    Plotly's internal groupby is fragile with sparse category×color combos.
    """
    # Safest approach: don't pass category_orders at all.
    # Plotly will auto-detect categories from the data.
    return {}


@st.cache_data(ttl=300)
def load_companies():
    """Load all companies from DB."""
    engine = get_engine()
    query = """
        SELECT c.id, c.name, c.domain, c.normalized_name,
               c.country, c.city, c.latitude, c.longitude, c.location_source,
               c.verification_status, c.ai_score, c.startup_score, c.ai_tags,
               c.first_seen_at, c.last_seen_at, c.created_at
        FROM companies c
        ORDER BY c.ai_score DESC NULLS LAST, c.startup_score DESC NULLS LAST
    """
    return _read_sql_df(query, engine)


@st.cache_data(ttl=300)
def load_github_signals():
    """Load github signals."""
    engine = get_engine()
    query = """
        SELECT gs.id, gs.company_id, gs.repo_full_name, gs.repo_url,
               gs.owner_login, gs.owner_type, gs.description, gs.topics,
               gs.homepage_url, gs.created_at, gs.pushed_at,
               gs.stars, gs.forks, gs.collected_at
        FROM github_signals gs
        ORDER BY gs.stars DESC NULLS LAST
    """
    return _read_sql_df(query, engine)


@st.cache_data(ttl=300)
def load_funding_signals():
    """Load funding signals with company name and match method."""
    engine = get_engine()
    query = """
        SELECT fs.id, fs.company_id, c.name AS company_name, c.domain,
               fs.source, fs.deal_date,
               fs.round_type, fs.deal_size, fs.investors, fs.collected_at,
               sm.match_method, sm.match_confidence
        FROM funding_signals fs
        JOIN companies c ON c.id = fs.company_id
        LEFT JOIN LATERAL (
            SELECT sm2.match_method, sm2.match_confidence
            FROM source_matches sm2
            WHERE sm2.company_id = fs.company_id
              AND sm2.pitchbook_id IS NOT NULL
            LIMIT 1
        ) sm ON true
        ORDER BY fs.deal_date DESC NULLS LAST
    """
    return _read_sql_df(query, engine)


@st.cache_data(ttl=300)
def load_latest_snapshots():
    """Load the most recent snapshot per repo (for trending)."""
    engine = get_engine()
    # Check if table exists first
    try:
        query = """
            SELECT DISTINCT ON (repo_full_name)
                   repo_full_name, collected_at,
                   stars, forks, open_issues, watchers, size_kb,
                   pushed_at, language, license,
                   owner_login, owner_type,
                   ai_subdomain, stack_layer,
                   startup_likelihood, trend_score,
                   stars_7d_delta, forks_7d_delta, issues_7d_delta,
                   description, homepage_url,
                   llm_classification, llm_confidence, llm_reason
            FROM github_repo_snapshots
            ORDER BY repo_full_name, collected_at DESC
        """
        return _read_sql_df(query, engine)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_latest_trend_report():
    """Load the latest trend report JSON."""
    report_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    pattern = os.path.join(report_dir, "github_weekly_trends_*.json")
    report_files = sorted(glob(pattern), reverse=True)
    if report_files:
        with open(report_files[0]) as f:
            return json.load(f)
    return None


@st.cache_data(ttl=300)
def load_latest_report():
    """Load the latest weekly report JSON (legacy)."""
    report_files = sorted(glob("data/weekly_report_*.json"), reverse=True)
    if report_files:
        with open(report_files[0]) as f:
            return json.load(f)
    return None


@st.cache_data(ttl=300)
def load_incubator_signals():
    """Load incubator signals with company info."""
    engine = get_engine()
    try:
        query = """
            SELECT ins.id, ins.company_id, ins.source, ins.company_name_raw,
                   ins.website_url, ins.industry, ins.batch, ins.program,
                   ins.description, ins.profile_url, ins.collected_at,
                   c.name AS company_name, c.domain, c.ai_score, c.startup_score,
                   c.country, c.city, c.verification_status, c.incubator_source
            FROM incubator_signals ins
            JOIN companies c ON c.id = ins.company_id
            ORDER BY ins.source, ins.company_name_raw
        """
        return _read_sql_df(query, engine)
    except Exception:
        return pd.DataFrame()


# ── Helper functions ───────────────────────────────────────────────────

def is_tracked(row):
    return (row.get("ai_score") or 0) >= 0.6 and (row.get("startup_score") or 0) >= 0.6


COUNTRY_COORDS = {
    "US": (37.09, -95.71), "USA": (37.09, -95.71), "United States": (37.09, -95.71),
    "GB": (55.38, -3.44), "UK": (55.38, -3.44), "United Kingdom": (55.38, -3.44),
    "DE": (51.17, 10.45), "Germany": (51.17, 10.45),
    "FR": (46.23, 2.21), "France": (46.23, 2.21),
    "CN": (35.86, 104.20), "China": (35.86, 104.20),
    "IN": (20.59, 78.96), "India": (20.59, 78.96),
    "CA": (56.13, -106.35), "Canada": (56.13, -106.35),
    "IL": (31.05, 34.85), "Israel": (31.05, 34.85),
    "SG": (1.35, 103.82), "Singapore": (1.35, 103.82),
    "JP": (36.20, 138.25), "Japan": (36.20, 138.25),
    "KR": (35.91, 127.77), "South Korea": (35.91, 127.77),
    "AU": (-25.27, 133.78), "Australia": (-25.27, 133.78),
    "BR": (-14.24, -51.93), "Brazil": (-14.24, -51.93),
    "SE": (60.13, 18.64), "Sweden": (60.13, 18.64),
    "NL": (52.13, 5.29), "Netherlands": (52.13, 5.29),
    "CH": (46.82, 8.23), "Switzerland": (46.82, 8.23),
    "IE": (53.14, -7.69), "Ireland": (53.14, -7.69),
    "ES": (40.46, -3.75), "Spain": (40.46, -3.75),
    "IT": (41.87, 12.57), "Italy": (41.87, 12.57),
    "AE": (23.42, 53.85), "UAE": (23.42, 53.85),
    "EE": (58.60, 25.01), "Estonia": (58.60, 25.01),
    "FI": (61.92, 25.75), "Finland": (61.92, 25.75),
    "PL": (51.92, 19.15), "Poland": (51.92, 19.15),
    "TW": (23.70, 120.96), "Taiwan": (23.70, 120.96),
    "HK": (22.32, 114.17), "Hong Kong": (22.32, 114.17),
    "RU": (61.52, 105.32), "Russia": (61.52, 105.32),
    "TR": (38.96, 35.24), "Turkey": (38.96, 35.24),
    "UA": (48.38, 31.17), "Ukraine": (48.38, 31.17),
    "AT": (47.52, 14.55), "Austria": (47.52, 14.55),
    "DK": (56.26, 9.50), "Denmark": (56.26, 9.50),
    "NO": (60.47, 8.47), "Norway": (60.47, 8.47),
    "PT": (39.40, -8.22), "Portugal": (39.40, -8.22),
    "CZ": (49.82, 15.47), "Czechia": (49.82, 15.47),
    "MX": (23.63, -102.55), "Mexico": (23.63, -102.55),
    "AR": (-38.42, -63.62), "Argentina": (-38.42, -63.62),
    "NZ": (-40.90, 174.89), "New Zealand": (-40.90, 174.89),
    "ZA": (-30.56, 22.94), "South Africa": (-30.56, 22.94),
    "NG": (9.08, 8.68), "Nigeria": (9.08, 8.68),
    "KE": (-0.02, 37.91), "Kenya": (-0.02, 37.91),
    "ID": (-0.79, 113.92), "Indonesia": (-0.79, 113.92),
    "TH": (15.87, 100.99), "Thailand": (15.87, 100.99),
    "VN": (14.06, 108.28), "Vietnam": (14.06, 108.28),
    "MY": (4.21, 101.98), "Malaysia": (4.21, 101.98),
    "PH": (12.88, 121.77), "Philippines": (12.88, 121.77),
}


def _project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _agentic_runs_dir() -> str:
    return os.path.join(_project_root(), "reports", "agentic_runs")


def _write_agentic_report_json(report) -> str | None:
    """Persist one run to reports/agentic_runs/{run_id}.json. Returns path or None."""
    try:
        d = _agentic_runs_dir()
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, f"{report.run_id}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(mode="json"), f, indent=2, default=str)
        return out
    except Exception:
        return None


def _flatten_agentic_report_previews(reports: list[dict]) -> list[dict]:
    """One row per company with source_site for tables."""
    rows: list[dict] = []
    for r in reports:
        domain = r.get("site_domain") or r.get("input_url", "")
        for rec in r.get("extracted_preview") or []:
            rows.append({**rec, "source_site": domain})
    return rows


def _load_latest_agentic_reports(limit: int = 200) -> list[dict]:
    """Load most recent agentic run reports from disk, deduped by domain (keep latest)."""
    runs_dir = _agentic_runs_dir()
    if not os.path.isdir(runs_dir):
        return []
    pattern = os.path.join(runs_dir, "agentic_run_*.json")
    files = sorted(glob(pattern), key=lambda p: os.path.getmtime(p), reverse=True)
    reports = []
    seen_domains: set = set()
    for f in files[:500]:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            # Dedup: keep only the latest report per domain
            domain = data.get("site_domain") or data.get("input_url", "")
            if domain in seen_domains:
                continue
            seen_domains.add(domain)
            reports.append(data)
            if len(reports) >= limit:
                break
        except Exception:
            continue
    return reports


def _render_results_table(records: list, height: int = 450):
    """Reusable company results table."""
    if not records:
        return
    df = pd.DataFrame(records)
    cols, rename = [], {}
    for col, label in [
        ("source_site", "Source"), ("name", "Company"), ("industry", "Industry"),
        ("country", "Country"), ("city", "City"), ("is_ai_startup", "AI?"),
        ("ai_category", "AI Category"), ("website_url", "Website"),
    ]:
        if col in df.columns:
            cols.append(col)
            rename[col] = label
    st.dataframe(df[cols].rename(columns=rename), use_container_width=True, height=height)


def render_ai_scraper_tab():
    """Tavily + Claude agentic scrape: single URL or view results."""

    # ── All scraped companies (persistent) ───────────────────────
    cached_reports = _load_latest_agentic_reports()
    all_cached_records = _flatten_agentic_report_previews(cached_reports) if cached_reports else []

    if all_cached_records:
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Sites Scraped", len(cached_reports))
        with m2:
            st.metric("Companies Found", len(all_cached_records))
        with m3:
            ai_ct = sum(1 for r in all_cached_records if r.get("is_ai_startup"))
            st.metric("AI Startups", ai_ct)

        _render_results_table(all_cached_records, height=500)
        st.caption(f"{len(all_cached_records)} companies from {len(cached_reports)} sites")
    else:
        st.info("No scraped data yet. Use the sidebar to run a batch scrape, or scrape a single URL below.")

    st.divider()

    # ── Single URL Scrape ────────────────────────────────────────
    st.markdown("##### Scrape a URL")
    url_col, btn_col = st.columns([4, 1])
    with url_col:
        url = st.text_input(
            "URL", placeholder="https://example.com/portfolio",
            key="agentic_url", label_visibility="collapsed",
        )
    with btn_col:
        run_btn = st.button("Scrape", type="primary", key="agentic_run_btn", use_container_width=True)

    if run_btn:
        if not (url or "").strip():
            st.warning("Enter a URL.")
            return
        status = st.status("Scraping…", expanded=True)

        def _progress(msg: str):
            status.write(msg)

        try:
            report = run_agentic_scrape(
                url=url.strip(), save_to_db=True, max_retries=2,
                progress_callback=_progress,
            )
        except Exception as e:
            status.update(label="Failed", state="error")
            st.error(str(e))
            return

        status.update(label="Done", state="complete")
        load_companies.clear()
        _write_agentic_report_json(report)

        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Extracted", report.total_records_after_clean)
        with m2:
            st.metric("New", report.db_new_companies)
        with m3:
            st.metric("Updated", report.db_updated_companies)

        prev = report.extracted_preview or []
        if prev:
            for rec in prev:
                rec["source_site"] = report.site_domain or report.input_url
            _render_results_table(prev)


def render_scrape_history_tab():
    """Instruction YAML files + agent run JSON + scheduler logs."""
    st.markdown("### Scrape history")
    root = _project_root()

    sub1, sub2, sub3 = st.tabs(["Instruction YAMLs", "Agent run reports", "Scheduler logs"])

    inst_dir = os.path.join(root, "data", "scrape_instructions")
    with sub1:
        pattern = os.path.join(inst_dir, "*.yaml")
        yamls = sorted(glob(pattern))
        if not yamls:
            st.info("No instruction files yet. Run a successful AI Scraper job to create `data/scrape_instructions/<domain>.yaml`.")
        else:
            choice = st.selectbox("File", yamls, format_func=lambda p: os.path.basename(p), key="hist_yaml_pick")
            if choice and os.path.isfile(choice):
                with open(choice, "r", encoding="utf-8") as f:
                    content = f.read()
                st.code(content, language="yaml")

    runs_dir = os.path.join(root, "reports", "agentic_runs")
    with sub2:
        pattern = os.path.join(runs_dir, "agentic_run_*.json")
        reports = sorted(glob(pattern), key=lambda p: os.path.getmtime(p), reverse=True)
        if not reports:
            st.info("No agentic run JSON files in `reports/agentic_runs/`.")
        else:
            choice = st.selectbox(
                "Recent reports (newest first)",
                reports[:100],
                format_func=lambda p: f"{os.path.basename(p)}  ({datetime.utcfromtimestamp(os.path.getmtime(p)).isoformat()}Z)",
                key="hist_report_pick",
            )
            if choice and os.path.isfile(choice):
                with open(choice, "r", encoding="utf-8") as f:
                    data = json.load(f)
                st.json(data)

    log_dir = os.path.join(root, "reports", "scheduler_logs")
    with sub3:
        pattern = os.path.join(log_dir, "*.log")
        logs = sorted(glob(pattern), key=lambda p: os.path.getmtime(p), reverse=True)
        if not logs:
            st.info("No scheduler logs yet (`reports/scheduler_logs/*.log`). Run `scripts/run_scheduled_scraper.py`.")
        else:
            choice = st.selectbox(
                "Log files",
                logs[:50],
                format_func=lambda p: os.path.basename(p),
                key="hist_log_pick",
            )
            if choice and os.path.isfile(choice):
                with open(choice, "r", encoding="utf-8") as f:
                    tail = f.read()[-80000:]
                st.text_area("Tail (last ~80k chars)", tail, height=400, key="hist_log_body")


# ── Main ───────────────────────────────────────────────────────────────

def main():
    load_dotenv()
    # Clear stale module-level orders (e.g. CA/NY/TX) so filtered DataFrames cannot hit KeyError.
    px.defaults.category_orders = {}

    st.title("AI Startup Tracker")
    st.caption("Discover, track, and analyze AI startups across 113+ sources")

    # Load data
    try:
        df = load_companies()
        gh_df = load_github_signals()
        fund_df = load_funding_signals()
        snap_df = load_latest_snapshots()
        inc_df = load_incubator_signals()
        trend_report = load_latest_trend_report()
    except Exception as e:
        st.error(f"Database error: {e}")
        return

    if len(df) == 0:
        st.info("No companies yet. Use the AI Scraper tab or sidebar to start scraping.")

    has_snapshots = len(snap_df) > 0

    # Compute tracked vs candidates
    df["is_tracked"] = df.apply(is_tracked, axis=1)
    tracked_count = df["is_tracked"].sum()
    candidate_count = len(df) - tracked_count

    # ── Sidebar: Scraper Controls + Live Log ─────────────────────
    with st.sidebar:
        st.header("AI Scraper")
        _sb_sites = load_registered_sites()

        sb_col1, sb_col2 = st.columns(2)
        with sb_col1:
            sb_save_db = st.checkbox("Save to DB", value=True, key="sb_save_db")
        with sb_col2:
            sb_force = st.checkbox("Force re-scrape", value=False, key="sb_force")

        sb_run_btn = st.button(
            f"Run All {len(_sb_sites)} Sites",
            type="primary",
            key="sb_run_all",
            use_container_width=True,
        )

        # Live progress log container
        sb_log = st.container(height=500)

        if sb_run_btn:
            _sb_all_reports = []
            _sb_failed = []
            sb_log.markdown(f"**Scraping {len(_sb_sites)} sites…**")
            sb_progress = st.sidebar.progress(0)

            for _i, _site in enumerate(_sb_sites):
                sb_log.markdown(f"━━━ [{_i+1}/{len(_sb_sites)}] **{_site['name']}** ━━━")

                def _sb_progress_cb(msg, _log=sb_log):
                    _log.caption(msg)

                try:
                    _report = run_agentic_scrape(
                        url=_site["url"],
                        save_to_db=sb_save_db,
                        max_retries=1,
                        force=sb_force,
                        progress_callback=_sb_progress_cb,
                    )
                    _sb_all_reports.append(_report)
                    sb_log.markdown(
                        f"&rarr; **{_report.total_records_after_clean}** companies "
                        f"({_report.db_new_companies} new, {_report.db_updated_companies} updated)"
                    )
                except Exception as _e:
                    _sb_failed.append(_site["name"])
                    sb_log.markdown(f"&rarr; FAILED: {_e}")

                sb_progress.progress((_i + 1) / len(_sb_sites))

            sb_log.markdown("---")
            _total_ext = sum(r.total_records_after_clean for r in _sb_all_reports)
            _total_new = sum(r.db_new_companies for r in _sb_all_reports)
            sb_log.markdown(f"**Done!** {_total_ext} companies, {_total_new} new")
            if _sb_failed:
                sb_log.markdown(f"**Failed:** {', '.join(_sb_failed)}")

            if sb_save_db:
                load_companies.clear()

            st.session_state["last_agentic_batch_reports"] = [
                _r.model_dump(mode="json") for _r in _sb_all_reports
            ]
            st.session_state.pop("last_agentic_single_report", None)
            for _r in _sb_all_reports:
                _write_agentic_report_json(_r)
        else:
            # When not running, show last run results with expandable details
            _report_dir = os.path.join(_project_root(), "reports", "agentic_runs")
            _report_files = sorted(
                glob(os.path.join(_report_dir, "agentic_run_*.json")),
                key=lambda p: os.path.getmtime(p),
                reverse=True,
            ) if os.path.isdir(_report_dir) else []

            if _report_files:
                # Dedup by domain, keep latest
                _sb_seen: set = set()
                _sb_reports: list = []
                for _rf in _report_files[:500]:
                    try:
                        with open(_rf, "r", encoding="utf-8") as _f:
                            _rd = json.load(_f)
                        _domain = _rd.get("site_domain") or _rd.get("input_url", "")
                        if _domain in _sb_seen:
                            continue
                        _sb_seen.add(_domain)
                        _sb_reports.append(_rd)
                    except Exception:
                        continue

                _sb_total = sum(r.get("total_records_after_clean", 0) for r in _sb_reports)
                sb_log.markdown(f"**{len(_sb_reports)} sites scraped** | {_sb_total} companies total")

                for _rd in _sb_reports:
                    _domain = _rd.get("site_domain") or _rd.get("input_url", "?")
                    _count = _rd.get("total_records_after_clean", 0)
                    _label = f"{_domain} ({_count})"

                    with sb_log.expander(_label, expanded=False):
                        # Summary line
                        _new = _rd.get("db_new_companies", 0)
                        _upd = _rd.get("db_updated_companies", 0)
                        _val = _rd.get("final_validation", {})
                        st.caption(f"{_new} new, {_upd} updated")

                        # Attempts / pipeline steps
                        for _att in _rd.get("attempts", []):
                            _strat = _att.get("strategy", "?")
                            _att_val = _att.get("validation", {})
                            _rec_count = _att_val.get("record_count", 0)
                            _reason = _att_val.get("reason", "")
                            _urls = _att.get("fetched_urls", [])
                            st.markdown(f"**{_strat}** - {_rec_count} records")
                            st.caption(_reason)
                            if _urls:
                                st.caption("Fetched: " + ", ".join(_urls[:4]))

                        # Instruction info
                        _instr_loaded = _rd.get("instruction_loaded", False)
                        _instr_saved = _rd.get("instruction_saved", False)
                        if _instr_loaded or _instr_saved:
                            st.caption(
                                f"Instruction: {'loaded' if _instr_loaded else 'none'}"
                                f"{' | saved' if _instr_saved else ''}"
                            )

                        # Timing
                        _started = (_rd.get("started_at") or "")[:19]
                        _finished = (_rd.get("finished_at") or "")[:19]
                        if _started:
                            st.caption(f"{_started} - {_finished[11:]}")
            else:
                sb_log.info("No scrape runs yet. Click 'Run All' to start.")

        st.markdown("---")
        st.header("Filters")

        status_filter = st.multiselect(
            "Verification Status",
            options=sorted(df["verification_status"].dropna().unique().tolist()),
            default=sorted(df["verification_status"].dropna().unique().tolist()),
        )

        min_ai = st.slider("Min AI Score", 0.0, 1.0, 0.0, 0.1)
        min_startup = st.slider("Min Startup Score", 0.0, 1.0, 0.0, 0.1)

        show_tracked_only = st.checkbox("Tracked startups only", value=False)

    # Apply filters
    filtered = df.copy()
    if status_filter:
        filtered = filtered[filtered["verification_status"].isin(status_filter)]
    filtered = filtered[filtered["ai_score"].fillna(0) >= min_ai]
    filtered = filtered[filtered["startup_score"].fillna(0) >= min_startup]
    if show_tracked_only:
        filtered = filtered[filtered["is_tracked"]]

    # ── Tabs ───────────────────────────────────────────────────────
    tab_names = [
        "AI Scraper",
        "Overview",
        "Emerging This Week",
        "Pipeline Health",
        "Temporal Trends",
        "Trending Repos",
        "Categories",
        "Startup Directory",
        "GitHub Signals",
        "Funding",
        "Incubators",
        "Unselected Repos",
        "Scrape History",
    ]
    (
        tab_ai,
        tab1,
        tab_emerging,
        tab_health,
        tab_temporal,
        tab2,
        tab3,
        tab4,
        tab5,
        tab6,
        tab_inc,
        tab7,
        tab_history,
    ) = st.tabs(tab_names)

    with tab_ai:
        render_ai_scraper_tab()

    # ── Tab: Emerging This Week ──────────────────────────────────
    with tab_emerging:
        st.subheader("Newly Discovered This Week")
        try:
            engine = get_engine()
            emerging_df = _read_sql_df("""
                SELECT c.name, c.domain, c.country, c.city, c.ai_score,
                       c.startup_score, c.verification_status, c.first_seen_at,
                       c.description, c.ai_tags
                FROM companies c
                WHERE c.first_seen_at >= NOW() - INTERVAL '7 days'
                ORDER BY c.ai_score DESC NULLS LAST, c.first_seen_at DESC
            """, engine)

            if emerging_df.empty:
                st.info("No new companies discovered in the last 7 days.")
            else:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("New This Week", len(emerging_df))
                with col2:
                    ai_count = len(emerging_df[emerging_df["ai_score"].fillna(0) >= 0.5])
                    st.metric("AI Companies", ai_count)
                with col3:
                    countries = emerging_df["country"].dropna().nunique()
                    st.metric("Countries", countries)

                st.dataframe(
                    emerging_df[["name", "domain", "country", "city", "ai_score",
                                "verification_status", "first_seen_at", "description"]],
                    use_container_width=True,
                    height=500,
                )
        except Exception as e:
            st.error(f"Could not load emerging companies: {e}")

    # ── Tab: Pipeline Health ─────────────────────────────────────
    with tab_health:
        st.subheader("Scraper Pipeline Health")
        try:
            engine = get_engine()

            # Site health summary
            health_df = _read_sql_df("""
                SELECT domain, url, difficulty, status, scraper_name,
                       consecutive_failures, last_success_at, last_failure_at,
                       last_error, last_record_count, next_scrape_at,
                       exclude_until, total_runs, total_successes
                FROM site_health
                ORDER BY
                    CASE status
                        WHEN 'broken' THEN 1
                        WHEN 'degraded' THEN 2
                        WHEN 'excluded' THEN 3
                        WHEN 'pending' THEN 4
                        WHEN 'healthy' THEN 5
                    END,
                    domain
            """, engine)

            if health_df.empty:
                st.info("No sites registered yet. Run: python scripts/run_orchestrator.py --register-easy")
            else:
                # Summary metrics
                col1, col2, col3, col4, col5 = st.columns(5)
                with col1:
                    st.metric("Total Sites", len(health_df))
                with col2:
                    st.metric("Healthy", len(health_df[health_df["status"] == "healthy"]),
                             delta_color="normal")
                with col3:
                    degraded = len(health_df[health_df["status"] == "degraded"])
                    st.metric("Degraded", degraded)
                with col4:
                    broken = len(health_df[health_df["status"] == "broken"])
                    st.metric("Broken", broken)
                with col5:
                    excluded = len(health_df[health_df["status"] == "excluded"])
                    st.metric("Excluded", excluded)

                # Color-coded status
                st.markdown("### Site Status")

                def color_status(val):
                    colors = {
                        "healthy": "background-color: #1a472a; color: #4ade80",
                        "degraded": "background-color: #422006; color: #fbbf24",
                        "broken": "background-color: #450a0a; color: #f87171",
                        "excluded": "background-color: #1e1b4b; color: #a78bfa",
                        "pending": "background-color: #1e293b; color: #94a3b8",
                    }
                    return colors.get(val, "")

                display_cols = ["domain", "difficulty", "status", "scraper_name",
                               "consecutive_failures", "last_success_at", "last_record_count",
                               "total_runs", "total_successes"]
                available_cols = [c for c in display_cols if c in health_df.columns]
                styled = health_df[available_cols].style.map(
                    color_status, subset=["status"]
                )
                st.dataframe(styled, use_container_width=True, height=400)

                # Difficulty breakdown
                st.markdown("### Tier Breakdown")
                col1, col2 = st.columns(2)
                with col1:
                    easy_count = len(health_df[health_df["difficulty"] == "easy"])
                    hard_count = len(health_df[health_df["difficulty"] == "hard"])
                    tier_data = pd.DataFrame({
                        "Tier": ["Easy", "Hard"],
                        "Count": [easy_count, hard_count]
                    })
                    fig = px.pie(tier_data, values="Count", names="Tier",
                                title="Easy vs Hard Tier",
                                color_discrete_sequence=["#60a5fa", "#f97316"])
                    st.plotly_chart(fig, use_container_width=True)

            # Recent scrape runs
            st.markdown("### Recent Scrape Runs")
            runs_df = _read_sql_df("""
                SELECT domain, scraper_name, difficulty, status,
                       records_found, records_new, records_updated,
                       duration_seconds, error_message, started_at
                FROM scrape_runs
                ORDER BY started_at DESC
                LIMIT 50
            """, engine)

            if not runs_df.empty:
                st.dataframe(runs_df, use_container_width=True, height=300)
            else:
                st.info("No scrape runs recorded yet.")

        except Exception as e:
            st.error(f"Could not load pipeline health: {e}")

    # ── Tab: Overview ────────────────────────────────────────────
    with tab1:
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Companies", len(filtered))
        with col2:
            st.metric("Tracked", int(filtered["is_tracked"].sum()))
        with col3:
            verified = filtered[filtered["verification_status"].str.contains("verified", na=False)]
            st.metric("Verified (CB/PB)", len(verified))
        with col4:
            countries = filtered["country"].dropna().nunique()
            st.metric("Countries", countries)
        with col5:
            avg_ai = filtered["ai_score"].mean()
            st.metric("Avg AI Score", f"{avg_ai:.2f}" if not pd.isna(avg_ai) else "N/A")

        col_map, col_charts = st.columns([6, 4])

        with col_map:
            st.markdown("### Geographic Distribution")
            map_data = []
            for _, row in filtered.iterrows():
                lat, lon = row.get("latitude"), row.get("longitude")
                if pd.isna(lat) or pd.isna(lon):
                    c = row.get("country", "")
                    if c and c in COUNTRY_COORDS:
                        lat, lon = COUNTRY_COORDS[c]
                    else:
                        continue
                lat += np.random.uniform(-1.5, 1.5)
                lon += np.random.uniform(-1.5, 1.5)
                map_data.append({
                    "name": row["name"],
                    "lat": lat, "lon": lon,
                    "country": row.get("country") or "Unknown",
                    "ai_score": row.get("ai_score") or 0,
                    "status": row["verification_status"],
                })

            if map_data:
                map_df = pd.DataFrame(map_data)
                map_df["ai_score"] = map_df["ai_score"].fillna(0)
                fig = px.scatter_mapbox(
                    map_df, lat="lat", lon="lon",
                    hover_name="name",
                    hover_data=["country", "ai_score", "status"],
                    color="ai_score", size="ai_score", size_max=18,
                    color_continuous_scale="YlOrRd",
                    zoom=1, height=500,
                )
                fig.update_layout(mapbox_style="carto-darkmatter", showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No location data available for map.")

        with col_charts:
            st.markdown("### Verification Status")
            status_counts = filtered["verification_status"].value_counts()
            fig = px.pie(
                values=status_counts.values, names=status_counts.index,
                hole=0.4, color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig.update_layout(template="plotly_dark", height=250, margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("### Top Countries")
            country_counts = filtered["country"].dropna().value_counts().head(8)
            if len(country_counts) > 0:
                fig = px.bar(
                    x=country_counts.values, y=country_counts.index,
                    orientation="h", color=country_counts.values,
                    color_continuous_scale="Viridis",
                )
                fig.update_layout(
                    template="plotly_dark", height=250, showlegend=False,
                    margin=dict(t=10, b=10), xaxis_title="Count", yaxis_title="",
                )
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("### Score Distribution")
        col1, col2 = st.columns(2)
        with col1:
            fig = px.histogram(
                filtered, x="ai_score", nbins=20,
                title="AI Score Distribution",
                color_discrete_sequence=["#4CAF50"],
            )
            fig.update_layout(template="plotly_dark", height=300)
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = px.histogram(
                filtered, x="startup_score", nbins=20,
                title="Startup Score Distribution",
                color_discrete_sequence=["#2196F3"],
            )
            fig.update_layout(template="plotly_dark", height=300)
            st.plotly_chart(fig, use_container_width=True)

    # ── Tab Temporal: Temporal Trends ──────────────────────────────
    with tab_temporal:
        st.markdown("### Temporal Trends: AI Startup Formation & Funding")
        st.markdown("How AI startup creation and funding have evolved over time.")

        # --- Section 1: Startup Formation Rate ---
        st.markdown("---")
        st.markdown("## 1. AI Startup Formation Rate")

        # Use GitHub signals created_at as proxy for repo/company founding date
        if len(gh_df) > 0 and "created_at" in gh_df.columns:
            gh_temporal = gh_df[gh_df["created_at"].notna()].copy()
            gh_temporal["created_at"] = pd.to_datetime(gh_temporal["created_at"], errors="coerce")
            gh_temporal = gh_temporal[gh_temporal["created_at"] >= "2015-01-01"]

            if len(gh_temporal) > 0:
                # Yearly formation
                gh_temporal["year"] = gh_temporal["created_at"].dt.year
                gh_temporal["quarter"] = gh_temporal["created_at"].dt.to_period("Q").astype(str)
                gh_temporal["month"] = gh_temporal["created_at"].dt.to_period("M").astype(str)

                # Merge with company data to get owner_type
                gh_with_owner = gh_temporal.copy()

                # Yearly bar chart
                yearly = gh_with_owner.groupby("year").size().reset_index(name="repos_created")

                col_y1, col_y2 = st.columns(2)

                with col_y1:
                    fig = px.bar(
                        yearly, x="year", y="repos_created",
                        title="AI Repos Created per Year",
                        color="repos_created", color_continuous_scale="YlOrRd",
                        text="repos_created",
                    )
                    fig.update_layout(
                        template="plotly_dark", height=400,
                        xaxis_title="Year", yaxis_title="Repos Created",
                        showlegend=False,
                    )
                    fig.update_traces(textposition="outside")
                    st.plotly_chart(fig, use_container_width=True)

                with col_y2:
                    # YoY growth rate
                    yearly["yoy_growth"] = yearly["repos_created"].pct_change() * 100
                    yearly_growth = yearly[yearly["yoy_growth"].notna()]
                    if len(yearly_growth) > 0:
                        fig = px.bar(
                            yearly_growth, x="year", y="yoy_growth",
                            title="Year-over-Year Growth Rate (%)",
                            color="yoy_growth", color_continuous_scale="RdYlGn",
                            text=yearly_growth["yoy_growth"].round(0).astype(int).astype(str) + "%",
                        )
                        fig.update_layout(
                            template="plotly_dark", height=400,
                            xaxis_title="Year", yaxis_title="YoY Growth %",
                            showlegend=False,
                        )
                        fig.update_traces(textposition="outside")
                        st.plotly_chart(fig, use_container_width=True)

                # Quarterly trend line
                quarterly = gh_with_owner.groupby("quarter").size().reset_index(name="repos_created")
                quarterly = quarterly.sort_values("quarter")
                fig = px.line(
                    quarterly, x="quarter", y="repos_created",
                    title="Quarterly AI Repo Creation Trend",
                    markers=True,
                )
                fig.update_layout(
                    template="plotly_dark", height=350,
                    xaxis_title="Quarter", yaxis_title="Repos Created",
                    xaxis=dict(tickangle=45),
                )
                st.plotly_chart(fig, use_container_width=True)

                # By owner type over time
                if "owner_type" in gh_with_owner.columns:
                    yearly_owner = (
                        gh_with_owner.groupby(["year", "owner_type"])
                        .size()
                        .reset_index(name="count")
                    )
                    yearly_owner["owner_type"] = yearly_owner["owner_type"].astype(str)
                    # plotly.express px.bar + color hits pandas groupby/get_group bugs with some
                    # category_orders / defaults; build stacked bars with graph_objects instead.
                    _ot_palette = {"Organization": "#4CAF50", "User": "#FFC107"}
                    _ot_order = sorted(yearly_owner["owner_type"].dropna().unique().tolist())
                    pvt = yearly_owner.pivot_table(
                        index="year",
                        columns="owner_type",
                        values="count",
                        aggfunc="sum",
                        fill_value=0,
                    )
                    pvt = pvt.reindex(columns=_ot_order, fill_value=0)
                    fig = go.Figure()
                    for ot in pvt.columns:
                        fig.add_trace(
                            go.Bar(
                                name=str(ot),
                                x=pvt.index,
                                y=pvt[ot],
                                marker_color=_ot_palette.get(str(ot), "#888888"),
                            )
                        )
                    fig.update_layout(
                        template="plotly_dark",
                        height=400,
                        barmode="stack",
                        title="Repo Creation by Owner Type (Organization vs User)",
                        xaxis_title="Year",
                        yaxis_title="Repos Created",
                    )
                    st.plotly_chart(fig, use_container_width=True)

                # By country over time (top 8 countries)
                if len(filtered) > 0:
                    gh_with_country = pd.merge(
                        gh_with_owner,
                        df[["id", "country"]],
                        left_on="company_id", right_on="id", how="left",
                    )
                    gh_with_country = gh_with_country[gh_with_country["country"].notna()]

                    if len(gh_with_country) > 0:
                        top_countries = gh_with_country["country"].value_counts().head(8).index
                        gh_top = gh_with_country[gh_with_country["country"].isin(top_countries)]
                        yearly_country = (
                            gh_top.groupby(["year", "country"])
                            .size()
                            .reset_index(name="count")
                        )
                        yearly_country = yearly_country.copy()
                        yearly_country["country"] = yearly_country["country"].astype(str).str.strip()
                        fig = px.line(
                            yearly_country,
                            x="year",
                            y="count",
                            color="country",
                            title="AI Startup Formation by Country (Top 8)",
                            markers=True,
                        )
                        fig.update_layout(
                            template="plotly_dark", height=400,
                            xaxis_title="Year", yaxis_title="Repos Created",
                        )
                        st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No GitHub signal data with creation dates available.")

        # --- Section 2: AI Subdomain Trends ---
        st.markdown("---")
        st.markdown("## 2. AI Subdomain Trends Over Time")

        if has_snapshots and "ai_subdomain" in snap_df.columns:
            snap_temporal = snap_df.copy()
            # Use pushed_at as activity timestamp
            if "pushed_at" in snap_temporal.columns:
                snap_temporal["pushed_at"] = pd.to_datetime(snap_temporal["pushed_at"], errors="coerce")
                snap_temporal = snap_temporal[snap_temporal["pushed_at"] >= "2020-01-01"]

                if len(snap_temporal) > 0:
                    snap_temporal["year"] = snap_temporal["pushed_at"].dt.year
                    subdomain_yearly = (
                        snap_temporal[snap_temporal["ai_subdomain"].notna()]
                        .groupby(["year", "ai_subdomain"])
                        .size()
                        .reset_index(name="count")
                    )

                    if len(subdomain_yearly) > 0:
                        # Area chart showing subdomain composition over time
                        _co_sub = _px_category_orders(subdomain_yearly, "ai_subdomain")
                        _area_kw = {"category_orders": _co_sub} if _co_sub else {}
                        fig = px.area(
                            subdomain_yearly, x="year", y="count", color="ai_subdomain",
                            title="AI Subdomain Growth Over Time",
                            color_discrete_sequence=px.colors.qualitative.Set3,
                            **_area_kw,
                        )
                        fig.update_layout(
                            template="plotly_dark", height=450,
                            xaxis_title="Year", yaxis_title="Repos",
                        )
                        st.plotly_chart(fig, use_container_width=True)

                        # Normalized (percentage) view
                        yearly_totals = subdomain_yearly.groupby("year")["count"].sum().reset_index(name="total")
                        subdomain_pct = pd.merge(subdomain_yearly, yearly_totals, on="year")
                        subdomain_pct["pct"] = subdomain_pct["count"] / subdomain_pct["total"] * 100

                        _co_pct = _px_category_orders(subdomain_pct, "ai_subdomain")
                        _pct_kw = {"category_orders": _co_pct} if _co_pct else {}
                        fig = px.area(
                            subdomain_pct, x="year", y="pct", color="ai_subdomain",
                            title="AI Subdomain Share Over Time (%)",
                            color_discrete_sequence=px.colors.qualitative.Set3,
                            **_pct_kw,
                        )
                        fig.update_layout(
                            template="plotly_dark", height=400,
                            xaxis_title="Year", yaxis_title="Share (%)",
                            yaxis=dict(range=[0, 100]),
                        )
                        st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No snapshot data with AI subdomain classification available.")

        # --- Section 3: Funding Trends ---
        st.markdown("---")
        st.markdown("## 3. Funding Trends")

        if len(fund_df) > 0 and "deal_date" in fund_df.columns:
            fund_temporal = fund_df[fund_df["deal_date"].notna()].copy()
            fund_temporal["deal_date"] = pd.to_datetime(fund_temporal["deal_date"], errors="coerce")
            fund_temporal = fund_temporal[fund_temporal["deal_date"] >= "2015-01-01"]

            if len(fund_temporal) > 0:
                fund_temporal["year"] = fund_temporal["deal_date"].dt.year
                fund_temporal["quarter"] = fund_temporal["deal_date"].dt.to_period("Q").astype(str)

                col_f1, col_f2 = st.columns(2)

                with col_f1:
                    # Deal count by year
                    yearly_deals = fund_temporal.groupby("year").size().reset_index(name="deals")
                    fig = px.bar(
                        yearly_deals, x="year", y="deals",
                        title="Number of Deals per Year",
                        color="deals", color_continuous_scale="Blues",
                        text="deals",
                    )
                    fig.update_layout(
                        template="plotly_dark", height=380,
                        xaxis_title="Year", yaxis_title="Deals",
                        showlegend=False,
                    )
                    fig.update_traces(textposition="outside")
                    st.plotly_chart(fig, use_container_width=True)

                with col_f2:
                    # Average deal size by year
                    yearly_size = (
                        fund_temporal[fund_temporal["deal_size"].notna()]
                        .groupby("year")
                        .agg(avg_size=("deal_size", "mean"), total_size=("deal_size", "sum"))
                        .reset_index()
                    )
                    if len(yearly_size) > 0:
                        fig = px.bar(
                            yearly_size, x="year", y="avg_size",
                            title="Average Deal Size by Year (USD)",
                            color="avg_size", color_continuous_scale="Greens",
                        )
                        fig.update_layout(
                            template="plotly_dark", height=380,
                            xaxis_title="Year", yaxis_title="Avg Deal Size",
                            showlegend=False,
                        )
                        st.plotly_chart(fig, use_container_width=True)

                # Deal count by round type over time
                if "round_type" in fund_temporal.columns:
                    round_yearly = (
                        fund_temporal[fund_temporal["round_type"].notna()]
                        .groupby(["year", "round_type"])
                        .size()
                        .reset_index(name="count")
                    )
                    top_rounds = fund_temporal["round_type"].value_counts().head(6).index
                    round_yearly = round_yearly[round_yearly["round_type"].isin(top_rounds)]

                    if len(round_yearly) > 0:
                        _co_round = _px_category_orders(
                            round_yearly, "round_type", desired=list(top_rounds)
                        )
                        _bar_r_kw = {"category_orders": _co_round} if _co_round else {}
                        fig = px.bar(
                            round_yearly, x="year", y="count", color="round_type",
                            barmode="stack",
                            title="Deals by Round Type Over Time",
                            **_bar_r_kw,
                        )
                        fig.update_layout(
                            template="plotly_dark", height=400,
                            xaxis_title="Year", yaxis_title="Deals",
                        )
                        st.plotly_chart(fig, use_container_width=True)

                # Quarterly trend
                quarterly_deals = fund_temporal.groupby("quarter").size().reset_index(name="deals")
                quarterly_deals = quarterly_deals.sort_values("quarter")
                fig = px.line(
                    quarterly_deals, x="quarter", y="deals",
                    title="Quarterly Deal Flow",
                    markers=True,
                )
                fig.update_layout(
                    template="plotly_dark", height=300,
                    xaxis_title="Quarter", yaxis_title="Deals",
                    xaxis=dict(tickangle=45),
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No funding data with deal dates available. Run PitchBook import to populate.")

        # --- Section 4: Formation vs Funding Overlay ---
        st.markdown("---")
        st.markdown("## 4. Formation vs Funding: Dual Axis")

        if len(gh_df) > 0 and len(fund_df) > 0:
            gh_yearly = gh_df[gh_df["created_at"].notna()].copy()
            gh_yearly["created_at"] = pd.to_datetime(gh_yearly["created_at"], errors="coerce")
            gh_yearly = gh_yearly[gh_yearly["created_at"] >= "2015-01-01"]
            gh_yearly["year"] = gh_yearly["created_at"].dt.year
            formation = gh_yearly.groupby("year").size().reset_index(name="repos_created")

            fund_yearly = fund_df[fund_df["deal_date"].notna()].copy()
            fund_yearly["deal_date"] = pd.to_datetime(fund_yearly["deal_date"], errors="coerce")
            fund_yearly = fund_yearly[fund_yearly["deal_date"] >= "2015-01-01"]
            fund_yearly["year"] = fund_yearly["deal_date"].dt.year
            funding = fund_yearly.groupby("year").size().reset_index(name="deals")

            combined = pd.merge(formation, funding, on="year", how="outer").sort_values("year")
            combined = combined.fillna(0)

            if len(combined) > 0:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=combined["year"], y=combined["repos_created"],
                    name="AI Repos Created", marker_color="#4CAF50", opacity=0.7,
                ))
                fig.add_trace(go.Scatter(
                    x=combined["year"], y=combined["deals"],
                    name="Funding Deals", yaxis="y2",
                    mode="lines+markers", marker_color="#FF6B35",
                    line=dict(width=3),
                ))
                fig.update_layout(
                    template="plotly_dark", height=450,
                    title="AI Startup Formation vs Funding Activity",
                    xaxis_title="Year",
                    yaxis=dict(title=dict(text="Repos Created", font=dict(color="#4CAF50"))),
                    yaxis2=dict(
                        title=dict(text="Funding Deals", font=dict(color="#FF6B35")),
                        overlaying="y", side="right",
                    ),
                    legend=dict(x=0.01, y=0.99),
                )
                st.plotly_chart(fig, use_container_width=True)

                st.markdown("""
                > **Insight**: Compare the growth trajectory of AI startup formation (repos created)
                > against funding activity (deals matched). A gap between formation and funding
                > may indicate emerging opportunities or market inefficiencies.
                """)

    # ── Tab 2: Trending Repos ─────────────────────────────────────
    with tab2:
        st.markdown("### Top Trending Repos (7-day velocity)")

        if not has_snapshots:
            st.info("No snapshot data yet. Run the discovery script to generate snapshots.")
            st.code("python scripts/github_weekly_discover.py --since-days 7 --init-db", language="bash")
        else:
            # Filter to startups only (LLM-classified or unclassified legacy data)
            startup_snap = snap_df[
                snap_df["llm_classification"].isin(["startup"]) | snap_df["llm_classification"].isna()
            ] if "llm_classification" in snap_df.columns else snap_df

            # Top metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Startup Repos", len(startup_snap))
            with col2:
                with_trend = startup_snap[startup_snap["trend_score"].notna() & (startup_snap["trend_score"] > 0)]
                st.metric("With Trend Data", len(with_trend))
            with col3:
                avg_trend = startup_snap["trend_score"].mean()
                st.metric("Avg Trend Score", f"{avg_trend:.3f}" if not pd.isna(avg_trend) else "N/A")
            with col4:
                avg_startup_lk = startup_snap["startup_likelihood"].mean()
                st.metric("Avg Startup Likelihood", f"{avg_startup_lk:.3f}" if not pd.isna(avg_startup_lk) else "N/A")

            # Trending table sorted by trend_score
            trending = startup_snap.sort_values("trend_score", ascending=False, na_position="last").head(100)
            display_cols = [
                "repo_full_name", "stars", "trend_score",
                "stars_7d_delta", "forks_7d_delta",
                "startup_likelihood", "ai_subdomain", "stack_layer",
                "language", "owner_type",
            ]
            available_cols = [c for c in display_cols if c in trending.columns]
            display_trending = trending[available_cols].copy()
            for col in ["trend_score", "startup_likelihood"]:
                if col in display_trending.columns:
                    display_trending[col] = display_trending[col].round(3)
            for col in ["stars", "stars_7d_delta", "forks_7d_delta"]:
                if col in display_trending.columns:
                    display_trending[col] = display_trending[col].fillna(0).astype(int)

            st.dataframe(display_trending, use_container_width=True, height=500)

            # Trend score distribution
            st.markdown("### Trend Score Distribution")
            valid_trends = snap_df[snap_df["trend_score"].notna()]
            if len(valid_trends) > 0:
                fig = px.histogram(
                    valid_trends, x="trend_score", nbins=30,
                    title="Trend Score Distribution",
                    color_discrete_sequence=["#FF6B35"],
                )
                fig.update_layout(template="plotly_dark", height=300)
                st.plotly_chart(fig, use_container_width=True)

            # Stars delta distribution
            st.markdown("### Stars Growth (7d delta)")
            valid_deltas = snap_df[snap_df["stars_7d_delta"].notna() & (snap_df["stars_7d_delta"] != 0)]
            if len(valid_deltas) > 0:
                fig = px.histogram(
                    valid_deltas, x="stars_7d_delta", nbins=30,
                    title="Stars 7-Day Delta Distribution",
                    color_discrete_sequence=["#FFC107"],
                )
                fig.update_layout(template="plotly_dark", height=300)
                st.plotly_chart(fig, use_container_width=True)

    # ── Tab 3: Categories ─────────────────────────────────────────
    with tab3:
        st.markdown("### AI Category Classification")

        if not has_snapshots:
            st.info("No classification data yet. Run the discovery script first.")
        else:
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### AI Subdomain Distribution")
                subdomain_counts = snap_df["ai_subdomain"].dropna().value_counts()
                if len(subdomain_counts) > 0:
                    fig = px.pie(
                        values=subdomain_counts.values,
                        names=subdomain_counts.index,
                        hole=0.4,
                        color_discrete_sequence=px.colors.qualitative.Set3,
                    )
                    fig.update_layout(template="plotly_dark", height=400)
                    st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.markdown("### Stack Layer Distribution")
                layer_counts = snap_df["stack_layer"].dropna().value_counts()
                if len(layer_counts) > 0:
                    fig = px.pie(
                        values=layer_counts.values,
                        names=layer_counts.index,
                        hole=0.4,
                        color_discrete_sequence=px.colors.qualitative.Pastel,
                    )
                    fig.update_layout(template="plotly_dark", height=400)
                    st.plotly_chart(fig, use_container_width=True)

            # Subdomain bar chart with avg scores
            st.markdown("### Subdomain by Count and Avg Startup Likelihood")
            subdomain_stats = (
                snap_df.groupby("ai_subdomain")
                .agg(
                    count=("ai_subdomain", "size"),
                    avg_startup_lk=("startup_likelihood", "mean"),
                    avg_trend=("trend_score", "mean"),
                )
                .reset_index()
                .sort_values("count", ascending=False)
            )
            if len(subdomain_stats) > 0:
                fig = px.bar(
                    subdomain_stats, x="ai_subdomain", y="count",
                    color="avg_startup_lk",
                    color_continuous_scale="YlOrRd",
                    hover_data=["avg_trend"],
                    title="Repos per AI Subdomain (color = avg startup likelihood)",
                )
                fig.update_layout(template="plotly_dark", height=400, xaxis_title="", yaxis_title="Count")
                st.plotly_chart(fig, use_container_width=True)

            # Language by subdomain
            st.markdown("### Top Languages by Subdomain")
            if "language" in snap_df.columns:
                lang_sub = (
                    snap_df[snap_df["language"].notna()]
                    .groupby(["ai_subdomain", "language"])
                    .size()
                    .reset_index(name="count")
                    .sort_values("count", ascending=False)
                )
                top_langs = lang_sub.groupby("ai_subdomain").head(5)
                if len(top_langs) > 0:
                    _co_lang = _px_category_orders(top_langs, "language")
                    _lang_kw = {"category_orders": _co_lang} if _co_lang else {}
                    fig = px.bar(
                        top_langs, x="ai_subdomain", y="count",
                        color="language", barmode="stack",
                        title="Top Languages per AI Subdomain",
                        **_lang_kw,
                    )
                    fig.update_layout(template="plotly_dark", height=400)
                    st.plotly_chart(fig, use_container_width=True)

            # Country x subdomain from trend report
            if trend_report:
                geo = trend_report.get("geography_summary", {})
                breakdown = geo.get("country_subdomain_breakdown", {})
                if breakdown:
                    st.markdown("### Country x Subdomain Breakdown")
                    rows = []
                    for country, subs in breakdown.items():
                        for sub, cnt in subs.items():
                            rows.append({"country": country, "subdomain": sub, "count": cnt})
                    if rows:
                        heatmap_df = pd.DataFrame(rows)
                        pivot = heatmap_df.pivot_table(
                            index="country", columns="subdomain", values="count", fill_value=0,
                        )
                        # Show top 15 countries
                        pivot = pivot.loc[pivot.sum(axis=1).nlargest(15).index]
                        fig = px.imshow(
                            pivot, aspect="auto",
                            color_continuous_scale="YlOrRd",
                            title="Country vs AI Subdomain Heatmap",
                        )
                        fig.update_layout(template="plotly_dark", height=500)
                        st.plotly_chart(fig, use_container_width=True)

    # ── Tab 4: Directory ───────────────────────────────────────────
    with tab4:
        st.markdown("### Startup Directory")
        st.markdown(f"**{len(filtered)} companies** matching filters")

        sort_col = st.selectbox(
            "Sort by", ["ai_score", "startup_score", "name", "first_seen_at"],
            index=0,
        )
        sort_asc = sort_col == "name"
        sorted_df = filtered.sort_values(sort_col, ascending=sort_asc, na_position="last")

        page_size = 50
        total_pages = max(1, (len(sorted_df) + page_size - 1) // page_size)
        page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
        start = (page - 1) * page_size
        page_df = sorted_df.iloc[start : start + page_size]
        st.caption(f"Showing {start+1}--{min(start+page_size, len(sorted_df))} of {len(sorted_df)}")

        for _, row in page_df.iterrows():
            tracked_class = "tracked" if is_tracked(row) else "candidate"
            ai_s = f"{row['ai_score']:.2f}" if not pd.isna(row.get("ai_score")) else "N/A"
            su_s = f"{row['startup_score']:.2f}" if not pd.isna(row.get("startup_score")) else "N/A"
            domain_str = f" | {row['domain']}" if row.get("domain") else ""
            country_str = f" | {row['country']}" if row.get("country") else ""

            tags_html = ""
            if row.get("ai_tags"):
                tag_list = row["ai_tags"] if isinstance(row["ai_tags"], list) else []
                for t in tag_list[:5]:
                    tags_html += f'<span class="tag">{t}</span>'

            st.markdown(f"""
            <div class="company-card {tracked_class}">
                <strong>{row['name']}</strong>{domain_str}{country_str}
                <br><small>Status: {row['verification_status']} | AI: {ai_s} | Startup: {su_s}</small>
                <br>{tags_html}
            </div>
            """, unsafe_allow_html=True)

    # ── Tab 5: GitHub Signals ──────────────────────────────────────
    with tab5:
        st.markdown("### GitHub Repositories")

        company_ids = set(filtered["id"].tolist())
        gh_filtered = gh_df[gh_df["company_id"].isin(company_ids)] if len(company_ids) < len(df) else gh_df

        if len(gh_filtered) == 0:
            st.info("No GitHub signals found.")
        else:
            # Split by owner type
            org_repos = gh_filtered[gh_filtered["owner_type"] == "Organization"]
            user_repos = gh_filtered[gh_filtered["owner_type"] == "User"]

            # Overview metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Repos", len(gh_filtered))
            with col2:
                st.metric("Organization Repos", len(org_repos))
            with col3:
                st.metric("User Repos", len(user_repos))
            with col4:
                org_pct = len(org_repos) / len(gh_filtered) * 100 if len(gh_filtered) > 0 else 0
                st.metric("Org %", f"{org_pct:.1f}%")

            # Sub-tabs for All / Organization / User
            gh_tab_all, gh_tab_org, gh_tab_user = st.tabs([
                f"All ({len(gh_filtered)})",
                f"Organization ({len(org_repos)})",
                f"User ({len(user_repos)})",
            ])

            def _render_repo_table(repo_df, key_suffix=""):
                """Render a repo table with stars distribution chart."""
                if len(repo_df) == 0:
                    st.info("No repos in this category.")
                    return

                # Summary metrics
                mc1, mc2, mc3 = st.columns(3)
                with mc1:
                    st.metric("Avg Stars", f"{repo_df['stars'].fillna(0).mean():.0f}")
                with mc2:
                    st.metric("Avg Forks", f"{repo_df['forks'].fillna(0).mean():.0f}")
                with mc3:
                    st.metric("Unique Owners", repo_df["owner_login"].nunique())

                # Table
                display_repos = repo_df[
                    ["repo_full_name", "stars", "forks", "owner_login", "owner_type", "description"]
                ].copy()
                display_repos["stars"] = display_repos["stars"].fillna(0).astype(int)
                display_repos["forks"] = display_repos["forks"].fillna(0).astype(int)
                st.dataframe(display_repos, use_container_width=True, height=500)

                # Stars distribution
                fig = px.histogram(
                    repo_df, x="stars", nbins=40,
                    title="Stars Distribution",
                    color_discrete_sequence=["#FFC107"],
                )
                fig.update_layout(template="plotly_dark", height=280)
                st.plotly_chart(fig, use_container_width=True)

                # Top owners by repo count
                top_owners = repo_df["owner_login"].value_counts().head(15)
                if len(top_owners) > 1:
                    fig = px.bar(
                        x=top_owners.values, y=top_owners.index,
                        orientation="h", title="Top Owners by Repo Count",
                        color=top_owners.values, color_continuous_scale="Viridis",
                    )
                    fig.update_layout(
                        template="plotly_dark", height=350,
                        showlegend=False, xaxis_title="Repos", yaxis_title="",
                        yaxis=dict(autorange="reversed"),
                    )
                    st.plotly_chart(fig, use_container_width=True)

            with gh_tab_all:
                _render_repo_table(gh_filtered, "all")

            with gh_tab_org:
                st.markdown("**Organization-owned repos** are more likely to be startup/company products.")
                _render_repo_table(org_repos, "org")

            with gh_tab_user:
                st.markdown("**User-owned repos** — personal projects, solo founders, or early-stage startups.")
                _render_repo_table(user_repos, "user")

    # ── Tab 6: Funding ─────────────────────────────────────────────
    with tab6:
        st.markdown("### Funding Signals (PitchBook)")

        if len(fund_df) == 0:
            st.info("No funding signals yet. Run the PitchBook import to populate.")
            st.code(
                "python scripts/import_pitchbook.py "
                "--deal data/pitchbook_other_glob_deal.parquet "
                "--relation data/pitchbook_other_glob_deal_investor_relation.parquet",
                language="bash",
            )
        else:
            company_ids = set(filtered["id"].tolist())
            fund_filtered = fund_df[fund_df["company_id"].isin(company_ids)] if len(company_ids) < len(df) else fund_df

            st.metric("Total Deals Matched", len(fund_filtered))

            if "round_type" in fund_filtered.columns:
                round_counts = fund_filtered["round_type"].dropna().value_counts().head(10)
                if len(round_counts) > 0:
                    fig = px.bar(
                        x=round_counts.index, y=round_counts.values,
                        title="Deals by Round Type",
                        color=round_counts.values, color_continuous_scale="Viridis",
                    )
                    fig.update_layout(template="plotly_dark", height=350)
                    st.plotly_chart(fig, use_container_width=True)

            deal_sizes = fund_filtered["deal_size"].dropna()
            if len(deal_sizes) > 0:
                fig = px.histogram(
                    deal_sizes, nbins=30,
                    title="Deal Size Distribution (USD M)",
                    color_discrete_sequence=["#2196F3"],
                )
                fig.update_layout(template="plotly_dark", height=300)
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("### Recent Deals")
            display_cols = ["company_name", "domain", "deal_date", "round_type",
                            "deal_size", "match_method", "match_confidence", "source"]
            available_cols = [c for c in display_cols if c in fund_filtered.columns]
            recent = fund_filtered.head(30)[available_cols].copy()
            st.dataframe(recent, use_container_width=True)

        st.markdown("---")
        st.subheader("GitHub vs. Capital Markets: Trend Comparison")
        st.markdown("Comparing **Emerging GitHub** startups vs. **Verified/Funded** companies (Crunchbase/PitchBook).")

        # Data Prep for Comparison
        if df.empty:
            st.info("No company data available for comparison.")
        elif gh_df.empty:
            st.info("No GitHub data available for comparison.")
        elif snap_df.empty:
            st.warning("No snapshot data available. Please run `scripts/github_weekly_discover.py` to generate trend data.")
        else:
            # 1. Classify companies
            def get_category(status):
                if status == "emerging_github":
                    return "Emerging (GitHub)"
                return "Funded (CB/PB)"

            comp_data = df.copy()
            comp_data["source_category"] = comp_data["verification_status"].apply(get_category)

            # 2. Merge to get AI Subdomain (Company -> Signal -> Snapshot)
            # Use primary repo (most stars) for mapping
            gh_primary = gh_df.sort_values("stars", ascending=False).drop_duplicates("company_id")
            merged_sub = pd.merge(comp_data, gh_primary[["company_id", "repo_full_name"]], left_on="id", right_on="company_id", how="left")
            merged_sub = pd.merge(merged_sub, snap_df[["repo_full_name", "ai_subdomain"]], on="repo_full_name", how="left")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### Geographic Divergence")
                loc_df = merged_sub[merged_sub["country"].notna()]
                # Filter to top 15 countries overall
                top_countries = loc_df["country"].value_counts().head(15).index
                loc_counts = loc_df[loc_df["country"].isin(top_countries)].groupby(["country", "source_category"]).size().reset_index(name="count")

                _src_palette = {"Emerging (GitHub)": "#4CAF50", "Funded (CB/PB)": "#2196F3"}
                _co_src_loc = _px_category_orders(
                    loc_counts,
                    "source_category",
                    desired=["Emerging (GitHub)", "Funded (CB/PB)"],
                )
                _src_seq_loc = (
                    [_src_palette.get(str(lbl), "#888888") for lbl in _co_src_loc["source_category"]]
                    if _co_src_loc
                    else None
                )
                _loc_kw = {}
                if _co_src_loc:
                    _loc_kw["category_orders"] = _co_src_loc
                if _src_seq_loc:
                    _loc_kw["color_discrete_sequence"] = _src_seq_loc
                fig_loc = px.bar(
                    loc_counts, x="country", y="count", color="source_category",
                    barmode="group", title="Top Countries: Emerging vs. Funded",
                    **_loc_kw,
                )
                fig_loc.update_layout(template="plotly_dark", height=400)
                st.plotly_chart(fig_loc, use_container_width=True)

            with col2:
                st.markdown("#### Sector Focus (AI Subdomain)")
                sec_df = merged_sub[merged_sub["ai_subdomain"].notna()]
                sec_counts = sec_df.groupby(["ai_subdomain", "source_category"]).size().reset_index(name="count")

                _co_src_sec = _px_category_orders(
                    sec_counts,
                    "source_category",
                    desired=["Emerging (GitHub)", "Funded (CB/PB)"],
                )
                _src_seq_sec = (
                    [_src_palette.get(str(lbl), "#888888") for lbl in _co_src_sec["source_category"]]
                    if _co_src_sec
                    else None
                )
                _sec_kw = {}
                if _co_src_sec:
                    _sec_kw["category_orders"] = _co_src_sec
                if _src_seq_sec:
                    _sec_kw["color_discrete_sequence"] = _src_seq_sec
                fig_sec = px.bar(
                    sec_counts, x="ai_subdomain", y="count", color="source_category",
                    barmode="group", title="AI Subdomains: Emerging vs. Funded",
                    **_sec_kw,
                )
                fig_sec.update_layout(template="plotly_dark", height=400)
                st.plotly_chart(fig_sec, use_container_width=True)


    # ── Tab Incubators ──────────────────────────────────────────
    with tab_inc:
        st.markdown("### Incubator / Accelerator Portfolio Companies")
        st.markdown("Companies scraped from **Capital Factory**, **gener8tor**, and **Village Global**.")

        if len(inc_df) == 0:
            st.info("No incubator data yet. Run the scraper to populate:")
            st.code("python scripts/scrape_incubators.py --init-db", language="bash")
        else:
            # Overview metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Incubator Companies", len(inc_df))
            with col2:
                sources = inc_df["source"].nunique()
                st.metric("Sources", sources)
            with col3:
                with_website = inc_df["website_url"].notna().sum()
                st.metric("With Website", int(with_website))
            with col4:
                with_github = inc_df[inc_df["ai_score"].notna() & (inc_df["ai_score"] > 0)]
                st.metric("Also on GitHub", len(with_github))

            # Per-source breakdown
            st.markdown("### Companies by Source")
            source_counts = inc_df["source"].value_counts()

            with st.container():
                source_summary = (
                    inc_df.groupby("source")
                    .agg(
                        companies=("id", "count"),
                        with_website=("website_url", lambda x: x.notna().sum()),
                        with_industry=("industry", lambda x: x.notna().sum()),
                        with_program=("program", lambda x: x.notna().sum()),
                    )
                    .reset_index()
                )
                st.dataframe(source_summary, use_container_width=True)

            # Industry breakdown (for sources that have it)
            inc_with_industry = inc_df[inc_df["industry"].notna()]
            if len(inc_with_industry) > 0:
                st.markdown("### Industry Distribution")
                # Split comma-separated industries
                all_industries = []
                for _, row in inc_with_industry.iterrows():
                    for ind in str(row["industry"]).split(","):
                        ind = ind.strip()
                        if ind:
                            all_industries.append({"industry": ind, "source": row["source"]})

                if all_industries:
                    ind_df = pd.DataFrame(all_industries)
                    top_industries = ind_df["industry"].value_counts().head(15)
                    fig = px.bar(
                        x=top_industries.values, y=top_industries.index,
                        orientation="h",
                        title="Top 15 Industries Across All Incubators",
                        color=top_industries.values,
                        color_continuous_scale="Viridis",
                    )
                    fig.update_layout(
                        template="plotly_dark", height=450,
                        showlegend=False, xaxis_title="Count", yaxis_title="",
                        yaxis=dict(autorange="reversed"),
                    )
                    st.plotly_chart(fig, use_container_width=True)

            # Cross-reference: incubator companies that also have GitHub signals
            st.markdown("### Cross-Reference: Incubator x GitHub")
            st.markdown("Incubator companies that were **also discovered via GitHub** (strong signal of active technical product).")

            inc_companies = inc_df[["company_id", "company_name_raw", "source", "website_url", "industry"]].drop_duplicates("company_id")
            gh_company_ids = set(gh_df["company_id"].tolist()) if len(gh_df) > 0 else set()
            inc_companies["on_github"] = inc_companies["company_id"].isin(gh_company_ids)

            on_github = inc_companies[inc_companies["on_github"]]
            not_on_github = inc_companies[~inc_companies["on_github"]]

            col1, col2 = st.columns(2)
            with col1:
                st.metric("On GitHub", len(on_github))
            with col2:
                st.metric("Not on GitHub (hidden gems)", len(not_on_github))

            if len(on_github) > 0:
                st.markdown("**Incubator companies with GitHub presence:**")
                # Merge with GitHub data for stars
                on_gh_merged = pd.merge(
                    on_github,
                    gh_df[["company_id", "repo_full_name", "stars", "forks"]].drop_duplicates("company_id"),
                    on="company_id", how="left",
                )
                display_gh = on_gh_merged[["company_name_raw", "source", "industry", "repo_full_name", "stars", "forks"]].copy()
                display_gh.columns = ["Company", "Incubator", "Industry", "GitHub Repo", "Stars", "Forks"]
                display_gh = display_gh.sort_values("Stars", ascending=False, na_position="last")
                st.dataframe(display_gh, use_container_width=True, height=400)

            # Source-specific sub-tabs
            st.markdown("---")
            st.markdown("### Browse by Source")
            inc_sources = sorted(inc_df["source"].unique().tolist())
            inc_tabs = st.tabs([f"{s} ({len(inc_df[inc_df['source'] == s])})" for s in inc_sources])

            for i, source_name in enumerate(inc_sources):
                with inc_tabs[i]:
                    source_data = inc_df[inc_df["source"] == source_name].copy()

                    # Search
                    search = st.text_input(f"Search {source_name}", key=f"inc_search_{source_name}")
                    if search:
                        mask = source_data["company_name_raw"].str.contains(search, case=False, na=False)
                        if "description" in source_data.columns:
                            mask |= source_data["description"].str.contains(search, case=False, na=False)
                        source_data = source_data[mask]

                    display_cols = ["company_name_raw", "website_url", "city", "country", "industry", "program", "batch", "description"]
                    available = [c for c in display_cols if c in source_data.columns]
                    st.dataframe(source_data[available], use_container_width=True, height=500)

    # ── Tab 7: Unselected Repos ─────────────────────────────────
    with tab7:
        st.markdown("### Unselected Repos (Non-Startup)")
        st.markdown("Repos the LLM classified as **personal projects**, **research**, or **community tools**. "
                     "Review these to spot-check the filter.")

        if not has_snapshots:
            st.info("No snapshot data yet. Run the discovery script first.")
        elif "llm_classification" not in snap_df.columns:
            st.info("No LLM classification data yet. Run the pipeline without `--no-llm` to classify repos.")
        else:
            non_startup = snap_df[
                snap_df["llm_classification"].notna()
                & ~snap_df["llm_classification"].isin(["startup"])
            ]

            if len(non_startup) == 0:
                st.info("No unselected repos found. Either all repos are startups or LLM filter hasn't run yet.")
            else:
                # Metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Unselected", len(non_startup))
                with col2:
                    personal = len(non_startup[non_startup["llm_classification"] == "personal_project"])
                    st.metric("Personal Projects", personal)
                with col3:
                    research = len(non_startup[non_startup["llm_classification"] == "research"])
                    st.metric("Research", research)
                with col4:
                    community = len(non_startup[non_startup["llm_classification"] == "community_tool"])
                    st.metric("Community Tools", community)

                # Filter by classification type
                class_filter = st.multiselect(
                    "Filter by classification",
                    options=sorted(non_startup["llm_classification"].dropna().unique().tolist()),
                    default=sorted(non_startup["llm_classification"].dropna().unique().tolist()),
                    key="unselected_class_filter",
                )
                if class_filter:
                    non_startup = non_startup[non_startup["llm_classification"].isin(class_filter)]

                # Sort options
                sort_by = st.selectbox(
                    "Sort by",
                    ["stars", "startup_likelihood", "llm_confidence", "trend_score"],
                    index=0,
                    key="unselected_sort",
                )
                non_startup_sorted = non_startup.sort_values(
                    sort_by, ascending=False, na_position="last",
                )

                # Display table
                display_cols = [
                    "repo_full_name", "stars", "forks",
                    "llm_classification", "llm_confidence", "llm_reason",
                    "startup_likelihood", "ai_subdomain",
                    "language", "owner_type", "description",
                ]
                available_cols = [c for c in display_cols if c in non_startup_sorted.columns]
                display_df = non_startup_sorted[available_cols].copy()

                for col in ["startup_likelihood", "llm_confidence"]:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].round(3)
                for col in ["stars", "forks"]:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].fillna(0).astype(int)

                st.dataframe(display_df, use_container_width=True, height=600)

                # Classification distribution chart
                st.markdown("### Classification Breakdown")
                class_counts = non_startup["llm_classification"].value_counts()
                fig = px.pie(
                    values=class_counts.values,
                    names=class_counts.index,
                    hole=0.4,
                    color_discrete_sequence=["#FF6B6B", "#4ECDC4", "#45B7D1"],
                )
                fig.update_layout(template="plotly_dark", height=300)
                st.plotly_chart(fig, use_container_width=True)

    with tab_history:
        render_scrape_history_tab()


if __name__ == "__main__":
    main()
