"""
Normalize country values in the companies table:
  - Strip "; Remote" suffix (e.g. "USA; Remote" -> "United States")
  - Expand abbreviations: US/USA -> United States, UK -> United Kingdom
  - Null out meaningless values: "Remote", "Rest of the world"
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.db.connection import get_engine
from sqlalchemy import text

ALIASES = {
    "US": "United States",
    "USA": "United States",
    "UK": "United Kingdom",
}

NULL_VALUES = {"Remote", "Rest of the world"}


def normalize(raw: str) -> str | None:
    country = raw.split(";")[0].strip()
    if country in NULL_VALUES:
        return None
    return ALIASES.get(country, country)


def main(dry_run: bool = False):
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT country FROM companies WHERE country IS NOT NULL")
        ).fetchall()

    mapping: dict[str, str | None] = {}
    for (raw,) in rows:
        normalized = normalize(raw)
        if normalized != raw:
            mapping[raw] = normalized

    if not mapping:
        print("Nothing to normalize.")
        return

    print(f"{'DRY RUN — ' if dry_run else ''}{len(mapping)} values to update:\n")
    for old, new in sorted(mapping.items()):
        print(f"  {old!r:40s} -> {new!r}")

    if dry_run:
        return

    with engine.begin() as conn:
        for old, new in mapping.items():
            if new is None:
                conn.execute(
                    text("UPDATE companies SET country = NULL WHERE country = :old"),
                    {"old": old},
                )
            else:
                conn.execute(
                    text("UPDATE companies SET country = :new WHERE country = :old"),
                    {"new": new, "old": old},
                )

    print(f"\nDone. {len(mapping)} distinct values updated.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
