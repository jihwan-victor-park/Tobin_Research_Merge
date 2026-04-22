"""
Crunchbase Bulk Import — filters organizations.parquet and returns matching
companies as ScrapedCompany objects.

Ported from Alastair branch to BaseScraper class.

Filters applied (in order):
  1. roles contains 'company'
  2. status in ['operating', 'ipo']
  3. founded_on year >= 2015
  4. name is not null
  5. short_description OR total_funding_usd not null

NOTE: This scraper reads from local parquet files, not a URL. The parquet
paths are configured via environment variables CB_ORGANIZATIONS_PATH and
CB_CATEGORIES_PATH (see .env.example).
"""

import logging
import os
import re
from pathlib import Path
from typing import List

import pandas as pd

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper
from backend.utils.denylist import is_denylisted

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
BATCH_SIZE = 10_000

AI_KEYWORDS_FOR_REGEX = [
    "artificial intelligence", "machine learning", "large language model", "llm",
    "generative ai", "generative", "gpt", "neural network", "deep learning", "nlp",
    "natural language processing", "computer vision", "data science", "autonomous",
    "robotics", "predictive", "recommendation engine",
]
AI_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(kw) for kw in AI_KEYWORDS_FOR_REGEX) + r")\b",
    re.IGNORECASE,
)


class CrunchbaseImportScraper(BaseScraper):
    name = "crunchbase"
    domain = "crunchbase.com"
    difficulty = "easy"
    source_url = "crunchbase_parquet"

    def scrape(self) -> List[ScrapedCompany]:
        orgs_path = os.environ.get("CB_ORGANIZATIONS_PATH", str(DATA_DIR / "organizations.parquet"))
        if not Path(orgs_path).exists():
            raise FileNotFoundError(f"Crunchbase parquet not found: {orgs_path}")

        logger.info(f"Loading {orgs_path} ...")
        df = pd.read_parquet(orgs_path)
        logger.info(f"Total rows: {len(df):,}")

        # Apply filters
        df = df[df["roles"].str.contains("company", na=False)]
        # 'ipo' excluded — public companies aren't emerging startups
        df = df[df["status"] == "operating"]
        df["founded_year"] = pd.to_datetime(df["founded_on"], errors="coerce").dt.year
        df = df[df["founded_year"] >= 2015]
        df = df[df["name"].notna()]
        df = df[df["short_description"].notna() | df["total_funding_usd"].notna()]

        # Cap funding at $500M — beyond that it's a mega-cap, not an emerging startup.
        # Keep rows with NULL funding (unknown) so early-stage companies aren't dropped.
        if "total_funding_usd" in df.columns:
            funding = pd.to_numeric(df["total_funding_usd"], errors="coerce")
            df = df[funding.isna() | (funding < 500_000_000)]
        logger.info(f"After filters: {len(df):,}")

        # Vectorized AI detection
        text = (
            df["short_description"].fillna("") + " " +
            df["category_list"].fillna("") + " " +
            df["category_groups_list"].fillna("")
        )
        df["uses_ai"] = text.str.contains(AI_PATTERN, regex=True)

        # Convert to ScrapedCompany
        results = []
        dropped_big_tech = 0
        for row in df.itertuples(index=False):
            name = row.name
            if not name or pd.isna(name):
                continue

            homepage = getattr(row, "homepage_url", None)
            if is_denylisted(str(name), str(homepage) if homepage and not pd.isna(homepage) else None):
                dropped_big_tech += 1
                continue

            description = None
            if hasattr(row, "short_description") and not pd.isna(row.short_description):
                description = str(row.short_description)

            website = None
            if hasattr(row, "homepage_url") and not pd.isna(row.homepage_url):
                website = str(row.homepage_url)

            founded_year = None
            if hasattr(row, "founded_year") and not pd.isna(row.founded_year):
                founded_year = int(row.founded_year)

            # Location
            country = None
            city = None
            if hasattr(row, "country_code") and not pd.isna(row.country_code):
                country = str(row.country_code)
            if hasattr(row, "city") and not pd.isna(row.city):
                city = str(row.city)

            # Tags
            industry = None
            if hasattr(row, "category_list") and not pd.isna(row.category_list):
                industry = str(row.category_list)

            results.append(ScrapedCompany(
                name=str(name),
                description=description,
                website_url=website,
                country=country,
                city=city,
                industry=industry,
                is_ai_startup=bool(row.uses_ai),
                source_url=self.source_url,
            ))

        logger.info(
            f"Total: {len(results):,} companies "
            f"({sum(1 for r in results if r.is_ai_startup):,} AI, "
            f"{dropped_big_tech:,} big-tech dropped)"
        )
        return results
