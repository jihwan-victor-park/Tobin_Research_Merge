"""
Sync the `category` field in site_health from the YAML scrape instruction files.
Each YAML file is named <domain>.yaml and contains a `category` key.
"""
from __future__ import annotations

import os
import sys
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.db.connection import get_engine
from sqlalchemy import text

INSTR_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "scrape_instructions")


def main(dry_run: bool = False):
    engine = get_engine()

    # Load all YAML categories
    yaml_cats: dict[str, str] = {}
    for fname in os.listdir(INSTR_DIR):
        if not fname.endswith(".yaml"):
            continue
        domain = fname[:-5]
        with open(os.path.join(INSTR_DIR, fname)) as f:
            try:
                d = yaml.safe_load(f)
            except Exception:
                continue
        if d and d.get("category"):
            yaml_cats[domain] = d["category"]

    # Find site_health rows that need updating
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT domain, category FROM site_health")
        ).fetchall()

    updates: list[tuple[str, str]] = []
    for domain, current_cat in rows:
        new_cat = yaml_cats.get(domain)
        if new_cat and new_cat != current_cat:
            updates.append((domain, new_cat))

    if not updates:
        print("Nothing to update.")
        return

    print(f"{'DRY RUN — ' if dry_run else ''}{len(updates)} sites to categorize:\n")
    for domain, cat in sorted(updates):
        print(f"  {domain:45s} -> {cat}")

    if dry_run:
        return

    with engine.begin() as conn:
        for domain, cat in updates:
            conn.execute(
                text("UPDATE site_health SET category = :cat WHERE domain = :domain"),
                {"cat": cat, "domain": domain},
            )

    print(f"\nDone. {len(updates)} sites updated.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
