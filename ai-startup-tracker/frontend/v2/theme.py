"""Design tokens and CSS for the V2 homepage.

Two palettes — light and dark — expressed as one frozen dataclass so that
every surface (HTML, Plotly, Streamlit widget overrides) is derived from the
same numbers instead of drifting apart.

Chart colors were validated with the dataviz palette checker against each
mode's own page surface rather than flipped from one another:

    light  #1a56c4 / #127a52 / #b3261e  on #f7f7f4  → band, chroma, contrast PASS
    dark   #4a8ae0 / #35986b / #cf5b4e  on #0b0d0f  → band, chroma, contrast PASS

``accent`` is the only hue that ever carries series identity; the page never
plots two identity colors side by side. ``pos``/``neg`` are reserved status
colors and always ship with an arrow glyph and a signed number, never color
alone — the red/green pair is CVD-weak by construction, so the glyph is the
encoding that actually carries the direction.
"""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from .stylesheet import CSS

_STATE_KEY = "v2_theme_mode"

# Typography stacks. Inter Tight sets headlines tight and editorial; Inter runs
# the UI; IBM Plex Mono is reserved for labels, timestamps and small figures.
SANS = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
DISPLAY = "'Inter Tight', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif"
MONO = "'IBM Plex Mono', ui-monospace, 'SF Mono', Menlo, monospace"

_FONT_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Inter:wght@400;500;600;700"
    "&family=Inter+Tight:wght@500;600;700;800"
    "&family=IBM+Plex+Mono:wght@400;500;600"
    "&display=swap"
)


@dataclass(frozen=True)
class Palette:
    name: str
    # Surfaces
    bg: str            # page ground
    surface: str       # raised panel (answer panel, hovered rows)
    surface_alt: str   # wells, table heads, chips
    # Ink
    text: str          # primary
    text2: str         # secondary / body
    text3: str         # muted / metadata
    # Lines
    border: str        # structural rules, panel edges
    border_soft: str   # row separators, chart grid
    # Signal
    accent: str        # links, selected state, the one chart series
    accent_soft: str   # accent wash for fills and selected chips
    pos: str           # status: rising  (always with ↑ + signed number)
    neg: str           # status: falling (always with ↓ + signed number)
    context: str       # "everything else" marks — never carries identity
    # Chrome
    ink_button: str    # near-black / near-white primary button
    ink_button_text: str

    @property
    def is_dark(self) -> bool:
        return self.name == "dark"


LIGHT = Palette(
    name="light",
    bg="#f7f7f4",
    surface="#ffffff",
    surface_alt="#efefea",
    text="#111315",
    text2="#565d63",
    text3="#868d94",
    border="#dcdcd4",
    border_soft="#e7e7e0",
    accent="#1a56c4",
    accent_soft="rgba(26,86,196,0.08)",
    pos="#127a52",
    neg="#b3261e",
    context="#b9b9ae",
    ink_button="#111315",
    ink_button_text="#f7f7f4",
)

DARK = Palette(
    name="dark",
    bg="#0b0d0f",
    surface="#111417",
    surface_alt="#14171a",
    text="#f1f1ed",
    text2="#a2aab0",
    text3="#6f777e",
    border="#23282c",
    border_soft="#1b1f22",
    accent="#4a8ae0",
    accent_soft="rgba(74,138,224,0.12)",
    pos="#35986b",
    neg="#cf5b4e",
    context="#3a4147",
    ink_button="#f1f1ed",
    ink_button_text="#0b0d0f",
)


def current_mode() -> str:
    """Selected mode, defaulting to light. Persisted in session state."""
    return st.session_state.get(_STATE_KEY, "light")


def set_mode(mode: str) -> None:
    st.session_state[_STATE_KEY] = "dark" if mode == "dark" else "light"


def palette() -> Palette:
    return DARK if current_mode() == "dark" else LIGHT


# ── Plotly ───────────────────────────────────────────────────────────────

PLOT_CONFIG = {"displayModeBar": False, "scrollZoom": False}


def plot_layout(p: Palette, **kw) -> dict:
    """Base Plotly layout for this palette.

    Recessive axes and grid, transparent paper so charts sit directly on the
    page ground, one hover style. Callers override per chart.
    """
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color=p.text3, size=11),
        colorway=[p.accent],
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            linecolor=p.border,
            linewidth=1,
            ticks="outside",
            tickcolor=p.border,
            ticklen=4,
            tickfont=dict(size=11, color=p.text3, family="IBM Plex Mono"),
        ),
        yaxis=dict(
            gridcolor=p.border_soft,
            griddash="solid",
            zeroline=False,
            linecolor="rgba(0,0,0,0)",
            tickfont=dict(size=11, color=p.text3, family="IBM Plex Mono"),
        ),
        showlegend=False,
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=p.surface,
            bordercolor=p.border,
            font=dict(family="Inter", size=12, color=p.text),
        ),
        margin=dict(l=0, r=6, t=6, b=0),
        bargap=0.42,
    )
    base.update(kw)
    return base


# ── CSS ──────────────────────────────────────────────────────────────────

def inject_css(p: Palette) -> None:
    """Emit the whole V2 stylesheet for the active palette.

    Injected only while the V2 page renders, so the V1 pages keep the styling
    they already had — the base stylesheet in pipeline_dashboard.py stays
    authoritative everywhere else.
    """
    st.markdown(
        CSS.format(p=p, font_url=_FONT_URL, sans=SANS, display=DISPLAY, mono=MONO),
        unsafe_allow_html=True,
    )
