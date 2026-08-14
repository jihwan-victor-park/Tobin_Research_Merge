"""Read-only loaders for the V2 homepage.

Every figure the page shows comes from here, and every function here reads the
live database through the same engine and the same canonical AI predicate the
rest of the dashboard uses. Nothing writes.

Two data realities shape the queries:

* **Recording lag.** Founding-year coverage thins out for the most recent
  years, so a raw count series falls off a cliff that looks like a collapse in
  formation but is really a collapse in coverage. `formation_series` therefore
  reports which trailing years are provisional, and every growth figure is
  computed as *share of cohort* rather than raw count growth — share is
  invariant to how complete the cohort is.
* **Heterogeneous country values.** Rows arrive as `US`, `USA`, `United
  States` and ISO-3 alike. `normalize_country` from the backend handles free
  text and ISO-2; `_ISO3` layers ISO-3 on top without touching that shared
  helper.

Loaders degrade instead of raising: production and local databases are not
always on the same migration, so a missing column returns an empty frame and
the component that asked for it renders its empty state.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import text

from backend.db.connection import get_engine
from backend.utils.ai_filter import ai_filter_sql
from backend.utils.country import GLOBE_COUNTRIES, country_region, normalize_country
from backend.utils.denylist import BIG_TECH_DENYLIST

log = logging.getLogger("v2.data")

AI = ai_filter_sql()
HIDDEN = "emerging_github"   # verification bucket: in neither Crunchbase nor PitchBook

# Crunchbase-derived rows carry ISO-3; the backend normalizer only knows free
# text and ISO-2, so map the codes that actually occur before handing off.
_ISO3 = {
    "USA": "United States", "GBR": "United Kingdom", "IND": "India",
    "JPN": "Japan", "CAN": "Canada", "DEU": "Germany", "CHN": "China",
    "FRA": "France", "SGP": "Singapore", "ARE": "United Arab Emirates",
    "KOR": "South Korea", "TUR": "Turkey", "ISR": "Israel", "AUS": "Australia",
    "ESP": "Spain", "ITA": "Italy", "NLD": "Netherlands", "CHE": "Switzerland",
    "SWE": "Sweden", "BRA": "Brazil", "MEX": "Mexico", "RUS": "Russia",
    "POL": "Poland", "IRL": "Ireland", "DNK": "Denmark", "NOR": "Norway",
    "FIN": "Finland", "BEL": "Belgium", "AUT": "Austria", "PRT": "Portugal",
    "ZAF": "South Africa", "NGA": "Nigeria", "KEN": "Kenya", "EGY": "Egypt",
    "ARG": "Argentina", "CHL": "Chile", "COL": "Colombia", "IDN": "Indonesia",
    "MYS": "Malaysia", "THA": "Thailand", "VNM": "Vietnam", "PHL": "Philippines",
    "PAK": "Pakistan", "BGD": "Bangladesh", "LKA": "Sri Lanka", "NZL": "New Zealand",
    "UKR": "Ukraine", "CZE": "Czechia", "ROU": "Romania", "HUN": "Hungary",
    "GRC": "Greece", "TWN": "Taiwan", "HKG": "Hong Kong", "SAU": "Saudi Arabia",
    "EST": "Estonia", "LTU": "Lithuania", "LVA": "Latvia", "BGR": "Bulgaria",
    "HRV": "Croatia", "SRB": "Serbia", "SVN": "Slovenia", "SVK": "Slovakia",
    "LUX": "Luxembourg", "ISL": "Iceland", "PER": "Peru", "URY": "Uruguay",
}


# `normalize_country` returns unrecognised strings unchanged by design, so the
# column is full of city names, US states and scraper noise sitting where a
# country should be. Anything that does not land in this set is dropped rather
# than counted — otherwise "countries covered" reports hundreds instead of
# dozens.
_KNOWN_COUNTRIES = frozenset(GLOBE_COUNTRIES) | frozenset(_ISO3.values())


def clean_country(raw: str | None) -> str | None:
    """One recognised country label, or None if the value is not a country."""
    if not raw:
        return None
    v = str(raw).strip()
    if v.upper() in _ISO3:
        return _ISO3[v.upper()]
    norm = normalize_country(v)
    if norm and (norm in _KNOWN_COUNTRIES or country_region(norm)):
        return norm
    return None


def region_of(raw: str | None) -> str | None:
    return country_region(clean_country(raw))


# ── Query plumbing ───────────────────────────────────────────────────────

def _frame(sql: str, **params) -> pd.DataFrame:
    """Run a read-only query, returning an empty frame if the schema disagrees."""
    try:
        with get_engine().connect() as conn:
            return pd.DataFrame(conn.execute(text(sql), params).mappings().all())
    except Exception as exc:                       # noqa: BLE001 - page must not die
        log.warning("v2 query failed (%s): %s", exc.__class__.__name__, exc)
        return pd.DataFrame()


def _scalar(sql: str, default=0, **params):
    try:
        with get_engine().connect() as conn:
            v = conn.execute(text(sql), params).scalar()
        return default if v is None else v
    except Exception as exc:                       # noqa: BLE001
        log.warning("v2 scalar failed (%s): %s", exc.__class__.__name__, exc)
        return default


# ── Dataset scale ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Snapshot:
    total: int = 0
    ai: int = 0
    hidden: int = 0
    countries: int = 0
    added_7d: int = 0
    added_30d: int = 0
    as_of: date | None = None

    @property
    def ai_share(self) -> float:
        return (self.ai / self.total * 100) if self.total else 0.0

    @property
    def hidden_share(self) -> float:
        return (self.hidden / self.total * 100) if self.total else 0.0


@st.cache_data(ttl=180, show_spinner=False)
def snapshot() -> Snapshot:
    """Headline dataset scale, plus how much of it arrived recently.

    Recency is measured against the newest `first_seen_at` in the table rather
    than wall-clock now, so a paused pipeline reports "nothing new since <date>"
    instead of silently showing zeros.
    """
    row = _frame(f"""
        SELECT COUNT(*)                                             AS total,
               COUNT(*) FILTER (WHERE {AI})                         AS ai,
               COUNT(*) FILTER (WHERE verification_status = :hidden) AS hidden,
               MAX(first_seen_at)                                    AS as_of
        FROM companies
    """, hidden=HIDDEN)
    if row.empty:
        return Snapshot()
    r = row.iloc[0]
    as_of = pd.to_datetime(r["as_of"]) if pd.notna(r["as_of"]) else None

    added_7d = added_30d = 0
    if as_of is not None:
        win = _frame("""
            SELECT COUNT(*) FILTER (WHERE first_seen_at >= :d7)  AS a7,
                   COUNT(*) FILTER (WHERE first_seen_at >= :d30) AS a30
            FROM companies
        """, d7=as_of - pd.Timedelta(days=7), d30=as_of - pd.Timedelta(days=30))
        if not win.empty:
            added_7d = int(win.iloc[0]["a7"] or 0)
            added_30d = int(win.iloc[0]["a30"] or 0)

    raw = _frame("SELECT DISTINCT country FROM companies "
                 "WHERE country IS NOT NULL AND country <> ''")
    countries = 0
    if not raw.empty:
        countries = raw["country"].map(clean_country).dropna().nunique()

    return Snapshot(
        total=int(r["total"] or 0),
        ai=int(r["ai"] or 0),
        hidden=int(r["hidden"] or 0),
        countries=int(countries),
        added_7d=added_7d,
        added_30d=added_30d,
        as_of=as_of.date() if as_of is not None else None,
    )


# ── Formation over time ──────────────────────────────────────────────────

@dataclass
class Formation:
    series: pd.DataFrame = field(default_factory=pd.DataFrame)  # year, n
    last_complete: int | None = None   # last year with credible coverage
    latest: int = 0                    # count in last_complete
    prior: int = 0                     # count in last_complete - 1
    recent_range: tuple[int, int] | None = None
    prior_range: tuple[int, int] | None = None

    @property
    def cohort_total(self) -> int:
        """Companies founded in the recent cohort — the level the page quotes.

        A year-over-year percentage is deliberately not published here. Both
        years sit inside the recording lag, so the figure would move with
        coverage as much as with formation and would read as a collapse that
        the data cannot support.
        """
        if self.series.empty or not self.recent_range:
            return 0
        r0, r1 = self.recent_range
        return int(self.series[(self.series["year"] >= r0)
                               & (self.series["year"] <= r1)]["n"].sum())

    @property
    def peak_year(self) -> int | None:
        if self.series.empty:
            return None
        return int(self.series.loc[self.series["n"].idxmax(), "year"])

    @property
    def provisional(self) -> pd.DataFrame:
        """Trailing years still filling in — plotted, but marked as partial."""
        if self.series.empty or self.last_complete is None:
            return pd.DataFrame()
        return self.series[self.series["year"] >= self.last_complete]


@st.cache_data(ttl=600, show_spinner=False)
def formation() -> Formation:
    """AI company formation by founding year, with the coverage cliff labelled.

    A trailing year counts as provisional when it holds less than half the
    median of the three years before it — the signature of records that have
    not landed yet, not of firms that were never founded.
    """
    df = _frame(f"""
        SELECT founded_year AS year, COUNT(*) AS n
        FROM companies
        WHERE {AI} AND founded_year BETWEEN 2010 AND EXTRACT(YEAR FROM NOW())::int
        GROUP BY 1 ORDER BY 1
    """)
    if df.empty:
        return Formation()
    df["year"] = df["year"].astype(int)
    df["n"] = df["n"].astype(int)

    last_complete = int(df["year"].max())
    for y in sorted(df["year"], reverse=True):
        window = df[(df["year"] >= y - 3) & (df["year"] < y)]["n"]
        if len(window) < 3:
            break
        if df.loc[df["year"] == y, "n"].iloc[0] >= 0.5 * window.median():
            last_complete = int(y)
            break
        last_complete = int(y) - 1

    cur = df[df["year"] == last_complete]["n"]
    prev = df[df["year"] == last_complete - 1]["n"]
    return Formation(
        series=df,
        last_complete=last_complete,
        latest=int(cur.iloc[0]) if len(cur) else 0,
        prior=int(prev.iloc[0]) if len(prev) else 0,
        recent_range=(last_complete - 2, last_complete),
        prior_range=(last_complete - 5, last_complete - 3),
    )


def cohorts() -> tuple[tuple[int, int], tuple[int, int]]:
    """(recent, prior) three-year founding windows used by every momentum figure."""
    f = formation()
    if f.recent_range and f.prior_range:
        return f.recent_range, f.prior_range
    y = date.today().year - 1
    return (y - 2, y), (y - 5, y - 3)


def _share_growth(df: pd.DataFrame, recent_total: int, prior_total: int) -> pd.DataFrame:
    """Turn recent/prior counts into share-of-cohort and its relative change.

    Raw count growth is unusable while recent cohorts are still filling in;
    share of cohort is not, because the incomplete denominator cancels.
    """
    if df.empty or not recent_total or not prior_total:
        return pd.DataFrame()
    out = df.copy()
    out["share"] = out["recent"] / recent_total * 100
    out["share_prior"] = out["prior"] / prior_total * 100
    out["growth"] = pd.NA
    ok = out["share_prior"] > 0
    out.loc[ok, "growth"] = (out.loc[ok, "share"] / out.loc[ok, "share_prior"] - 1) * 100
    return out


# ── Category momentum ────────────────────────────────────────────────────

# Umbrella and bookkeeping tags: true of most of the dataset, or written by our
# own classifier, so neither is a "category" a reader would recognise.
_TAG_SKIP = {
    "artificial-intelligence", "ai", "machine-learning", "deep-learning",
    "llm_classified_ai", "llm_classified_not_ai", "software", "saas",
    "technology", "information-technology", "internet", "apps", "mobile",
}

_TAG_NAMES = {
    "generative-ai": "Generative AI",
    "llm": "Large Language Models",
    "nlp": "Natural Language",
    "rag": "Retrieval-Augmented Gen",
    "agents": "AI Agents",
    "computer-vision": "Computer Vision",
    "autonomous-vehicles": "Autonomous Vehicles",
    "predictive-analytics": "Predictive Analytics",
    "image-recognition": "Image Recognition",
    "speech-recognition": "Speech Recognition",
    "intelligent-systems": "Intelligent Systems",
    "big-data": "Big Data",
    "rpa": "Process Automation",
    "robotics": "Robotics",
    "multimodal": "Multimodal",
    "diffusion": "Diffusion Models",
    "reinforcement-learning": "Reinforcement Learning",
    "neural-networks": "Neural Networks",
    "recommendation-engine": "Recommendation",
    "edge-computing": "Edge Computing",
}


def tag_label(tag: str) -> str:
    return _TAG_NAMES.get(tag, tag.replace("-", " ").replace("_", " ").title())


@st.cache_data(ttl=600, show_spinner=False)
def category_momentum(limit: int = 8, min_recent: int = 50) -> pd.DataFrame:
    """Which AI categories are gaining share of new company formation.

    `min_recent` is a floor on the recent cohort, not decoration: a tag with a
    dozen companies can post a four-figure percentage move that says nothing
    about the ecosystem, and it would crowd out the categories that do.

    Columns: tag, label, recent, prior, share, share_prior, growth.
    """
    (r0, r1), (p0, p1) = cohorts()
    df = _frame(f"""
        SELECT t AS tag,
               COUNT(*) FILTER (WHERE c.founded_year BETWEEN :r0 AND :r1) AS recent,
               COUNT(*) FILTER (WHERE c.founded_year BETWEEN :p0 AND :p1) AS prior
        FROM companies c, unnest(c.ai_tags) t
        WHERE {ai_filter_sql('c')} AND c.founded_year BETWEEN :p0 AND :r1
        GROUP BY 1
    """, r0=r0, r1=r1, p0=p0, p1=p1)
    if df.empty:
        return pd.DataFrame()

    df = df[~df["tag"].isin(_TAG_SKIP)]
    df = df[(df["recent"] >= min_recent) & (df["prior"] >= 15)]
    if df.empty:
        return pd.DataFrame()

    rt = int(_scalar(f"SELECT COUNT(*) FROM companies WHERE {AI} "
                     "AND founded_year BETWEEN :a AND :b", a=r0, b=r1))
    pt = int(_scalar(f"SELECT COUNT(*) FROM companies WHERE {AI} "
                     "AND founded_year BETWEEN :a AND :b", a=p0, b=p1))
    out = _share_growth(df, rt, pt)
    if out.empty:
        return out
    out["label"] = out["tag"].map(tag_label)
    return out.sort_values("growth", ascending=False).head(limit).reset_index(drop=True)


# ── Geographic momentum ──────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def geographic_momentum(limit: int = 6, min_recent: int = 20) -> pd.DataFrame:
    """City share of recent AI company formation, and how that share moved.

    Columns: city, country, recent, prior, share, share_prior, growth.
    """
    (r0, r1), (p0, p1) = cohorts()
    df = _frame(f"""
        SELECT city, country,
               COUNT(*) FILTER (WHERE founded_year BETWEEN :r0 AND :r1) AS recent,
               COUNT(*) FILTER (WHERE founded_year BETWEEN :p0 AND :p1) AS prior
        FROM companies
        WHERE {AI} AND city IS NOT NULL AND city <> ''
          AND founded_year BETWEEN :p0 AND :r1
        GROUP BY 1, 2
    """, r0=r0, r1=r1, p0=p0, p1=p1)
    if df.empty:
        return pd.DataFrame()

    df["city"] = df["city"].astype(str).str.strip()
    df["country"] = df["country"].map(clean_country)
    df = (df.groupby(["city", "country"], dropna=False)[["recent", "prior"]]
            .sum().reset_index())
    df = df[df["recent"] >= min_recent]
    if df.empty:
        return pd.DataFrame()

    rt = int(_scalar(f"SELECT COUNT(*) FROM companies WHERE {AI} "
                     "AND founded_year BETWEEN :a AND :b AND city IS NOT NULL AND city <> ''",
                     a=r0, b=r1))
    pt = int(_scalar(f"SELECT COUNT(*) FROM companies WHERE {AI} "
                     "AND founded_year BETWEEN :a AND :b AND city IS NOT NULL AND city <> ''",
                     a=p0, b=p1))
    out = _share_growth(df, rt, pt)
    if out.empty:
        return out
    return out.sort_values("share", ascending=False).head(limit).reset_index(drop=True)


@st.cache_data(ttl=600, show_spinner=False)
def country_totals(min_companies: int = 5) -> pd.DataFrame:
    """Per-country totals for the world map. Aggregates only — no company rows."""
    df = _frame(f"""
        SELECT country, COUNT(*) AS total, COUNT(*) FILTER (WHERE {AI}) AS ai
        FROM companies
        WHERE country IS NOT NULL AND country <> ''
        GROUP BY 1
    """)
    if df.empty:
        return df
    df["country"] = df["country"].map(clean_country)
    df = df.dropna(subset=["country"])
    df = df.groupby("country", as_index=False)[["total", "ai"]].sum()
    return df[df["total"] >= min_companies].reset_index(drop=True)


@st.cache_data(ttl=600, show_spinner=False)
def region_totals() -> pd.DataFrame:
    """Hidden AI companies rolled up to the region layer. Columns: region, n."""
    df = _frame(f"""
        SELECT country, COUNT(*) AS n FROM companies
        WHERE verification_status = :hidden AND {AI}
          AND country IS NOT NULL AND country <> ''
        GROUP BY 1
    """, hidden=HIDDEN)
    if df.empty:
        return df
    df["region"] = df["country"].map(region_of)
    out = (df.dropna(subset=["region"]).groupby("region", as_index=False)["n"].sum()
             .sort_values("n", ascending=False).reset_index(drop=True))
    return out


# ── Weekly intake ────────────────────────────────────────────────────────

@dataclass
class Week:
    start: date | None = None
    end: date | None = None
    total: int = 0
    hidden: int = 0
    ai: int = 0
    countries: int = 0
    prior_total: int = 0
    top_countries: pd.DataFrame = field(default_factory=pd.DataFrame)
    channels: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def hidden_share(self) -> float:
        return (self.hidden / self.total * 100) if self.total else 0.0

    @property
    def wow(self) -> float | None:
        if not self.prior_total:
            return None
        return (self.total - self.prior_total) / self.prior_total * 100


@st.cache_data(ttl=300, show_spinner=False)
def latest_week() -> Week:
    """The most recent week in which companies actually entered the dataset.

    Anchored on the newest `first_seen_at` rather than on today, so the brief
    reports a real window with a real date range even when ingestion is paused.
    """
    weeks = _frame("""
        SELECT date_trunc('week', first_seen_at)::date AS wk, COUNT(*) AS n
        FROM companies WHERE first_seen_at IS NOT NULL
        GROUP BY 1 ORDER BY 1 DESC LIMIT 2
    """)
    if weeks.empty:
        return Week()

    start = pd.to_datetime(weeks.iloc[0]["wk"]).date()
    prior_total = int(weeks.iloc[1]["n"]) if len(weeks) > 1 else 0

    agg = _frame(f"""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE verification_status = :hidden) AS hidden,
               COUNT(*) FILTER (WHERE {AI}) AS ai
        FROM companies WHERE date_trunc('week', first_seen_at)::date = :wk
    """, wk=start, hidden=HIDDEN)
    if agg.empty:
        return Week(start=start)
    a = agg.iloc[0]

    countries = _frame("""
        SELECT country, COUNT(*) AS n FROM companies
        WHERE date_trunc('week', first_seen_at)::date = :wk
          AND country IS NOT NULL AND country <> ''
        GROUP BY 1
    """, wk=start)
    n_countries = 0
    top = pd.DataFrame()
    if not countries.empty:
        countries["country"] = countries["country"].map(clean_country)
        countries = countries.dropna(subset=["country"])
        countries = countries.groupby("country", as_index=False)["n"].sum()
        n_countries = int(countries["country"].nunique())
        top = countries.sort_values("n", ascending=False).head(6).reset_index(drop=True)

    channels = _frame("""
        SELECT CASE
                 WHEN source_domain IN ('nih.gov', 'nsf.gov') THEN 'Government grant awards'
                 WHEN incubator_source IS NOT NULL            THEN 'Accelerator & VC portfolios'
                 WHEN source_domain IS NOT NULL               THEN 'Startup media & directories'
                 ELSE 'GitHub & model hubs'
               END AS channel,
               COUNT(*) AS n
        FROM companies WHERE date_trunc('week', first_seen_at)::date = :wk
        GROUP BY 1 ORDER BY 2 DESC
    """, wk=start)

    return Week(
        start=start,
        end=start + pd.Timedelta(days=6).to_pytimedelta(),
        total=int(a["total"] or 0),
        hidden=int(a["hidden"] or 0),
        ai=int(a["ai"] or 0),
        countries=n_countries,
        prior_total=prior_total,
        top_countries=top,
        channels=channels,
    )


# ── Discovery-channel facts used by the secondary stories ────────────────

@st.cache_data(ttl=600, show_spinner=False)
def channel_facts() -> dict:
    """Standing counts the weekly brief cites. All hidden-AI unless noted."""
    where = f"c.verification_status = '{HIDDEN}' AND {ai_filter_sql('c')}"
    return {
        "hidden_ai": int(_scalar(f"SELECT COUNT(*) FROM companies c WHERE {where}")),
        "github_native": int(_scalar(
            "SELECT COUNT(DISTINCT c.id) FROM companies c "
            f"JOIN github_signals g ON g.company_id = c.id WHERE {where}")),
        "grant_backed": int(_scalar(
            "SELECT COUNT(*) FROM companies c "
            f"WHERE {where} AND c.source_domain IN ('nih.gov', 'nsf.gov')")),
        "portfolio": int(_scalar(
            f"SELECT COUNT(*) FROM companies c WHERE {where} "
            "AND c.incubator_source IS NOT NULL")),
        "with_domain": int(_scalar(
            f"SELECT COUNT(*) FROM companies c WHERE {where} "
            "AND c.domain IS NOT NULL AND c.domain <> ''")),
    }


@st.cache_data(ttl=600, show_spinner=False)
def hidden_vs_commercial() -> pd.DataFrame:
    """AI density by verification bucket — the tracker's core comparison."""
    df = _frame(f"""
        SELECT verification_status AS bucket, COUNT(*) AS total,
               COUNT(*) FILTER (WHERE {AI}) AS ai
        FROM companies WHERE verification_status IS NOT NULL
        GROUP BY 1
    """)
    if df.empty:
        return df
    df["ai_pct"] = (df["ai"] / df["total"] * 100).round(1)
    return df


