"""
Re-evaluate uses_ai for every company in the database using the current
keyword list. Useful after any change to AI_KEYWORDS — upserts only
update rows that are re-inserted, so historical rows need a separate pass.

Prints before/after counts by source and total changes made.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.db import get_connection

AI_KEYWORDS = [
    "artificial intelligence",
    "machine learning",
    "large language model",
    "llm",
    "generative ai",
    "generative",
    "gpt",
    "neural network",
    "deep learning",
    "nlp",
    "natural language processing",
    "computer vision",
    "data science",
    "autonomous",
    "robotics",
    "predictive",
    "recommendation engine",
    "ai",
]

_PATTERNS = [re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE) for kw in AI_KEYWORDS]


def detect_ai(description: str | None, tags_json: str | None) -> bool:
    tags = []
    if tags_json:
        try:
            tags = json.loads(tags_json)
        except (json.JSONDecodeError, TypeError):
            pass
    text = " ".join(filter(None, [description or "", " ".join(tags)]))
    return any(p.search(text) for p in _PATTERNS)


def main():
    conn = get_connection()

    # Snapshot before counts by source
    before_rows = conn.execute("""
        SELECT source, COUNT(*) AS total, SUM(uses_ai) AS ai_count
        FROM companies
        GROUP BY source
        ORDER BY total DESC
    """).fetchall()

    print("Before:")
    print(f"  {'source':<20} {'total':>7}  {'ai_before':>9}  {'ai%':>6}")
    print("  " + "-" * 50)
    before_by_source = {}
    for row in before_rows:
        pct = row["ai_count"] / row["total"] * 100 if row["total"] else 0
        print(f"  {row['source']:<20} {row['total']:>7,}  {row['ai_count']:>9,}  {pct:>5.1f}%")
        before_by_source[row["source"]] = {"total": row["total"], "ai": row["ai_count"]}

    # Re-evaluate every row
    all_rows = conn.execute("SELECT id, description, tags FROM companies").fetchall()
    print(f"\nRe-evaluating {len(all_rows):,} companies ...")

    updates = []
    for row in all_rows:
        new_val = 1 if detect_ai(row["description"], row["tags"]) else 0
        updates.append((new_val, row["id"]))

    conn.executemany("UPDATE companies SET uses_ai = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", updates)
    conn.commit()

    # Snapshot after counts by source
    after_rows = conn.execute("""
        SELECT source, COUNT(*) AS total, SUM(uses_ai) AS ai_count
        FROM companies
        GROUP BY source
        ORDER BY total DESC
    """).fetchall()

    print("\nAfter:")
    print(f"  {'source':<20} {'total':>7}  {'ai_before':>9}  {'ai_after':>9}  {'change':>7}  {'ai%':>6}")
    print("  " + "-" * 66)
    total_changed = 0
    for row in after_rows:
        before = before_by_source.get(row["source"], {}).get("ai", 0)
        change = row["ai_count"] - before
        total_changed += abs(change)
        pct = row["ai_count"] / row["total"] * 100 if row["total"] else 0
        sign = f"+{change}" if change > 0 else str(change)
        print(f"  {row['source']:<20} {row['total']:>7,}  {before:>9,}  {row['ai_count']:>9,}  {sign:>7}  {pct:>5.1f}%")

    print(f"\n  Total rows changed: {total_changed:,}")
    conn.close()


if __name__ == "__main__":
    main()
