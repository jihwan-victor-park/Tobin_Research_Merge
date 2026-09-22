"""The weekly intelligence briefing.

Each brief is a short paragraph written from figures this dataset actually
holds, followed by a few places to read around the subject. The dataset drives
the insight; the links are context, not the story.

**On the links.** These point into our own quarterly analyses, not out to news
outlets. An earlier version sent each brief's subject into Reuters, the FT,
TechCrunch and others as a search query — real destinations, but they returned
whatever those outlets happened to publish, which is not evidence for anything
said above them. A brief now hands the reader the section of our own research
that the figure was computed from. `Brief.sources` is unchanged as a seam.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .. import vocabulary as V
from . import data as D

# Our own analyses, refreshed quarterly. Keys are the site's own routes, which
# the shell reads back off `?page=`.
_SIGNALS = {
    "formation": ("Formation timeline", "?page=Findings"),
    "geography": ("Geographic concentration", "?page=Findings"),
    "sectors": ("Sector adoption", "?page=Findings"),
    "landscape": ("What these companies do", "?page=Landscape"),
    "coverage": ("Companies commercial databases miss", "?page=Findings"),
    "directory": ("Company directory", "?page=Companies"),
}


def _links(keys: tuple[str, ...]) -> list[tuple[str, str]]:
    return [_SIGNALS[k] for k in keys if k in _SIGNALS]


@dataclass
class Brief:
    headline: str
    body: str                     # may contain <b>; figures come from the data
    kicker: str = ""
    figure: str = ""              # the one number the brief rests on
    figure_caption: str = ""
    sources: list[tuple[str, str]] = field(default_factory=list)


def build(week: D.Activity, snap: D.Snapshot, facts: dict,
          cats: pd.DataFrame, geo: pd.DataFrame) -> list[Brief]:
    """Assemble the window's briefs, skipping any the data cannot support."""
    briefs: list[Brief] = []
    (r0, r1), (p0, p1) = D.cohorts()

    # ── Lead: what arrived, and how much of it is invisible elsewhere ──
    if week.total:
        share = week.hidden_share
        reach = (f" They carry headquarters in <b>{week.countries:,}</b> "
                 f"countries." if week.countries else "")
        briefs.append(Brief(
            kicker="Lead · dataset intake",
            headline=("Most of what arrived is invisible to commercial databases"
                      if share >= 60 else
                      "Commercial coverage kept pace with this intake"),
            body=(f"<b>{week.total:,}</b> companies entered the dataset in the 30 "
                  f"days to {week.end:%B %d, %Y}, of which "
                  f"<b>{week.hidden:,} ({share:.1f}%)</b> {V.ABSENT} — often "
                  f"long before a commercial database registers them, if it "
                  f"ever does.{reach}"),
            figure=f"{share:.1f}%",
            figure_caption=f"of these arrivals are {V.ABSENT_SHORT}",
            sources=_links(("coverage", "formation", "directory")),
        ))

    # ── Category momentum ──
    if not cats.empty:
        top = cats.iloc[0]
        label = str(top["label"])
        briefs.append(Brief(
            kicker="Sectors",
            headline=f"{label} is taking share of new AI company formation",
            body=(f"{label} accounts for <b>{float(top['share']):.1f}%</b> of AI "
                  f"companies founded in {r0}–{r1}, against "
                  f"<b>{float(top['share_prior']):.1f}%</b> in {p0}–{p1} — a "
                  f"<b>{float(top['growth']):+.1f}%</b> move on "
                  f"<b>{int(top['recent']):,}</b> companies. Shares are used rather "
                  f"than raw counts because the most recent founding years are still "
                  f"filling in."),
            figure=f"{float(top['growth']):+.1f}%",
            figure_caption=f"change in share of formation, {r0}–{r1} vs {p0}–{p1}",
            sources=_links(("sectors", "landscape", "formation")),
        ))

    # ── Formation outside the United States ──
    if not geo.empty:
        non_us = geo[geo["country"] != "United States"]
        if not non_us.empty:
            city = non_us.iloc[0]
            name = f"{city['city']}"
            country = str(city["country"]) if pd.notna(city["country"]) else ""
            where = f"{name}, {country}" if country else name
            briefs.append(Brief(
                kicker="Geography",
                headline=f"{name} leads AI company formation outside the United States",
                body=(f"{where} accounts for <b>{float(city['share']):.1f}%</b> of AI "
                      f"companies founded in {r0}–{r1}, on <b>{int(city['recent']):,}</b> "
                      f"firms. Place figures cover only companies that carry a location "
                      f"in the dataset, so they describe where formation is recorded, "
                      f"not the whole world."),
                figure=f"{float(city['share']):.1f}%",
                figure_caption=f"share of {r0}–{r1} AI company formation",
                sources=_links(("geography", "formation")),
            ))

    # ── Coverage ──
    # This brief used to describe how the companies were found. The finding is
    # that they are absent from the commercial databases while plainly being
    # real operating firms; the channel that surfaced them is our business.
    if facts.get("hidden_ai"):
        hidden_ai = facts["hidden_ai"]
        with_site = facts.get("with_domain") or 0
        # Stated as coverage, not as a survival claim: a recorded address is
        # not a live site, and the companies without one are companies we hold
        # no address for -- not companies without a website.
        detail = ""
        if with_site:
            detail = (f" We hold a web address for <b>{with_site:,}</b> of them "
                      f"({with_site / hidden_ai * 100:.0f}%); for the rest we "
                      f"hold none, which is a gap in what we know rather than a "
                      f"finding about the company.")
        briefs.append(Brief(
            kicker="Coverage",
            headline="A large AI population sits outside the commercial databases",
            body=(f"<b>{hidden_ai:,}</b> AI companies in this dataset "
                  f"{V.ABSENT}.{detail}"),
            figure=f"{hidden_ai:,}",
            figure_caption=f"AI companies {V.ABSENT_SHORT}",
            sources=_links(("coverage", "landscape")),
        ))

    return briefs
