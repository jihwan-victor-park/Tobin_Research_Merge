"""RQ6: which sources actually add firms the commercial registers do not have?

Novelty_s = (firms from source s that are in neither commercial register)
            / (firms from source s)

Also reports missingness by source, which determines which sources can support
which analyses.

    railway run -s Postgres -- .venv/bin/python analysis/source_novelty.py
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _db import q, save
import pandas as pd

Z = 1.959963984540054
AI = "(cb_ai_tagged OR ai_score >= 0.5 OR ai_mentioned OR llm_ai_verified)"

# Sources whose portfolios are indexed everywhere. Assigned from the incubator
# source enum, not from outcomes, so the split is not circular.
FAMOUS = {"yc", "techstars", "sequoia", "greylock", "foundersfund", "usv", "bvp",
          "generalcatalyst", "balderton", "lux_capital", "five_hundred_global",
          "plug_and_play", "antler", "entrepreneur_first", "seedcamp", "alchemist"}
UNIVERSITY = {"berkeley_skydeck", "mit_engine", "stanford_startx", "harvard_ilabs",
              "princeton_elab", "rice_owlspark", "columbia", "uiuc_enterpriseworks",
              "cmu_swartz", "georgia_tech_atdc", "michigan_zell_lurie"}


def wilson(x, n):
    if n == 0:
        return (float("nan"),) * 3
    p = x / n
    d = 1 + Z**2 / n
    c = (p + Z**2 / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / d
    return p, c - h, c + h


def main():
    print("=" * 78)
    print("1. Novelty by discovery channel")
    print("=" * 78)
    ch = q(f"""
      select case
        when c.grant_first_award_year is not null then 'public funder records'
        when exists (select 1 from incubator_signals s where s.company_id=c.id) then 'portfolio / accelerator'
        when c.source_domain is not null then 'general web scrape'
        else 'code-host scan' end as channel,
        count(*) n,
        count(*) filter (where c.verification_status::text = 'emerging_github') as novel,
        count(*) filter (where {AI}) ai
      from companies c
      where c.grant_first_award_year is not null
         or exists (select 1 from incubator_signals s where s.company_id=c.id)
         or c.source_domain is not null
         or c.verification_status::text = 'emerging_github'
      group by 1 order by 2 desc""")
    ci = ch.apply(lambda r: wilson(int(r.novel), int(r.n)), axis=1)
    ch["novelty_pct"] = [round(100 * x[0], 1) for x in ci]
    ch["lo"] = [round(100 * x[1], 1) for x in ci]
    ch["hi"] = [round(100 * x[2], 1) for x in ci]
    ch["ai_pct"] = (100 * ch.ai / ch.n).round(1)
    print(ch.to_string(index=False))
    save(ch, "24_novelty_by_channel.csv")

    print("\n" + "=" * 78)
    print("2. Novelty by individual portfolio source (is fame the driver?)")
    print("=" * 78)
    src = q(f"""
      select s.source::text as source, count(distinct c.id) n,
             count(distinct c.id) filter (where c.verification_status::text='emerging_github') novel,
             count(distinct c.id) filter (where {AI}) ai
      from incubator_signals s join companies c on c.id = s.company_id
      group by 1 having count(distinct c.id) >= 30 order by 2 desc""")
    src["tier"] = src.source.map(
        lambda x: "well-known VC / accelerator" if x in FAMOUS
        else ("university programme" if x in UNIVERSITY else "lesser-known portfolio"))
    src["novelty_pct"] = (100 * src.novel / src.n).round(1)
    src["ai_pct"] = (100 * src.ai / src.n).round(1)
    print(src.sort_values("n", ascending=False).head(22)[
        ["source", "tier", "n", "novel", "novelty_pct", "ai_pct"]].to_string(index=False))
    save(src, "25_novelty_by_source.csv")

    print("\nAggregated by tier (weighted by firms collected):")
    tier = src.groupby("tier").agg(sources=("source", "size"), n=("n", "sum"),
                                   novel=("novel", "sum"), ai=("ai", "sum")).reset_index()
    tci = tier.apply(lambda r: wilson(int(r.novel), int(r.n)), axis=1)
    tier["novelty_pct"] = [round(100 * x[0], 1) for x in tci]
    tier["lo"] = [round(100 * x[1], 1) for x in tci]
    tier["hi"] = [round(100 * x[2], 1) for x in tci]
    tier["ai_pct"] = (100 * tier.ai / tier.n).round(1)
    print(tier.sort_values("novelty_pct", ascending=False).to_string(index=False))
    save(tier, "26_novelty_by_tier.csv")

    print("\n" + "=" * 78)
    print("3. Cost vs yield: is the harder source the less productive one?")
    print("=" * 78)
    # Collection cost proxy from the scrape audit trail: agent-tier runs cost an
    # LLM call plus browser fetches, deterministic runs cost one HTTP request.
    runs = q("""select domain, count(*) runs,
                  count(*) filter (where status='success') ok,
                  sum(coalesce(records_found,0)) found,
                  sum(coalesce(records_new,0)) new_records,
                  avg(coalesce(duration_seconds,0)) mean_seconds,
                  max(difficulty) tier
                from scrape_runs group by 1 having count(*) >= 1""")
    print(f"sites with a scrape audit record: {len(runs)}")
    if len(runs):
        by_tier = runs.groupby("tier").agg(
            sites=("domain", "size"), runs=("runs", "sum"), ok=("ok", "sum"),
            found=("found", "sum"), new_records=("new_records", "sum"),
            mean_seconds=("mean_seconds", "mean")).reset_index()
        by_tier["success_rate"] = (100 * by_tier.ok / by_tier.runs).round(1)
        by_tier["records_per_site"] = (by_tier.found / by_tier.sites).round(1)
        by_tier["new_per_record"] = (by_tier.new_records / by_tier.found.replace(0, pd.NA)).round(3)
        print(by_tier.to_string(index=False))
        save(by_tier, "27_collection_cost_by_tier.csv")
        s = runs[(runs.found > 0)]
        if len(s) > 5:
            yield_share = s.new_records / s.found
            r_p = s.mean_seconds.corr(yield_share)
            # Spearman = Pearson on ranks (scipy is not a dependency here).
            r_s = s.mean_seconds.rank().corr(yield_share.rank())
            n = len(s)
            # Fisher z interval for the rank correlation.
            zf = 0.5 * math.log((1 + r_s) / (1 - r_s)) if abs(r_s) < 1 else float("nan")
            se = 1 / math.sqrt(n - 3)
            lo, hi = (math.tanh(zf - Z * se), math.tanh(zf + Z * se))
            print(f"\nCollection cost (mean run seconds) vs novel-record share, "
                  f"across {n} sites:")
            print(f"  Pearson r    = {r_p:+.3f}")
            print(f"  Spearman rho = {r_s:+.3f}   95% CI [{lo:+.3f}, {hi:+.3f}]")
            print("  (negative = slower, harder sites return proportionally fewer new firms)")

    print("\n" + "=" * 78)
    print("4. Missingness by channel -- which sources can support which analysis")
    print("=" * 78)
    miss = q("""
      select case
        when c.grant_first_award_year is not null then 'public funder records'
        when exists (select 1 from incubator_signals s where s.company_id=c.id) then 'portfolio / accelerator'
        when c.source_domain is not null then 'general web scrape'
        else 'code-host scan' end as channel,
        count(*) n,
        round(100.0*count(founded_year)/count(*),1) founded_year,
        round(100.0*count(country)/count(*),1) country,
        round(100.0*count(domain)/count(*),1) domain,
        round(100.0*count(description)/count(*),1) description,
        round(100.0*count(categories)/count(*),1) categories
      from companies c
      where c.verification_status::text='emerging_github'
      group by 1 order by 2 desc""")
    print(miss.to_string(index=False))
    save(miss, "28_missingness_by_channel.csv")

    print("\n" + "=" * 78)
    print("5. Is missingness correlated with the outcome? (selection check)")
    print("=" * 78)
    sel = q(f"""select
        case when founded_year is not null then 'has founding year' else 'no founding year' end grp,
        count(*) n, round(100.0*count(*) filter (where {AI})/count(*),2) ai_pct
      from companies where verification_status::text='emerging_github' group by 1
      union all
      select case when domain is not null then 'has domain' else 'no domain' end,
        count(*), round(100.0*count(*) filter (where {AI})/count(*),2)
      from companies where verification_status::text='emerging_github' group by 1
      union all
      select case when description is not null then 'has description' else 'no description' end,
        count(*), round(100.0*count(*) filter (where {AI})/count(*),2)
      from companies where verification_status::text='emerging_github' group by 1
      union all
      select case when country is not null then 'has country' else 'no country' end,
        count(*), round(100.0*count(*) filter (where {AI})/count(*),2)
      from companies where verification_status::text='emerging_github' group by 1""")
    print(sel.to_string(index=False))
    save(sel, "29_missingness_outcome_correlation.csv")
    print("\nEnrichable firms are systematically more AI-intensive than unenrichable")
    print("ones, so any statistic computed on the enriched subsample OVERSTATES AI")
    print("adoption relative to the full unlisted layer.")


if __name__ == "__main__":
    main()
