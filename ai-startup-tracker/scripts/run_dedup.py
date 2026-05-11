#!/usr/bin/env python3
"""
Cross-source deduplication for the companies table.

Usage:
    python scripts/run_dedup.py              # show top 20 domain duplicates
    python scripts/run_dedup.py --limit 50   # show top 50
    python scripts/run_dedup.py --merge      # dry run — show what would be merged
    python scripts/run_dedup.py --merge --confirm  # execute domain-duplicate merges
"""
import argparse
import logging
import os
import sys
from typing import List

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dedup")

from sqlalchemy import text
from backend.db.connection import session_scope
from backend.db.models import Company, IncubatorSignal
from backend.utils.normalize import normalize_company_name, fuzzy_name_match


# ── Detection ─────────────────────────────────────────────────────────────────

def find_domain_duplicates(session, limit: int) -> List[dict]:
    """Return groups of companies that share the same non-null domain."""
    rows = session.execute(text("""
        SELECT
            domain,
            COUNT(*) AS cnt,
            array_agg(id              ORDER BY first_seen_at ASC) AS ids,
            array_agg(name            ORDER BY first_seen_at ASC) AS names,
            array_agg(COALESCE(ai_score::text, 'NULL')
                                      ORDER BY first_seen_at ASC) AS ai_scores,
            array_agg(COALESCE(description, '')
                                      ORDER BY first_seen_at ASC) AS descs
        FROM companies
        WHERE domain IS NOT NULL AND domain != ''
        GROUP BY domain
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT :limit
    """), {"limit": limit}).fetchall()

    results = []
    for row in rows:
        signal_counts = {
            cid: session.query(IncubatorSignal)
                        .filter(IncubatorSignal.company_id == cid).count()
            for cid in row.ids
        }
        results.append({
            "type": "DOMAIN",
            "key": row.domain,
            "count": row.cnt,
            "companies": [
                {
                    "id": cid,
                    "name": name,
                    "ai_score": score,
                    "signals": signal_counts.get(cid, 0),
                    "description": desc[:80] + "..." if len(desc) > 80 else desc,
                }
                for cid, name, score, desc in zip(row.ids, row.names, row.ai_scores, row.descs)
            ],
        })
    return results


def find_name_duplicates(session, limit: int, threshold: float = 0.92) -> List[dict]:
    """Return pairs of no-domain companies with similar names (read-only, never auto-merged)."""
    rows = session.execute(text("""
        SELECT id, name, ai_score, description
        FROM companies
        WHERE (domain IS NULL OR domain = '')
          AND name IS NOT NULL AND name != ''
        ORDER BY first_seen_at ASC
    """)).fetchall()

    if not rows:
        return []

    indexed = []
    for row in rows:
        norm = normalize_company_name(row.name or "")
        if norm:
            indexed.append({
                "id": row.id,
                "name": row.name,
                "norm": norm,
                "ai_score": str(row.ai_score) if row.ai_score is not None else "NULL",
                "description": (row.description or "")[:80],
            })

    seen_pairs: set = set()
    groups = []
    for i, a in enumerate(indexed):
        for b in indexed[i + 1:]:
            pair_key = (min(a["id"], b["id"]), max(a["id"], b["id"]))
            if pair_key in seen_pairs:
                continue
            score = fuzzy_name_match(a["name"], b["name"])
            if score >= threshold:
                seen_pairs.add(pair_key)
                groups.append({
                    "type": "NAME",
                    "key": f'"{a["name"]}" / "{b["name"]}"',
                    "similarity": round(score, 3),
                    "count": 2,
                    "companies": [a, b],
                })

    groups.sort(key=lambda x: x["similarity"], reverse=True)
    return groups[:limit]


def _pick_canonical(companies: List[dict]) -> tuple[int, List[int]]:
    """Return (keep_id, [drop_ids]) — keep the one with most signals, then highest ai_score."""
    keep = max(companies, key=lambda c: (
        c["signals"],
        float(c["ai_score"]) if c["ai_score"] != "NULL" else 0.0,
    ))
    drop_ids = [c["id"] for c in companies if c["id"] != keep["id"]]
    return keep["id"], drop_ids


# ── Merge logic ───────────────────────────────────────────────────────────────

