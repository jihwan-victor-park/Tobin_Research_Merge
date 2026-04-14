"""
Crunchbase bulk data investigation script.
Reads organizations.parquet and organization_descriptions.parquet and reports
on structure, column names, row counts, and key field samples.
Investigation only — nothing is written to the database.
"""

import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def investigate_orgs(path: Path) -> pd.DataFrame:
    section("organizations.parquet")
    df = pd.read_parquet(path)

    print(f"\nRow count    : {len(df):,}")
    print(f"Column count : {len(df.columns)}")
    print(f"\nAll columns  :\n  " + "\n  ".join(df.columns.tolist()))

    print("\n--- First 3 rows ---")
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 120)
    pd.set_option("display.max_colwidth", 60)
    print(df.head(3).to_string())

    # Unique values in status/type columns
    print("\n--- Status / type columns ---")
    for col in df.columns:
        if any(kw in col.lower() for kw in ("status", "type", "stage", "category")):
            uniq = df[col].dropna().unique()
            print(f"\n  {col} ({len(uniq)} unique values):")
            print(f"    {sorted(uniq[:30])}")

    # Founding year / date columns
    print("\n--- Date / founding year columns ---")
    for col in df.columns:
        if any(kw in col.lower() for kw in ("founded", "date", "year", "created", "started")):
            sample = df[col].dropna().head(10).tolist()
            print(f"\n  {col}:")
            print(f"    {sample}")

    return df


def investigate_descriptions(path: Path) -> None:
    section("organization_descriptions.parquet")
    df = pd.read_parquet(path)

    print(f"\nRow count    : {len(df):,}")
    print(f"Column count : {len(df.columns)}")
    print(f"\nAll columns  :\n  " + "\n  ".join(df.columns.tolist()))

    print("\n--- First 3 rows ---")
    pd.set_option("display.max_colwidth", 200)
    print(df.head(3).to_string())


def main():
    orgs_path = ROOT / "organizations.parquet"
    descs_path = ROOT / "organization_descriptions.parquet"

    for path in (orgs_path, descs_path):
        if not path.exists():
            print(f"ERROR: {path} not found")
            return

    investigate_orgs(orgs_path)
    investigate_descriptions(descs_path)

    print("\n" + "=" * 60)
    print("  Investigation complete — nothing written to database")
    print("=" * 60)


if __name__ == "__main__":
    main()