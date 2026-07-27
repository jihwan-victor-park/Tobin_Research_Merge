"""
Build an AI-startup founder dataset from Revelio (LinkedIn) shards.

Stages (run in order). Each stage reads whatever raw shards are present in
data/revelio_raw/, so it composes with a download→process→delete loop:

    match       company_mapping  -> derived/matched_rcids.parquet   (our company <-> Revelio rcid)
    positions   positions-*.parquet -> derived/founder_positions.parquet   (founders at our rcids)
    education    user_education-*.parquet -> derived/founder_education.parquet (founders' schools)
    users        user-*.parquet -> derived/founder_users.parquet     (founders' demographics)
    aggregate    -> output/founder_*.csv  (+ optional DB load)

Design constraints:
  - positions is sorted by rcid with row-group stats, so we push a
    ("rcid","in",our_rcids) predicate and only touch matching row groups.
  - education/user are keyed by user_id; we push ("user_id","in",founders).
  - Nothing here holds a whole shard beyond a single read; person-level
    outputs stay under data/revelio_derived/ (git-ignored, PII).

Founder definition: role_k17000_v3 contains "founder" (e.g. "Executive
Founder", "Tech Founder") OR equals "Chief Executive Officer". role_type
tags which. Validated on shard 044: ~median 1 founder/company, seniority
concentrated at 7 (top).
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RAW = os.path.join(ROOT, "data", "revelio_raw")
DERIVED = os.path.join(ROOT, "data", "revelio_derived")
OUTPUT = os.path.join(ROOT, "output")
os.makedirs(DERIVED, exist_ok=True)

FOUNDER_RE = r"founder"                       # role_k17000_v3 contains this (case-insens)
CEO_LABEL = "Chief Executive Officer"


def _clean_domain(u) -> str | None:
    if u is None or (isinstance(u, float) and pd.isna(u)):
        return None
    import re
    u = str(u).lower().strip()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.split("/")[0].strip() or None


def _shards(prefix: str) -> list[str]:
    return sorted(glob.glob(os.path.join(RAW, f"{prefix}-*.parquet")))


# ── stage: positions → founder rows at our companies ─────────────────
def stage_positions(delete_after: bool = False) -> None:
    rc_path = os.path.join(DERIVED, "matched_rcids.parquet")
    if not os.path.exists(rc_path):
        sys.exit("run `match` first (need derived/matched_rcids.parquet)")
    our_rcids = pd.read_parquet(rc_path)["rcid"].dropna().unique().tolist()
    rcid_set = set(our_rcids)
    print(f"filtering positions to {len(rcid_set):,} matched rcids")

    cols = ["user_id", "rcid", "role_k17000_v3", "seniority", "startdate", "enddate"]
    out_path = os.path.join(DERIVED, "founder_positions.parquet")
    writer = None
    total = 0
    for path in _shards("revelio_individual_positions"):
        # predicate pushdown on rcid (row-group stats skip most data)
        tbl = pq.read_table(path, columns=cols,
                            filters=[("rcid", "in", our_rcids)])
        if tbl.num_rows:
            df = tbl.to_pandas()
            role = df["role_k17000_v3"].fillna("")
            keep = role.str.contains(FOUNDER_RE, case=False, regex=True) | role.eq(CEO_LABEL)
            df = df[keep & df["rcid"].isin(rcid_set)].copy()
            if len(df):
                df["role_type"] = df["role_k17000_v3"].str.contains(
                    FOUNDER_RE, case=False).map({True: "founder", False: "ceo"})
                t = pa.Table.from_pandas(df, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(out_path, t.schema)
                writer.write_table(t)
                total += len(df)
        print(f"  {os.path.basename(path)}: cumulative founders {total:,}")
        if delete_after:
            os.remove(path)
    if writer:
        writer.close()
    print(f"✓ founder positions: {total:,} -> {out_path}")


# ── stage: education for founders ────────────────────────────────────
def stage_education(delete_after: bool = False) -> None:
    users = _founder_user_ids()
    cols = ["user_id", "university_name", "degree", "field",
            "university_country", "startdate", "enddate"]
    _filter_by_user("revelio_individual_user_education", cols, users,
                    os.path.join(DERIVED, "founder_education.parquet"), delete_after)


# ── stage: demographics for founders ─────────────────────────────────
def stage_users(delete_after: bool = False) -> None:
    users = _founder_user_ids()
    cols = ["user_id", "fullname", "sex_predicted", "ethnicity_predicted",
            "f_prob", "white_prob", "black_prob", "api_prob", "hispanic_prob",
            "highest_degree", "prestige", "user_country", "profile_linkedin_url"]
    _filter_by_user("revelio_individual_user", cols, users,
                    os.path.join(DERIVED, "founder_users.parquet"), delete_after)


def _founder_user_ids() -> list[float]:
    p = os.path.join(DERIVED, "founder_positions.parquet")
    if not os.path.exists(p):
        sys.exit("run `positions` first (need derived/founder_positions.parquet)")
    return pd.read_parquet(p, columns=["user_id"])["user_id"].dropna().unique().tolist()


def _filter_by_user(prefix, cols, users, out_path, delete_after):
    user_set = set(users)
    print(f"filtering {prefix} to {len(user_set):,} founder user_ids")
    writer, total = None, 0
    for path in _shards(prefix):
        tbl = pq.read_table(path, columns=cols, filters=[("user_id", "in", users)])
        if tbl.num_rows:
            df = tbl.to_pandas()
            df = df[df["user_id"].isin(user_set)]
            if len(df):
                t = pa.Table.from_pandas(df, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(out_path, t.schema)
                writer.write_table(t)
                total += len(df)
        print(f"  {os.path.basename(path)}: cumulative {total:,}")
        if delete_after:
            os.remove(path)
    if writer:
        writer.close()
    print(f"✓ {prefix}: {total:,} rows -> {out_path}")


# ── stage: aggregates for the dashboard ──────────────────────────────
DEGREE_LEVELS = ["High School", "Associate", "Bachelor", "Master", "MBA", "Doctor"]


def stage_aggregate() -> None:
    pos = pd.read_parquet(os.path.join(DERIVED, "founder_positions.parquet"))
    edu = pd.read_parquet(os.path.join(DERIVED, "founder_education.parquet"))
    usr = _maybe(os.path.join(DERIVED, "founder_users.parquet"))
    os.makedirs(OUTPUT, exist_ok=True)

    founders = pos["user_id"].nunique()
    print(f"founders: {founders:,} · companies: {pos['rcid'].nunique():,}")

    # higher-ed only for university stats (drop high school)
    he = edu[~edu["degree"].fillna("").eq("High School")].copy()
    he = he[he["university_name"].notna()]

    # top universities among founders (distinct founder per university)
    uni = (he.groupby("university_name")["user_id"].nunique()
           .sort_values(ascending=False).head(40)
           .rename("founders").reset_index())
    uni["pct_of_founders"] = (uni["founders"] / founders * 100).round(2)
    uni.to_csv(os.path.join(OUTPUT, "founder_top_universities.csv"), index=False)

    stanford = he.loc[he["university_name"].str.contains("stanford", case=False, na=False),
                      "user_id"].nunique()
    print(f"Stanford founders: {stanford:,} ({stanford/founders*100:.1f}%)")

    # degree level mix
    if len(he):
        deg = (he.groupby("user_id")["degree"].apply(_highest_degree)
               .value_counts().rename("founders").reset_index())
        deg.columns = ["degree", "founders"]
        deg.to_csv(os.path.join(OUTPUT, "founder_degree_mix.csv"), index=False)

    # demographics
    if usr is not None:
        demo = usr.drop_duplicates("user_id")
        sex = demo["sex_predicted"].value_counts(normalize=True).mul(100).round(1)
        eth = demo["ethnicity_predicted"].value_counts(normalize=True).mul(100).round(1)
        sex.rename("pct").reset_index().to_csv(
            os.path.join(OUTPUT, "founder_sex.csv"), index=False)
        eth.rename("pct").reset_index().to_csv(
            os.path.join(OUTPUT, "founder_ethnicity.csv"), index=False)
        print("sex %:\n", sex.to_string())
        print("ethnicity %:\n", eth.to_string())

    print(f"✓ wrote founder_*.csv to {OUTPUT}")


def _highest_degree(s: pd.Series) -> str:
    ranks = {d: i for i, d in enumerate(DEGREE_LEVELS)}
    best, best_r = "Other", -1
    for d in s.dropna():
        r = ranks.get(d, -1)
        if r > best_r:
            best, best_r = d, r
    return best


def _maybe(path):
    return pd.read_parquet(path) if os.path.exists(path) else None


# NOTE: stage_match is filled in once company_mapping schema is confirmed
# (need exact rcid / url / name column names). Placeholder guard:
def stage_match(delete_after: bool = False) -> None:
    sys.exit("stage_match: pending company_mapping schema confirmation — "
             "inspect revelio_company_mapping-000000.parquet first")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["match", "positions", "education", "users", "aggregate"])
    ap.add_argument("--delete-after", action="store_true",
                    help="delete each raw shard after processing (streaming mode)")
    a = ap.parse_args()
    {
        "match": stage_match,
        "positions": stage_positions,
        "education": stage_education,
        "users": stage_users,
        "aggregate": lambda **_: stage_aggregate(),
    }[a.stage](delete_after=a.delete_after)
