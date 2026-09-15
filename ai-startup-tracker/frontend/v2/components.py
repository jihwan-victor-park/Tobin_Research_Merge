"""Rendering pieces for the V2 homepage.

Each function draws one region of the page and takes already-loaded data, so
layout never triggers a query and the page can be re-composed freely. Anything
that came out of the database is escaped before it reaches the DOM.

Tables are hand-rendered HTML rather than `st.dataframe`: the grid widget paints
to a canvas the stylesheet cannot reach, which would leave a light-mode table
sitting in the middle of the dark theme.
"""
from __future__ import annotations

from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backend.utils.anonymize import stealth_label, strip_provenance

from . import data as D
from .intelligence import Answer
from .theme import PLOT_CONFIG, Palette, plot_layout


def _md(html: str) -> None:
    st.markdown(html, unsafe_allow_html=True)


def spacer(px: int) -> None:
    """Vertical space between top-level page sections.

    Only reliable at page level: inside `st.columns`, Streamlit's element
    wrapper does not grow to an empty child's height, so a spacer there
    collapses to a fixed ~18px whatever value it is given. Use the `top`
    argument on `section_head` for gaps inside a column instead.
    """
    _md(f'<div style="height:{px}px"></div>')


def section_head(label: str, meta: str = "", soft: bool = False, top: int = 0) -> None:
    cls = "v2-secthead soft" if soft else "v2-secthead"
    style = f' style="margin-top:{top}px"' if top else ""
    _md(f'<div class="{cls}"{style}><p class="v2-label">{escape(label)}</p>'
        f'<p class="v2-meta">{escape(meta)}</p></div>')


def _signed(value: float | None, unit: str = "%", digits: int = 1) -> str:
    """A signed figure with its arrow. The arrow is the encoding that carries
    direction — color alone would fail for red/green colorblind readers."""
    if value is None or pd.isna(value):
        return '<span class="v2-flat">—</span>'
    if value > 0.5:
        return f'<span class="v2-up">+{value:.{digits}f}{unit} ↑</span>'
    if value < -0.5:
        return f'<span class="v2-down">{value:.{digits}f}{unit} ↓</span>'
    return f'<span class="v2-flat">{value:+.{digits}f}{unit} ·</span>'


# ── Top bar ──────────────────────────────────────────────────────────────

def topbar(nav_items: list[str], mode: str) -> tuple[str, str | None]:
    """Brand, primary nav and theme switch.

    Returns (selected_page, picked_mode). `picked_mode` is None when the switch
    holds no selection, so deselecting it keeps the current theme instead of
    silently reverting to light.
    """
    with st.container(key="v2topbar"):
        brand_col, nav_col, theme_col = st.columns([1.5, 3.1, 0.62],
                                                   vertical_alignment="center")
        with brand_col:
            _md('<div class="v2-brand">'
                '<span class="v2-brand-name">AI Startup Tracker</span>'
                '</div>')
        with nav_col:
            with st.container(key="v2nav"):
                selected = st.radio("Navigation", nav_items, horizontal=True,
                                    label_visibility="collapsed", key="v2_nav_choice")
        with theme_col:
            with st.container(key="v2theme"):
                picked = st.segmented_control(
                    "Theme", ["Light", "Dark"],
                    default="Dark" if mode == "dark" else "Light",
                    label_visibility="collapsed", key="v2_theme_choice",
                )
        spacer(12)
    picked_mode = {"Dark": "dark", "Light": "light"}.get(picked)
    return selected, picked_mode


def status_line(snap: D.Snapshot) -> None:
    """The thin dataset rule under the nav. Information, not a badge.

    The lead segment reports collection state rather than always reading
    "LIVE DATASET": the figures below it are a snapshot, and calling a
    month-old snapshot live is the one claim on this rule that could mislead.
    """
    as_of = snap.as_of.strftime("%b %d, %Y").upper() if snap.as_of else "—"
    lead = ('<span class="live">LIVE DATASET</span>' if not snap.is_stale
            else f'<span class="stale">SNAPSHOT · {snap.stale_days} DAYS OLD</span>')
    segs = [
        f'<span class="seg">{lead}</span>',
        f'<span class="seg"><b>{snap.total:,}</b> COMPANIES</span>',
        f'<span class="seg"><b>{snap.hidden:,}</b> NOT IN CRUNCHBASE OR PITCHBOOK</span>',
        f'<span class="seg"><b>{snap.countries:,}</b> COUNTRIES</span>',
        f'<span class="seg">UPDATED {as_of}</span>',
    ]
    _md(f'<div class="v2-status">{"".join(segs)}</div>')


