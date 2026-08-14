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


# ── Ask bar ──────────────────────────────────────────────────────────────

def ask_bar(examples: list[str]) -> str | None:
    """The natural-language query bar. Returns a question when one is submitted."""
    _md('<p class="v2-label" style="margin-bottom:10px">Ask the global AI ecosystem</p>')

    submitted: str | None = None
    with st.container(key="v2ask"):
        field, button = st.columns([5.4, 1], vertical_alignment="center")
        with field:
            typed = st.text_input(
                "Question", key="v2_question",
                placeholder="Ask anything about companies, sectors, locations, or trends...",
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

    spacer(12)
    with st.container(key="v2examples"):
        cols = st.columns(len(examples))
        for col, example in zip(cols, examples):
            with col:
                if st.button(example, key=f"v2_ex_{hash(example) & 0xffff}",
                             type="tertiary", use_container_width=True):
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

def metrics_strip(items: list[tuple[str, str, str | None]]) -> None:
    """Compact market strip: (label, value, sub) per cell."""
    cells = "".join(
        f'<div class="cell"><span class="k">{escape(k)}</span>'
        f'<span class="v">{v}</span>'
        + (f'<span class="d">{sub}</span>' if sub else "")
        + "</div>"
        for k, v, sub in items
    )
    _md(f'<div class="v2-strip">{cells}</div>')


def rank_rows(df: pd.DataFrame, unit: str = "%", signed: bool = False,
              show_bar: bool = False, rank: bool = False) -> None:
    """A ranked list on hairlines. Expects columns label, value, and optional sub."""
    if df.empty:
        empty_state("No ranking available for this scope.")
        return
    peak = float(df["value"].abs().max()) or 1.0
    rows = []
    for i, r in df.reset_index(drop=True).iterrows():
        val = float(r["value"])
        value_html = _signed(val, unit) if signed else \
            f'<span>{val:.1f}{unit}</span>'
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


def world_map(df: pd.DataFrame, p: Palette, height: int = 380) -> None:
    """Choropleth on a log scale — one hue, light to dark, magnitude only."""
    if df.empty:
        empty_state("No country coverage available.")
        return
    import numpy as np

    scale = [[0, p.accent_soft.replace("rgba", "rgba")], [1, p.accent]] if p.is_dark else \
            [[0, "#dfe8f8"], [0.55, "#5b8ede"], [1, p.accent]]
    if p.is_dark:
        scale = [[0, "#16233a"], [0.55, "#2f5f9f"], [1, p.accent]]

    m = df.copy()
    m["log_total"] = np.log10(m["total"].clip(lower=1))
    fig = go.Figure(go.Choropleth(
        locations=m["country"], locationmode="country names", z=m["log_total"],
        customdata=m[["total", "ai"]], colorscale=scale,
        marker_line_color=p.bg, marker_line_width=0.4,
        colorbar=dict(
            title=dict(text="", font=dict(size=10, color=p.text3)),
            tickvals=[0, 1, 2, 3, 4, 5],
            ticktext=["1", "10", "100", "1K", "10K", "100K"],
            thickness=8, len=0.62, outlinewidth=0, x=1.0,
            tickfont=dict(size=10, color=p.text3, family="IBM Plex Mono"),
        ),
        hovertemplate="<b>%{location}</b><br>%{customdata[0]:,} companies · "
                      "%{customdata[1]:,} AI<extra></extra>",
    ))
    fig.update_geos(showframe=False, showcoastlines=False, showland=True,
                    landcolor=p.surface_alt, bgcolor="rgba(0,0,0,0)",
                    lakecolor="rgba(0,0,0,0)", projection_type="natural earth")
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color=p.text3),
        hoverlabel=dict(bgcolor=p.surface, bordercolor=p.border,
                        font=dict(family="Inter", size=12, color=p.text)),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)


# ── Weekly brief ─────────────────────────────────────────────────────────

