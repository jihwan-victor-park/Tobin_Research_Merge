# Claim → evidence

Every numerical claim in `main.tex`, the script that produces it, and the
output file it lands in. Scripts run from `ai-startup-tracker/`:

```bash
railway run -s Postgres -- .venv/bin/python analysis/<script>.py
```

Results land in `ai-startup-tracker/results/`. Figures are built from those
CSVs alone by `analysis/make_figures.py` (no database access).

Status key: **V** = verified against live production data in this pass ·
**H** = historical, recorded in a project report but not reproducible now ·
**M** = model-adjudicated reference, human labels pending.

---

## §5 Data and measurement system

| Claim | Value | Script | Output | Status |
|---|---|---|---|---|
| Total resolved firms | 988,576 | `analysis/inventory.py` | `00_verification_status.csv` | V |
| Database A / B / unlisted | 650,200 / 281,395 / 56,981 | same | same | V |
| Country values; with country | 280; 954,370 (96.5%) | same | `00_top_countries.csv` | V |
| Founding year, whole DB | 93.9% | same | `00_field_coverage.csv` | V |
| Industry coverage | 92.4%, 17 verticals | same | `00_top_categories.csv` | V |
| Auxiliary tables (269,181 financing; 33,844 portfolio; 111,678 taxonomy; 53,480 enrichment) | — | same | console | V |
| Deterministic scrapers | 36 | `ls backend/scrapers/easy/*.py` | — | V |
| Sites attempted / succeeded | 410 / 220 (53.7%) | `data/scrape_instructions/*.yaml`, `last_success` key | — | V |
| Yield mean / median / max | 22.9 / 6 / 814 | same | — | V |
| Agent budget (10 / 12 / 8) | — | `backend/agentic/engine.py:1003,1122` | — | V |
| Health transitions (2 / 3 / 90d / 7d) | — | `backend/orchestrator/health.py` | — | V |
| Field coverage by bucket | Table 3 | `analysis/coverage_bias.py` | `06_field_coverage_by_bucket.csv` | V |
| AI-signal availability by bucket (tags 7.0/0.7/0.0%; verdicts 0.7/98.8/2.3%) | — | same | `05c_ai_signal_availability_by_bucket.csv` | V |
| Database B under tag-or-score = 1.3% vs 10.7% under the union | — | same | `01_ai_share_by_bucket.csv` | V |
| Provenance source tags in use | 9 tags | `analysis/inventory.py` (enrichment section) | console | V |

## §6 Results — time, geography, industry, concentration

| Claim | Value | Script | Output | Status |
|---|---|---|---|---|
| AI share by founding year (3.0% 2000 → 59.0% 2025) | — | `analysis/ai_trends.py` | `11_ai_formation_by_year.csv` | V |
| AI **count** peaks 2018 at 8,038 | — | same | same | V |
| Denominator 54,150 (2015) → 2,531 (2025) | — | same | same | V |
| Financed-only series 5.9% (2005) → 68.3% (2025) | — | same | `14_trend_constant_selection.csv` | V |
| Firms with recorded financing 17.3% → 43.0% | — | same | `13_cohort_entry_lag.csv` | V |
| Both databases show the trend (A 2.7→63.7; B 3.6→58.3) | — | same | `12_ai_formation_by_year_by_db.csv` | V |
| Country intensity (Israel 37.2%, US 29.4% recent) | — | `analysis/geography.py` | `20_country_ai.csv` | V |
| Country growth (US +20.4, Chile +19.7, Israel +18.1; Nigeria +5.8) | — | same | `21_country_ai_growth.csv` | V |
| Regional world-AI share (NA 45.0→57.6; Europe 22.1→17.1; East Asia 10.6→6.5) | — | same | `23_region_ai.csv` | V |
| HHI(AI) 0.190 (2000) → 0.155 (2017) → 0.726 (2025) | — | same | `22_concentration_by_cohort.csv` | V |
| HHI(all) 0.149 → 0.161 → 0.609 | — | same | same | V |
| Entropy 2.62 → 2.87; countries 59 → 103 → 43 | — | same | same | V |
| US share of AI firms 41.3% → 36.8% → 85.0% | — | same | same | V |
| Sector AI share early vs late (Data 35.9→71.4; Biotech 23.2→60.0; Food 3.7→13.0) | — | `analysis/industry.py` | `30_sector_ai.csv` | V |
| Location quotients (China hardware 2.43; Israel security 2.10; India education 2.04) | — | same | `32_location_quotient.csv` | V |

## §7 The unlisted layer