def freshness_notice(act: D.Activity) -> None:
    """Say when the window shown is not the window the reader assumes.

    Collection has been paused since mid-August; without this the 30-day
    section reads as the last 30 days.
    """
    end = act.end.strftime("%B %d, %Y") if act.end else "—"
    _md('<div class="v2-notice">'
        f'No companies have been recorded since {escape(end)} '
        f'({act.stale_days} days ago). The window below is the 30 days ending '
        'then, not the 30 days ending today.'
        '</div>')


def hero() -> None:
    _md('<div class="v2-hero">'
        '<h1 class="v2-hero-title">Understand AI as it happens.</h1>'
        '<p class="v2-hero-lede">Explore the companies, sectors, locations and '
        'signals shaping the AI ecosystem — including the firms commercial '
        'databases have not registered yet.</p>'
        '</div>')


def hero_map(df: pd.DataFrame, p: Palette, height: int = 268,
             caption: str = "") -> None:
    """A quiet density map beside the headline.

    Low-contrast and non-interactive: it anchors the opening band and shows the
    coverage the page is about, without competing with the ask panel or
    duplicating the detailed map further down. `caption` names what is being
    shaded — the panel otherwise reads as a different dataset from the headline
    beside it.
    """
    if df.empty:
        return
    import numpy as np

    m = df.copy()
    m["z"] = np.log10(m["total"].clip(lower=1))
    # Deliberately shallow: this is a locator, and at full accent strength it
    # pulled the eye away from the ask panel it sits beside.
    ramp = ([[0, "#171c22"], [0.6, "#22384f"], [1, "#3a6a9e"]] if p.is_dark
            else [[0, "#e6e4da"], [0.6, "#c3cfe2"], [1, "#8ba6cd"]])
    fig = go.Figure(go.Choropleth(
        locations=m["country"], locationmode="country names", z=m["z"],
        colorscale=ramp, showscale=False,
        marker_line_color=p.bg, marker_line_width=0.5,
        hoverinfo="skip",
    ))
    fig.update_geos(showframe=False, showcoastlines=False, showland=True,
                    landcolor=p.surface_alt, bgcolor="rgba(0,0,0,0)",
                    lakecolor="rgba(0,0,0,0)", projection_type="natural earth",
                    lataxis_range=[-58, 84])
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0),
                      paper_bgcolor="rgba(0,0,0,0)", dragmode=False)
    # A real container, not a markdown <div>: Streamlit closes each markdown
    # block in its own wrapper, so an opening tag never actually encloses the
    # chart that follows it.
    with st.container(key="v2heromap"):
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False, "staticPlot": True})
        if caption:
            # Without this the map reads as a second, unrelated dataset sitting
            # beside the headline. It is the same one, shaded by how many
            # companies each country holds.
            _md(f'<p class="v2-small" style="margin-top:-4px">{escape(caption)}</p>')


# ── Ask bar ──────────────────────────────────────────────────────────────

def ask_panel(examples: list[str]) -> str | None:
    """The natural-language query bar, label and prompts as one surface.

    Returns a question when one is submitted. Kept inside the opening band so
    the reader meets it as the way into the page, not as a search widget parked
    beneath the headline.
    """
    submitted: str | None = None
    with st.container(key="v2askpanel"):
        _md('<p class="v2-label" style="margin-bottom:11px">'
            'Ask the global AI ecosystem</p>')
        with st.container(key="v2ask"):
            field, button = st.columns([4.6, 1.15], vertical_alignment="center")
            with field:
                typed = st.text_input(
                    "Question", key="v2_question",
                    placeholder="Ask anything about companies, sectors, "
                                "locations, or trends...",
                    label_visibility="collapsed",
                )
            with button:
                clicked = st.button("Ask →", key="v2_ask_go", use_container_width=True)

        # Enter in the field and the button both submit; a queued example wins once.
        queued = st.session_state.pop("v2_queued_question", None)
        if queued:
            submitted = queued
        elif typed and (clicked or typed != st.session_state.get("v2_last_question")):
            submitted = typed
        if submitted:
            st.session_state["v2_last_question"] = submitted

        with st.container(key="v2examples"):
            cols = st.columns(len(examples))
            for col, example in zip(cols, examples):
                with col:
                    if st.button(example, key=f"v2_ex_{hash(example) & 0xffff}",
                                 use_container_width=True):
                        st.session_state["v2_queued_question"] = example
                        st.rerun()
    return submitted


