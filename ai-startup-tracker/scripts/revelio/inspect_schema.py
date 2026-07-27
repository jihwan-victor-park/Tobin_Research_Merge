"""
Inspect Revelio parquet + schema files without loading them fully.

Run this after downloading the tiny .txt schema docs (and optionally ONE
sample shard of each table) so we can write the extraction against the real
column names instead of guessing.

Usage:
    # print every .txt schema doc found in data/revelio_schema/
    python scripts/revelio/inspect_schema.py

    # also inspect specific parquet files (columns + 3 sample rows, read light)
    python scripts/revelio/inspect_schema.py path/to/revelio_individual_positions-000000.parquet ...

Reads only the parquet footer + first record batch, so a 1.3 GB shard is
inspected in a second without pulling it into memory.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pyarrow.parquet as pq

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "data" / "revelio_schema"


def dump_txt_docs() -> None:
    txts = sorted(SCHEMA_DIR.glob("*.txt"))
    if not txts:
        print(f"(no .txt schema docs in {SCHEMA_DIR} yet — download them first)\n")
        return
    for t in txts:
        print("=" * 70)
        print(f"  {t.name}")
        print("=" * 70)
        print(t.read_text(errors="replace").strip() or "(empty)")
        print()


def dump_parquet(path: str) -> None:
    p = Path(path)
    print("=" * 70)
    print(f"  {p.name}  ({p.stat().st_size / 1e9:.2f} GB)" if p.exists() else f"  {p.name} (MISSING)")
    print("=" * 70)
    if not p.exists():
        print("  file not found\n")
        return
    pf = pq.ParquetFile(p)
    print(f"  rows: {pf.metadata.num_rows:,} · row groups: {pf.metadata.num_row_groups}")
    print("  columns:")
    for field in pf.schema_arrow:
        print(f"    - {field.name:32} {field.type}")
    # First few rows, read light (one small batch)
    try:
        batch = next(pf.iter_batches(batch_size=3))
        sample = batch.to_pylist()
        print("\n  sample rows:")
        for i, row in enumerate(sample[:3]):
            print(f"    [{i}] " + ", ".join(
                f"{k}={_short(v)}" for k, v in row.items()))
    except StopIteration:
        print("  (no rows)")
    print()


def _short(v, n: int = 40) -> str:
    if isinstance(v, bytes):
        v = v.decode("utf-8", "replace")
    s = str(v)
    return s if len(s) <= n else s[:n] + "…"


if __name__ == "__main__":
    dump_txt_docs()
    for arg in sys.argv[1:]:
        dump_parquet(arg)