def lead_story(week: D.Week, facts: dict, snap: D.Snapshot) -> None:
    """The main data-driven story, written from the week's own numbers."""
    if not week.total:
        empty_state("No ingestion recorded for the most recent week.")
        return

    share = week.hidden_share
    if share >= 60:
        headline = "Most new arrivals are invisible to commercial databases"
        lede = (f"Of the {week.total:,} companies that entered the dataset this week, "
                f"<b>{week.hidden:,} ({share:.1f}%)</b> appear in neither Crunchbase nor "
                f"PitchBook. They surface first through code hosts, model hubs, "
                f"accelerator portfolios and public grant awards — months before a "
                f"commercial database registers them, if it ever does.")
    else:
        headline = "Commercial coverage caught up with this week's intake"
        lede = (f"{week.total:,} companies entered the dataset this week, of which "
                f"<b>{week.hidden:,} ({share:.1f}%)</b> are in neither Crunchbase nor "
                f"PitchBook — a lower hidden share than the {snap.hidden_share:.1f}% "
                f"the full dataset carries.")

    channel = ""
    if not week.channels.empty:
        top = week.channels.iloc[0]
        channel = (f" The largest single channel was <b>{escape(str(top['channel']))}</b>, "
                   f"accounting for {int(top['n']):,} of them.")

    reach = ""
    if week.countries:
        reach = f" The week's arrivals carry headquarters in {week.countries:,} countries."

    _md('<p class="v2-lead-kicker">Lead · dataset intake</p>'
        f'<h2 class="v2-lead-title">{escape(headline)}</h2>'
        f'<p class="v2-body">{lede}{channel}{reach}</p>')

    _md('<div class="v2-datacallout">'
        '<span class="tag">Our data</span>'
        f'<span class="fig">{share:.1f}%</span>'
        '<span class="cap">of this week&rsquo;s arrivals are in neither Crunchbase '
        'nor PitchBook</span>'
        '</div>')


def secondary_stories(week: D.Week, facts: dict, snap: D.Snapshot,
                      cats: pd.DataFrame, geo: pd.DataFrame) -> None:
    """Three more findings, each carrying the figure it rests on."""
    stories: list[tuple[str, str]] = []

    if facts.get("github_native"):
        stories.append((
            "GitHub-native companies keep arriving before anyone lists them",
            f"<b>{facts['github_native']:,}</b> hidden AI companies were found through a "
            f"public code repository rather than a funding announcement or a directory.",
        ))

    if not cats.empty:
        top = cats.iloc[0]
        stories.append((
            f"{top['label']} is taking share of new AI company formation",
            f"Its share of AI companies founded in the latest three-year cohort is "
            f"<b>{float(top['growth']):+.1f}%</b> against the previous cohort, on "
            f"<b>{int(top['recent']):,}</b> companies.",
        ))

    if not geo.empty:
        non_us = geo[geo["country"] != "United States"]
        if not non_us.empty:
            city = non_us.iloc[0]
            stories.append((
                f"{city['city']} leads formation outside the United States",
                f"It accounts for <b>{float(city['share']):.1f}%</b> of AI companies "
                f"founded in the latest cohort, on <b>{int(city['recent']):,}</b> firms.",
            ))

    if facts.get("grant_backed"):
        stories.append((
            "Federal grant awards keep surfacing firms with no commercial footprint",
            f"<b>{facts['grant_backed']:,}</b> hidden AI companies entered the dataset "
            f"through NIH or NSF award records.",
        ))

    if not stories:
        empty_state("Not enough recent activity to derive secondary findings.")
        return

    html = "".join(
        f'<div class="v2-story"><span class="idx">{i + 1:02d}</span>'
        f'<div class="body"><p class="t">{escape(title)}</p>'
        f'<p class="d">{body}</p></div></div>'
        for i, (title, body) in enumerate(stories[:3])
    )
    _md(f'<div style="margin-top:30px">{html}</div>')


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


def geographic_momentum(geo: pd.DataFrame) -> None:
    if geo.empty:
        empty_state("City-level coverage is too thin to rank.")
        return

    def label(r) -> str:
        city = str(r["city"])
        if not pd.notna(r["country"]):
            return city
        country = str(r["country"])
        return f"{city}, {_SHORT_COUNTRY.get(country, country)}"

    df = pd.DataFrame({
        "label": geo.apply(label, axis=1),
        "value": geo["share"].astype(float),
        "sub": geo["growth"].map(lambda g: "—" if pd.isna(g) else f"{float(g):+.0f}%"),
    })
    rank_rows(df, unit="%", show_bar=True)


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