def answer_panel(ans: Answer, p: Palette) -> None:
    """The expanded intelligence report under the ask bar."""
    with st.container(key="v2answer"):
        _md(f'<p class="v2-answer-q">› {escape(ans.question)}</p>'
            f'<p class="v2-answer-kicker">Dataset intelligence</p>'
            f'<h2 class="v2-h2">{escape(ans.headline)}</h2>'
            f'<p class="v2-body">{escape(ans.narrative)}</p>')

        if ans.empty:
            _md(f'<p class="v2-answer-note">{escape(ans.basis)}</p>')
            return

        if ans.metrics:
            cells = "".join(
                f'<div class="cell"><span class="k">{escape(m.label)}</span>'
                f'<span class="v">{escape(m.value)}</span>'
                + (f'<span class="d">{escape(m.delta)}</span>' if m.delta else "")
                + "</div>"
                for m in ans.metrics
            )
            _md(f'<div class="v2-strip compact">{cells}</div>')

        spacer(14)
        left, right = st.columns([1.6, 1], gap="large")
        with left:
            if not ans.series.empty and len(ans.series) > 2:
                _md('<p class="v2-meta" style="margin-bottom:6px">'
                    'Companies founded per year, this scope</p>')
                _line_chart(ans.series, p, height=178)
            elif not ans.companies.empty:
                _company_table(ans.companies)
        with right:
            if not ans.ranking.empty:
                _md(f'<p class="v2-meta" style="margin-bottom:8px">'
                    f'{escape(ans.ranking_title)}</p>')
                rank_rows(ans.ranking, unit=ans.ranking_unit, signed=True)

        if not ans.series.empty and len(ans.series) > 2 and not ans.companies.empty:
            spacer(18)
            _md('<p class="v2-meta" style="margin-bottom:8px">'
                'Recently discovered in this scope · not in Crunchbase or PitchBook</p>')
            _company_table(ans.companies)

        if ans.sources:
            coverage(ans.sources)

        engine = {
            "model": "Claude synthesis over computed aggregates, figures verified "
                     "against them",
            "computed": "Computed aggregates, summarised without a model",
            "rejected": "Computed aggregates — a model summary was discarded for "
                        "citing a figure not in the data",
        }[ans.narrative_source]
        _md(f'<p class="v2-answer-note">{escape(ans.basis)} · {engine}</p>')


def loading(message: str = "Querying dataset") -> None:
    _md(f'<p class="v2-loading">{escape(message)}</p>')


# ── Strips, rows, tables ─────────────────────────────────────────────────

def sparkline(values: list[float], p: Palette, width: int = 66, height: int = 24) -> str:
    """An inline SVG trend line for a metric cell.

    Drawn by hand rather than with the chart library: four of these render on
    every page load, and at this size a polyline is both lighter and easier to
    keep on the type baseline.
    """
    pts = [float(v) for v in values if v is not None]
    if len(pts) < 3:
        return ""
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    step = width / (len(pts) - 1)
    pad = 2.5
    coords = [
        (i * step, height - pad - (v - lo) / span * (height - 2 * pad))
        for i, v in enumerate(pts)
    ]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    ex, ey = coords[-1]
    return (
        f'<span class="spark"><svg width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" aria-hidden="true">'
        f'<polyline points="{path}" fill="none" stroke="{p.accent}" '
        f'stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="2" fill="{p.accent}"/>'
        f"</svg></span>"
    )


