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
                '<span class="v2-brand-sub">Tobin Center for Economic Policy · Yale</span>'
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
    """The thin live-dataset rule under the nav. Information, not a badge."""
    as_of = snap.as_of.strftime("%b %d, %Y").upper() if snap.as_of else "—"
    segs = [
        '<span class="seg"><span class="live">● LIVE DATASET</span></span>',
        f'<span class="seg"><b>{snap.total:,}</b> COMPANIES</span>',
        f'<span class="seg"><b>{snap.hidden:,}</b> NOT IN CRUNCHBASE OR PITCHBOOK</span>',
        f'<span class="seg"><b>{snap.countries:,}</b> COUNTRIES</span>',
        f'<span class="seg">UPDATED {as_of}</span>',
    ]
    _md(f'<div class="v2-status">{"".join(segs)}</div>')


def hero() -> None:
    _md('<div class="v2-hero">'
        '<h1 class="v2-hero-title">Understand AI as it happens.</h1>'
        '<p class="v2-hero-lede">Explore the companies, sectors, locations and '
        'signals shaping the AI ecosystem — including the firms commercial '
        'databases have not registered yet.</p>'
        '</div>')


def hero_map(df: pd.DataFrame, p: Palette, height: int = 268) -> None:
    """A quiet density map beside the headline.

    Low-contrast and non-interactive: it anchors the opening band and shows the
    coverage the page is about, without competing with the ask panel or
    duplicating the detailed map further down.
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
              count: bool = False) -> None:
    """A ranked list on hairlines. Expects columns label, value, and optional sub."""
    if df.empty:
        empty_state("No ranking available for this scope.")
        return
    peak = float(df["value"].abs().max()) or 1.0
    rows = []
    for i, r in df.reset_index(drop=True).iterrows():
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
            "<th>Location</th><th>Discovered</th></tr>")
    body = []
    for _, r in df.iterrows():
        name = escape(_text(r.get("name")) or "—")
        domain = _text(r.get("domain"))
        if domain:
            url = domain if domain.startswith("http") else f"https://{domain}"
            name = f'<a href="{escape(url)}" target="_blank" rel="noopener">{name}</a>'
        desc = escape(_clip(_text(r.get("description")), 132)) or "—"
        place = " · ".join(x for x in [_text(r.get("city")) or None,
                                       _text(r.get("country")) or None] if x) or "—"
        body.append(
            f'<tr><td class="name">{name}</td><td>{desc}</td>'
            f'<td class="mut">{escape(place)}</td>'
            f'<td class="mut">{escape(D.discovery_channel(r))}</td></tr>'
        )
    _md(f'<div class="v2-tablewrap"><table class="v2-table">{cols}'
        f"<thead>{head}</thead><tbody>{''.join(body)}</tbody></table></div>")


def coverage(links: list[tuple[str, str]]) -> None:
    """External outlets, framed as searches because no article feed is connected."""
    items = "".join(
        f'<a href="{escape(url)}" target="_blank" rel="noopener">{escape(name)}</a>'
        for name, url in links
    )
    _md('<div class="v2-coverage">'
        '<div class="head">Related coverage · outlet search</div>'
        f'<div class="links">{items}</div></div>')


def empty_state(message: str) -> None:
    _md(f'<div class="v2-empty">{escape(message)}</div>')


# ── Charts ───────────────────────────────────────────────────────────────

def _line_chart(df: pd.DataFrame, p: Palette, height: int = 300,
                provisional_from: int | None = None) -> None:
    """One series, thin stroke. Years still filling in continue as a dashed
    context-colored segment so the coverage cliff is never read as a real drop."""
    complete = df if provisional_from is None else df[df["year"] <= provisional_from]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=complete["year"], y=complete["n"], mode="lines",
        line=dict(color=p.accent, width=2, shape="linear"),
        hovertemplate="%{y:,} companies<extra></extra>", name="Founded",
    ))
    if provisional_from is not None:
        tail = df[df["year"] >= provisional_from]
        if len(tail) > 1:
            fig.add_trace(go.Scatter(
                x=tail["year"], y=tail["n"], mode="lines",
                line=dict(color=p.context, width=2, dash="dot"),
                hovertemplate="%{y:,} companies (partial)<extra></extra>",
                name="Partial",
            ))
    if not complete.empty:
        last = complete.iloc[-1]
        fig.add_trace(go.Scatter(
            x=[last["year"]], y=[last["n"]], mode="markers",
            marker=dict(color=p.accent, size=8), hoverinfo="skip", showlegend=False,
        ))
    fig.update_layout(**plot_layout(
        p, height=height,
        yaxis=dict(gridcolor=p.border_soft, zeroline=False, rangemode="tozero",
                   tickformat=",.0f", linecolor="rgba(0,0,0,0)",
                   tickfont=dict(size=11, color=p.text3, family="IBM Plex Mono")),
        xaxis=dict(showgrid=False, zeroline=False, linecolor=p.border, dtick=2,
                   ticks="outside", tickcolor=p.border, ticklen=4,
                   tickfont=dict(size=11, color=p.text3, family="IBM Plex Mono")),
    ))
    st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)


def formation_chart(f: D.Formation, p: Palette) -> None:
    if f.series.empty:
        empty_state("Formation history is not available for this dataset yet.")
        return
    _line_chart(f.series, p, height=316, provisional_from=f.last_complete)
    if f.last_complete:
        note = (f"Founding years after {f.last_complete} are still filling in and appear "
                "as a dotted continuation — that decline is coverage, not formation.")
        _md(f'<p class="v2-small" style="margin-top:10px">{escape(note)}</p>')


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
        more = ""
        if b.sources:
            links = "".join(
                f'<a href="{escape(url)}" target="_blank" rel="noopener">'
                f'{escape(name)}</a>'
                for name, url in b.sources
            )
            more = f'<div class="more"><span class="lbl">Read more</span>{links}</div>'
        kicker = (f'<p class="kicker">{escape(b.kicker)}</p>' if b.kicker else "")
        blocks.append(
            f'<div class="{cls}">{kicker}'
            f'<p class="t">{escape(b.headline)}</p>'
            f'<p class="d">{b.body}</p>{fig}{more}</div>'
        )
    _md("".join(blocks))


def market_signals(cats: pd.DataFrame) -> None:
    if cats.empty:
        empty_state("Category momentum needs more founding-year coverage.")
        return
    # Share and base together: a percentage move means little without the
    # number of companies it rests on.
    df = pd.DataFrame({
        "label": cats["label"],
        "value": cats["growth"].astype(float),
        "sub": [f"{s:.1f}% · {int(n):,}" for s, n in zip(cats["share"], cats["recent"])],
    })
    rank_rows(df, unit="%", signed=True)


def discovery_channels(week: D.Week) -> None:
    """Which channels produced the week's arrivals — the intake's composition."""
    if week.channels.empty or not week.total:
        empty_state("No intake recorded for the most recent week.")
        return
    ch = week.channels.copy()
    df = pd.DataFrame({
        "label": ch["channel"],
        "value": ch["n"] / week.total * 100,
        "sub": ch["n"].map(lambda n: f"{int(n):,}"),
    })
    rank_rows(df, unit="%", show_bar=True)


def category_ranking(cats: pd.DataFrame) -> None:
    if cats.empty:
        empty_state("Category momentum needs more founding-year coverage.")
        return
    df = pd.DataFrame({
        "label": cats["label"],
        "value": cats["growth"].astype(float),
        "sub": cats["recent"].map(lambda n: f"{int(n):,} cos"),
    })
    rank_rows(df, unit="%", signed=True, rank=True)


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
        "value": geo["recent"].astype(float),
        "sub": geo["growth"].map(lambda g: "—" if pd.isna(g) else f"{float(g):+.0f}%"),
    })
    rank_rows(df, unit="", count=True, rank=True)


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
      <p>The tracker records AI company formation across public code hosts and model
      hubs, accelerator and venture portfolios, government grant awards, and startup
      media. Its distinguishing coverage is the <b>{snap.hidden:,}</b> companies that
      appear in neither Crunchbase nor PitchBook.</p>
      <p>Company-level records are published only for that hidden population.
      Crunchbase- and PitchBook-derived rows appear here as aggregate statistics
      only, under their licence terms.</p>
    </div>
    <div>
      <p class="fh">How growth is measured</p>
      <p>Momentum figures compare the {r0}&ndash;{r1} founding cohort's share of all AI
      company formation with {p0}&ndash;{p1}. Share is used rather than raw counts
      because the most recent founding years are still filling in.</p>
      <p>Coverage is judged complete through <b>{f.last_complete or "—"}</b>; later
      years are drawn as partial.</p>
    </div>
    <div>
      <p class="fh">Coverage &amp; limits</p>
      <p>Country and city fields are normalised from mixed source formats, so place
      counts cover only companies that carry a location.</p>
      <p>Related-coverage links point at each outlet's own search; no newsroom feed
      is connected to the dataset.</p>
    </div>
  </div>
  <div class="fine">TOBIN CENTER FOR ECONOMIC POLICY · YALE UNIVERSITY &nbsp;·&nbsp;
  DATASET UPDATED {escape(as_of.upper())} &nbsp;·&nbsp;
  {snap.total:,} COMPANIES TRACKED</div>
</div>
""")
