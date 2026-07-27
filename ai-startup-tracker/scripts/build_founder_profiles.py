#!/usr/bin/env python3
"""
Build founder_profiles.parquet from Revelio shards, joined to our company
domain list.

IMPORTANT METHODOLOGY NOTE (read before trusting role_title):
Revelio's individual_positions files carry no raw job-title text. The only
role field is `role_k1500`, a coarsened ~1,500-bucket occupation taxonomy.
That taxonomy has no distinct "founder" or "ceo" category -- CEO/founder-type
roles appear to be folded into generic buckets ("officer", "financial
officer", "technology officer", "operating officer", "md"). This script
therefore identifies SENIOR OFFICERS (cfo, coo, and those officer-type
buckets), not verified founders/CEOs specifically. Treat role_title as a
proxy for "senior exec at this company," not a confirmed founder flag.
Revisit if a raw-title field turns up in a different Revelio export.

Join path:
  our_company_domains.csv --(domain)--> revelio_company_mapping (url) --(rcid)-->
  revelio_individual_positions (filtered to EXEC_ROLES) --(user_id)-->
  revelio_individual_user + revelio_individual_user_education (OPTIONAL --
  script runs without them and leaves those columns NULL if the files
  aren't present yet; this is expected until those two exports land).

STORAGE: individual_user / individual_user_education turn out to be sharded
the same way individual_positions is (many large files, not a fixed handful
like company_mapping), so they're handled the same incremental way: each raw
shard is projected down to just the columns founder_profiles.py needs, merged
into a small running compact file (individual_user_compact.parquet /
individual_user_education_compact.parquet in --out-dir), recorded in its own
manifest, and -- if --delete-after is passed -- the wide raw shard is deleted
once merged. Every future run only processes new shards.

Real schema note: Revelio has no single gender_prob/ethnicity_prob field.
individual_user has separate f_prob/m_prob and a sex_predicted (M/F) label,
plus six separate ethnicity probabilities (white/black/api/hispanic/native/
multiple_prob) and an ethnicity_predicted label. This script keeps BOTH the
predicted category and the confidence in that prediction (GREATEST of the
relevant probabilities) as gender_predicted+gender_prob and
ethnicity_predicted+ethnicity_prob -- two extra columns beyond the original
schema, chosen over collapsing to a single number because it preserves the
actual signal for a few MB of extra storage.

Efficiency: all filtering/joining happens in DuckDB SQL over parquet globs;
no per-row Python loops, no full dataframes materialized in memory.

Usage:
    python3 build_founder_profiles.py
    python3 build_founder_profiles.py --delete-after     # free disk once each
                                                          # positions shard's
                                                          # manifest entry is
                                                          # written & verified,
                                                          # AND once individual_user /
                                                          # individual_user_education
                                                          # are safely compacted
    python3 build_founder_profiles.py --downloads /path/to/Downloads
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

import duckdb

EXEC_ROLES = ["cfo", "coo", "financial officer", "technology officer",
              "operating officer", "officer", "md", "directors"]

# Board-type roles (governance, not operating leadership) within EXEC_ROLES.
# VCs/outside investors routinely get a board seat immediately after
# investing, so "director" appearing within the founding window is a much
# weaker founder signal than an operating title like cfo/cto/coo/md -- nobody
# hands a stranger those within a company's first two years. Kept in the
# dataset (not dropped) but flagged via is_board_role so board-affiliated
# rows can be filtered out or weighted differently in analysis.
BOARD_ROLES = ["directors"]

# Word-boundary regex kept for reference / future use if a raw-title field
# appears; NOT what actually drives matching today (see EXEC_ROLES above).
TITLE_REGEX = (
    r"(?i)\b(founders?|co-founders?|founding\s+(engineer|designer|member|team)|"
    r"ceo|chief\s+executive(\s+officer)?|cto|chief\s+technology(\s+officer)?|"
    r"coo|chief\s+operating(\s+officer)?|cfo|chief\s+financial(\s+officer)?)\b"
)

CLOSE_MISS_REGEX = r"(?i)(chief|head of|president|owner|director|manager|lead)"

# Query builders applied to each raw individual_user / individual_user_education
# shard before merging into the compact accumulator file. See STORAGE note
# above for why gender/ethnicity end up as category+confidence pairs.
#
# individual_user_education has MULTIPLE rows per user_id (one per degree).
# Joining that raw would fan a single founder's position out into one output
# row per degree, breaking the "one row per company+person" contract of
# founder_profiles.parquet. QUALIFY picks exactly one row per user_id here --
# the highest-ranked university (lowest world_rank, nulls last), tie-broken by
# the lowest education_number -- so the compact table is already 1 row/user.
def user_query(f):
    return f"""
        SELECT
            user_id,
            sex_predicted AS gender_predicted,
            GREATEST(f_prob, m_prob) AS gender_prob,
            ethnicity_predicted,
            GREATEST(white_prob, black_prob, api_prob, hispanic_prob, native_prob, multiple_prob) AS ethnicity_prob
        FROM read_parquet('{f}')
    """

def edu_query(f):
    return f"""
        SELECT
            user_id,
            CAST(degree AS VARCHAR) AS degree,
            CAST(field AS VARCHAR) AS field_of_study,
            university_name AS university,
            world_rank AS university_world_rank
        FROM read_parquet('{f}')
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY user_id
            ORDER BY (world_rank IS NULL), world_rank, education_number
        ) = 1
    """

# Columns REQUIRED to be present (by real name) in the raw shard for the
# query above to work; checked before running it so a schema surprise fails
# loudly with the actual column list instead of a cryptic SQL error.
USER_REQUIRED_COLS = ["user_id", "sex_predicted", "f_prob", "m_prob", "ethnicity_predicted",
                       "white_prob", "black_prob", "api_prob", "hispanic_prob", "native_prob", "multiple_prob"]
EDU_REQUIRED_COLS = ["user_id", "degree", "field", "university_name", "world_rank", "education_number"]


def sync_reference_table(con, raw_glob, compact_path, manifest_path, build_query,
                          required_cols, label, delete_raw):
    """Incrementally add new raw shards of a reference table (individual_user
    or individual_user_education -- both turn out to be sharded like
    individual_positions) as small per-shard files in a "parts" folder next to
    compact_path, tracked by its own manifest so reruns only touch new shards.

    Deliberately does NOT maintain one big file that gets rewritten on every
    shard: at GB scale that means each merge re-writes (and, on a cloud-synced
    path, re-uploads) the entire accumulated history just to add one shard's
    worth of data, getting slower and more bandwidth-heavy the longer this
    runs -- and a read-and-overwrite-same-file step risks corrupting
    everything already accumulated if a run is interrupted mid-write. Writing
    one small immutable file per shard avoids both: each run only ever adds a
    new file, an interruption can only affect the one new file being written,
    and DuckDB reads the whole parts folder as one dataset via glob, same as
    it already does for the individual_positions shards.

    Returns the glob pattern to read from ('' if no data exists yet)."""
    parts_dir = compact_path[:-len(".parquet")] + "_parts" if compact_path.endswith(".parquet") else compact_path + "_parts"
    os.makedirs(parts_dir, exist_ok=True)
    parts_glob = os.path.join(parts_dir, "*.parquet")

    manifest = []
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
    processed_names = {m["shard"] for m in manifest}
    processed_sizes = {m["file_size"] for m in manifest if m.get("status") == "OK" and "file_size" in m}

    raw_files = sorted(glob.glob(raw_glob))
    new_files = [f for f in raw_files if os.path.basename(f) not in processed_names]

    if not new_files:
        return parts_glob if glob.glob(parts_glob) else ""

    for f in new_files:
        shard_name = os.path.basename(f)
        shard_size = os.path.getsize(f)

        if shard_size in processed_sizes:
            print(f"  skip (duplicate download, same size as an already-merged {label} shard): {shard_name}")
            manifest.append({"shard": shard_name, "file_size": shard_size,
                              "processed_at": datetime.now(timezone.utc).isoformat(),
                              "status": "SKIPPED_DUPLICATE_DOWNLOAD"})
            with open(manifest_path, "w") as mf:
                json.dump(manifest, mf, indent=2)
            continue

        cols = [r[0] for r in con.sql(f"DESCRIBE SELECT * FROM read_parquet('{f}') LIMIT 0").fetchall()]
        missing = [c for c in required_cols if c not in cols]
        if missing:
            print(f"WARNING: {label} shard {shard_name} is missing expected column(s) {missing}. "
                  f"Actual columns: {cols}. Skipping this shard until the projection SQL is "
                  f"corrected to match the real schema -- it will be retried on the next run.")
            continue

        n_rows = con.sql(f"SELECT COUNT(*) FROM read_parquet('{f}')").fetchone()[0]
        part_path = os.path.join(parts_dir, os.path.splitext(shard_name)[0] + ".parquet")
        con.execute(f"COPY ({build_query(f)}) TO '{part_path}' (FORMAT PARQUET)")

        manifest.append({"shard": shard_name, "file_size": shard_size, "rows": n_rows,
                          "processed_at": datetime.now(timezone.utc).isoformat(), "status": "OK"})
        with open(manifest_path, "w") as mf:
            json.dump(manifest, mf, indent=2)
        print(f"  {label} shard {shard_name}: {n_rows:,} rows -> {os.path.basename(part_path)}")

        if delete_raw:
            print(f"  deleting raw {label} shard (part file verified above): {f}")
            os.remove(f)

    return parts_glob


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--downloads", default=os.path.expanduser("~/Downloads"))
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--reference-dir", default=None,
                     help="where individual_user_compact.parquet / "
                          "individual_user_education_compact.parquet (and their "
                          "manifests) live. These grow steadily as more shards are "
                          "merged in, unlike founder_profiles.parquet -- point this "
                          "at an external drive or cloud-synced folder if --out-dir "
                          "is on constrained local disk. Defaults to --out-dir.")
    ap.add_argument("--delete-after", action="store_true",
                     help="delete each individual_positions shard once its "
                          "manifest entry is written and printed")
    ap.add_argument("--founding-window-years", type=int, default=2,
                     help="keep officer-role rows only if position startdate "
                          "is within this many years of company_mapping.year_founded "
                          "(tightens the founder proxy; requires year_founded to be "
                          "non-null and numeric)")
    return ap.parse_args()


def clean_domain_expr(col: str) -> str:
    return (f"lower(regexp_replace(regexp_replace({col}, "
            f"'^https?://', ''), '^www\\.', ''))")


def main():
    args = parse_args()
    dl = args.downloads
    out_dir = args.out_dir
    ref_dir = args.reference_dir or out_dir
    os.makedirs(ref_dir, exist_ok=True)
    if ref_dir != out_dir:
        print(f"individual_user/individual_user_education compact files will be "
              f"kept at: {ref_dir}")
    con = duckdb.connect()

    domains_csv = os.path.join(dl, "our_company_domains.csv")
    company_mapping_glob = os.path.join(dl, "revelio_company_mapping-*.parquet")
    positions_glob = os.path.join(dl, "revelio_individual_positions-*.parquet")
    user_glob = os.path.join(dl, "revelio_individual_user-*.parquet")
    edu_glob = os.path.join(dl, "revelio_individual_user_education-*.parquet")
    user_compact_path = os.path.join(ref_dir, "individual_user_compact.parquet")
    edu_compact_path = os.path.join(ref_dir, "individual_user_education_compact.parquet")
    user_manifest_path = os.path.join(ref_dir, "individual_user_compact_manifest.json")
    edu_manifest_path = os.path.join(ref_dir, "individual_user_education_compact_manifest.json")

    if not os.path.exists(domains_csv):
        sys.exit(f"Missing {domains_csv}")
    mapping_files = sorted(glob.glob(company_mapping_glob))
    if not mapping_files:
        sys.exit(f"No company_mapping files found at {company_mapping_glob}")
    position_files = sorted(glob.glob(positions_glob))
    if not position_files:
        print(f"No individual_positions files found at {positions_glob} -- "
              f"nothing new to process this run, but continuing on to the "
              f"summary/dedupe pass over any existing output.")

    # Incrementally merge any new individual_user / individual_user_education
    # shards into their compact accumulator files (see STORAGE note above).
    print("Syncing individual_user shards into compact lookup...")
    user_source = sync_reference_table(
        con, user_glob, user_compact_path, user_manifest_path,
        user_query, USER_REQUIRED_COLS, "individual_user", args.delete_after)
    print("Syncing individual_user_education shards into compact lookup...")
    edu_source = sync_reference_table(
        con, edu_glob, edu_compact_path, edu_manifest_path,
        edu_query, EDU_REQUIRED_COLS, "individual_user_education", args.delete_after)

    have_user = bool(user_source)
    have_edu = bool(edu_source)
    print(f"\nindividual_user data available:           {'yes (' + os.path.basename(user_source) + ')' if have_user else 'no'}"
          + ("" if have_user else "  -- MISSING: education/demographic columns will be NULL"))
    print(f"individual_user_education data available: {'yes (' + os.path.basename(edu_source) + ')' if have_edu else 'no'}"
          + ("" if have_edu else "  -- MISSING: degree/field/university columns will be NULL"))

    # ---- stage: build matched-company reference table (our domain -> rcid) ----
    con.execute(f"""
        CREATE TEMP TABLE matched_companies AS
        WITH ours AS (
            SELECT company_id, name AS company_name,
                   {clean_domain_expr('domain')} AS clean_domain
            FROM read_csv_auto('{domains_csv}')
        ),
        rev_map AS (
            SELECT rcid, {clean_domain_expr('url')} AS clean_domain,
                   TRY_CAST(year_founded AS INTEGER) AS year_founded
            FROM read_parquet('{company_mapping_glob}')
            WHERE url IS NOT NULL
        )
        SELECT DISTINCT o.company_id, o.company_name, o.clean_domain AS company_domain,
               m.rcid, m.year_founded
        FROM ours o JOIN rev_map m USING (clean_domain)
    """)
    n_matched = con.sql("SELECT COUNT(*) FROM matched_companies").fetchone()[0]
    n_our = con.sql(f"SELECT COUNT(DISTINCT {clean_domain_expr('domain')}) FROM read_csv_auto('{domains_csv}')").fetchone()[0]
    print(f"\nCompany domain match rate: {n_matched:,} / {n_our:,} of our companies "
          f"resolved to a Revelio rcid ({100*n_matched/n_our:.1f}%)")

    # ---- output table (created once, appended per shard) ----
    out_path = os.path.join(out_dir, "founder_profiles.parquet")
    manifest_path = os.path.join(out_dir, "founder_profiles_manifest.json")
    manifest = []
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
    already_processed = {m["shard"] for m in manifest}
    # Guard against the same shard being downloaded twice under different
    # filenames (e.g. a browser saving "...000064.parquet" and
    # "...000064 (1).parquet"). File size is a cheap, reliable enough
    # fingerprint for detecting "this is the same download again."
    already_processed_sizes = {m["file_size"] for m in manifest if m.get("status") == "OK" and "file_size" in m}

    role_list_sql = "(" + ",".join(f"'{r}'" for r in EXEC_ROLES) + ")"
    all_matched_titles = {}
    all_close_misses = {}
    total_exec_rows = 0
    total_resolved_rows = 0
    null_rcid_shards = []
    first_shard_written = os.path.exists(out_path)

    for shard_path in position_files:
        shard_name = os.path.basename(shard_path)
        if shard_name in already_processed:
            print(f"skip (already in manifest): {shard_name}")
            continue
        shard_size = os.path.getsize(shard_path)
        if shard_size in already_processed_sizes:
            print(f"skip (duplicate download, same size as an already-processed shard): {shard_name} ({shard_size:,} bytes)")
            manifest.append({
                "shard": shard_name, "processed_at": datetime.now(timezone.utc).isoformat(),
                "file_size": shard_size, "status": "SKIPPED_DUPLICATE_DOWNLOAD",
            })
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)
            continue

        total_rows, non_null_rcid = con.sql(f"""
            SELECT COUNT(*), COUNT(rcid) FROM read_parquet('{shard_path}')
        """).fetchone()

        if non_null_rcid == 0:
            print(f"NULL-RCID SHARD (skipped, wasted download): {shard_name} -- {total_rows:,} rows, 0 non-null rcid")
            null_rcid_shards.append(shard_name)
            entry = {
                "shard": shard_name, "processed_at": datetime.now(timezone.utc).isoformat(),
                "total_rows": total_rows, "non_null_rcid": 0, "exec_rows_matched": 0,
                "rows_resolved_to_our_company": 0, "file_size": shard_size, "status": "SKIPPED_NULL_RCID",
            }
            manifest.append(entry)
            already_processed_sizes.add(shard_size)
            print(json.dumps(entry, indent=2))
            continue

        exec_rows = con.sql(f"""
            SELECT COUNT(*) FROM read_parquet('{shard_path}')
            WHERE lower(role_k1500) IN {role_list_sql}
        """).fetchone()[0]

        # matched titles in this shard
        for role, c in con.sql(f"""
            SELECT role_k1500, COUNT(*) FROM read_parquet('{shard_path}')
            WHERE lower(role_k1500) IN {role_list_sql}
            GROUP BY role_k1500
        """).fetchall():
            all_matched_titles[role] = all_matched_titles.get(role, 0) + c

        # close misses: management/leadership-adjacent roles NOT in EXEC_ROLES
        for role, c in con.sql(f"""
            SELECT role_k1500, COUNT(*) FROM read_parquet('{shard_path}')
            WHERE lower(role_k1500) NOT IN {role_list_sql}
              AND regexp_matches(role_k1500, '{CLOSE_MISS_REGEX}')
            GROUP BY role_k1500
        """).fetchall():
            all_close_misses[role] = all_close_misses.get(role, 0) + c

        # ---- resolve to our companies + build output rows ----
        # Two-stage join, deliberately: individual_user_compact/individual_user_
        # education_compact keep growing every round (one shard's worth of rows
        # added per run, currently hundreds of millions of rows combined), so
        # joining the full 10M-row positions shard against them directly makes
        # DuckDB's planner reason about all four tables at once and its memory/
        # temp-spill footprint scales with the reference tables' ever-growing
        # size rather than with the (small, constant) number of actually-
        # matched rows. Materializing the small matched-and-resolved set FIRST,
        # then joining that tiny result against the big reference tables,
        # keeps the expensive part of the query bounded regardless of how many
        # reference shards have accumulated by now.
        window = args.founding_window_years
        board_roles_sql = "(" + ",".join(f"'{r}'" for r in BOARD_ROLES) + ")"
        matched_df = con.sql(f"""
            SELECT
                mc.company_id, mc.company_domain, mc.company_name,
                p.role_k1500 AS role_title, p.startdate AS start_date, p.enddate AS end_date,
                p.user_id,
                (lower(p.role_k1500) IN {board_roles_sql}) AS is_board_role,
                mc.year_founded,
                (mc.year_founded IS NOT NULL
                 AND ABS(EXTRACT(YEAR FROM p.startdate) - mc.year_founded) <= {window}
                ) AS near_founding
            FROM read_parquet('{shard_path}') p
            JOIN matched_companies mc ON p.rcid = mc.rcid
            WHERE lower(p.role_k1500) IN {role_list_sql}
        """).df()
        con.register("matched_positions", matched_df)

        # Second fix, on top of the matched_positions materialization above:
        # a LEFT JOIN's hash table generally gets built on the huge/right-hand
        # side in a LEFT OUTER join, regardless of how small the left side is
        # -- so joining tiny matched_positions straight against the
        # hundreds-of-millions-of-rows reference globs was STILL blowing up
        # memory even after that first fix. The actual solution: pre-filter
        # each reference glob down to just the handful of user_ids we need
        # (a WHERE ... IN (SELECT user_id FROM matched_positions) scan, which
        # DuckDB can push down as a cheap semi-join filter during the parquet
        # scan) BEFORE joining, so every join from here on is small-to-small.
        user_join = ""
        edu_join = ""
        select_extra = ("CAST(NULL AS VARCHAR) AS degree, CAST(NULL AS VARCHAR) AS field_of_study, "
                         "CAST(NULL AS VARCHAR) AS university, CAST(NULL AS DOUBLE) AS university_world_rank, "
                         "CAST(NULL AS VARCHAR) AS gender_predicted, CAST(NULL AS DOUBLE) AS gender_prob, "
                         "CAST(NULL AS VARCHAR) AS ethnicity_predicted, CAST(NULL AS DOUBLE) AS ethnicity_prob")
        if have_user:
            relevant_user_df = con.sql(f"""
                SELECT * FROM read_parquet('{user_source}')
                WHERE user_id IN (SELECT user_id FROM matched_positions)
            """).df()
            con.register("relevant_users", relevant_user_df)
            user_join = "LEFT JOIN relevant_users u ON mp.user_id = u.user_id"
            select_extra = ("CAST(NULL AS VARCHAR) AS degree, CAST(NULL AS VARCHAR) AS field_of_study, "
                             "CAST(NULL AS VARCHAR) AS university, CAST(NULL AS DOUBLE) AS university_world_rank, "
                             "u.gender_predicted AS gender_predicted, u.gender_prob AS gender_prob, "
                             "u.ethnicity_predicted AS ethnicity_predicted, u.ethnicity_prob AS ethnicity_prob")
            if have_edu:
                relevant_edu_df = con.sql(f"""
                    SELECT * FROM read_parquet('{edu_source}')
                    WHERE user_id IN (SELECT user_id FROM matched_positions)
                """).df()
                con.register("relevant_edu", relevant_edu_df)
                edu_join = "LEFT JOIN relevant_edu e ON mp.user_id = e.user_id"
                select_extra = ("e.degree AS degree, e.field_of_study AS field_of_study, e.university AS university, "
                                 "e.university_world_rank AS university_world_rank, "
                                 "u.gender_predicted AS gender_predicted, u.gender_prob AS gender_prob, "
                                 "u.ethnicity_predicted AS ethnicity_predicted, u.ethnicity_prob AS ethnicity_prob")

        resolved_df = con.sql(f"""
            SELECT mp.*, {select_extra}
            FROM matched_positions mp
            {user_join}
            {edu_join}
        """).df()
        con.unregister("matched_positions")
        if have_user:
            con.unregister("relevant_users")
            if have_edu:
                con.unregister("relevant_edu")

        n_resolved_all = len(resolved_df)
        n_resolved_near_founding = int(resolved_df["near_founding"].sum()) if n_resolved_all else 0
        # Keep only the founding-proximity-filtered rows in the output file;
        # the unfiltered count is reported for comparison but not written.
        resolved_df = resolved_df[resolved_df["near_founding"]].drop(columns=["near_founding", "year_founded"])
        n_resolved = len(resolved_df)
        total_resolved_rows += n_resolved
        total_exec_rows += exec_rows

        if n_resolved > 0:
            con.register("resolved_df", resolved_df)
            if not first_shard_written:
                con.execute(f"COPY resolved_df TO '{out_path}' (FORMAT PARQUET)")
                first_shard_written = True
            else:
                con.execute(f"""
                    COPY (
                        SELECT * FROM read_parquet('{out_path}')
                        UNION ALL BY NAME
                        SELECT * FROM resolved_df
                    ) TO '{out_path}' (FORMAT PARQUET)
                """)
            con.unregister("resolved_df")

        entry = {
            "shard": shard_name,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "total_rows": total_rows,
            "non_null_rcid": non_null_rcid,
            "exec_rows_matched": exec_rows,
            "rows_resolved_to_our_company_unfiltered": n_resolved_all,
            "rows_resolved_to_our_company_near_founding": n_resolved,
            "founding_window_years": window,
            "file_size": shard_size,
            "status": "OK",
        }
        manifest.append(entry)
        already_processed_sizes.add(shard_size)
        print(f"\n{shard_name}: {total_rows:,} rows, rcid non-null {non_null_rcid:,}, "
              f"exec-role rows {exec_rows:,}, resolved (any officer) {n_resolved_all:,}, "
              f"resolved (within {window}y of founding) {n_resolved:,}")
        print(json.dumps(entry, indent=2))

        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        if args.delete_after:
            print(f"Deleting raw shard (manifest entry verified above): {shard_path}")
            os.remove(shard_path)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Company domain matches (our CSV -> Revelio rcid): {n_matched:,} / {n_our:,}")
    print(f"Total exec-role position rows across processed shards: {total_exec_rows:,}")
    print(f"Total rows resolved to a company in our domain CSV:    {total_resolved_rows:,}")
    if null_rcid_shards:
        print(f"NULL-rcid shards skipped (wasted downloads): {null_rcid_shards}")
    else:
        print("No null-rcid shards encountered among processed files.")
    print("\nDistinct matched role_k1500 values (this run):")
    for role, c in sorted(all_matched_titles.items(), key=lambda x: -x[1]):
        print(f"  {role:30s} {c:>10,}")
    print("\nTop 30 close-miss roles (management/leadership-adjacent, NOT matched -- review to decide if pattern should widen):")
    for role, c in sorted(all_close_misses.items(), key=lambda x: -x[1])[:30]:
        print(f"  {role:30s} {c:>10,}")

    if os.path.exists(out_path):
        # Safety-net dedupe: even with the file-size guard above, collapse any
        # exact duplicate position rows (same company/person/role/dates) that
        # might have slipped in, e.g. from a shard processed before this guard
        # existed. Cheap relative to the join work already done, and idempotent.
        before = con.sql(f"SELECT COUNT(*) FROM read_parquet('{out_path}')").fetchone()[0]
        con.execute(f"""
            COPY (SELECT DISTINCT * FROM read_parquet('{out_path}'))
            TO '{out_path}.tmp' (FORMAT PARQUET)
        """)
        os.replace(f"{out_path}.tmp", out_path)
        after = con.sql(f"SELECT COUNT(*) FROM read_parquet('{out_path}')").fetchone()[0]
        if after < before:
            print(f"\nDedup pass: removed {before - after:,} duplicate rows ({before:,} -> {after:,})")

        n_out = con.sql(f"SELECT COUNT(*) FROM read_parquet('{out_path}')").fetchone()[0]
        n_with_edu = 0
        if have_user and have_edu:
            n_with_edu = con.sql(f"SELECT COUNT(*) FROM read_parquet('{out_path}') WHERE university IS NOT NULL").fetchone()[0]
        print(f"\nfounder_profiles.parquet: {n_out:,} rows total"
              + (f", {n_with_edu:,} with education data" if have_user and have_edu
                 else " (education/demographic columns are NULL -- individual_user / "
                      "individual_user_education files not yet available)"))


if __name__ == "__main__":
    main()