def metrics_strip(items: list[tuple[str, str, str | None, str]]) -> None:
    """Compact market strip: (label, value, sub, sparkline_html) per cell."""
    cells = "".join(
        f'<div class="cell"><span class="k">{escape(k)}</span>'
        f'<span class="row"><span class="v">{v}</span>{spark}</span>'
        + (f'<span class="d">{sub}</span>' if sub else "")
        + "</div>"
        for k, v, sub, spark in items
    )
    _md(f'<div class="v2-strip">{cells}</div>')


def rank_rows(df: pd.DataFrame, unit: str = "%", signed: bool = False,
              show_bar: bool = False, rank: bool = False,
              count: bool = False, total: float | None = None,
              note: str | None = None) -> None:
    """A ranked list on hairlines. Expects columns label, value, and optional sub.

    `total` and `note` exist because every list here is a top-N slice of a much
    larger set, so the percentages never summed to 100 and readers reasonably
    took that for an error. Pass `total` (the full denominator, in the same
    unit as `value`) and the remainder is drawn as an explicit "Other" row
    rather than left missing; pass `note` to name the denominator in words.
    A residual under half a unit is dropped -- an "Other 0.0%" row is noise.
    """
    if df.empty:
        empty_state("No ranking available for this scope.")
        return

    df = df.reset_index(drop=True)
    if total is not None:
        residual = float(total) - float(df["value"].sum())
        if residual >= (0.5 if not count else 1):
            df = pd.concat([df, pd.DataFrame([{
                "label": "Other",
                "value": residual,
                **({"sub": ""} if "sub" in df.columns else {}),
            }])], ignore_index=True)

    peak = float(df["value"].abs().max()) or 1.0
    rows = []
    for i, r in df.iterrows():
        val = float(r["value"])
        if signed:
            value_html = _signed(val, unit)
        elif count:
            value_html = f"<span>{int(round(val)):,}{unit}</span>"
        else:
            value_html = f'<span>{val:.1f}{unit}</span>'
        parts = []
        if rank:
            parts.append(f'<span class="rank">{i + 1:02d}</span>')
        parts.append(f'<span class="name">{escape(str(r["label"]))}</span>')
        if show_bar:
            width = min(100.0, abs(val) / peak * 100)
            parts.append(f'<span class="bar"><i style="width:{width:.1f}%"></i></span>')
        if "sub" in df.columns and pd.notna(r.get("sub")):
            parts.append(f'<span class="sub">{escape(str(r["sub"]))}</span>')
        parts.append(f'<span class="val">{value_html}</span>')
        rows.append(f'<div class="row">{"".join(parts)}</div>')
    _md(f'<div class="v2-rows">{"".join(rows)}</div>')
    if note:
        _md(f'<p class="v2-small" style="margin-top:8px">{escape(note)}</p>')


def _text(value) -> str:
    """A trimmed string from a dataframe cell. NaN is a float and truthy, so a
    plain `or ""` is not enough here."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _clip(text: str, limit: int) -> str:
    """Trim to a word boundary. Descriptions arrive pre-cut by the query, which
    leaves them ending mid-word."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:·-")
    return f"{cut}…"


def _company_table(df: pd.DataFrame) -> None:
    if df.empty:
        empty_state("No companies to show yet.")
        return
    cols = ('<colgroup><col class="c-name"><col class="c-desc">'
            '<col class="c-place"><col class="c-chan"></colgroup>')
    head = ("<tr><th>Company</th><th>What it does</th>"
            "<th>Location</th><th>First recorded</th></tr>")
    body = []
    for i, (_, r) in enumerate(df.iterrows()):
        # Identity withheld -- see backend/utils/anonymize. The label is
        # derived from the surrogate key so the same company reads the same on
        # every render; `name` and `domain` are never emitted.
        key = r.get("id", r.get("domain", f"row-{i}"))
        name = escape(stealth_label(key))
        # The last column used to name the channel a company arrived through
        # (a grant portal, a named portfolio page), and grant-sourced
        # descriptions open with the award programme. Both state the
        # collection method once per row; the date says as much without it.
        desc = escape(_clip(strip_provenance(r.get("description")), 132)) or "—"
        place = " · ".join(x for x in [_text(r.get("city")) or None,
                                       _text(r.get("country")) or None] if x) or "—"
        seen = _text(r.get("first_seen")) or "—"
        body.append(
            f'<tr><td class="name">{name}</td><td>{desc}</td>'
            f'<td class="mut">{escape(place)}</td>'
            f'<td class="mut">{escape(seen)}</td></tr>'
        )
    _md(f'<div class="v2-tablewrap"><table class="v2-table">{cols}'
        f"<thead>{head}</thead><tbody>{''.join(body)}</tbody></table></div>")


