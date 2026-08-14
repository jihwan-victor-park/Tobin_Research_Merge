"""Page shell for V2: stylesheet, top bar, theme state, and the way back to V1.

The host script hands control here when `?v=2` is set. Everything V2 renders is
scoped to that request — the stylesheet is injected per render, so leaving the
route leaves the V1 styling exactly as it was.
"""
from __future__ import annotations

import streamlit as st

from . import components as C
from . import home, theme

# Mirrors the host script's public routes so the bar stays a real navigation
# rather than a decoration. "Home" is V2 itself; the rest hand back to V1.
NAV = ["Home", "Companies", "Findings", "GitHub Discovery", "About", "Internal"]

QUERY_FLAG = "v"
QUERY_VALUE = "2"


def is_active() -> bool:
    return st.query_params.get(QUERY_FLAG) == QUERY_VALUE


def activate() -> None:
    """Enter V2 and reload into it.

    The V2 nav is reset here rather than on the way out. Streamlit refuses to
    write a widget's session key once that widget has been created during the
    current run, and on the way out the V2 radio already exists — but on the way
    in, only the V1 shell has rendered, so the write is legal. Without it, a
    reader who left V2 for another page would bounce straight back out on their
    next visit, because the V2 radio would still be holding that page.
    """
    st.session_state["v2_nav_choice"] = "Home"
    st.query_params[QUERY_FLAG] = QUERY_VALUE
    st.rerun()


def _leave_for(page: str) -> None:
    """Drop back to the V1 shell with `page` selected.

    Sets the V1 radio's key — untouched so far this run, since `main()` returns
    before building the V1 header when V2 is active — and mirrors the choice in
    the URL so the route survives a reload.
    """
    st.session_state["lnav_choice"] = page
    st.query_params.clear()
    st.query_params["page"] = page
    st.rerun()


def render() -> None:
    p = theme.palette()
    theme.inject_css(p)

    with st.container(key="v2root"):
        selected, picked_mode = C.topbar(NAV, theme.current_mode())

        if picked_mode and picked_mode != theme.current_mode():
            theme.set_mode(picked_mode)
            st.rerun()

        if selected and selected != "Home":
            _leave_for(selected)

        home.render(p)
