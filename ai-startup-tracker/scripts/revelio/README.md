# Revelio (LinkedIn) founder enrichment

Goal: for each AI startup we track, identify its **founders** from LinkedIn
(Revelio Labs) work history, then join their **education** (and demographics)
so we can report things like *"what share of AI-startup founders studied at
Stanford"*, top universities, degrees/fields, and gender/ethnicity mix.

## Why we don't store the raw data

The Revelio LinkedIn dump is ~151 GB. This laptop has ~13 GB free, and the
person-level rows contain PII (names, schools). So:

- **Raw shards** → download one at a time, filter, **delete** (`data/revelio_raw/`, git-ignored).
- **Person-level derived** (founder names/schools) → stay local / in DB only
  (`data/revelio_derived/`, git-ignored). Never committed, never on the public site.
- **Only aggregates** (e.g. `% Stanford`, top-20 universities) go to `output/`
  and the dashboard.

## Files (from the Google Drive dump)

| File | Size | Keep? | Role |
|---|---|---|---|
| `revelio_company_mapping-000000.parquet` | 7.5 GB | scan once → matched rcids, then delete | our company domain → Revelio `rcid` |
| `revelio_individual_positions-*` (89) | ~107 GB | stream, keep only founder rows | who was founder/CEO at each `rcid` |
| `revelio_individual_user_education-*` (34) | ~7.8 GB | stream, keep only founders' rows | founder → university / degree / field |
| `revelio_individual_user-*` (30) | ~29 GB | stream, keep only founders' rows | founder demographics (name, gender, ethnicity, geo) |
| `revelio_individual_role_lookup_v3.parquet` | 0.5 MB | keep | decode role codes |
| `*.txt` (5 schema docs) | ~19 KB | keep (`data/revelio_schema/`) | authoritative column names |

Peak local footprint stays ≈ 8 GB (only during the company_mapping scan);
everything else is one ~1.3 GB shard at a time.

## Pipeline (streaming, download → filter → delete)

1. **Match companies → rcid.** Scan `company_mapping` in row-group chunks;
   join our companies (domain) to Revelio `rcid`. Emit
   `data/revelio_derived/matched_rcids.parquet` (small). Delete the raw file.
2. **Find founders.** For each `individual_positions` shard: keep rows where
   `rcid ∈ matched_rcids` AND the title/role is founder-like
   (founder / co-founder / founding / CEO / CTO-founder). Append to
   `data/revelio_derived/founder_positions.parquet`. Delete the shard.
3. **Education.** Collect founder `user_id`s. For each
   `individual_user_education` shard: keep rows for those users → append
   `data/revelio_derived/founder_education.parquet`. Delete the shard.
4. **Demographics.** Same pattern over `individual_user` →
   `data/revelio_derived/founder_users.parquet`. Delete the shard.
5. **Aggregate + load.** Build university / degree / demographic aggregates
   into `output/*.csv` (committed) and a `founders` table in the DB
   (person-level, local/Railway only). Surface on the dashboard Findings page.

## Download mechanics (Google Drive)

Data lives in a shared Google Drive folder.

- **Tiny files first** (schema docs + role lookup): easiest via `gdown` with a
  per-file share link, dropped into `data/revelio_schema/`.
- **Bulk shards**: use `rclone` against the Drive folder (no 50-file cap,
  supports name patterns, downloads one file at a time so we can delete as we
  go). `gdown --folder` is capped and not suitable for 150 files / 151 GB.

## Step 0 — confirm the schema (do this first)

```bash
# after dropping the 5 .txt files (and optionally one sample shard of each
# table) into data/revelio_schema/ or data/revelio_raw/:
python scripts/revelio/inspect_schema.py \
    data/revelio_raw/revelio_individual_positions-000000.parquet \
    data/revelio_raw/revelio_individual_user_education-000000.parquet \
    data/revelio_raw/revelio_individual_user-000000.parquet
```

The exact column names from this step determine the founder-detection filter
and the join keys in the extraction script (written next).