def coverage(links: list[tuple[str, str]]) -> None:
    """Where in our own research the figure above was computed.

    Internal routes, not outlet searches: a link out to whatever a newsroom
    happens to have published is not support for a number we derived here.
    """
    if not links:
        return
    items = "".join(
        f'<a href="{escape(url)}">{escape(name)}</a>' for name, url in links
    )
    _md('<div class="v2-coverage">'
        '<div class="head">Related analysis · this dataset</div>'
        f'<div class="links">{items}</div></div>')


def empty_state(message: str) -> None:
    _md(f'<div class="v2-empty">{escape(message)}</div>')


# ── Charts ───────────────────────────────────────────────────────────────

def _line_chart(df: pd.DataFrame, p: Palette, height: int = 300,
                provisional_from: int | None = None, value_col: str = "n",
                unit: str = "", tickformat: str = ",.0f",
                hover: str = "%{y:,} companies",
                customdata: str | None = None) -> None:
    """One series, thin stroke. Years still filling in continue as a dashed
    context-colored segment so the coverage cliff is never read as a real drop.

    `value_col` exists so the same chart can plot a share instead of a count;
    `customdata` names a second column carried into the hover, which lets a
    share label the base it was computed on.
    """
    complete = df if provisional_from is None else df[df["year"] <= provisional_from]

    def _cd(frame):
        return frame[[customdata]].to_numpy() if customdata else None

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=complete["year"], y=complete[value_col], mode="lines",
        line=dict(color=p.accent, width=2, shape="linear"),
        customdata=_cd(complete),
        hovertemplate=f"{hover}<extra></extra>", name="Founded",
    ))
    if provisional_from is not None:
        tail = df[df["year"] >= provisional_from]
        if len(tail) > 1:
            fig.add_trace(go.Scatter(
                x=tail["year"], y=tail[value_col], mode="lines",
                line=dict(color=p.context, width=2, dash="dot"),
                customdata=_cd(tail),
                hovertemplate=f"{hover} (partial)<extra></extra>",
                name="Partial",
            ))
    if not complete.empty:
        last = complete.iloc[-1]
        fig.add_trace(go.Scatter(
            x=[last["year"]], y=[last[value_col]], mode="markers",
            marker=dict(color=p.accent, size=8), hoverinfo="skip", showlegend=False,
        ))
    fig.update_layout(**plot_layout(
        p, height=height,
        yaxis=dict(gridcolor=p.border_soft, zeroline=False, rangemode="tozero",
                   tickformat=tickformat, ticksuffix=unit,
                   linecolor="rgba(0,0,0,0)",
                   tickfont=dict(size=11, color=p.text3, family="IBM Plex Mono")),
        xaxis=dict(showgrid=False, zeroline=False, linecolor=p.border, dtick=2,
                   ticks="outside", tickcolor=p.border, ticklen=4,
                   tickfont=dict(size=11, color=p.text3, family="IBM Plex Mono")),
    ))
    st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)


