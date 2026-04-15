#!/usr/bin/env python3
"""
Cross-source deduplication analysis for the companies table.

Usage:
    python scripts/run_dedup.py              # show top 20 likely duplicates (default)
    python scripts/run_dedup.py --show       # same
    python scripts/run_dedup.py --limit 50   # show top 50
    python scripts/run_dedup.py --merge --confirm  # merge (NOT YET IMPLEMENTED — requires approval)

IMPORTANT: --merge is not implemented. This script is show-only until the user
explicitly approves a merge strategy after reviewing the output.
"""
import argparse
import logging
import os
import sys
from typing import List, Tuple

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

logging.basicConfig(
    level=logging.WARNING,  # Suppress info noise for clean output
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from backend.db.connection import session_scope
from backend.db.models import Company, IncubatorSignal
from backend.utils.domain import canonicalize_domain
from backend.utils.normalize import normalize_company_name, fuzzy_name_match
from sqlalchemy import func, text


def find_domain_duplicates(session, limit: int) -> List[dict]:
    """Find companies sharing the same canonicalized domain."""
    rows = session.execute(text("""
        SELECT
            domain,
            COUNT(*) as cnt,
            array_agg(id ORDER BY first_seen_at ASC) as ids,
            array_agg(name ORDER BY first_seen_at ASC) as names,
            array_agg(COALESCE(ai_score::text, 'NULL') ORDER BY first_seen_at ASC) as ai_scores,
            array_agg(COALESCE(description, '') ORDER BY first_seen_at ASC) as descs
        FROM companies
        WHERE domain IS NOT NULL AND domain != ''
        GROUP BY domain
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT :limit
    """), {"limit": limit}).fetchall()

    results = []
    for row in rows:
        # Count signals per company
        signal_counts = {}
        for company_id in row.ids:
            count = session.query(IncubatorSignal).filter(
                IncubatorSignal.company_id == company_id
            ).count()
            signal_counts[company_id] = count

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
    """Find companies with no domain whose normalized names are very similar."""
    # Get companies without a domain set
    no_domain = session.execute(text("""
        SELECT id, name, ai_score, description
        FROM companies
        WHERE (domain IS NULL OR domain = '')
        AND name IS NOT NULL AND name != ''
        ORDER BY first_seen_at ASC
    """)).fetchall()

    if not no_domain:
        return []

    # Build normalized name index
    indexed = []
    for row in no_domain:
        norm = normalize_company_name(row.name or "")
        if norm:
            indexed.append({
                "id": row.id,
                "name": row.name,
                "norm": norm,
                "ai_score": str(row.ai_score) if row.ai_score is not None else "NULL",
                "description": (row.description or "")[:80],
            })

    # Find pairs with similarity >= threshold (O(n²) but limited by no-domain subset)
    seen_pairs = set()
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

    # Sort by similarity descending, return top limit
    groups.sort(key=lambda x: x["similarity"], reverse=True)
    return groups[:limit]


def print_results(domain_dups: List[dict], name_dups: List[dict], limit: int):
    total = len(domain_dups) + len(name_dups)
    if total == 0:
        print("\nNo duplicates found.")
        return

    print(f"\n{'='*60}")
    print(f"DEDUPLICATION REPORT — Top {limit} likely duplicates")
    print(f"{'='*60}")

    idx = 1

    if domain_dups:
        print(f"\n--- DOMAIN MATCHES ({len(domain_dups)}) ---")
        for dup in domain_dups:
            print(f"\n[{idx}] domain: {dup['key']}  ({dup['count']} rows)")
            for c in dup["companies"]:
                signals = c["signals"]
                print(f"     Row {c['id']:6d}: {c['name']!r:40s} ai_score={c['ai_score']:6s}  signals={signals}")
                if c["description"]:
                    print(f"              desc: {c['description']}")
            # Suggest which to keep (most signals, then highest ai_score)
            keep = max(dup["companies"], key=lambda c: (
                c["signals"],
                float(c["ai_score"]) if c["ai_score"] != "NULL" else 0.0
            ))
            print(f"     → Suggested: keep row {keep['id']} ({keep['name']!r}), merge others into it")
            idx += 1

    if name_dups:
        print(f"\n--- NAME MATCHES (similarity ≥ 0.92, {len(name_dups)} pairs) ---")
        for dup in name_dups:
            print(f"\n[{idx}] similarity={dup['similarity']}  {dup['key']}")
            for c in dup["companies"]:
                print(f"     Row {c['id']:6d}: {c['name']!r:40s} ai_score={c['ai_score']:6s}")
                if c["description"]:
                    print(f"              desc: {c['description']}")
            idx += 1

    print(f"\n{'='*60}")
    print(f"Total: {len(domain_dups)} domain duplicates, {len(name_dups)} name-similarity pairs")
    print(f"To merge: run with --merge --confirm (NOT YET IMPLEMENTED — review first)")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Cross-source company deduplication")
    parser.add_argument("--show", action="store_true", default=True, help="Show likely duplicates (default)")
    parser.add_argument("--limit", type=int, default=20, help="Max duplicates to show per type (default: 20)")
    parser.add_argument("--merge", action="store_true", help="Merge duplicates (NOT IMPLEMENTED — requires review)")
    parser.add_argument("--confirm", action="store_true", help="Required alongside --merge")
    args = parser.parse_args()

    if args.merge:
        print("ERROR: --merge is not yet implemented. Review --show output first and request merge explicitly.")
        sys.exit(1)

    print(f"Scanning companies table for duplicates (limit={args.limit} per type)...")

    with session_scope() as session:
        total = session.query(Company).count()
        print(f"Total companies: {total:,}")

        domain_dups = find_domain_duplicates(session, limit=args.limit)
        print(f"Domain duplicates found: {len(domain_dups)}")

        name_dups = find_name_duplicates(session, limit=args.limit)
        print(f"Name-similarity pairs found: {len(name_dups)}")

        print_results(domain_dups, name_dups, args.limit)


if __name__ == "__main__":
    main()
