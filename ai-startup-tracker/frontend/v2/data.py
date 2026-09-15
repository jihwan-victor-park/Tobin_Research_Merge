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
from datetime import date, timedelta

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

# Floor on a founding year's total intake before its AI share is plotted.
# 2026 currently holds ~16 companies; a 69% share off that base is noise.
MIN_COHORT = 500

# Length of the "recent activity" window the homepage reports, in days.
WINDOW_DAYS = 30

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
    def stale_days(self) -> int:
        """Days since the newest record. 0 when the dataset has no records."""
        return max(0, (date.today() - self.as_of).days) if self.as_of else 0

    @property
    def is_stale(self) -> bool:
        return self.stale_days > WINDOW_DAYS

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


# Broad "AI and data" definition. The narrow AI filter (`AI`) counts 124,093
# companies; adding the Data & Analytics vertical reaches 191,488, which is the
# ~200,000 the research programme reports. The two are never used
# interchangeably, and neither is shown without its denominator.
AI_BROAD = f"(({AI}) OR categories && ARRAY['Data & Analytics'])"


@st.cache_data(ttl=600, show_spinner=False)
def headline_counts() -> dict:
    """The two figures the research programme reports, plus their bases.

    Both come from the SAME broad definition, which is why they can be read
    together: 191,488 AI and data companies, of which 13,696 appear in no
    commercial database. Mixing the broad total with the narrow hidden count
    (13,579) would put two different definitions side by side and invite the
    reader to subtract one from the other.
    """
    row = _frame(f"""
        SELECT
          COUNT(*) FILTER (WHERE {AI_BROAD})                              AS ai_total,
          COUNT(*) FILTER (WHERE {AI_BROAD} AND verification_status = :h) AS ai_hidden,
          COUNT(*) FILTER (WHERE {AI})                                    AS ai_narrow,
          COUNT(*)                                                        AS all_companies
        FROM companies
    """, h=HIDDEN)
    if row.empty:
        return {}
    out = {k: int(v) for k, v in row.iloc[0].items()}
    # Same country cleaner the rest of the page uses; a raw DISTINCT counts
    # "Alabama", "Bologna" and a bare latitude as countries.
    places = _frame(f"SELECT DISTINCT country FROM companies "
                    f"WHERE {AI_BROAD} AND country IS NOT NULL")
    out["countries"] = len({c for c in places["country"].map(clean_country) if c})
    return out


@st.cache_data(ttl=600, show_spinner=False)
def metric_trends() -> dict[str, list[float]]:
    """Short cumulative series behind each headline metric, for the sparklines.

    All four describe the same thing the strip reports — how the dataset itself
    has grown — so the little charts and the numbers beside them cannot be read
    as measuring different quantities. Returns empty lists when there is not
    enough history to draw an honest line.
    """
    df = _frame(f"""
        SELECT date_trunc('month', first_seen_at)::date AS m,
               COUNT(*)                                             AS n,
               COUNT(*) FILTER (WHERE verification_status = :hidden) AS hidden,
               COUNT(*) FILTER (WHERE {AI})                          AS ai
        FROM companies WHERE first_seen_at IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """, hidden=HIDDEN)
    if df.empty or len(df) < 3:
        return {}

    total = df["n"].cumsum()
    hidden = df["hidden"].cumsum()
    ai = df["ai"].cumsum()

    # Distinct countries has no cumulative form in SQL; accumulate the sets.
    pairs = _frame("""
        SELECT date_trunc('month', first_seen_at)::date AS m, country
        FROM companies
        WHERE first_seen_at IS NOT NULL AND country IS NOT NULL AND country <> ''
        GROUP BY 1, 2 ORDER BY 1
    """)
    countries: list[float] = []
    if not pairs.empty:
        pairs["country"] = pairs["country"].map(clean_country)
        pairs = pairs.dropna(subset=["country"])
        seen: set[str] = set()
        by_month = {m: set(g["country"]) for m, g in pairs.groupby("m")}
        for m in df["m"]:
            seen |= by_month.get(m, set())
            countries.append(float(len(seen)))

    return {
        "total": [float(v) for v in total],
        "hidden": [float(v) for v in hidden],
        "ai_share": [float(a) / float(t) * 100 if t else 0.0
                     for a, t in zip(ai, total)],
        "countries": countries,
    }