def formation_chart(f: D.Formation, p: Palette) -> None:
    """AI's share of company formation by founding year.

    Share rather than count, deliberately — see `D.Formation`. Plotting the
    count here drew a line falling from 2018 onward, which is the shape of our
    coverage, not of the world.
    """
    if f.series.empty:
        empty_state("Formation history is not available for this dataset yet.")
        return
    _line_chart(f.series, p, height=316, provisional_from=f.last_complete,
                value_col="share", unit="%", tickformat=".0f",
                hover="%{y:.1f}% of %{customdata[0]:,} companies founded",
                customdata="total")

    notes = ["Each point is AI companies as a share of all companies founded "
             "that year. Share rather than count: the most recent founding "
             "years are still filling in, and in the ratio that incomplete "
             "coverage largely cancels."]
    if f.last_complete:
        # Stating the direction of the residual bias matters more than the
        # dotting. The ratio is robust to coverage falling evenly; it is not
        # robust to AI companies surfacing faster than the rest, which the
        # discovery channels make likely.
        notes.append(f"Years after {f.last_complete} appear as a dotted "
                     "continuation: coverage there is thin enough that the "
                     "share is indicative only, and it likely leans high, "
                     "because the channels that find companies quickly are "
                     "themselves AI-tilted.")
    _md(f'<p class="v2-small" style="margin-top:10px">{escape(" ".join(notes))}</p>')


# ── Weekly briefing ──────────────────────────────────────────────────────

def briefing(briefs: list) -> None:
    """The week's briefs as one continuous stream on a timeline rail.

    Each brief is a paragraph, the figure it rests on, and where to read around
    it. The first is set larger because it is the lead, not because it is a
    different kind of thing.
    """
    if not briefs:
        empty_state("Not enough recent activity to assemble a briefing.")
        return

    blocks = []
    for i, b in enumerate(briefs):
        cls = "v2-brief v2-reveal" + (" lead" if i == 0 else "")
        fig = ""
        if b.figure:
            fig = ('<div class="fig"><span class="tag">Our data</span>'
                   f'<span class="n">{escape(b.figure)}</span>'
                   f'<span class="cap">{escape(b.figure_caption)}</span></div>')
        kicker = (f'<p class="kicker">{escape(b.kicker)}</p>' if b.kicker else "")
        blocks.append(
            f'<div class="{cls}">{kicker}'
            f'<p class="t">{escape(b.headline)}</p>'
            f'<p class="d">{b.body}</p>{fig}</div>'
        )
    _md("".join(blocks))


def quarterly_update(df: pd.DataFrame) -> None:
    """Our collection, quarter by quarter, in the briefing's own layout.

    Reuses the `v2-brief` classes on purpose: the meeting asked for the news
    slot to carry our quarterly research signal, and keeping the visual form
    means the page rhythm does not change -- only the source of the content,
    which is now entirely our own scrapers.
    """
    if df.empty:
        empty_state("Not enough quarterly history to report yet.")
        return

    blocks = []
    for i, (_, r) in enumerate(df.iterrows()):
        q = pd.Timestamp(r["q"])
        label = f"{q.year} Q{(q.month - 1) // 3 + 1}"
        n = int(r["discovered"])
        delta = r.get("delta")

        if pd.notna(delta):
            direction = "up" if float(delta) >= 0 else "down"
            move = (f' That is <b>{abs(float(delta)):.0f}% '
                    f'{"more" if direction == "up" else "fewer"}</b> than the '
                    f'quarter before.')
            headline = (f"Discovery {'rose' if direction == 'up' else 'slowed'} "
                        f"in {label}")
        else:
            move = ""
            headline = f"{label}: {n:,} companies found"

        site = int(r["with_site"])
        body = (f"Our scrapers found <b>{n:,}</b> AI companies in {label} that "
                f"appear in neither Crunchbase nor PitchBook, across "
                f"<b>{int(r['countries'])}</b> countries.{move} "
                f"<b>{site:,}</b> of them already run a live website.")

        cls = "v2-brief v2-reveal" + (" lead" if i == 0 else "")
        blocks.append(
            f'<div class="{cls}"><p class="kicker">Quarterly update · {escape(label)}</p>'
            f'<p class="t">{escape(headline)}</p>'
            f'<p class="d">{body}</p>'
            f'<div class="fig"><span class="tag">Our scrapers</span>'
            f'<span class="n">{n:,}</span>'
            f'<span class="cap">companies discovered in {escape(label)}</span></div>'
            f'</div>'
        )
    _md("".join(blocks))
    _md('<p class="v2-small" style="margin-top:14px">Counts companies our own '
        'collection found, in neither commercial database. Bulk-imported records '
        'are excluded: they would date tens of thousands of companies to the '
        'quarter a file was loaded.</p>')