# ── Company rows (hidden only — CB/PB rows stay aggregate) ───────────────

PLACEHOLDER_DESC = "Hugging Face organization%"

# Scraping accelerator and fund pages inevitably picks up the funds themselves,
# and bulk imports carry in incumbent research labs. Both are real rows, but a
# public "recently discovered companies" list is claiming they are young firms,
# so they are held back from that list only — no record is deleted or altered.
_NOT_A_STARTUP = (
    "venture capital", "venture firm", "venture fund", "investment firm",
    "portfolio companies", "we invest in", "early stage investor",
    "angel investor", "accelerator program", "seed fund", "growth equity",
    "private equity",
)


def drop_non_startups(df: pd.DataFrame) -> pd.DataFrame:
    """Remove investors and incumbent labs from a company list."""
    if df.empty:
        return df
    name_l = df["name"].fillna("").str.strip().str.lower()
    dom = (df.get("domain", pd.Series("", index=df.index)).fillna("")
             .str.strip().str.lower().str.replace(r"^www\.", "", regex=True))
    desc_l = df.get("description", pd.Series("", index=df.index)).fillna("").str.lower()

    # Sub-brands arrive as "Facebook Reality Labs" or "Google Quantum AI", which
    # the exact-name denylist misses; the leading token catches them.
    first_token = name_l.str.split().str[0].fillna("")
    big_tech = (name_l.isin(BIG_TECH_DENYLIST)
                | first_token.isin(BIG_TECH_DENYLIST)
                | dom.str.split(".").str[0].isin(BIG_TECH_DENYLIST))
    investor = desc_l.str.contains("|".join(_NOT_A_STARTUP), regex=True, na=False)
    return df[~(big_tech | investor)]


