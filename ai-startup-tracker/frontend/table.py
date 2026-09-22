"""One table style, used everywhere a table is shown to the public.

`st.dataframe` paints to a canvas the stylesheet cannot reach. That has two
consequences the design could not live with: the widget keeps its own
typeface and greys regardless of the page around it, and in dark mode it
renders a light table in the middle of a dark page. The homepage already
hand-rendered its tables for exactly that reason; this is that approach made
general, so the pages carried over from the old dashboard match it.

What you get instead of the grid widget: the site's own type — IBM Plex Mono
small-caps for headers and figures, Inter for prose — hairline rules rather
than boxes, a header that stays put while the body scrolls, and ink that
follows the active theme.

What you give up: the widget's click-to-sort and its virtualised scrolling.
Sorting is worth more than styling on an operations screen, so the internal
pages keep the widget; the public tables are ordered the way the page means
them to be read, and are capped at a few hundred rows with the full set behind
the CSV.
"""
from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

# How a column is drawn. Anything unnamed is body prose.
STRONG = "strong"    # the row's subject — full-strength ink
MUTED = "mut"        # metadata: place, dates — mono, quiet, never wraps
NUMBER = "num"       # figures — mono, right-aligned, tabular figures
BAR = "bar"          # a 0–1 score, drawn as a rule rather than printed

MAX_ROWS = 500


def _cell(value, role: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return '<td class="mut">—</td>'

    if role == BAR:
        try:
            pct = max(0.0, min(1.0, float(value))) * 100
        except (TypeError, ValueError):
            return '<td class="mut">—</td>'
        return (f'<td class="num"><span class="v2-bar">'
                f'<i style="width:{pct:.0f}%"></i></span>'
                f'<span class="v2-bar-v">{float(value):.2f}</span></td>')

    if role == NUMBER and isinstance(value, (int, float)) and not isinstance(value, bool):
        # Thousands separators and a consistent number of decimals, because a
        # column of figures is only comparable if they are written alike.
        value = f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"

    text = escape(str(value)).strip() or "—"
    return f'<td class="{role}">{text}</td>' if role else f"<td>{text}</td>"


def render(df: pd.DataFrame, *, roles: dict[str, str] | None = None,
           widths: dict[str, str] | None = None, height: int | None = None,
           max_rows: int = MAX_ROWS, empty: str = "Nothing to show yet.") -> int:
    """Draw a frame as the site's table. Returns the number of rows drawn.

    `roles` maps column name to one of the constants above; `widths` maps
    column name to any CSS width, which is worth setting whenever one column
    holds prose and the rest hold short values — left to itself the browser
    gives the prose column too little room.
    """
    if df is None or df.empty:
        st.markdown(f'<p class="v2-empty">{escape(empty)}</p>',
                    unsafe_allow_html=True)
        return 0

    roles = roles or {}
    shown = df.head(max_rows)
    cols = "".join(
        f'<col style="width:{widths[c]}">' if widths and c in widths else "<col>"
        for c in shown.columns)
    head = "".join(
        # A right-aligned column needs its header right-aligned too, or the
        # label floats away from the figures it names.
        f'<th class="num">{escape(str(c))}</th>'
        if roles.get(c) in (NUMBER, BAR) else f"<th>{escape(str(c))}</th>"
        for c in shown.columns)
    body = "".join(
        "<tr>" + "".join(_cell(r[c], roles.get(c, "")) for c in shown.columns) + "</tr>"
        for _, r in shown.iterrows())

    style = f' style="max-height:{height}px"' if height else ""
    st.markdown(
        f'<div class="v2-tablewrap{" scroll" if height else ""}"{style}>'
        f'<table class="v2-table"><colgroup>{cols}</colgroup>'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>",
        unsafe_allow_html=True,
    )
    return len(shown)
