"""
Scraper Registry — maps domains to their scraper class and difficulty tier.

Sites not in the registry are automatically classified as "hard" and
routed to the agentic engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Type

from backend.scrapers.base import BaseScraper

# Import all easy scrapers
from backend.scrapers.easy.alchemist_scraper import AlchemistScraper
from backend.scrapers.easy.antler_scraper import AntlerScraper
from backend.scrapers.easy.capitalfactory_scraper import CapitalFactoryScraper
from backend.scrapers.easy.columbia_scraper import ColumbiaScraper
from backend.scrapers.easy.eranyc_scraper import ERANYCScraper
from backend.scrapers.easy.crunchbase_import import CrunchbaseImportScraper
from backend.scrapers.easy.ef_scraper import EFScraper
from backend.scrapers.easy.harvard_scraper import HarvardScraper
from backend.scrapers.easy.mit_deltav_scraper import MitDeltavScraper
from backend.scrapers.easy.princeton_scraper import PrincetonScraper
from backend.scrapers.easy.rice_owlspark_scraper import RiceOwlsparkScraper
from backend.scrapers.easy.seedcamp_scraper import SeedcampScraper
from backend.scrapers.easy.skydeck_scraper import SkydeckScraper
from backend.scrapers.easy.startx_scraper import StartxScraper
from backend.scrapers.easy.techstars_scraper import TechstarsScraper
from backend.scrapers.easy.villageglobal_scraper import VillageGlobalScraper
from backend.scrapers.easy.yc_scraper import YCScraper


@dataclass
class ScraperEntry:
    cls: Type[BaseScraper]
    difficulty: str  # "easy" or "hard"
    pattern: str     # "api_direct", "bs_single", "bs_paginated", "wp_ajax", "claude_extraction", "parquet", "agentic"


# ── Registry ──────────────────────────────────────────────────────────────

SCRAPER_REGISTRY: Dict[str, ScraperEntry] = {
    # API Direct (Algolia / Typesense)
    "ycombinator.com": ScraperEntry(cls=YCScraper, difficulty="easy", pattern="api_direct"),
    "techstars.com": ScraperEntry(cls=TechstarsScraper, difficulty="easy", pattern="api_direct"),

    # BeautifulSoup single-page
    "seedcamp.com": ScraperEntry(cls=SeedcampScraper, difficulty="easy", pattern="bs_single"),

    # BeautifulSoup paginated
    "antler.co": ScraperEntry(cls=AntlerScraper, difficulty="easy", pattern="bs_paginated"),
    "innovationlabs.harvard.edu": ScraperEntry(cls=HarvardScraper, difficulty="easy", pattern="bs_paginated"),
    "web.startx.com": ScraperEntry(cls=StartxScraper, difficulty="easy", pattern="bs_paginated"),
    "kellercenter.princeton.edu": ScraperEntry(cls=PrincetonScraper, difficulty="easy", pattern="bs_paginated"),
    "alliance.rice.edu": ScraperEntry(cls=RiceOwlsparkScraper, difficulty="easy", pattern="bs_single"),

    # WordPress AJAX
    "joinef.com": ScraperEntry(cls=EFScraper, difficulty="easy", pattern="wp_ajax"),
    "skydeck.berkeley.edu": ScraperEntry(cls=SkydeckScraper, difficulty="easy", pattern="wp_ajax"),

    # REST API
    "startups.columbia.edu": ScraperEntry(cls=ColumbiaScraper, difficulty="easy", pattern="api_direct"),

    # Claude extraction
    "entrepreneurship.mit.edu": ScraperEntry(cls=MitDeltavScraper, difficulty="easy", pattern="claude_extraction"),

    # Bulk import (parquet)
    "crunchbase.com": ScraperEntry(cls=CrunchbaseImportScraper, difficulty="easy", pattern="parquet"),

    # REST API (additional)
    "alchemistaccelerator.com": ScraperEntry(cls=AlchemistScraper, difficulty="easy", pattern="api_direct"),

    # BeautifulSoup single-page (additional)
    "capitalfactory.com": ScraperEntry(cls=CapitalFactoryScraper, difficulty="easy", pattern="bs_single"),
    "villageglobal.com": ScraperEntry(cls=VillageGlobalScraper, difficulty="easy", pattern="bs_single"),
    "eranyc.com": ScraperEntry(cls=ERANYCScraper, difficulty="easy", pattern="bs_single"),
}


def get_scraper(domain: str) -> Optional[BaseScraper]:
    """Look up and instantiate a registered easy scraper. Returns None for unknown domains."""
    entry = SCRAPER_REGISTRY.get(domain)
    if entry is None:
        return None
    return entry.cls()


def classify_difficulty(domain: str) -> str:
    """Return 'easy' if a registered scraper exists, else 'hard'."""
    entry = SCRAPER_REGISTRY.get(domain)
    return entry.difficulty if entry else "hard"


def list_easy_scrapers() -> list[str]:
    """Return list of all registered easy-tier domains."""
    return [domain for domain, entry in SCRAPER_REGISTRY.items() if entry.difficulty == "easy"]


def list_all_entries() -> Dict[str, ScraperEntry]:
    """Return the full registry."""
    return SCRAPER_REGISTRY.copy()