def _merge_one(session, keep_id: int, drop_id: int, dry_run: bool) -> dict:
    """
    Merge drop_id into keep_id.

    Uses raw SQL for child-table reassignment to avoid ORM cascade-delete
    running before we can move the rows across.
    """
    stats = {"reassigned": 0, "skipped": 0, "fields_filled": 0}

    if not dry_run:
        # ── incubator_signals ──────────────────────────────────────────
        # Reassign rows that don't conflict with canonical's (source, company_name_raw)
        r = session.execute(text("""
            UPDATE incubator_signals
            SET company_id = :keep
            WHERE company_id = :drop
              AND (source::text, company_name_raw) NOT IN (
                  SELECT source::text, company_name_raw
                  FROM incubator_signals
                  WHERE company_id = :keep
              )
        """), {"keep": keep_id, "drop": drop_id})
        stats["reassigned"] += r.rowcount

        # Delete any remaining signals on drop (they were duplicates of canonical's)
        r2 = session.execute(text(
            "DELETE FROM incubator_signals WHERE company_id = :drop"
        ), {"drop": drop_id})
        stats["skipped"] += r2.rowcount

        # ── github_signals ─────────────────────────────────────────────
        r = session.execute(text(
            "UPDATE github_signals SET company_id = :keep WHERE company_id = :drop"
        ), {"keep": keep_id, "drop": drop_id})
        stats["reassigned"] += r.rowcount

        # ── funding_signals ────────────────────────────────────────────
        r = session.execute(text(
            "UPDATE funding_signals SET company_id = :keep WHERE company_id = :drop"
        ), {"keep": keep_id, "drop": drop_id})
        stats["reassigned"] += r.rowcount

        # ── source_matches ─────────────────────────────────────────────
        r = session.execute(text(
            "UPDATE source_matches SET company_id = :keep WHERE company_id = :drop"
        ), {"keep": keep_id, "drop": drop_id})
        stats["reassigned"] += r.rowcount

        # ── Merge scalar fields onto canonical ─────────────────────────
        keep = session.get(Company, keep_id)
        drop = session.get(Company, drop_id)

        if keep and drop:
            FILLABLE = [
                "description", "country", "city", "founded_year", "team_size",
                "stage", "operating_status", "incubator_source",
            ]
            for field in FILLABLE:
                if getattr(keep, field) is None and getattr(drop, field) is not None:
                    setattr(keep, field, getattr(drop, field))
                    stats["fields_filled"] += 1

            # Take the better ai_score
            if drop.ai_score is not None:
                if keep.ai_score is None or drop.ai_score > keep.ai_score:
                    keep.ai_score = drop.ai_score

            # Union ai_tags
            if drop.ai_tags:
                keep.ai_tags = list(set(keep.ai_tags or []) | set(drop.ai_tags))

            # Earliest first_seen_at, latest last_seen_at
            if drop.first_seen_at and (
                keep.first_seen_at is None or drop.first_seen_at < keep.first_seen_at
            ):
                keep.first_seen_at = drop.first_seen_at
            if drop.last_seen_at and (
                keep.last_seen_at is None or drop.last_seen_at > keep.last_seen_at
            ):
                keep.last_seen_at = drop.last_seen_at

            session.flush()
            session.delete(drop)

    return stats


def merge_domain_duplicates(session, domain_dups: List[dict], dry_run: bool) -> dict:
    totals = {"groups": 0, "companies_removed": 0, "reassigned": 0, "skipped": 0, "fields_filled": 0}

    for group in domain_dups:
        keep_id, drop_ids = _pick_canonical(group["companies"])
        keep_name = next(c["name"] for c in group["companies"] if c["id"] == keep_id)

        if dry_run:
            drop_names = [c["name"] for c in group["companies"] if c["id"] != keep_id]
            print(f"  [DRY RUN] domain={group['key']!r}: keep {keep_id} ({keep_name!r})"
                  f" | drop {drop_ids} ({drop_names})")
        else:
            for drop_id in drop_ids:
                s = _merge_one(session, keep_id, drop_id, dry_run=False)
                totals["reassigned"] += s["reassigned"]
                totals["skipped"] += s["skipped"]
                totals["fields_filled"] += s["fields_filled"]
                totals["companies_removed"] += 1
                logger.warning(
                    "merged %d→%d (%r): %d reassigned, %d skipped, %d fields filled",
                    drop_id, keep_id, group["key"],
                    s["reassigned"], s["skipped"], s["fields_filled"],
                )

        totals["groups"] += 1

    return totals