# ── Formation over time ──────────────────────────────────────────────────

@dataclass
class Formation:
    """AI formation by founding year, carried as both a count and a share.

    The page plots `share`, not `n`. Raw AI counts fall from 2018 onward
    (8,105 -> 5,612 in 2024 -> 1,611 in 2025), which reads as AI startup
    formation collapsing. It is not: total company coverage falls with it --
    output/07_data_lag_estimate.csv puts 2024 at ~80% undercounted and 2025 at
    ~95%. In the ratio the incomplete denominator largely cancels, and the
    same data rises monotonically (15.9% in 2018 -> 59.0% in 2025). Both
    columns are kept so the count is still available for hover and for the
    cohort totals the header quotes.
    """
    series: pd.DataFrame = field(default_factory=pd.DataFrame)  # year, n, total, share
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
        """The year AI's share of formation peaks -- restricted to complete years.

        Taken off `share` rather than `n`: the count peaks in 2018 purely
        because that is where coverage peaks, which would put "PEAK 2018" on a
        page whose whole argument is that AI formation is still climbing.
        """
        if self.series.empty or "share" not in self.series:
            return None
        usable = self.series
        if self.last_complete is not None:
            usable = usable[usable["year"] <= self.last_complete]
        if usable.empty:
            return None
        return int(usable.loc[usable["share"].idxmax(), "year"])

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
        SELECT founded_year AS year,
               COUNT(*)                     AS total,
               COUNT(*) FILTER (WHERE {AI}) AS n
        FROM companies
        WHERE founded_year BETWEEN 2010 AND EXTRACT(YEAR FROM NOW())::int
        GROUP BY 1 ORDER BY 1
    """)
    if df.empty:
        return Formation()
    df["year"] = df["year"].astype(int)
    df["n"] = df["n"].astype(int)
    df["total"] = df["total"].astype(int)

    # A share computed on a handful of companies is noise, not a finding: the
    # current year typically holds a few dozen records. Drop those years
    # outright rather than plotting a ratio nobody should read.
    df = df[df["total"] >= MIN_COHORT].reset_index(drop=True)
    if df.empty:
        return Formation()
    df["share"] = df["n"] / df["total"] * 100

    # Completeness is a property of coverage, so it is judged on the total
    # intake for a year, not on the AI subset -- the AI count can hold up in a
    # thin year simply because AI-tilted channels report faster.
    last_complete = int(df["year"].max())
    for y in sorted(df["year"], reverse=True):
        window = df[(df["year"] >= y - 3) & (df["year"] < y)]["total"]
        if len(window) < 3:
            break
        if df.loc[df["year"] == y, "total"].iloc[0] >= 0.5 * window.median():
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
class Activity:
    """Companies that entered the dataset in the trailing window.

    This measures *discovery*, not formation — when a record reached us, not
    when the company was founded. The two are routinely confused, so every
    label built from this says "recorded" or "arrived", never "founded".
    """
    start: date | None = None
    end: date | None = None
    total: int = 0
    hidden: int = 0
    ai: int = 0
    countries: int = 0
    prior_total: int = 0
    top_countries: pd.DataFrame = field(default_factory=pd.DataFrame)
    channels: pd.DataFrame = field(default_factory=pd.DataFrame)
    stale_days: int = 0                # days between `end` and today

    @property
    def is_stale(self) -> bool:
        """Whether the window has drifted behind the calendar.

        The window is anchored on the newest record rather than on today, so a
        paused pipeline produces a full-looking window that is simply old. The
        page has to say so or the figures read as current.
        """
        return self.stale_days > WINDOW_DAYS

    @property
    def hidden_share(self) -> float:
        return (self.hidden / self.total * 100) if self.total else 0.0

    @property
    def wow(self) -> float | None:
        if not self.prior_total:
            return None
        return (self.total - self.prior_total) / self.prior_total * 100


@st.cache_data(ttl=600, show_spinner=False)
def quarterly_discovery(quarters: int = 5) -> pd.DataFrame:
    """What our own collection found each quarter.

    Restricted to companies in neither commercial database, because those are
    the ones the scrapers actually discovered. Counting every arrival would
    date tens of thousands of companies to whichever quarter a bulk parquet was
    imported, and show the quarter after as a collapse.

    Columns: q, discovered, countries, with_site, delta.
    """
    df = _frame(f"""
        SELECT date_trunc('quarter', first_seen_at)::date   AS q,
               COUNT(*)                                     AS discovered,
               COUNT(DISTINCT country)                      AS countries,
               COUNT(*) FILTER (WHERE domain IS NOT NULL)   AS with_site
        FROM companies
        WHERE {AI} AND verification_status = :h AND first_seen_at IS NOT NULL
        GROUP BY 1 ORDER BY 1 DESC LIMIT :n
    """, h=HIDDEN, n=quarters + 1)
    if df.empty:
        return df
    df = df.sort_values("q").reset_index(drop=True)
    df["delta"] = df["discovered"].pct_change() * 100
    return df.tail(quarters).iloc[::-1].reset_index(drop=True)


@st.cache_data(ttl=300, show_spinner=False)
def recent_activity() -> Activity:
    """The trailing 30 days of intake, anchored on the newest record.

    Anchored on the newest `first_seen_at` rather than on today, so the page
    reports a real window with a real date range even when ingestion is
    paused — `stale_days` is what tells the reader which of those it is.
    """
    anchor = _frame("SELECT MAX(first_seen_at)::date AS d FROM companies")
    if anchor.empty or pd.isna(anchor.iloc[0]["d"]):
        return Activity()
    end = pd.to_datetime(anchor.iloc[0]["d"]).date()
    start = end - timedelta(days=WINDOW_DAYS - 1)
    prior_start = start - timedelta(days=WINDOW_DAYS)
    stale_days = max(0, (date.today() - end).days)

    prior_total = int(_scalar(
        "SELECT COUNT(*) FROM companies "
        "WHERE first_seen_at::date >= :p0 AND first_seen_at::date < :s",
        p0=prior_start, s=start))

    agg = _frame(f"""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE verification_status = :hidden) AS hidden,
               COUNT(*) FILTER (WHERE {AI}) AS ai
        FROM companies
        WHERE first_seen_at::date BETWEEN :s AND :e
    """, s=start, e=end, hidden=HIDDEN)
    if agg.empty:
        return Activity(start=start, end=end, stale_days=stale_days)
    a = agg.iloc[0]

    countries = _frame("""
        SELECT country, COUNT(*) AS n FROM companies
        WHERE first_seen_at::date BETWEEN :s AND :e
          AND country IS NOT NULL AND country <> ''
        GROUP BY 1
    """, s=start, e=end)
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
        FROM companies WHERE first_seen_at::date BETWEEN :s AND :e
        GROUP BY 1 ORDER BY 2 DESC
    """, s=start, e=end)

    return Activity(
        start=start,
        end=end,
        stale_days=stale_days,
        total=int(a["total"] or 0),
        hidden=int(a["hidden"] or 0),
        ai=int(a["ai"] or 0),
        countries=n_countries,
        prior_total=prior_total,
        top_countries=top,
        channels=channels,
    )


# ── What these companies do (bottom-up taxonomy) ─────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def domain_totals(limit: int = 6) -> tuple[pd.DataFrame, int]:
    """AI companies per discovered domain, with the full mapped total.

    Surfaced on the homepage so a reader meets "what these companies do"
    before deciding whether to open the Landscape page. The total comes back
    alongside the top rows so the caller can draw an honest remainder.

    Returns an empty frame where `company_taxonomy` does not exist -- that is
    the case on the local database, and `_frame` already swallows it.
    """
    df = _frame("""
        SELECT domain_l1 AS domain,
               COUNT(*) FILTER (WHERE bucket = 'hidden') AS unlisted,
               COUNT(*)                                  AS total
        FROM company_taxonomy
        WHERE status IN ('mapped', 'category_mapped')
        GROUP BY 1 ORDER BY total DESC
    """)
    if df.empty:
        return df, 0
    df["total"] = df["total"].astype(int)
    df["unlisted"] = df["unlisted"].astype(int)
    return df.head(limit).reset_index(drop=True), int(df["total"].sum())


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
        SELECT c.id, name, domain, country, city, founded_year,
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
