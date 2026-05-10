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
from backend.scrapers.easy.crunchbase_import import CrunchbaseImportScraper
from backend.scrapers.easy.ef_scraper import EFScraper
from backend.scrapers.easy.eranyc_scraper import ERANYCScraper
from backend.scrapers.easy.harvard_scraper import HarvardScraper
from backend.scrapers.easy.huggingface_scraper import HuggingFaceScraper
from backend.scrapers.easy.mit_deltav_scraper import MitDeltavScraper
from backend.scrapers.easy.princeton_scraper import PrincetonScraper
from backend.scrapers.easy.rice_owlspark_scraper import RiceOwlsparkScraper
from backend.scrapers.easy.seedcamp_scraper import SeedcampScraper
from backend.scrapers.easy.skydeck_scraper import SkydeckScraper
from backend.scrapers.easy.startx_scraper import StartxScraper
from backend.scrapers.easy.techstars_scraper import TechstarsScraper
from backend.scrapers.easy.villageglobal_scraper import VillageGlobalScraper
from backend.scrapers.easy.yc_scraper import YCScraper
from backend.scrapers.easy.sequoia_scraper import SequoiaScraper
from backend.scrapers.easy.greylock_scraper import GreylockScraper
from backend.scrapers.easy.balderton_scraper import BaldertonScraper
from backend.scrapers.easy.foundersfund_scraper import FoundersFundScraper
from backend.scrapers.easy.usv_scraper import USVScraper
from backend.scrapers.easy.bvp_scraper import BVPScraper
from backend.scrapers.easy.generalcatalyst_scraper import GeneralCatalystScraper


@dataclass
class ScraperEntry:
    cls: Type[BaseScraper]
    difficulty: str  # "easy" or "hard"
    pattern: str     # "api_direct", "bs_single", "bs_paginated", "wp_ajax", "claude_extraction", "parquet", "agentic"
    # Inventory bucket — see SiteHealth.category. One of:
    # university_incubator | accelerator | vc_portfolio
    # | discovery_aggregator | government_program | other
    category: str = "other"


# ── Registry ──────────────────────────────────────────────────────────────

SCRAPER_REGISTRY: Dict[str, ScraperEntry] = {
    # API Direct (Algolia / Typesense / REST)
    "ycombinator.com": ScraperEntry(cls=YCScraper, difficulty="easy", pattern="api_direct", category="accelerator"),
    "techstars.com": ScraperEntry(cls=TechstarsScraper, difficulty="easy", pattern="api_direct", category="accelerator"),
    "alchemistaccelerator.com": ScraperEntry(cls=AlchemistScraper, difficulty="easy", pattern="api_direct", category="accelerator"),

    # BeautifulSoup single-page
    "seedcamp.com": ScraperEntry(cls=SeedcampScraper, difficulty="easy", pattern="bs_single", category="accelerator"),
    "capitalfactory.com": ScraperEntry(cls=CapitalFactoryScraper, difficulty="easy", pattern="bs_single", category="accelerator"),
    "eranyc.com": ScraperEntry(cls=ERANYCScraper, difficulty="easy", pattern="bs_single", category="accelerator"),
    "villageglobal.com": ScraperEntry(cls=VillageGlobalScraper, difficulty="easy", pattern="bs_single", category="vc_portfolio"),

    # BeautifulSoup paginated
    "antler.co": ScraperEntry(cls=AntlerScraper, difficulty="easy", pattern="bs_paginated", category="vc_portfolio"),
    "innovationlabs.harvard.edu": ScraperEntry(cls=HarvardScraper, difficulty="easy", pattern="bs_paginated", category="university_incubator"),
    "web.startx.com": ScraperEntry(cls=StartxScraper, difficulty="easy", pattern="bs_paginated", category="university_incubator"),
    "kellercenter.princeton.edu": ScraperEntry(cls=PrincetonScraper, difficulty="easy", pattern="bs_paginated", category="university_incubator"),
    "alliance.rice.edu": ScraperEntry(cls=RiceOwlsparkScraper, difficulty="easy", pattern="bs_single", category="university_incubator"),

    # WordPress AJAX
    "joinef.com": ScraperEntry(cls=EFScraper, difficulty="easy", pattern="wp_ajax", category="accelerator"),
    "skydeck.berkeley.edu": ScraperEntry(cls=SkydeckScraper, difficulty="easy", pattern="wp_ajax", category="university_incubator"),

    # REST API
    "startups.columbia.edu": ScraperEntry(cls=ColumbiaScraper, difficulty="easy", pattern="api_direct", category="university_incubator"),

    # Claude extraction
    "entrepreneurship.mit.edu": ScraperEntry(cls=MitDeltavScraper, difficulty="easy", pattern="claude_extraction", category="university_incubator"),

    # Bulk import (parquet)
    "crunchbase.com": ScraperEntry(cls=CrunchbaseImportScraper, difficulty="easy", pattern="parquet", category="discovery_aggregator"),

    # VC portfolios — WordPress REST API (paginated)
    "sequoiacap.com": ScraperEntry(cls=SequoiaScraper, difficulty="easy", pattern="api_direct", category="vc_portfolio"),
    "greylock.com": ScraperEntry(cls=GreylockScraper, difficulty="easy", pattern="api_direct", category="vc_portfolio"),

    # VC portfolios — Playwright (JS-rendered, load-more pagination)
    "balderton.com": ScraperEntry(cls=BaldertonScraper, difficulty="easy", pattern="playwright", category="vc_portfolio"),

    # VC portfolios — WordPress REST API
    "foundersfund.com": ScraperEntry(cls=FoundersFundScraper, difficulty="easy", pattern="api_direct", category="vc_portfolio"),

    # VC portfolios — BeautifulSoup single-page
    "usv.com": ScraperEntry(cls=USVScraper, difficulty="easy", pattern="bs_single", category="vc_portfolio"),
    "bvp.com": ScraperEntry(cls=BVPScraper, difficulty="easy", pattern="bs_single", category="vc_portfolio"),
    "generalcatalyst.com": ScraperEntry(cls=GeneralCatalystScraper, difficulty="easy", pattern="bs_single", category="vc_portfolio"),

    # AI-native discovery aggregator
    "huggingface.co": ScraperEntry(cls=HuggingFaceScraper, difficulty="easy", pattern="bs_paginated", category="discovery_aggregator"),
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