def _overlap_note() -> str:
    """Why the category shares do not close at 100%, said once.

    Not a rounding artefact and not a top-N truncation: `ai_tags` is an array,
    so a company tagged both "agents" and "llm" is counted in both rows. The
    shares genuinely overlap. Every other ranked list on the page closes at
    100% with an explicit "Other", so this one has to explain itself.
    """
    (r0, r1), (p0, p1) = D.cohorts()
    return (f"Share of AI companies founded {r0}–{r1} carrying each tag. "
            f"Companies can carry several tags, so these shares overlap and do "
            f"not sum to 100%. Beside each: how many companies, and how its "
            f"share moved against {p0}–{p1}.")


def market_signals(cats: pd.DataFrame) -> None:
    if cats.empty:
        empty_state("Category momentum needs more founding-year coverage.")
        return
    df = pd.DataFrame({
        "label": cats["label"],
        "value": cats["share"].astype(float),
        "sub": [f"{int(n):,} · {float(g):+.0f}%"
                for n, g in zip(cats["recent"], cats["growth"])],
    })
    # No bar: this sits in a narrow column beside the chart.
    rank_rows(df, unit="%", note=_overlap_note())


def discovery_channels(week: D.Activity) -> None:
    """Which channels produced the arrivals — the intake's composition.

    Internal only: this names the collection method, which the public pages do
    not publish. Kept because the operations pages still want the breakdown.
    """
    if week.channels.empty or not week.total:
        empty_state("No intake recorded for the most recent week.")
        return
    ch = week.channels.copy()
    df = pd.DataFrame({
        "label": ch["channel"],
        "value": ch["n"] / week.total * 100,
        "sub": ch["n"].map(lambda n: f"{int(n):,}"),
    })
    rank_rows(df, unit="%", show_bar=True, total=100.0,
              note=f"Share of the {week.total:,} companies recorded in this window.")


def category_ranking(cats: pd.DataFrame) -> None:
    if cats.empty:
        empty_state("Category momentum needs more founding-year coverage.")
        return
    df = pd.DataFrame({
        "label": cats["label"],
        "value": cats["share"].astype(float),
        "sub": [f"{int(n):,} · {float(g):+.0f}%"
                for n, g in zip(cats["recent"], cats["growth"])],
    })
    # No `total` here, and that is deliberate. Categories come from ai_tags,
    # which is an array: a company tagged both "agents" and "llm" is counted in
    # both rows. These shares therefore overlap and CANNOT sum to 100, so
    # drawing an "Other" remainder would assert a breakdown that does not
    # exist. The note says so instead of leaving the reader to wonder.
    rank_rows(df, unit="%", rank=True, note=_overlap_note())


# Long country names push the city out of a compact row, so the ranked list
# uses the short form readers already use in print.
_SHORT_COUNTRY = {
    "United States": "US", "United Kingdom": "UK",
    "United Arab Emirates": "UAE", "South Korea": "S. Korea",
    "Netherlands": "NL", "Switzerland": "CH", "Germany": "DE",
}


def headquarters(geo: pd.DataFrame) -> None:
    """Cities ranked by companies founded in the recent cohort.

    The count is the value and the share change is the annotation: "how many
    were founded here" is the question a reader actually brings to a list of
    cities, and the share tells them whether it is rising.
    """
    if geo.empty:
        empty_state("City-level coverage is too thin to rank.")
        return

    def label(r) -> str:
        city = str(r["city"])
        if not pd.notna(r["country"]):
            return city
        country = str(r["country"])
        # City states repeat themselves — "Singapore, Singapore" reads as a bug.
        if country.lower() == city.lower():
            return city
        return f"{city}, {_SHORT_COUNTRY.get(country, country)}"

    df = pd.DataFrame({
        "label": geo.apply(label, axis=1),
        "value": geo["share"].astype(float),
        "sub": [f"{int(n):,} · {'—' if pd.isna(g) else f'{float(g):+.0f}%'}"
                for n, g in zip(geo["recent"], geo["growth"])],
    })
    # A company has one city, so these shares DO sum -- the remainder is drawn
    # as "Other" and the list closes at 100%. Cities used to be ranked by raw
    # count with the share change beside them, which put a third kind of
    # percentage next to the category and region panels and gave the reader
    # three different things all labelled "%".
    rank_rows(df, unit="%", rank=True, total=100.0,
              note="Share of AI companies founded in the recent cohort that "
                   "record a city. Beside each: how many, and how its share "
                   "moved against the prior cohort.")