| Claim | Value | Script | Output | Status |
|---|---|---|---|---|
| **Headline: 23.8% / 12.4% / 10.7%** | — | `analysis/coverage_bias.py` | `01_ai_share_by_bucket.csv` | V |
| Gap vs A +11.45pp [11.09, 11.81], OR 2.21 [2.17, 2.26] | — | same | `02_coverage_gap_tests.csv` | V |
| Gap vs B +13.17pp, OR 2.62 | — | same | same | V |
| Five AI definitions (+11.4 / +9.6 / +7.9 / +6.3 / −5.3) | — | same | `01_`, `02_` | V |
| Common-support (mention) 12.9 / 6.5 / 4.4; OR 2.11, 3.21 | — | same | same | V |
| Unlisted channels (31,909 / 14,375 / 9,931 / 766) | — | same | `04_unlisted_by_channel.csv` | V |
| Leave-one-out gap 3.8–8.1pp, OR 1.64–2.46, all CIs exclude 0 | — | same | `05b_leave_one_out_common_support.csv` | V |
| Reference label 19.0 / 9.5 / 11.0; z=2.70 p=0.007; z=2.24 p=0.025 | — | `analysis/measurement_correction.py` | `09_reference_label_direct_comparison.csv` | M |
| Sensitivity 0.79/0.73/0.90; specificity 0.91/0.98/0.85 | — | `experiments/ai_classifier_eval.py` | `62_ai_classifier_by_bucket.csv` | M |
| Corrected prevalence 4.11 / 12.33 / 18.16 | — | `analysis/measurement_correction.py` | `07_measurement_corrected_prevalence.csv` | M |
| Corrected gap vs A +14.16 [4.80, 22.45], Pr(>0)=0.998 | — | same | `08_corrected_coverage_gap.csv` | M |
| Corrected gap vs B +5.94 [−3.08, 13.64], Pr(>0)=0.914 | — | same | same | M |
| Described-frame sizes 598,084 / 274,793 / 16,815 | — | same | console | V |
| Novelty by tier (56.6 / 55.7 / 31.8%) | — | `analysis/source_novelty.py` | `26_novelty_by_tier.csv` | V |
| Individual sources (YC 24.1, Techstars 33.6, Princeton 87.0) | — | same | `25_novelty_by_source.csv` | V |
| Tier cost/yield (77.3% vs 26.5% success; 4,084 vs 163 records/site; 24.5% vs 9.6% new) | — | same | `27_collection_cost_by_tier.csv` | V |
| Site-level cost–yield Spearman −0.03 [−0.19, +0.13] — **null** | — | same | console | V |

## §8 Validation

| Claim | Value | Script | Output | Status |
|---|---|---|---|---|
| Historical imputation modes (SF 33.7%, 11–50 70.6%, US 46.1%, 2020 19.1%) | — | `reports/ENRICHMENT_METHOD.md` | — | **H** |
| 7,553 estimated values removed | — | same | — | **H** |
| Fill rate 87.7% (estimate) vs 2.2% (grounded) | — | `experiments/imputation_experiment.py` | `42_imputation_fill_rate.csv` | V |
| Predicted SF 10.6% vs true 1.5% | — | same | `43_imputation_distribution_distortion.csv` | V |
| Predicted US 52.9% vs true 43.2% | — | same | same | V |
| Year modes 2010/2015/2018 (17.0/16.0/11.0%) vs true mode 2017 (7.2%) | — | same | `40_imputation_estimate_mode.csv` | V |
| TV / JSD: city 0.69 / 0.39; year 0.45 / 0.16; country 0.18 / 0.04 | — | same | `43_` | V |
| Accuracy: country 66.0%, city 14.1%, year ±2y 39.8%; median error 3y, 31% >5y | — | same | `44_imputation_accuracy.csv` | V |
| Classifier P/R/F1 table | — | `experiments/ai_classifier_eval.py` | `61_ai_classifier_performance.csv` | M |
| Per-bucket precision 0.47 / 0.84 / 0.58 | — | same | `62_` | M |
| Normalised names shared by >1 domain: 28,029 | — | `experiments/entity_resolution_eval.py` | `50_normalized_name_collisions.csv` | V |
| Production 6,193 keys / 15,945 firms; conservative 3,226 / 7,245 | — | same | `51_normalizer_comparison.csv` | V |
| Suffix list responsible for 54.6% of exposure | — | same | same | V |
| 10.0% of groups AI-mixed (618 of 6,193); 653 AI firms at risk | — | same | console | V |
| 1,857 variant pairs, 767 (41.3%) identical after normalisation | — | same | `52_name_variant_pairs.csv` | V |
| τ sweep flat 784 → 767; 215 AI-asymmetric accepted at every τ | — | same | `53_threshold_sweep.csv` | V |

## §9 Limitations

| Claim | Value | Script | Output | Status |
|---|---|---|---|---|
| Unlisted founding year 8.0%, industry 9.4% | — | `analysis/coverage_bias.py` | `06_` | V |
| Description 32.7% AI vs no description 13.8% | — | `analysis/source_novelty.py` | `29_missingness_outcome_correlation.csv` | V |
| Domain 27.7% vs 21.5%; founding year 27.6% vs 23.5% | — | same | same | V |
| Channel coverage 20.1% (portfolio) vs 5.1% (code host) | — | same | `28_missingness_by_channel.csv` | V |

---

## Claims deliberately NOT made

- No causal estimate of AI on firm formation, survival, or financing.
- No interpretation of the post-2020 concentration rise as an economic fact.
- No interpretation of the AI **count** series as a formation series.
- No claim that harder sources yield less at the individual-site level — the
  correlation was tested and is null.
- No entity-resolution precision figure — only exposure counts, which need no
  human judgement.
- No use of the longitudinal AI-repackaging results from earlier project work:
  the multi-vintage snapshot files were deleted to free disk and the numbers
  could not be re-verified in this pass. See `RESEARCH_GAPS.md`.
- No row-level licensed data reproduced anywhere.
