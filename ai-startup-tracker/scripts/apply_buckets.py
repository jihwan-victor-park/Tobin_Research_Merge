"""Apply the failure-bucket classification to site_health.

Reads reports/failure_buckets.{tsv,md} produced by classify_failures.py and:
  - H_DEAD_SITE → status='excluded', exclude_until = NOW + 12 months
  - I_OFFTOPIC  → status='excluded', exclude_until = NOW + 3 months (revisit later;
                   the LLM might have meant a different page on the same domain)

Other buckets are reported but not auto-modified — those need bucket-specific
fixes (seed-URL discovery, proxy, etc.).

Run with --dry-run first to preview. --apply to actually write changes.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.db.connection import session_scope  # noqa: E402
from backend.db.models import SiteHealth  # noqa: E402

TSV_PATH = ROOT / "reports" / "failure_buckets.tsv"
MD_PATH = ROOT / "reports" / "failure_buckets.md"

EXCLUDE_RULES = {
    "H_DEAD_SITE": ("dead_site_probe", 365),
    "I_OFFTOPIC": ("offtopic_probe", 90),
}


def load_buckets() -> dict[str, list[tuple[str, str]]]:
    """Return {bucket: [(domain, reason), ...]} from TSV if present, else parse MD."""
    by_bucket: dict[str, list[tuple[str, str]]] = defaultdict(list)
    if TSV_PATH.exists():
        for line in TSV_PATH.read_text().splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) >= 2:
                bucket = parts[0]
                domain = parts[1]
                reason = parts[2] if len(parts) > 2 else ""
                by_bucket[bucket].append((domain, reason))
        return by_bucket

    # Fall back to parsing the markdown "Full domain → bucket mapping" code block
    if not MD_PATH.exists():
        sys.exit(f"Neither {TSV_PATH} nor {MD_PATH} exists. Run classify_failures.py first.")
    text = MD_PATH.read_text()
    m = re.search(r"## Full domain → bucket mapping\s*\n\s*```\n(.*?)```", text, re.S)
    if not m:
        sys.exit("Could not parse domain→bucket mapping out of report markdown.")
    for line in m.group(1).strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            by_bucket[parts[0]].append((parts[1], ""))
    return by_bucket


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually write changes (default is dry-run)")
    args = parser.parse_args()

    by_bucket = load_buckets()
    print("Bucket counts (from report):")
    for b in sorted(by_bucket, key=lambda x: -len(by_bucket[x])):
        print(f"  {b:24s} {len(by_bucket[b]):4d}")
    print()

    now = datetime.utcnow()
    plan: list[tuple[str, str, datetime, str]] = []  # (domain, reason, until, bucket)
    for bucket, (reason_tag, days) in EXCLUDE_RULES.items():
        for domain, probe_reason in by_bucket.get(bucket, []):
            full_reason = f"{reason_tag}: {probe_reason}" if probe_reason else reason_tag
            plan.append((domain, full_reason, now + timedelta(days=days), bucket))

    print(f"Will exclude {len(plan)} domains (H_DEAD_SITE + I_OFFTOPIC).")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print()

    if not args.apply:
        print("Sample of planned changes (first 15):")
        for domain, reason, until, bucket in plan[:15]:
            print(f"  [{bucket}] {domain:35s} until={until.date()} reason={reason}")
        print("\nRe-run with --apply to commit changes.")
        return

    updated = 0
    skipped_missing = 0
    with session_scope() as s:
        for domain, reason, until, bucket in plan:
            h = s.query(SiteHealth).filter(SiteHealth.domain == domain).one_or_none()
            if not h:
                skipped_missing += 1
                continue
            h.status = "excluded"
            h.exclude_reason = reason
            h.exclude_until = until
            h.pending_reason = reason
            h.pending_reason_at = now
            updated += 1
        s.commit()
    print(f"[apply] excluded {updated} sites (missing_in_db={skipped_missing})")


if __name__ == "__main__":
    main()