def domain_ranking(domains: pd.DataFrame, mapped_total: int) -> None:
    """The largest activity domains, as a share of everything classified.

    Grouped from company descriptions rather than assigned from a fixed sector
    list, so the labels are the ones the data produced.
    """
    if domains.empty or not mapped_total:
        empty_state("Activity domains are not classified for this dataset yet.")
        return
    df = pd.DataFrame({
        "label": domains["domain"],
        "value": domains["total"] / mapped_total * 100,
        "sub": domains["total"].map(lambda n: f"{int(n):,}"),
    })
    rank_rows(df, unit="%", show_bar=True, rank=True, total=100.0,
              note=(f"Share of the {mapped_total:,} AI companies classified so "
                    f"far. Companies without a usable description yet are not "
                    f"counted."))


def domain_note(domains: pd.DataFrame, mapped_total: int) -> None:
    """Where the unlisted population sits against the classified whole.

    A domain's unlisted share is the interesting number here: it says which
    kinds of work the commercial databases are least likely to have recorded.
    """
    if domains.empty or not mapped_total:
        return
    d = domains.copy()
    d["unlisted_share"] = d["unlisted"] / d["total"] * 100
    top = d.sort_values("unlisted_share", ascending=False).iloc[0]
    section_head("Where the unlisted sit", "SHARE UNLISTED", soft=True)
    rank_rows(
        pd.DataFrame({
            "label": d["domain"],
            "value": d["unlisted_share"],
            "sub": d["unlisted"].map(lambda n: f"{int(n):,}"),
        }).sort_values("value", ascending=False),
        unit="%", show_bar=True,
        note=(f"Within each domain, the share of companies that appear in "
              f"neither Crunchbase nor PitchBook. {escape(str(top['domain']))} "
              f"is the least well covered."),
    )


def latest_additions(df: pd.DataFrame) -> None:
    _company_table(df)


# ── Footer ───────────────────────────────────────────────────────────────

def footer(snap: D.Snapshot, f: D.Formation) -> None:
    (r0, r1), (p0, p1) = D.cohorts()
    as_of = snap.as_of.strftime("%B %d, %Y") if snap.as_of else "—"
    _md(f"""
<div class="v2-footer">
  <div class="cols">
    <div>
      <p class="fh">About this dataset</p>
      <p>The tracker measures where and when new AI companies form. It covers
      <b>{snap.total:,}</b> companies in <b>{snap.countries:,}</b> countries, of which
      <b>{snap.hidden:,}</b> appear in neither Crunchbase nor PitchBook &mdash; the
      layer this project exists to measure.</p>
      <p>Company-level records are published only for that unlisted population.
      Crunchbase- and PitchBook-derived rows appear here as aggregate statistics
      only, under their licence terms.</p>
    </div>
    <div>
      <p class="fh">How growth is measured</p>
      <p>Momentum figures compare the {r0}&ndash;{r1} founding cohort's share of all AI
      company formation with {p0}&ndash;{p1}. Share is used rather than raw counts
      because the most recent founding years are still filling in.</p>
      <p>Coverage is judged complete through <b>{f.last_complete or "—"}</b>; later
      years are drawn as partial and should be read as indicative.</p>
    </div>
    <div>
      <p class="fh">Coverage &amp; limits</p>
      <p>Country and city fields are normalised from mixed source formats, so place
      counts cover only companies that carry a location.</p>
      <p>Founding-year charts cover only companies that carry a founding year, which
      is far more common among listed companies than unlisted ones.</p>
      <p>Company identities are withheld; entries are shown by what they do and
      where they are.</p>
    </div>
  </div>
  <div class="fine">AI STARTUP TRACKER &nbsp;·&nbsp;
  DATASET UPDATED {escape(as_of.upper())} &nbsp;·&nbsp;
  {snap.total:,} COMPANIES TRACKED</div>
</div>
""")
