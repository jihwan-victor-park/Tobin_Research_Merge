"""
Backfill companies.ai_score using the unified `classify_ai` keyword classifier.

Why: rows ingested before the unified classifier landed (or via batch scripts
that bypassed it) often have NULL ai_score. We re-tag them in bulk using only
the keyword tier — the LLM fallback would cost too much for ~12k rows and the
keyword tier is already the source of truth for everything else.

Idempotent: only touches rows where ai_score IS NULL.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.connection import session_scope
from backend.db.models import Company
from backend.utils.classify_ai import _AI_PATTERN, _BARE_AI_PATTERN

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _is_ai_keyword(name: str | None, description: str | None, industry: str | None) -> bool:
    text = " ".join(filter(None, [name, description, industry]))
    if not text:
        return False
    return bool(_AI_PATTERN.search(text) or _BARE_AI_PATTERN.search(text))


def main(dry_run: bool = False, limit: int | None = None) -> None:
    updated = 0
    flagged_ai = 0
    scanned = 0

    with session_scope() as session:
        q = session.query(Company).filter(Company.ai_score.is_(None))
        if limit:
            q = q.limit(limit)

        for c in q.yield_per(500):
            scanned += 1
            tags = ",".join(c.ai_tags) if c.ai_tags else None
            is_ai = _is_ai_keyword(c.name, c.description, tags)
            # Match BaseScraper.save behavior: AI hit -> 0.7, miss -> 0.1.
            new_score = 0.7 if is_ai else 0.1
            c.ai_score = new_score
            updated += 1
            if is_ai:
                flagged_ai += 1
            if scanned % 1000 == 0:
                logger.info(f"scanned={scanned} flagged_ai={flagged_ai}")

        if dry_run:
            session.rollback()
            logger.info("[dry-run] rolled back")

    logger.info(
        f"Done: scanned={scanned} updated={updated} flagged_ai={flagged_ai} "
        f"({(flagged_ai / max(updated, 1)) * 100:.1f}% AI)"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()
    main(dry_run=args.dry_run, limit=args.limit)
