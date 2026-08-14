"""The V2 stylesheet, as one template rendered against the active palette.

**Why so many `!important`s.**

This sheet has to win two fights it did not pick — against the base stylesheet
in `pipeline_dashboard.py`, and against Streamlit's own generated classes:

1. The base sheet sizes `h1`/`h2`/`h3` with `!important`. No amount of
   specificity beats that; only `!important` does.
2. Its font-family rule is written as
   ``p, span:not([data-testid*="Icon"]):not([class*="icon"]):not([class*="Icon"]),
   div, …``. The three `:not()` arguments each contribute their own specificity,
   putting that selector at three classes plus an element — out of reach of any
   sane class chain here.
3. Streamlit's emotion classes style `p` inside markdown containers at one class
   plus one element, which beats a single `.v2-*` class.

So **type** properties (family, size, weight, letter-spacing, line-height,
colour) are marked important on the text primitives. Everything **structural**
— layout, borders, spacing, backgrounds — is left at normal weight, where
ordinary specificity is enough. Keeping that split makes it obvious which rules
are defensive and which are design.
"""
from __future__ import annotations

CSS = """
<style>
@import url('{font_url}');

:root {{
  --v2-bg: {p.bg};
  --v2-surface: {p.surface};
  --v2-surface-alt: {p.surface_alt};
  --v2-text: {p.text};
  --v2-text2: {p.text2};
  --v2-text3: {p.text3};
  --v2-border: {p.border};
  --v2-border-soft: {p.border_soft};
  --v2-accent: {p.accent};
  --v2-accent-soft: {p.accent_soft};
  --v2-pos: {p.pos};
  --v2-neg: {p.neg};
  --v2-context: {p.context};
  --v2-sans: {sans};
  --v2-display: {display};
  --v2-mono: {mono};
}}

/* ── Ground ─────────────────────────────────────────────────────────── */
html, body, .stApp,
.main, [data-testid="stAppViewContainer"], [data-testid="stMain"],
[data-testid="stHeader"], [data-testid="stBottomBlockContainer"] {{
  background: var(--v2-bg) !important;
}}
.stApp {{ color: var(--v2-text); font-family: var(--v2-sans) !important; }}
.stApp p, .stApp div, .stApp span, .stApp label,
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {{
  font-family: var(--v2-sans) !important;
}}

/* Editorial column: wider than the V1 shell, generous but not sprawling. */
.block-container {{
  max-width: 1360px !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  padding-left: 28px !important;
  padding-right: 28px !important;
}}

.stApp a {{ color: var(--v2-accent); text-decoration: none; }}
.stApp ::selection {{ background: var(--v2-accent-soft); }}

/* Streamlit's default vertical rhythm is replaced by explicit rules + spacers. */
.st-key-v2root [data-testid="stVerticalBlock"] {{ gap: 0 !important; }}

/* Streamlit wraps every markdown block in a `display:flex; align-items:center`
   div. Centred flex items do not make that wrapper grow to a custom block's
   height, so tall hand-written HTML (metric strips, ranked rows, tables)
   overflowed and the next element drew on top of it.
   `flow-root` fixes both halves of the problem: it restores ordinary block
   sizing, and it opens a new block formatting context so a child's top/bottom
   margins are contained instead of collapsing out and vanishing from the
   wrapper's measured height. */
.st-key-v2root [data-testid="stMarkdown"] > div {{
  display: flow-root !important;
  align-items: stretch !important;
}}
/* Streamlit also pulls markdown containers up with `margin-bottom: -16px`, to
   cancel the trailing margin an ordinary markdown paragraph carries. Custom
   HTML has no such margin, so that pull ate the last 16px of every block and
   the next element drew over it. */
.st-key-v2root [data-testid="stMarkdownContainer"] {{ margin-bottom: 0 !important; }}

/* ── Type primitives ───────────────────────────────────────────────── */
.stApp .v2-label {{
  font-family: var(--v2-mono) !important;
  font-size: 0.72rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.14em !important;
  line-height: 1.3 !important;
  text-transform: uppercase;
  color: var(--v2-text) !important;
  margin: 0;
}}
.stApp .v2-meta {{
  font-family: var(--v2-mono) !important;
  font-size: 0.675rem !important;
  font-weight: 500 !important;
  letter-spacing: 0.09em !important;
  line-height: 1.3 !important;
  text-transform: uppercase;
  color: var(--v2-text3) !important;
  font-variant-numeric: tabular-nums;
  margin: 0;
}}
.v2-secthead {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 9px;
  border-bottom: 1px solid var(--v2-text);
  margin-bottom: 20px;
}}
.v2-secthead.soft {{ border-bottom-color: var(--v2-border); }}

.stApp .v2-h2 {{
  font-family: var(--v2-display) !important;
  font-size: 1.45rem !important;
  font-weight: 700 !important;
  letter-spacing: -0.025em !important;
  line-height: 1.16 !important;
  color: var(--v2-text) !important;
  margin: 0 0 10px 0;
  text-wrap: balance;
}}
.stApp .v2-body {{
  font-size: 0.945rem !important;
  font-weight: 400 !important;
  line-height: 1.6 !important;
  letter-spacing: -0.003em !important;
  color: var(--v2-text2) !important;
  margin: 0;
}}
.stApp .v2-body b, .stApp .v2-body strong {{
  color: var(--v2-text) !important; font-weight: 600 !important;
}}
.stApp .v2-small {{
  font-size: 0.79rem !important;
  font-weight: 400 !important;
  line-height: 1.55 !important;
  color: var(--v2-text3) !important;
  margin: 0;
}}

/* ── Top bar ───────────────────────────────────────────────────────── */
.v2-brand {{ display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }}
.stApp .v2-brand-name {{
  font-family: var(--v2-display) !important;
  font-size: 1.1rem !important;
  font-weight: 700 !important;
  letter-spacing: -0.028em !important;
  color: var(--v2-text) !important;
  white-space: nowrap;
}}
.stApp .v2-brand-sub {{
  font-size: 0.71rem !important;
  font-weight: 400 !important;
  color: var(--v2-text3) !important;
  white-space: nowrap;
}}
.st-key-v2topbar {{ padding-top: 15px; }}
.st-key-v2topbar [data-testid="stHorizontalBlock"] {{ align-items: center; }}

/* Nav: flat text links, an underline marks the active one. */
.st-key-v2nav [role="radiogroup"] {{
  display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 0; row-gap: 2px;
}}
.st-key-v2nav [role="radiogroup"] label {{
  margin: 0 !important;
  padding: 6px 11px;
  border-radius: 0;
  background: transparent !important;
  border-bottom: 2px solid transparent;
  transition: border-color 180ms ease;
}}
.st-key-v2nav [role="radiogroup"] label > div:first-child {{ display: none; }}
.st-key-v2nav [role="radiogroup"] label p {{
  font-family: var(--v2-mono) !important;
  font-size: 0.685rem !important;
  font-weight: 500 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase;
  color: var(--v2-text2) !important;
  white-space: nowrap;
  transition: color 180ms ease;
}}
.st-key-v2nav [role="radiogroup"] label:hover p {{ color: var(--v2-text) !important; }}
.st-key-v2nav [role="radiogroup"] label:has(input:checked) {{
  border-bottom-color: var(--v2-accent);
}}
.st-key-v2nav [role="radiogroup"] label:has(input:checked) p {{
  color: var(--v2-text) !important; font-weight: 600 !important;
}}

/* Theme switch — two quiet mono chips. */
.st-key-v2theme [data-testid="stElementContainer"] {{
  display: flex; justify-content: flex-end;
}}
.st-key-v2theme button {{
  padding: 4px 10px !important;
  min-height: 0 !important;
  border-radius: 2px !important;
  border: 1px solid var(--v2-border) !important;
  background: transparent !important;
  transition: background 160ms ease, border-color 160ms ease;
}}
.st-key-v2theme button p {{
  font-family: var(--v2-mono) !important;
  font-size: 0.615rem !important;
  font-weight: 500 !important;
  letter-spacing: 0.11em !important;
  text-transform: uppercase;
  color: var(--v2-text3) !important;
  transition: color 160ms ease;
}}
.st-key-v2theme button:hover p {{ color: var(--v2-text) !important; }}
.st-key-v2theme [data-testid="stBaseButton-segmented_controlActive"] {{
  background: var(--v2-surface-alt) !important;
  border-color: var(--v2-text3) !important;
}}
.st-key-v2theme [data-testid="stBaseButton-segmented_controlActive"] p {{
  color: var(--v2-text) !important; font-weight: 600 !important;
}}

/* ── Live status line ──────────────────────────────────────────────── */
.v2-status {{
  display: flex; align-items: center; flex-wrap: wrap;
  padding: 8px 0;
  border-top: 1px solid var(--v2-border);
  border-bottom: 1px solid var(--v2-border);
}}
.stApp .v2-status, .stApp .v2-status span {{
  font-family: var(--v2-mono) !important;
  font-size: 0.66rem !important;
  font-weight: 400 !important;
  letter-spacing: 0.1em !important;
  text-transform: uppercase;
  color: var(--v2-text3) !important;
  font-variant-numeric: tabular-nums;
}}
.v2-status .seg {{ padding: 0 14px; border-left: 1px solid var(--v2-border); }}
.v2-status .seg:first-child {{ padding-left: 0; border-left: none; }}
.stApp .v2-status b {{
  font-family: var(--v2-mono) !important;
  color: var(--v2-text2) !important; font-weight: 600 !important;
}}
.stApp .v2-status .live {{
  color: var(--v2-accent) !important; font-weight: 600 !important;
}}

/* ── Hero ──────────────────────────────────────────────────────────── */
.v2-hero {{ padding: 46px 0 32px 0; }}
.stApp .v2-hero-title {{
  font-family: var(--v2-display) !important;
  font-size: clamp(2.4rem, 4.7vw, 3.5rem) !important;
  font-weight: 700 !important;
  letter-spacing: -0.04em !important;
  line-height: 1.02 !important;
  color: var(--v2-text) !important;
  margin: 0 0 17px 0;
  text-wrap: balance;
}}
.stApp .v2-hero-lede {{
  font-size: 1.06rem !important;
  font-weight: 400 !important;
  line-height: 1.52 !important;
  letter-spacing: -0.008em !important;
  color: var(--v2-text2) !important;
  max-width: 74ch;
  margin: 0;
}}

/* ── Ask bar ───────────────────────────────────────────────────────── */
.st-key-v2ask [data-testid="stHorizontalBlock"] {{ gap: 0 !important; }}
.st-key-v2ask [data-testid="stTextInput"] > div {{
  border: none !important; background: transparent !important; box-shadow: none !important;
}}
.st-key-v2ask [data-testid="stTextInput"] input {{
  font-family: var(--v2-sans) !important;
  font-size: 1.04rem !important;
  font-weight: 400 !important;
  color: var(--v2-text) !important;
  background: var(--v2-surface) !important;
  border: 1px solid var(--v2-border) !important;
  border-right: none !important;
  border-radius: 2px 0 0 2px !important;
  padding: 0 18px !important;
  height: 58px !important;
  box-shadow: none !important;
  transition: border-color 180ms ease;
}}
.st-key-v2ask [data-testid="stTextInput"] input::placeholder {{
  color: var(--v2-text3) !important; font-weight: 400 !important;
}}
.st-key-v2ask [data-testid="stTextInput"] input:focus {{
  border-color: var(--v2-accent) !important; outline: none !important;
}}
.st-key-v2ask button {{
  height: 58px !important;
  width: 100% !important;
  border-radius: 0 2px 2px 0 !important;
  border: 1px solid {p.ink_button} !important;
  background: {p.ink_button} !important;
  transition: opacity 160ms ease;
}}
.st-key-v2ask button p {{
  font-family: var(--v2-mono) !important;
  font-size: 0.73rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.13em !important;
  text-transform: uppercase;
  color: {p.ink_button_text} !important;
}}
.st-key-v2ask button:hover {{ opacity: 0.84; }}

/* Example questions — plain text prompts, each on its own hairline. */
.st-key-v2examples [data-testid="stHorizontalBlock"] {{ gap: 0 !important; }}
.st-key-v2examples button {{
  padding: 10px 18px 10px 0 !important;
  /* Equal height keeps the hairlines above them on one line even when one
     prompt wraps to two and another does not. */
  min-height: 62px !important;
  align-items: flex-start !important;
  border: none !important;
  border-top: 1px solid var(--v2-border-soft) !important;
  border-radius: 0 !important;
  background: transparent !important;
  text-align: left !important;
  justify-content: flex-start !important;
  transition: border-color 160ms ease;
}}
.st-key-v2examples button > div {{
  justify-content: flex-start !important;
  width: 100%;
  text-align: left !important;
}}
.st-key-v2examples button p {{
  font-family: var(--v2-sans) !important;
  font-size: 0.815rem !important;
  font-weight: 400 !important;
  line-height: 1.4 !important;
  color: var(--v2-text2) !important;
  text-align: left !important;
  transition: color 160ms ease;
}}
.st-key-v2examples button:hover {{ border-top-color: var(--v2-accent) !important; }}
.st-key-v2examples button:hover p {{ color: var(--v2-accent) !important; }}

/* ── AI answer panel ───────────────────────────────────────────────── */
@keyframes v2-open {{
  from {{ opacity: 0; transform: translateY(-5px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}
.st-key-v2answer {{
  animation: v2-open 280ms cubic-bezier(0.22, 0.61, 0.36, 1);
  border: 1px solid var(--v2-border);
  border-top: 2px solid var(--v2-accent);
  background: var(--v2-surface);
  padding: 24px 26px 20px 26px;
  margin-top: 24px;
}}
.stApp .v2-answer-kicker {{
  font-family: var(--v2-mono) !important;
  font-size: 0.64rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.14em !important;
  text-transform: uppercase;
  color: var(--v2-accent) !important;
  margin: 0 0 10px 0;
}}
.stApp .v2-answer-q {{
  font-family: var(--v2-mono) !important;
  font-size: 0.7rem !important;
  font-weight: 400 !important;
  color: var(--v2-text3) !important;
  margin: 0 0 7px 0;
}}
.stApp .v2-answer-note {{
  font-family: var(--v2-mono) !important;
  font-size: 0.655rem !important;
  font-weight: 400 !important;
  line-height: 1.65 !important;
  letter-spacing: 0.03em !important;
  color: var(--v2-text3) !important;
  margin: 18px 0 0 0;
  padding-top: 13px;
  border-top: 1px solid var(--v2-border-soft);
}}

/* ── Metric strips ─────────────────────────────────────────────────── */
.v2-strip {{
  display: flex;
  border-top: 1px solid var(--v2-border);
  border-bottom: 1px solid var(--v2-border);
  overflow-x: auto;
}}
.v2-strip .cell {{
  flex: 1 1 0;
  min-width: 172px;
  padding: 18px 22px 17px 22px;
  border-left: 1px solid var(--v2-border-soft);
}}
.v2-strip .cell:first-child {{ border-left: none; padding-left: 0; }}
.stApp .v2-strip .k {{
  display: block;
  font-family: var(--v2-mono) !important;
  font-size: 0.635rem !important;
  font-weight: 500 !important;
  letter-spacing: 0.12em !important;
  text-transform: uppercase;
  color: var(--v2-text3) !important;
  margin-bottom: 10px;
  white-space: nowrap;
}}
.stApp .v2-strip .v {{
  display: block;
  font-family: var(--v2-display) !important;
  font-size: 2.05rem !important;
  font-weight: 650 !important;
  letter-spacing: -0.035em !important;
  line-height: 1 !important;
  color: var(--v2-text) !important;
  font-variant-numeric: tabular-nums;
}}
.stApp .v2-strip .v span {{ font-family: var(--v2-display) !important; }}
.stApp .v2-strip .d {{
  display: block;
  font-family: var(--v2-mono) !important;
  font-size: 0.665rem !important;
  font-weight: 400 !important;
  line-height: 1.45 !important;
  margin-top: 10px;
  color: var(--v2-text3) !important;
  font-variant-numeric: tabular-nums;
}}
.v2-strip.compact {{ border: none; margin: 20px 0 4px 0; }}
.v2-strip.compact .cell {{ padding: 0 20px; min-width: 124px; }}
.v2-strip.compact .cell:first-child {{ padding-left: 0; }}
.stApp .v2-strip.compact .v {{ font-size: 1.42rem !important; }}
.stApp .v2-strip.compact .d {{ margin-top: 8px; }}

.stApp .v2-up   {{ color: var(--v2-pos) !important; font-weight: 600 !important; }}
.stApp .v2-down {{ color: var(--v2-neg) !important; font-weight: 600 !important; }}
.stApp .v2-flat {{ color: var(--v2-text3) !important; font-weight: 600 !important; }}

/* ── Signal rows (ranked lists) ────────────────────────────────────── */
.v2-rows .row {{
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 11px 6px 11px 0;
  border-bottom: 1px solid var(--v2-border-soft);
  transition: background 150ms ease;
}}
.v2-rows .row:hover {{ background: var(--v2-accent-soft); }}
.v2-rows .row:last-child {{ border-bottom: none; }}
.stApp .v2-rows .rank {{
  font-family: var(--v2-mono) !important;
  font-size: 0.67rem !important;
  font-weight: 400 !important;
  color: var(--v2-text3) !important;
  width: 20px; flex: none;
  font-variant-numeric: tabular-nums;
}}
.stApp .v2-rows .name {{
  flex: 1 1 auto;
  font-size: 0.875rem !important;
  font-weight: 500 !important;
  color: var(--v2-text) !important;
  min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}}
.stApp .v2-rows .sub {{
  font-family: var(--v2-mono) !important;
  font-size: 0.66rem !important;
  font-weight: 400 !important;
  color: var(--v2-text3) !important;
  flex: none;
  font-variant-numeric: tabular-nums;
}}
.stApp .v2-rows .val, .stApp .v2-rows .val span {{
  font-family: var(--v2-mono) !important;
  font-size: 0.805rem !important;
  font-weight: 600 !important;
  font-variant-numeric: tabular-nums;
}}
.stApp .v2-rows .val {{ color: var(--v2-text) !important; }}
.v2-rows .val {{ flex: none; text-align: right; min-width: 88px; }}
.v2-rows .bar {{
  position: relative; flex: 0 0 74px; height: 4px;
  background: var(--v2-border-soft);
}}
.v2-rows .bar i {{
  position: absolute; left: 0; top: 0; bottom: 0;
  background: var(--v2-accent); display: block;
}}

/* ── Stories ───────────────────────────────────────────────────────── */
.stApp .v2-lead-kicker {{
  font-family: var(--v2-mono) !important;
  font-size: 0.655rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.14em !important;
  text-transform: uppercase;
  color: var(--v2-accent) !important;
  margin: 0 0 12px 0;
}}
.stApp .v2-lead-title {{
  font-family: var(--v2-display) !important;
  font-size: clamp(1.6rem, 2.5vw, 2.05rem) !important;
  font-weight: 700 !important;
  letter-spacing: -0.032em !important;
  line-height: 1.09 !important;
  color: var(--v2-text) !important;
  margin: 0 0 14px 0;
  text-wrap: balance;
}}
.v2-datacallout {{
  display: flex; align-items: baseline; gap: 15px;
  margin: 22px 0 0 0; padding: 15px 0 0 0;
  border-top: 1px solid var(--v2-border);
}}
.stApp .v2-datacallout .tag {{
  font-family: var(--v2-mono) !important;
  font-size: 0.61rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.13em !important;
  text-transform: uppercase;
  color: var(--v2-text3) !important;
  border: 1px solid var(--v2-border);
  padding: 4px 8px;
  flex: none;
}}
.stApp .v2-datacallout .fig {{
  font-family: var(--v2-display) !important;
  font-size: 1.62rem !important;
  font-weight: 700 !important;
  letter-spacing: -0.035em !important;
  line-height: 1 !important;
  color: var(--v2-text) !important;
  font-variant-numeric: tabular-nums;
}}
.stApp .v2-datacallout .cap {{
  font-size: 0.8rem !important;
  font-weight: 400 !important;
  line-height: 1.4 !important;
  color: var(--v2-text3) !important;
}}

.v2-story {{
  display: flex; gap: 18px; padding: 17px 0;
  border-top: 1px solid var(--v2-border-soft);
}}
.stApp .v2-story .idx {{
  font-family: var(--v2-mono) !important;
  font-size: 0.71rem !important;
  font-weight: 500 !important;
  color: var(--v2-text3) !important;
  flex: none; padding-top: 3px;
  font-variant-numeric: tabular-nums;
}}
.v2-story .body {{ flex: 1 1 auto; min-width: 0; }}
.stApp .v2-story .t {{
  font-family: var(--v2-display) !important;
  font-size: 1.02rem !important;
  font-weight: 650 !important;
  letter-spacing: -0.018em !important;
  line-height: 1.28 !important;
  color: var(--v2-text) !important;
  margin: 0 0 5px 0;
}}
.stApp .v2-story .d {{
  font-size: 0.85rem !important;
  font-weight: 400 !important;
  line-height: 1.52 !important;
  color: var(--v2-text2) !important;
  margin: 0;
}}
.stApp .v2-story .d b {{ color: var(--v2-text) !important; font-weight: 600 !important; }}

/* ── Coverage links ────────────────────────────────────────────────── */
.v2-coverage {{ margin-top: 22px; }}
.stApp .v2-coverage .head {{
  font-family: var(--v2-mono) !important;
  font-size: 0.615rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.13em !important;
  text-transform: uppercase;
  color: var(--v2-text3) !important;
  margin-bottom: 10px;
}}
.v2-coverage .links {{ display: flex; flex-wrap: wrap; gap: 6px 20px; }}
.stApp .v2-coverage a {{
  font-size: 0.83rem !important;
  font-weight: 450 !important;
  color: var(--v2-text2) !important;
  border-bottom: 1px solid var(--v2-border);
  padding-bottom: 1px;
  transition: color 160ms ease, border-color 160ms ease;
}}
.stApp .v2-coverage a:hover {{
  color: var(--v2-accent) !important; border-bottom-color: var(--v2-accent);
}}
.v2-coverage a::after {{ content: " \\2197"; font-size: 0.72rem; opacity: 0.6; }}

/* ── Table ─────────────────────────────────────────────────────────── */
.v2-tablewrap {{ overflow-x: auto; }}
.v2-table {{ width: 100%; border-collapse: collapse; }}
/* Streamlit styles markdown tables with a full box border; keep only the
   horizontal rules this design uses. */
.stApp .v2-table th, .stApp .v2-table td {{
  border-left: none !important; border-right: none !important; border-top: none !important;
}}
.v2-table col.c-name {{ width: 17%; }}
.v2-table col.c-desc {{ width: 51%; }}
.v2-table col.c-place {{ width: 16%; }}
.v2-table col.c-chan {{ width: 16%; }}
.stApp .v2-table th {{
  font-family: var(--v2-mono) !important;
  font-size: 0.615rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.11em !important;
  text-transform: uppercase;
  color: var(--v2-text3) !important;
  text-align: left;
  padding: 0 14px 9px 0;
  border-bottom: 1px solid var(--v2-border);
  white-space: nowrap;
}}
.stApp .v2-table td {{
  font-size: 0.855rem !important;
  font-weight: 400 !important;
  line-height: 1.45 !important;
  color: var(--v2-text2) !important;
  padding: 11px 14px 11px 0;
  border-bottom: 1px solid var(--v2-border-soft);
  vertical-align: top;
}}
.v2-table tbody tr {{ transition: background 150ms ease; }}
.v2-table tbody tr:hover {{ background: var(--v2-accent-soft); }}
.stApp .v2-table td.name {{ color: var(--v2-text) !important; font-weight: 550 !important; }}
.stApp .v2-table td.mut {{
  font-family: var(--v2-mono) !important;
  font-size: 0.735rem !important;
  color: var(--v2-text3) !important;
  white-space: nowrap;
}}
.stApp .v2-table a {{
  color: var(--v2-text) !important; border-bottom: 1px solid var(--v2-border);
}}
.stApp .v2-table a:hover {{
  color: var(--v2-accent) !important; border-bottom-color: var(--v2-accent);
}}

/* ── States ────────────────────────────────────────────────────────── */
.stApp .v2-empty {{
  font-family: var(--v2-mono) !important;
  font-size: 0.715rem !important;
  font-weight: 400 !important;
  letter-spacing: 0.05em !important;
  color: var(--v2-text3) !important;
  padding: 24px 0;
  border-top: 1px solid var(--v2-border-soft);
}}
.stApp .v2-loading {{
  font-family: var(--v2-mono) !important;
  font-size: 0.7rem !important;
  font-weight: 400 !important;
  letter-spacing: 0.12em !important;
  text-transform: uppercase;
  color: var(--v2-text3) !important;
  padding: 18px 0;
}}
.v2-loading::after {{ content: ""; animation: v2-dots 1.4s steps(4, end) infinite; }}
@keyframes v2-dots {{
  0% {{ content: ""; }} 25% {{ content: "."; }}
  50% {{ content: ".."; }} 75% {{ content: "..."; }}
}}

/* ── Footer ────────────────────────────────────────────────────────── */
.v2-footer {{
  margin-top: 62px;
  padding: 30px 0 46px 0;
  border-top: 1px solid var(--v2-text);
}}
.v2-footer .cols {{ display: grid; grid-template-columns: 1.5fr 1fr 1fr; gap: 44px; }}
.stApp .v2-footer .fh {{
  font-family: var(--v2-mono) !important;
  font-size: 0.615rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.13em !important;
  text-transform: uppercase;
  color: var(--v2-text3) !important;
  margin: 0 0 11px 0;
}}
.stApp .v2-footer p {{
  font-size: 0.815rem !important;
  font-weight: 400 !important;
  line-height: 1.6 !important;
  color: var(--v2-text2) !important;
  margin: 0 0 9px 0;
}}
.stApp .v2-footer p b {{ color: var(--v2-text) !important; font-weight: 600 !important; }}
.stApp .v2-footer .fine {{
  font-family: var(--v2-mono) !important;
  font-size: 0.645rem !important;
  font-weight: 400 !important;
  line-height: 1.7 !important;
  letter-spacing: 0.06em !important;
  color: var(--v2-text3) !important;
  margin-top: 28px;
  padding-top: 16px;
  border-top: 1px solid var(--v2-border-soft);
}}

/* ── Streamlit chrome that would otherwise leak the default theme ──── */
[data-testid="stSpinner"] > div {{ border-top-color: var(--v2-accent) !important; }}
.stApp [data-testid="stSpinner"] p {{
  font-family: var(--v2-mono) !important;
  font-size: 0.7rem !important;
  letter-spacing: 0.1em !important;
  text-transform: uppercase;
  color: var(--v2-text3) !important;
}}
[data-testid="stAlertContainer"] {{
  background: var(--v2-surface-alt) !important;
  border: 1px solid var(--v2-border) !important;
  border-radius: 2px !important;
}}
.stApp [data-testid="stAlertContainer"] p {{
  color: var(--v2-text2) !important; font-size: 0.83rem !important;
}}
.stApp [data-testid="stTooltipHoverTarget"] svg {{ fill: var(--v2-text3); }}

/* ── Responsive ────────────────────────────────────────────────────── */
@media (max-width: 1100px) {{
  .v2-footer .cols {{ grid-template-columns: 1fr 1fr; gap: 30px; }}
}}
@media (max-width: 820px) {{
  .block-container {{ padding-left: 18px !important; padding-right: 18px !important; }}
  .v2-hero {{ padding: 30px 0 24px 0; }}
  .stApp .v2-hero-title {{
    font-size: 2.15rem !important; letter-spacing: -0.032em !important;
  }}
  .stApp .v2-hero-lede {{ font-size: 0.96rem !important; }}
  /* The strip scrolls sideways here, so cells get room rather than squeezing;
     labels wrap instead of running under the next cell. */
  .v2-strip .cell {{ min-width: 186px; padding: 15px 16px; }}
  .stApp .v2-strip .k {{ white-space: normal; }}
  .stApp .v2-strip .v {{ font-size: 1.6rem !important; }}
  .st-key-v2examples button {{ min-height: 0 !important; padding: 12px 0 !important; }}
  .v2-footer .cols {{ grid-template-columns: 1fr; gap: 26px; }}
  .st-key-v2nav [role="radiogroup"] {{ justify-content: flex-start; }}
  .st-key-v2nav [role="radiogroup"] label {{ padding: 5px 15px 5px 0; }}
  .st-key-v2ask [data-testid="stTextInput"] input {{
    border-right: 1px solid var(--v2-border) !important;
    border-radius: 2px !important;
    height: 52px !important;
    font-size: 0.97rem !important;
  }}
  .st-key-v2ask button {{
    border-radius: 2px !important; height: 48px !important; margin-top: 10px;
  }}
  .st-key-v2answer {{ padding: 18px 16px 15px 16px; }}
  .stApp .v2-lead-title {{ font-size: 1.5rem !important; }}
  .v2-rows .bar {{ display: none; }}
  .v2-status .seg {{ padding: 0 10px; }}
}}
@media (prefers-reduced-motion: reduce) {{
  .st-key-v2answer {{ animation: none; }}
  .v2-loading::after {{ animation: none; content: "..."; }}
  * {{ transition: none !important; }}
}}
</style>
"""
