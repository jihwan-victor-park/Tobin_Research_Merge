"""
Who founds AI companies — Crunchbase founder + education analysis, AI-scoped.

Uses the CB 2023 people / jobs / degrees tables (680K founder-role positions,
1.6M people, 709K degrees). Founders = jobs with a founder title/role; AI
companies = CB category taxonomy. Focus is the AI-company founder population; a
non-AI reference column is shown only to give the AI numbers meaning.

Outputs (aggregates only — NO individual names written):
  43_cb_ai_founder_profile.csv      team size, gender, serial-founder rate
  44_cb_ai_founder_education.csv     highest-degree mix (PhD / Master / Bachelor)
  45_cb_ai_founder_fields.csv        top fields of study
  46_cb_ai_founder_institutions.csv  top institutions

    python3 scripts/cb_ai_founders.py
"""
from __future__ import annotations

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "pb_longitudinal"
OUT = ROOT / "output"

AICAT = ("(lower(category_list) LIKE '%artificial intelligence%' "
         "OR lower(category_list) LIKE '%machine learning%' "
         "OR lower(category_list) LIKE '%generative%' "
         "OR lower(category_list) LIKE '%natural language%' "
         "OR lower(category_list) LIKE '%computer vision%' "
         "OR lower(category_list) LIKE '%deep learning%' "
         "OR lower(category_list) LIKE '%neural network%' "
         "OR lower(category_groups_list) LIKE '%artificial intelligence%')")

# highest-degree rank from the messy degree_type field
DEG_RANK = """CASE
  WHEN regexp_matches(lower(degree_type), 'phd|ph\\.d|doctor|dphil|d\\.phil|sc\\.d|doctorate') THEN 3
  WHEN regexp_matches(lower(degree_type), 'master|mba|msc|m\\.sc|meng|m\\.eng|llm|mph|mfa|(^|[^a-z])m\\.?[sa]([^a-z]|$)') THEN 2
  WHEN regexp_matches(lower(degree_type), 'bachelor|bba|bsc|beng|(^|[^a-z])b\\.?[sa]([^a-z]|$)|(^|[^a-z])ab([^a-z]|$)') THEN 1
  ELSE 0 END"""


