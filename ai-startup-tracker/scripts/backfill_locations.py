#!/usr/bin/env python3
"""
Backfill Locations for Existing Companies
==========================================
Fetches location data from GitHub API for companies that have linked
GitHub repos but no location yet.

Usage:
    python scripts/backfill_locations.py [--dry-run] [--limit 500]
"""
import argparse
import logging
import os
import sys
import time
from typing import Dict, Optional

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.db.connection import session_scope
from backend.db.models import Company, GithubSignal, LocationSource

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_locations")

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")


def github_headers():
    h = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h


COUNTRY_ALIASES = {
    "usa": "US", "us": "US", "united states": "US", "united states of america": "US",
    "uk": "GB", "united kingdom": "GB", "england": "GB", "scotland": "GB", "wales": "GB",
    "germany": "DE", "deutschland": "DE", "france": "FR", "india": "IN", "china": "CN",
    "canada": "CA", "japan": "JP", "south korea": "KR", "korea": "KR",
    "australia": "AU", "brazil": "BR", "israel": "IL",
    "singapore": "SG", "netherlands": "NL", "holland": "NL",
    "sweden": "SE", "switzerland": "CH", "spain": "ES",
    "italy": "IT", "ireland": "IE", "portugal": "PT",
    "poland": "PL", "austria": "AT", "belgium": "BE",
    "norway": "NO", "finland": "FI", "denmark": "DK",
    "czech republic": "CZ", "czechia": "CZ",
    "new zealand": "NZ", "mexico": "MX",
    "indonesia": "ID", "thailand": "TH", "vietnam": "VN",
    "taiwan": "TW", "hong kong": "HK", "uae": "AE",
    "united arab emirates": "AE", "russia": "RU",
    "turkey": "TR", "ukraine": "UA", "romania": "RO",
    "argentina": "AR", "colombia": "CO", "chile": "CL",
    "nigeria": "NG", "south africa": "ZA", "kenya": "KE",
    "egypt": "EG", "pakistan": "PK", "bangladesh": "BD",
    "philippines": "PH", "malaysia": "MY", "estonia": "EE",
    "luxembourg": "LU", "hungary": "HU", "greece": "GR",
}

US_STATES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
}


def parse_location(location_str: Optional[str]) -> Dict[str, Optional[str]]:
    """Parse a free-form location string into country and city."""
    if not location_str:
        return {"country": None, "city": None}

    location_str = location_str.strip()
    parts = [p.strip() for p in location_str.split(",")]

    if len(parts) >= 2:
        city = parts[0]
        last_part = parts[-1].strip().lower()

        if last_part in US_STATES or last_part.replace(".", "") in US_STATES:
            return {"country": "US", "city": city}
        if last_part in COUNTRY_ALIASES:
            return {"country": COUNTRY_ALIASES[last_part], "city": city}
        return {"country": last_part.upper() if len(last_part) == 2 else parts[-1].strip(), "city": city}

    single = location_str.lower().strip()
    if single in COUNTRY_ALIASES:
        return {"country": COUNTRY_ALIASES[single], "city": None}

    return {"country": None, "city": location_str.strip()}


def fetch_github_location(login: str, owner_type: str) -> Optional[str]:
    """Fetch location from GitHub org or user profile."""
    if owner_type == "Organization":
        url = f"{GITHUB_API}/orgs/{login}"
    else:
        url = f"{GITHUB_API}/users/{login}"

    resp = requests.get(url, headers=github_headers())
    if resp.status_code == 200:
        return resp.json().get("location") or None
    if resp.status_code == 403:
        # Rate limited — check headers
        remaining = int(resp.headers.get("X-RateLimit-Remaining", "0"))
        if remaining == 0:
            reset_time = int(resp.headers.get("X-RateLimit-Reset", "0"))
            wait = max(reset_time - int(time.time()), 1)
            logger.warning(f"Rate limited. Waiting {wait}s...")
            time.sleep(wait + 1)
            return fetch_github_location(login, owner_type)
    return None


def backfill(dry_run: bool = False, limit: int = 0):
    """Fetch locations from GitHub for companies missing location data."""
    stats = {"checked": 0, "updated": 0, "no_location": 0, "already_set": 0}

    with session_scope() as session:
        # Find companies with no country that have at least one GitHub signal
        query = (
            session.query(Company)
            .filter(Company.country.is_(None))
            .join(GithubSignal, GithubSignal.company_id == Company.id)
        )
        # Get distinct companies (a company may have multiple repos)
        companies = query.distinct().all()

        total = len(companies)
        if limit > 0:
            companies = companies[:limit]

        logger.info(f"Found {total} companies without location data (processing {len(companies)})")

        for i, company in enumerate(companies, start=1):
            # Get the first GitHub signal for this company to find owner login
            gh_signal = (
                session.query(GithubSignal)
                .filter(GithubSignal.company_id == company.id)
                .first()
            )
            if not gh_signal or not gh_signal.owner_login:
                continue

            owner_login = gh_signal.owner_login
            owner_type = gh_signal.owner_type or "User"

            stats["checked"] += 1

            if dry_run:
                logger.info(f"  [{i}/{len(companies)}] Would fetch location for {owner_login} ({owner_type})")
                continue

            location_raw = fetch_github_location(owner_login, owner_type)

            if location_raw:
                parsed = parse_location(location_raw)
                if parsed["country"]:
                    company.country = parsed["country"]
                    company.city = parsed["city"]
                    company.location_source = LocationSource.github
                    stats["updated"] += 1
                    logger.info(f"  [{i}/{len(companies)}] {company.name}: {location_raw} -> {parsed['country']}, {parsed['city']}")
                else:
                    stats["no_location"] += 1
            else:
                stats["no_location"] += 1

            # Respect rate limits: ~0.5s between requests
            time.sleep(0.5)

            if i % 100 == 0:
                session.flush()
                logger.info(f"  Progress: {i}/{len(companies)} checked, {stats['updated']} updated")

    logger.info("=" * 60)
    logger.info("Backfill Complete!")
    logger.info(f"  Checked:    {stats['checked']}")
    logger.info(f"  Updated:    {stats['updated']}")
    logger.info(f"  No location:{stats['no_location']}")
    logger.info("=" * 60)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill company locations from GitHub profiles")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    parser.add_argument("--limit", type=int, default=0, help="Max companies to process (0 = all)")
    args = parser.parse_args()

    if not GITHUB_TOKEN:
        logger.warning("No GITHUB_TOKEN set — rate limits will be very low (60/hr)")

    backfill(dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()
