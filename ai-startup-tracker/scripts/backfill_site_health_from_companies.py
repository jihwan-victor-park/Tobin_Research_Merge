"""
Backfill site_health from existing companies.incubator_source values.

Many companies in the DB came from older batch scripts (scrape_incubators.py /
scrape_international_incubators.py) that wrote directly to companies without
going through the orchestrator, so they never created a site_health row.

This script:
  - Reads distinct incubator_source values from companies
  - For each, ensures a site_health row exists
  - Marks worker_state='working' (since the scraper has produced records)
  - Backfills last_record_count, total_successes, total_runs, last_success_at
    from the most recent companies.first_seen_at for that source

Idempotent: re-running updates counts but doesn't duplicate rows.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func

from backend.db.connection import session_scope
from backend.db.models import Company, IncubatorSource, SiteHealth

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# Map IncubatorSource enum values to (canonical domain, seed URL, category).
# Domain matches what canonicalize_domain() would produce so it lines up
# with both the new registry and any future YAML-driven scrapes.
# category ∈ {university_incubator, accelerator, vc_portfolio,
#             discovery_aggregator, government_program, other}
SOURCE_TO_SITE: dict[str, tuple[str, str, str]] = {
    # US accelerators / incubators
    "capital_factory":      ("capitalfactory.com",         "https://capitalfactory.com/portfolio/",                                   "accelerator"),
    "gener8tor":            ("gener8tor.com",              "https://www.gener8tor.com/companies",                                     "accelerator"),
    "village_global":       ("villageglobal.com",          "https://www.villageglobal.com/portfolio",                                 "vc_portfolio"),
    "founder_institute":    ("fi.co",                      "https://fi.co/graduates",                                                 "accelerator"),
    "seedcamp":             ("seedcamp.com",               "https://seedcamp.com/our-companies/",                                     "accelerator"),
    "beenext":              ("beenext.com",                "https://www.beenext.com/portfolio/",                                      "vc_portfolio"),
    "antler":               ("antler.co",                  "https://www.antler.co/portfolio",                                         "vc_portfolio"),
    "entrepreneur_first":   ("joinef.com",                 "https://www.joinef.com/portfolio/",                                       "accelerator"),
    "pioneer_fund":         ("pioneerfund.vc",             "https://pioneerfund.vc/portfolio",                                        "vc_portfolio"),
    "dreamit":              ("dreamit.com",                "https://www.dreamit.com/portfolio",                                       "accelerator"),

    # University programs
    "berkeley_skydeck":     ("skydeck.berkeley.edu",       "https://skydeck.berkeley.edu/portfolio/",                                 "university_incubator"),
    "mit_engine":           ("engine.xyz",                 "https://engine.xyz/companies/",                                           "university_incubator"),
    "stanford_startx":      ("web.startx.com",             "https://web.startx.com/companies",                                        "university_incubator"),
    "uiuc_enterpriseworks": ("researchpark.illinois.edu",  "https://researchpark.illinois.edu/company/enterpriseworks/",              "university_incubator"),
    "cmu_swartz":           ("cmu.edu",                    "https://www.cmu.edu/swartz-center-for-entrepreneurship/",                 "university_incubator"),
    "harvard_ilabs":        ("innovationlabs.harvard.edu", "https://innovationlabs.harvard.edu/portfolio/",                           "university_incubator"),
    "georgia_tech_atdc":    ("atdc.org",                   "https://atdc.org/companies/",                                             "university_incubator"),
    "michigan_zell_lurie":  ("zli.umich.edu",              "https://zli.umich.edu/student-startups/",                                 "university_incubator"),

    # Big-name accelerators
    "techstars":            ("techstars.com",              "https://www.techstars.com/portfolio",                                     "accelerator"),
    "five_hundred_global":  ("500.co",                     "https://500.co/companies",                                                "accelerator"),
    "alchemist":            ("alchemistaccelerator.com",   "https://www.alchemistaccelerator.com/portfolio",                          "accelerator"),
    "sosv":                 ("sosv.com",                   "https://sosv.com/portfolio/",                                             "accelerator"),
    "plug_and_play":        ("plugandplaytechcenter.com",  "https://www.plugandplaytechcenter.com/our-portfolio/",                    "accelerator"),
    "masschallenge":        ("masschallenge.org",          "https://masschallenge.org/companies/",                                    "accelerator"),

    # VC firms (treated as portfolio scrapes)
    "lux_capital":          ("luxcapital.com",             "https://www.luxcapital.com/companies",                                    "vc_portfolio"),

    # Discovery sources
    "betalist":             ("betalist.com",               "https://betalist.com/",                                                   "discovery_aggregator"),
    "wellfound":            ("wellfound.com",              "https://wellfound.com/startups",                                          "discovery_aggregator"),
    "hn_who_is_hiring":     ("news.ycombinator.com",       "https://news.ycombinator.com/from?site=whoishiring",                      "discovery_aggregator"),
    "techcrunch_battlefield": ("techcrunch.com",           "https://techcrunch.com/events/disrupt-startup-battlefield/",              "discovery_aggregator"),

    # International (NA)
    "era_nyc":              ("eranyc.com",                 "https://eranyc.com/portfolio/",                                           "accelerator"),
    "parallel18":           ("parallel18.com",             "https://parallel18.com/companies/",                                       "government_program"),

    # International (LATAM / Africa / EU / APAC)
    "startup_chile":        ("startupchile.org",           "https://startupchile.org/en/portfolio/",                                  "government_program"),
    "ventures_platform":    ("venturesplatform.com",       "https://venturesplatform.com/portfolio/",                                 "vc_portfolio"),
    "hax":                  ("hax.co",                     "https://hax.co/portfolio/",                                               "accelerator"),
    "surge":                ("surgeahead.com",             "https://www.surgeahead.com/portfolio",                                    "accelerator"),
    "brinc":                ("brinc.io",                   "https://www.brinc.io/portfolio",                                          "accelerator"),
    "sparklabs":            ("sparklabs.co.kr",            "https://sparklabs.co.kr/portfolio/",                                      "accelerator"),
    "wayra":                ("wayra.com",                  "https://wayra.com/portfolio/",                                            "accelerator"),
    "nxtp_ventures":        ("nxtp.vc",                    "https://nxtp.vc/portfolio",                                               "vc_portfolio"),
    "allvp":                ("allvp.vc",                   "https://allvp.vc/portfolio",                                              "vc_portfolio"),
    "astrolabs":            ("astrolabs.com",              "https://astrolabs.com/companies/",                                        "accelerator"),
    "grindstone":           ("grindstone.co.za",           "https://www.grindstone.co.za/our-portfolio/",                             "accelerator"),
    "seedstars":            ("seedstars.com",              "https://www.seedstars.com/companies/",                                    "accelerator"),
    "station_f":            ("stationf.co",                "https://stationf.co/companies",                                           "accelerator"),
    "startupbootcamp":      ("startupbootcamp.org",        "https://www.startupbootcamp.org/portfolio/",                              "accelerator"),
    "h_farm":               ("h-farm.com",                 "https://www.h-farm.com/en/portfolio",                                     "accelerator"),
    "sting_stockholm":      ("sting.co",                   "https://sting.co/portfolio/",                                             "accelerator"),
    "rockstart":            ("rockstart.com",              "https://www.rockstart.com/portfolio/",                                    "accelerator"),
    "flat6labs":            ("flat6labs.com",              "https://www.flat6labs.com/our-startups/",                                 "accelerator"),

    # Generic
    "agentic_scrape":       ("agentic_scrape", "agentic_scrape", "other"),  # placeholder, skip below
}

SKIP_SOURCES = {"agentic_scrape", "unknown", None}


def main(dry_run: bool = False) -> None:
    now = datetime.now(timezone.utc)

    with session_scope() as session:
        # Aggregate per-source counts and last activity
        rows = (
            session.query(
                Company.incubator_source,
                func.count(Company.id).label("n"),
                func.max(Company.first_seen_at).label("last_seen"),
            )
            .filter(Company.incubator_source.isnot(None))
            .group_by(Company.incubator_source)
            .all()
        )

        existing_domains = {d for (d,) in session.query(SiteHealth.domain).all()}

        inserted = 0
        updated = 0
        skipped = 0

        for source_enum, n, last_seen in rows:
            source_value = source_enum.value if hasattr(source_enum, "value") else str(source_enum)
            if source_value in SKIP_SOURCES:
                skipped += 1
                continue
            mapping = SOURCE_TO_SITE.get(source_value)
            if mapping is None:
                logger.warning(f"No domain mapping for incubator_source={source_value!r} ({n} companies). Skipping.")
                skipped += 1
                continue

            domain, seed_url, category = mapping
            health = (
                session.query(SiteHealth)
                .filter(SiteHealth.domain == domain)
                .first()
            )

            scraper_name = f"batch:{source_value}"
            tier = "easy"  # batch script is deterministic

            if health is None:
                health = SiteHealth(
                    domain=domain,
                    url=seed_url,
                    difficulty=tier,
                    scraper_name=scraper_name,
                    status="healthy",
                    worker_state="working",
                    category=category,
                    consecutive_failures=0,
                    last_success_at=last_seen or now,
                    last_record_count=n,
                    total_runs=1,
                    total_successes=1,
                    next_scrape_at=now,
                    created_at=now,
                )
                if not dry_run:
                    session.add(health)
                inserted += 1
                logger.info(f"INSERT {domain:35s} ({n:>5} records, source={source_value}, cat={category})")
            else:
                health.worker_state = "working"
                health.status = "healthy"
                if not health.category:
                    health.category = category
                if health.last_record_count is None or n > (health.last_record_count or 0):
                    health.last_record_count = n
                if last_seen and (health.last_success_at is None or last_seen > health.last_success_at):
                    health.last_success_at = last_seen
                if not health.url:
                    health.url = seed_url
                if not health.scraper_name:
                    health.scraper_name = scraper_name
                health.total_successes = max(health.total_successes or 0, 1)
                health.total_runs = max(health.total_runs or 0, 1)
                updated += 1
                logger.info(f"UPDATE {domain:35s} ({n:>5} records, source={source_value}, cat={category})")

        if dry_run:
            session.rollback()
            logger.info("[dry-run] rolled back")
        logger.info(f"Done: inserted={inserted} updated={updated} skipped={skipped} total_sources={len(rows)}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    main(dry_run=args.dry_run)