def main() -> None:
    con = duckdb.connect(); con.execute("SET enable_progress_bar=false")

    # founder positions -> (person, org, is_ai company)
    con.execute(f"""CREATE TABLE f AS
        SELECT DISTINCT j.person_uuid pid, j.org_uuid oid, o.is_ai
        FROM (SELECT person_uuid, org_uuid FROM read_parquet('{D}/cb2023_jobs.parquet')
              WHERE person_uuid IS NOT NULL AND org_uuid IS NOT NULL
                AND (lower(coalesce(title,'')) LIKE '%founder%' OR lower(coalesce(job_type,'')) LIKE '%founder%')) j
        JOIN (SELECT uuid, {AICAT} AS is_ai FROM read_parquet('{D}/cb2023_organizations.parquet')) o
             ON j.org_uuid = o.uuid""")
    tot_pos = con.execute("SELECT count(*) FROM f").fetchone()[0]
    ai_orgs = con.execute("SELECT count(DISTINCT oid) FROM f WHERE is_ai").fetchone()[0]
    ai_founders = con.execute("SELECT count(DISTINCT pid) FROM f WHERE is_ai").fetchone()[0]
    print(f"founder-position links: {tot_pos:,}")
    print(f"AI companies with a named founder: {ai_orgs:,}  |  distinct AI founders: {ai_founders:,}\n")

    # ---- profile: team size, gender, serial rate (AI vs non-AI ref) ----
    con.execute(f"""CREATE TABLE ppl AS SELECT uuid pid, gender FROM read_parquet('{D}/cb2023_people.parquet')""")
    rows = []
    for label, flag in [("AI", "is_ai"), ("Non-AI (ref)", "NOT is_ai")]:
        team = con.execute(f"SELECT avg(nf) FROM (SELECT oid, count(DISTINCT pid) nf FROM f WHERE {flag} GROUP BY oid)").fetchone()[0]
        # gender among founders
        g = con.execute(f"""SELECT
            count(*) FILTER (WHERE lower(gender)='female') fem,
            count(*) FILTER (WHERE lower(gender) IN ('male','female')) known
            FROM (SELECT DISTINCT pid FROM f WHERE {flag}) d JOIN ppl USING(pid)""").fetchone()
        # serial founders: founded >1 distinct company
        serial = con.execute(f"""SELECT
            count(*) FILTER (WHERE norg>1) mult, count(*) total
            FROM (SELECT pid, count(DISTINCT oid) norg FROM f WHERE {flag} GROUP BY pid)""").fetchone()
        rows.append({"cohort": label,
                     "avg_founders_per_company": round(team, 2),
                     "pct_female_founders": round(100*g[0]/g[1], 1) if g[1] else None,
                     "pct_serial_founders": round(100*serial[0]/serial[1], 1) if serial[1] else None})
    import pandas as pd
    prof = pd.DataFrame(rows)
    print("=== AI founder profile (CB) ===")
    print(prof.to_string(index=False))
    prof.to_csv(OUT / "43_cb_ai_founder_profile.csv", index=False)

    # ---- education: highest degree per founder ----
    con.execute(f"""CREATE TABLE hd AS
        SELECT person_uuid pid, max({DEG_RANK}) lvl
        FROM read_parquet('{D}/cb2023_degrees.parquet')
        WHERE person_uuid IS NOT NULL GROUP BY person_uuid""")
    rows = []
    for label, flag in [("AI", "is_ai"), ("Non-AI (ref)", "NOT is_ai")]:
        r = con.execute(f"""SELECT
            count(*) with_degree,
            round(100.0*count(*) FILTER (WHERE lvl=3)/count(*),1) pct_phd,
            round(100.0*count(*) FILTER (WHERE lvl=2)/count(*),1) pct_masters,
            round(100.0*count(*) FILTER (WHERE lvl=1)/count(*),1) pct_bachelor
            FROM (SELECT DISTINCT pid FROM f WHERE {flag}) d JOIN hd USING(pid) WHERE lvl>0""").fetchone()
        rows.append({"cohort": label, "founders_with_a_degree": r[0],
                     "pct_PhD": r[1], "pct_Masters_incl_MBA": r[2], "pct_Bachelor_only": r[3]})
    edu = pd.DataFrame(rows)
    print("\n=== Highest degree among founders with a degree record ===")
    print(edu.to_string(index=False))
    edu.to_csv(OUT / "44_cb_ai_founder_education.csv", index=False)

    # ---- top fields of study (AI founders) ----
    fields = con.execute(f"""
        SELECT trim(subject) field, count(*) n
        FROM (SELECT DISTINCT pid FROM f WHERE is_ai) d
        JOIN read_parquet('{D}/cb2023_degrees.parquet') g ON d.pid=g.person_uuid
        WHERE subject IS NOT NULL AND trim(subject)<>'' GROUP BY 1 ORDER BY 2 DESC LIMIT 20""").fetchdf()
    print("\n=== Top fields of study — AI founders ===")
    print(fields.head(12).to_string(index=False))
    fields.to_csv(OUT / "45_cb_ai_founder_fields.csv", index=False)

    # ---- top institutions (AI founders) ----
    inst = con.execute(f"""
        SELECT trim(institution_name) institution, count(*) n
        FROM (SELECT DISTINCT pid FROM f WHERE is_ai) d
        JOIN read_parquet('{D}/cb2023_degrees.parquet') g ON d.pid=g.person_uuid
        WHERE institution_name IS NOT NULL AND trim(institution_name)<>'' GROUP BY 1 ORDER BY 2 DESC LIMIT 20""").fetchdf()
    print("\n=== Top institutions — AI founders ===")
    print(inst.head(12).to_string(index=False))
    inst.to_csv(OUT / "46_cb_ai_founder_institutions.csv", index=False)

    print("\nsaved -> output/43_cb_ai_founder_profile.csv .. 46_cb_ai_founder_institutions.csv")


if __name__ == "__main__":
    main()
