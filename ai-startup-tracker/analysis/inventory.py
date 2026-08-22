"""Phase 1: what data actually exists. Writes results/00_inventory_*.csv."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _db import q, save
import pandas as pd

print("== columns on companies ==")
cols = q("""select column_name, data_type from information_schema.columns
            where table_name='companies' order by ordinal_position""")
print(cols.to_string(index=False))

print("\n== field coverage over all companies ==")
fields = ["domain","country","city","description","founded_year","cohort_year",
          "grant_first_award_year","web_first_seen_year","team_size","stage",
          "total_raised","naics_code","categories","ai_score","cb_ai_tagged",
          "ai_mentioned","llm_ai_verified","domain_status","source_domain",
          "latitude","operating_status"]
sel = ",\n".join([f"count({f}) as {f}" for f in fields])
cov = q(f"select count(*) as n, {sel} from companies")
tot = int(cov['n'][0])
rows = [{"field": f, "n_present": int(cov[f][0]), "coverage_pct": round(100*int(cov[f][0])/tot,2)} for f in fields]
covdf = pd.DataFrame(rows).sort_values("coverage_pct", ascending=False)
print(f"total companies: {tot:,}")
print(covdf.to_string(index=False))
save(covdf, "00_field_coverage.csv")

print("\n== verification_status (source/coverage bucket) ==")
vs = q("select verification_status::text as verification_status, count(*) n from companies group by 1 order by 2 desc")
print(vs.to_string(index=False))
save(vs, "00_verification_status.csv")

print("\n== how firms entered: source_domain / incubator / github ==")
src = q("""
select
  case
    when exists (select 1 from incubator_signals s where s.company_id=c.id) then 'incubator_or_portfolio'
    when c.source_domain is not null then 'scraped_site'
    when c.verification_status::text like 'verified%' then 'commercial_import'
    else 'other'
  end as entry_channel,
  count(*) n
from companies c group by 1 order by 2 desc
""")
print(src.to_string(index=False))
save(src, "00_entry_channel.csv")

print("\n== founding-year coverage & range ==")
fy = q("""select min(founded_year) mn, max(founded_year) mx, count(founded_year) n_stated,
        count(coalesce(founded_year, cohort_year, grant_first_award_year, nullif(web_first_seen_year,0))) n_effective
        from companies""")
print(fy.to_string(index=False))

print("\n== countries ==")
cty = q("select count(distinct country) n_countries, count(country) n_with_country from companies")
print(cty.to_string(index=False))
top = q("select country, count(*) n from companies where country is not null group by 1 order by 2 desc limit 25")
print(top.to_string(index=False))
save(top, "00_top_countries.csv")

print("\n== industry categories ==")
cat = q("""select unnest(categories) as category, count(*) n from companies
           where categories is not null group by 1 order by 2 desc limit 30""")
print(cat.to_string(index=False))
save(cat, "00_top_categories.csv")

print("\n== AI flags ==")
ai = q("""select
  count(*) filter (where cb_ai_tagged) as cb_tag,
  count(*) filter (where ai_score >= 0.5) as score_ge_05,
  count(*) filter (where llm_ai_verified) as llm_true,
  count(*) filter (where llm_ai_verified is not null) as llm_any,
  count(*) filter (where ai_mentioned) as ai_mentioned,
  count(*) filter (where cb_ai_tagged or ai_score>=0.5 or llm_ai_verified) as ai_union
  from companies""")
print(ai.to_string(index=False))
save(ai, "00_ai_flag_counts.csv")

print("\n== company_enrichment provenance columns ==")
ec = q("""select column_name, data_type from information_schema.columns
          where table_name='company_enrichment' order by ordinal_position""")
print(ec.to_string(index=False))
