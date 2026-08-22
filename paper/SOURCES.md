# Where every number in `main.tex` comes from

Each row names the claim, the value, and the artifact in this repo that
produces it. Anything not listed here is not in the paper.

## Infrastructure scale (§3)

| Claim | Value | Source |
|---|---|---|
| Lines of Python | ~43,000 | `backend` 11,833 + `scripts` 22,990 + `frontend` 8,448 |
| Commits / window / authors | 189, Feb 14 – Aug 17 2026, 2 authors | `git log` |
| Company records | 986,326 | `reports/ECONOMIC_ANALYSIS_FINDINGS_2026_07_15.md` §1 |
| Deterministic scrapers | 36 | `backend/scrapers/easy/*.py` |
| Agent budget (10 iters / 12 fetch / 8 rendered) | — | `backend/agentic/engine.py:1003,1122` |
| Health-state transitions (2 / 3 / 90d / 7d) | — | `backend/orchestrator/health.py`, `README.md` |
| Sites attempted / succeeded | 410 / 220 (53.7%) | `data/scrape_instructions/*.yaml`, `last_success` key |
| Strategy split (188/15/12) | single-page 87.7%, subpage 6.8%, pagination 5.5% | same |
| Yield: 5,040 records, mean 22.9, median 6, p90 50, max 814 | — | same |
| Validation means (name 1.000, dup 0.004, complete 0.996) | — | same |
| Yield-projection error (files are attempts, not playbooks) | — | `reports/SCRAPING_PLAN.md` §0 |

Recompute the YAML statistics with the snippet in the session scratchpad, or:
`python - <<'PY'` over `data/scrape_instructions/*.yaml`, counting `last_success`.

## Entity resolution (§3.6)

| Claim | Value | Source |
|---|---|---|
| Domain-canonical key, public-suffix reduction | — | `backend/utils/domain.py:canonicalize_domain` |
| Non-product domain blocklist | — | `backend/utils/domain.py:NON_PRODUCT_DOMAINS` |
| Fuzzy thresholds τ = 0.92 / 0.95 | — | `backend/utils/dedup.py:NAME_MATCH_THRESHOLD` |
| Shared-signal requirement | — | `backend/utils/dedup.py:resolve_entity` |
| Match audit trail | — | `source_matches` table, `backend/db/models.py` |

## AI classification (§4)

| Claim | Value | Source |
|---|---|---|
| Score weights 0.3/0.2/0.2/0.1/0.2, threshold 0.5 | — | `backend/utils/scoring.py:compute_ai_score`, `backend/utils/ai_filter.py` |
| Database-B ceiling 0.3 → structurally excluded | — | `HANDOFF.md`, "Open Question" |
| Threshold 0.1 adds ~22K with flat ~1,200/yr cohort profile | — | `HANDOFF.md` |
| Cascade (strong keyword / no tech term / LLM) | — | `backend/utils/classify_ai.py` |
| Tag-vs-text, n=500: 19.8 / 14.8 / 12.6 / 0.8 / 52.0 | — | `output/40_cb_repackager_summary.csv`; `scripts/classify_repackagers_cb.py` |

## Enrichment (§5)

| Claim | Value | Source |
|---|---|---|
| Evidence tiers + unit costs ($0 / $0.003 / $0.0007) | — | `reports/ENRICHMENT_METHOD.md` Rule 2 |
| Founding-year coverage 8.6% → 59.5% via registries | — | same |
| 7,420 firms gained named executives | — | same |
| Imputation modes: SF 33.7%, 11–50 70.6%, US 46.1%, 2020 19.1% | — | same, Rule 3 |
| 7,553 estimated values withdrawn | — | same |
| Per-field coverage table | — | same, "Current coverage" |
| Intersection coverage 5,778 (21.4% of 26,981) | — | same |
| `ai_subfield` = other 63.7% | — | same, "Known limits" |
| Provenance store `{field: {source, confidence}}` | — | `scripts/enrich_fields.py:upsert`, `company_enrichment.sources` |
| Founding-year proxy COALESCE order | — | `backend/db/models.py` (`cohort_year`, `grant_first_award_year`, `web_first_seen_year`) |
| cohort_year 2,414 / grant year 7,681 | — | `reports/ECONOMIC_ANALYSIS_FINDINGS_2026_07_15.md` §4h |

## Observability frontier (§6)

