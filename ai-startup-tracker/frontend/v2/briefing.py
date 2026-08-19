"""The weekly intelligence briefing.

Each brief is a short paragraph written from figures this dataset actually
holds, followed by a few places to read around the subject. The dataset drives
the insight; the links are context, not the story.

**On the links.** No newsroom feed is connected to the database, so nothing here
claims to have found a specific article. Each brief carries its own subject
into the outlets' own search endpoints — real destinations, honestly labelled.
`Brief.sources` is the seam: when a coverage table exists, fill it with real
headlines and the rendering does not change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote_plus

import pandas as pd

from . import data as D

# Outlets that actually cover company formation and venture activity.
_OUTLETS = {
    "reuters": ("Reuters", "https://www.reuters.com/site-search/?query={q}"),
    "ft": ("Financial Times", "https://www.ft.com/search?q={q}"),
    "techcrunch": ("TechCrunch", "https://techcrunch.com/?s={q}"),
    "theverge": ("The Verge", "https://www.theverge.com/search?q={q}"),
    "sifted": ("Sifted", "https://sifted.eu/?s={q}"),
    "theinformation": ("The Information", "https://www.theinformation.com/search?query={q}"),
    "github": ("GitHub", "https://github.com/search?q={q}&type=repositories"),
}


def _links(subject: str, keys: tuple[str, ...]) -> list[tuple[str, str]]:
    q = quote_plus(subject)
    return [(_OUTLETS[k][0], _OUTLETS[k][1].format(q=q)) for k in keys if k in _OUTLETS]


@dataclass
class Brief:
    headline: str
    body: str                     # may contain <b>; figures come from the data
    kicker: str = ""
    figure: str = ""              # the one number the brief rests on
    figure_caption: str = ""
    sources: list[tuple[str, str]] = field(default_factory=list)


def build(week: D.Week, snap: D.Snapshot, facts: dict,
          cats: pd.DataFrame, geo: pd.DataFrame) -> list[Brief]:
    """Assemble the week's briefs, skipping any the data cannot support."""
    briefs: list[Brief] = []
    (r0, r1), (p0, p1) = D.cohorts()

    # ── Lead: what arrived, and how much of it is invisible elsewhere ──
    if week.total:
        share = week.hidden_share
        channel = ""
        if not week.channels.empty:
            top = week.channels.iloc[0]
            channel = (f" The largest single channel was {top['channel']}, "
                       f"accounting for <b>{int(top['n']):,}</b> of them.")
        reach = (f" The week's arrivals carry headquarters in "
                 f"<b>{week.countries:,}</b> countries." if week.countries else "")
        briefs.append(Brief(
            kicker="Lead · dataset intake",
            headline=("Most of this week's arrivals are invisible to commercial databases"
                      if share >= 60 else
                      "Commercial coverage kept pace with this week's intake"),
            body=(f"<b>{week.total:,}</b> companies entered the dataset this week, of "
                  f"which <b>{week.hidden:,} ({share:.1f}%)</b> appear in neither "
                  f"Crunchbase nor PitchBook. They surface first through code hosts, "
                  f"model hubs, accelerator portfolios and public grant awards — often "
                  f"long before a commercial database registers them, if it ever "
                  f"does.{channel}{reach}"),
            figure=f"{share:.1f}%",
            figure_caption="of this week's arrivals are in neither Crunchbase nor PitchBook",
            sources=_links("AI startup funding database",
                           ("reuters", "techcrunch", "theinformation")),
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
            sources=_links(f"{label} startups", ("techcrunch", "reuters", "theverge")),
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
                sources=_links(f"{name} AI startups", ("sifted", "ft", "techcrunch")),
            ))

    # ── Discovery channel ──
    if facts.get("github_native"):
        with_site = facts.get("with_domain") or 0
        briefs.append(Brief(
            kicker="Discovery",
            headline="Companies keep arriving through code before anyone lists them",
            body=(f"<b>{facts['github_native']:,}</b> of the companies missing from "
                  f"Crunchbase and PitchBook were found through a public code "
                  f"repository rather than a funding announcement or a directory"
                  + (f", and <b>{with_site:,}</b> of that hidden population already "
                     f"run a live website" if with_site else "") + "."),
            figure=f"{facts['github_native']:,}",
            figure_caption="hidden companies found through a public repository",
            sources=_links("AI startup open source", ("github", "techcrunch", "theverge")),
        ))

    return briefs
