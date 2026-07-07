#!/usr/bin/env python3
"""
TLD → Country Inference
=======================
Tags companies with country=NULL by inferring country from their domain TLD.

Only uses high-confidence country-specific TLDs (e.g. .de, .co.uk, .fr).
Generic TLDs used as branding (.ai, .io, .co, .eu, .me, .sh) are skipped.

Usage:
    python scripts/infer_country_from_tld.py --dry-run
    python scripts/infer_country_from_tld.py
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

from backend.db.connection import session_scope
from backend.db.models import Company, LocationSource

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("infer_country_tld")

# High-confidence country TLDs only.
# Excluded (used as branding, not geographic): .ai .io .co .eu .me .sh .cc .app .dev
TLD_TO_COUNTRY = {
    # Two-part ccTLDs
    ".co.uk":  "GB",
    ".org.uk": "GB",
    ".me.uk":  "GB",
    ".com.au": "AU",
    ".net.au": "AU",
    ".org.au": "AU",
    ".co.jp":  "JP",
    ".com.br": "BR",
    ".net.br": "BR",
    ".com.sg": "SG",
    ".co.nz":  "NZ",
    ".co.kr":  "KR",
    ".co.in":  "IN",
    ".co.il":  "IL",
    ".co.za":  "ZA",
    # Single ccTLDs
    ".de": "DE",
    ".fr": "FR",
    ".nl": "NL",
    ".se": "SE",
    ".no": "NO",
    ".dk": "DK",
    ".fi": "FI",
    ".be": "BE",
    ".at": "AT",
    ".ch": "CH",
    ".it": "IT",
    ".es": "ES",
    ".pt": "PT",
    ".pl": "PL",
    ".cz": "CZ",
    ".hu": "HU",
    ".ro": "RO",
    ".gr": "GR",
    ".ie": "IE",
    ".il": "IL",
    ".kr": "KR",
    ".jp": "JP",
    ".cn": "CN",
    ".in": "IN",
    ".sg": "SG",
    ".au": "AU",
    ".nz": "NZ",
    ".za": "ZA",
    ".br": "BR",
    ".mx": "MX",
    ".ar": "AR",
    ".cl": "CL",
    ".ca": "CA",
    ".ru": "RU",
    ".ua": "UA",
    ".tr": "TR",
    ".ae": "AE",
    ".sa": "SA",
    ".ng": "NG",
    ".ke": "KE",
    ".eg": "EG",
    ".pk": "PK",
    ".bd": "BD",
    ".id": "ID",
    ".my": "MY",
    ".th": "TH",
    ".vn": "VN",
    ".ph": "PH",
    ".tw": "TW",
    ".hk": "HK",
    ".ee": "EE",
    ".lv": "LV",
    ".lt": "LT",
}


def extract_tld(domain: str) -> str | None:
    """Return the matching TLD key from TLD_TO_COUNTRY, longest match first."""
    domain = domain.lower().strip()
    # Try two-part TLDs first (.co.uk before .uk)
    for tld in sorted(TLD_TO_COUNTRY, key=len, reverse=True):
        if domain.endswith(tld):
            return tld
    return None


def main():
    parser = argparse.ArgumentParser(description="Infer country from domain TLD for null-country companies")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    stats: dict[str, int] = {}

    # Load candidates into memory first (single fast query)
    with session_scope() as db:
        candidates = (
            db.query(Company.id, Company.domain, Company.location_source)
            .filter(Company.country == None, Company.domain != None)
            .all()
        )
    logger.info(f"Checking {len(candidates):,} companies with country=NULL and a domain")

    # Compute updates in memory
    updates: list[dict] = []
    skipped_no_match = 0
    for row in candidates:
        tld = extract_tld(row.domain)
        if not tld:
            skipped_no_match += 1
            continue
        country = TLD_TO_COUNTRY[tld]
        stats[country] = stats.get(country, 0) + 1
        updates.append({
            "id": row.id,
            "country": country,
            "location_source": (row.location_source or LocationSource.unknown).value,
        })

    updated = len(updates)

    if not args.dry_run:
        BATCH = 200
        for i in range(0, len(updates), BATCH):
            batch = updates[i: i + BATCH]
            with session_scope() as db:
                for u in batch:
                    db.query(Company).filter(Company.id == u["id"]).update(
                        {"country": u["country"], "updated_at": now},
                        synchronize_session=False,
                    )
            logger.info(f"  Committed batch {i // BATCH + 1}/{(len(updates) + BATCH - 1) // BATCH}")

        logger.info("=" * 55)
        logger.info(f"TLD Country Inference {'(dry run) ' if args.dry_run else ''}Complete")
        logger.info(f"  Would tag / Tagged: {updated:,}")
        logger.info(f"  No TLD match:       {skipped_no_match:,}")
        logger.info("")
        logger.info("  By country:")
        for country, count in sorted(stats.items(), key=lambda x: -x[1]):
            logger.info(f"    {country}: {count:,}")
        logger.info("=" * 55)


if __name__ == "__main__":
    main()
