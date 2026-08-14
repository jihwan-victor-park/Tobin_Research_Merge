"""Page shell for V2: stylesheet, top bar, theme state, and page dispatch.

The host script hands control here when `?v=2` is set, and from that point V2
owns the whole shell. Every route renders inside it — the homepage from this
package, and the existing Companies / Findings / GitHub Discovery / About /
Internal pages by calling the very functions the V1 shell calls. Those pages
keep their own logic and queries untouched; only the surface they are drawn on
changes.
"""
from __future__ import annotations

from contextlib import contextmanager

import streamlit as st

from . import components as C
from . import home, theme
from .theme import Palette

# Mirrors the host script's public routes.
NAV = ["Home", "Companies", "Findings", "GitHub Discovery", "About", "Internal"]
INTERNAL = ["AI Analysis", "Trends", "Pipeline Health", "Inventory", "Scraper"]

QUERY_FLAG = "v"
QUERY_VALUE = "2"


def is_active() -> bool:
    return st.query_params.get(QUERY_FLAG) == QUERY_VALUE


def activate() -> None:
    """Enter V2 and reload into it.

    The V2 nav is reset here rather than on the way out. Streamlit refuses to
    write a widget's session key once that widget has been created during the
    current run, and on the way out the V2 radio already exists — but on the way
    in, only the V1 shell has rendered, so the write is legal.
    """
    st.session_state["v2_nav_choice"] = "Home"
    st.query_params[QUERY_FLAG] = QUERY_VALUE
    st.rerun()


def leave() -> None:
    """Return to the V1 shell."""
    st.query_params.clear()
    st.rerun()


# ── Rendering the existing pages under this theme ────────────────────────

@contextmanager
def _v1_chart_palette(mod, p: Palette):
    """Point the host script's chart colours at the active V2 palette.

    Those pages build Plotly figures from module-level colour constants read at
    call time, so swapping the constants for the duration of the render themes
    every chart on them without touching a single chart call. In dark mode this
    is the difference between readable and a white plot on a black page.

    Caveat worth knowing: module globals are process-wide, so a V1 request
    served concurrently in another session could observe the swapped values for
    the length of one render. Acceptable on an experimental branch that is not
    deployed; a real fix means threading a palette through `_layout()`.
    """
    swap = {
        "BG": p.bg, "BG_OFF": p.surface_alt, "BG_CARD": p.surface,
        "BORDER": p.border, "BORDER_LIGHT": p.border_soft,
        "TXT": p.text, "TXT2": p.text2, "TXT3": p.text3,
        "ACCENT": p.accent, "GRAY_CTX": p.context,
        "GREEN": p.pos, "RED": p.neg,
    }
    saved = {k: getattr(mod, k) for k in swap if hasattr(mod, k)}
    try:
        for k, v in swap.items():
            if hasattr(mod, k):
                setattr(mod, k, v)
        yield
    finally:
        for k, v in saved.items():
            setattr(mod, k, v)


def _render_v1_page(page: str, p: Palette) -> None:
    """Draw one of the existing pages inside the V2 shell."""
    from frontend import pipeline_dashboard as v1

    with _v1_chart_palette(v1, p):
        if page == "Companies":
            v1.page_companies()
        elif page == "Findings":
            v1.page_research()
        elif page == "About":
            v1.page_about()
        elif page == "GitHub Discovery":
            _scraper, github_all = v1._company_frames()
            if "llm_classification" in github_all.columns:
                github = github_all[github_all["llm_classification"] == "startup"].copy()
            else:
                github = github_all.iloc[0:0].copy()
            v1.page_github(github, github_all)
        elif page == "Internal":
            _render_internal(v1)


def _render_internal(v1) -> None:
    """The operations pages, behind the same sub-nav the V1 shell uses."""
    with st.container(key="v2subnav"):
        sub = st.radio("Internal pages", INTERNAL, horizontal=True,
                       label_visibility="collapsed", key="v2_internal_choice")
    C.spacer(18)

    if sub == "AI Analysis":
        scraper_df, _gh = v1._company_frames()
        v1.page_ai_analysis(scraper_df, v1._load_overview_stats(),
                            source_stats=v1._load_source_ai_stats(),
                            country_stats=v1._load_country_ai_stats(min_companies=1))
    elif sub == "Trends":
        scraper_df, _gh = v1._company_frames()
        v1.page_trends(scraper_df)
    elif sub == "Pipeline Health":
        v1.page_health(v1.load_site_health(), v1.load_recent_runs())
    elif sub == "Inventory":
        v1.page_inventory()
    elif sub == "Scraper":
        v1.page_scraper()


# ── Entry point ──────────────────────────────────────────────────────────

def render() -> None:
    p = theme.palette()
    theme.inject_css(p)

    with st.container(key="v2root"):
        selected, picked_mode = C.topbar(NAV, theme.current_mode())

        if picked_mode and picked_mode != theme.current_mode():
            theme.set_mode(picked_mode)
            st.rerun()

        if selected == "Home" or not selected:
            home.render(p)
        else:
            C.spacer(14)
            _render_v1_page(selected, p)