# ── Display ───────────────────────────────────────────────────────────────────

def print_results(domain_dups: List[dict], name_dups: List[dict], limit: int):
    total = len(domain_dups) + len(name_dups)
    if total == 0:
        print("\nNo duplicates found.")
        return

    print(f"\n{'='*60}")
    print(f"DEDUPLICATION REPORT — top {limit} per type")
    print(f"{'='*60}")

    idx = 1
    if domain_dups:
        print(f"\n--- DOMAIN MATCHES ({len(domain_dups)}) ---")
        for dup in domain_dups:
            print(f"\n[{idx}] domain: {dup['key']}  ({dup['count']} rows)")
            for c in dup["companies"]:
                print(f"     Row {c['id']:6d}: {c['name']!r:40s}"
                      f" ai_score={c['ai_score']:6s}  signals={c['signals']}")
                if c["description"]:
                    print(f"              desc: {c['description']}")
            keep_id, drop_ids = _pick_canonical(dup["companies"])
            keep_name = next(c["name"] for c in dup["companies"] if c["id"] == keep_id)
            print(f"     → Keep {keep_id} ({keep_name!r}), drop {drop_ids}")
            idx += 1

    if name_dups:
        print(f"\n--- NAME MATCHES (similarity ≥ 0.92, {len(name_dups)} pairs) ---")
        print("    (read-only — name matches require manual review before merging)")
        for dup in name_dups:
            print(f"\n[{idx}] similarity={dup['similarity']}  {dup['key']}")
            for c in dup["companies"]:
                print(f"     Row {c['id']:6d}: {c['name']!r:40s} ai_score={c['ai_score']:6s}")
                if c["description"]:
                    print(f"              desc: {c['description']}")
            idx += 1

    print(f"\n{'='*60}")
    print(f"Total: {len(domain_dups)} domain groups, {len(name_dups)} name-similarity pairs")
    print(f"Run with --merge to preview, --merge --confirm to execute domain merges.")
    print(f"{'='*60}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Cross-source company deduplication")
    parser.add_argument("--limit", type=int, default=20,
                        help="Max duplicate groups to show/merge per type (default: 20)")
    parser.add_argument("--merge", action="store_true",
                        help="Preview (dry run) what would be merged")
    parser.add_argument("--confirm", action="store_true",
                        help="Combined with --merge: actually execute the merges")
    args = parser.parse_args()

    dry_run = not args.confirm

    if args.merge and args.confirm:
        print(f"Running dedup MERGE (executing on up to {args.limit} domain groups)...")
    elif args.merge:
        print(f"Running dedup MERGE dry run (no changes will be made)...")
    else:
        print(f"Scanning for duplicates (limit={args.limit} per type)...")

    with session_scope() as session:
        total_before = session.query(Company).count()
        print(f"Total companies before: {total_before:,}")

        domain_dups = find_domain_duplicates(session, limit=args.limit)
        print(f"Domain duplicate groups: {len(domain_dups)}")

        name_dups = find_name_duplicates(session, limit=args.limit)
        print(f"Name-similarity pairs:  {len(name_dups)}")

        if args.merge:
            if domain_dups:
                totals = merge_domain_duplicates(session, domain_dups, dry_run=dry_run)
                if dry_run:
                    print(f"\nDry run complete — {totals['groups']} groups would be merged, "
                          f"{totals['companies_removed']} companies removed.")
                    print("Re-run with --merge --confirm to execute.")
                else:
                    total_after = session.query(Company).count()
                    print(f"\nMerge complete:")
                    print(f"  Groups merged:     {totals['groups']}")
                    print(f"  Companies removed: {totals['companies_removed']}")
                    print(f"  Signals moved:     {totals['reassigned']}")
                    print(f"  Signals dropped:   {totals['skipped']} (were exact duplicates)")
                    print(f"  Fields back-filled:{totals['fields_filled']}")
                    print(f"  Companies before:  {total_before:,}")
                    print(f"  Companies after:   {total_after:,}")
            else:
                print("No domain duplicates found — nothing to merge.")
            if name_dups:
                print(f"\n{len(name_dups)} name-similarity pairs found (not auto-merged — "
                      "review manually and re-run with specific IDs if needed).")
        else:
            print_results(domain_dups, name_dups, args.limit)


if __name__ == "__main__":
    main()