| Claim | Value | Source |
|---|---|---|
| Funnel 56,981 → 45,812 → 36,534 → 26,981; 11,169 personal; 4,527 by rule | — | `reports/ENRICHMENT_METHOD.md` Rule 1 |
| **AI share 20.4 / 12.3 / 10.6 / 26.3** | — | `output/13_hidden_vs_institutional_ai_adoption.csv` |
| Sector tilt (healthcare 10.1 vs 3.2 etc.) | — | `output/12_hidden_vs_institutional_verticals.csv`; findings §4i |
| Region shares (NA 57.9% …) and continents | — | `reports/ENRICHMENT_METHOD.md` "Country" |
| 64% of year-covered unlisted firms are grant firms | — | findings §4i composition caveat |
| Discovery yield by channel (100 / 96.5 / 76 / 23–30 / 75.8) | — | `reports/ENRICHMENT_METHOD.md` "Where hidden companies come from" |
| Taxonomy tilt, dev tools 2,450 / 31,377 | — | `output/49_taxonomy_full_domain_tilt.csv` |
| Formation trend 3.0 → 9.1 → 17.3 → 43.4 → 58.3 | — | `output/01_formation_timeline.csv` |

## Longitudinal demonstrations (§7)

| Claim | Value | Source |
|---|---|---|
| Panel 641,442; 3.8% → 4.7%; +7,648 / −2,206 | — | findings §6; `scripts/pb_longitudinal_repackaging.py` |
| Diff-classifier n=2,000: 18.1 / 34.5 / 10.5 / 3.4 / 33.5 | — | `output/22_pb_repackaging_summary.csv` |
| Triangulation 28% no growth vs 3.4% text | — | findings §6 `--triangulate` |
| Sector: IT 2.5% added; B2B 20% washing | — | `output/24_repackaging_by_sector.csv` |
| Cohort: 0.7 / 1.6 / 3.0 / 4.0 | — | `output/25_repackaging_by_cohort.csv` |
| Identity timing 21.3 / 6.0 / 57.5 | — | `output/34_cb_ai_identity_timing.csv` |
| 0.3% generative in "already AI 2023"; 50% non-AI in 2021 | — | findings §10j correction 2 |
| Agents 13,906 (10.1%) / 8,257 (6.0%) of 137,857 | — | findings §10j correction 1 |
| Substring bug 0.48% → 0.007 / 0.011 / 0.079 | — | findings §10g |
| Exits 577,921 matched | — | `output/23_exit_outcomes.csv` |
| Cohort-matched closure 6.5/13.7, 3.5/17.8, 2.2/6.6 | — | `output/27_repackaging_exit_cohort_matched.csv` |
| Founders: PhD 20.5 vs 10.8; 1.72 vs 1.39; serial 3.1 vs 11.9; female 10.0 vs 13.4 | — | `output/43_…`, `output/44_cb_ai_founder_education.csv` |
| Seed → next round 23.2 vs 18.8 | — | `output/30_cb_graduation_by_ai.csv` |
| Gender contradiction with employment-database aggregate | — | findings §10h note vs `output/15_founder_gender_prestige.csv` |
| Archive null: 88–90% no 2021 homepage | — | findings §9; `scripts/wayback_repackaging.py` |

## Limitations (§8)

| Claim | Value | Source |
|---|---|---|
| Stated founding year 8.3% | — | findings §4a |
| Selection: 27.5 vs 20.1 (year), 28.0 vs 16.8 (domain) | — | findings §4b |
| Channel coverage 20.1% vs 4.1% | — | findings §4c |
| No frame / no denominator | — | findings §4d |
| Domain liveness is a proxy | — | findings §4e; `scripts/check_domain_liveness.py` |
| No funding/headcount/exit for unlisted layer | — | findings §4f |
| Healthcare overstated at 20.8% | — | `reports/ENRICHMENT_METHOD.md` |
| Employment source has no founder role category | — | findings §3 caveat (`role_k1500`) |
| June run: 706 runs, 73% error rate | — | memory `project_pipeline_state_jul2026` |

## Deliberately **not** claimed

- No per-field extraction precision/recall/F1 — there is no labeled gold set.
- No causal estimate of AI on firm formation or survival.
- No learned entity-resolution model — the current matcher is a rule.
- No source-reliability model — described in §9 as unimplemented.
- No row-level licensed data reproduced anywhere in the paper.