@st.cache_data(ttl=300, show_spinner=False)
def recent_hidden(limit: int = 8) -> pd.DataFrame:
    """Most recently discovered hidden AI companies that describe themselves.

    Rows carrying only scraper boilerplate for a description are excluded — real
    records, but they say nothing a reader can use.
    """
    df = _frame(f"""
        SELECT name, domain, country, city, founded_year,
               LEFT(description, 260) AS description,
               source_domain, incubator_source,
               first_seen_at::date AS first_seen
        FROM companies c
        WHERE c.verification_status = :hidden AND {ai_filter_sql('c')}
          AND name IS NOT NULL AND name <> ''
          AND description IS NOT NULL AND length(description) > 60
          AND description NOT ILIKE :ph
        ORDER BY first_seen_at DESC NULLS LAST
        LIMIT :lim
    """, hidden=HIDDEN, ph=PLACEHOLDER_DESC, lim=limit * 6)
    if df.empty:
        return df

    df = drop_non_startups(df).head(limit).reset_index(drop=True)
    df["country"] = df["country"].map(clean_country)
    return df


def discovery_channel(row) -> str:
    """Human label for how a company was found.

    Missing values arrive as NaN, which is truthy — so each field is checked
    with `pd.notna` rather than plain truthiness.
    """
    src = row.get("source_domain")
    src = str(src).strip() if pd.notna(src) else ""
    inc = row.get("incubator_source")

    if src in ("nih.gov", "nsf.gov"):
        return "Government grant"
    if pd.notna(inc) and str(inc).strip():
        return "Portfolio scrape"
    if src:
        return f"Web · {src}"
    return "GitHub"
