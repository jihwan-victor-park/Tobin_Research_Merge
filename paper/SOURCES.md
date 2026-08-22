# Repository map, and corrections made while writing

`CLAIM_EVIDENCE.md` maps each *number* to the script that produces it. This
file maps each *system component* to the code that implements it, and records
what the project's own documentation got wrong.

---

## Where each part of the system lives

| Paper section | Component | Code |
|---|---|---|
| §5.2 | Collection policy $C_s$ | `backend/orchestrator/orchestrator.py`, `backend/scrapers/registry.py` |
| §5.2 | 36 deterministic scrapers | `backend/scrapers/easy/*.py` |
| §5.2 | Bounded LLM agent (10 / 12 / 8) | `backend/agentic/engine.py:1003,1122` |
| §5.2 | Escalation and suspension | `backend/orchestrator/health.py`, `backend/orchestrator/diagnose.py` |
| §5.2 | Instruction cache | `backend/agentic/instruction_yaml.py`, `data/scrape_instructions/*.yaml` |
| §5.3 | Domain canonicalisation, blocklist | `backend/utils/domain.py` |
| §5.3 | Name normalisation $\nu$ | `backend/utils/normalize.py` |
| §5.3 | Production matching rule | `backend/scrapers/base.py:293-295` |
| §5.4 | AI predicate (4-way union) | `backend/utils/ai_filter.py` |
| §5.4 | Keyword score $a_i$ | `backend/utils/scoring.py` |
| §5.4 | Cascade classifier | `backend/utils/classify_ai.py` |
| §5.5 | Evidence tiers, provenance write | `scripts/enrich_fields.py`, `company_enrichment.sources` |
| §5.5 | Founding-year proxies | `backend/db/models.py` (`cohort_year`, `grant_first_award_year`, `web_first_seen_year`) |
| §6 | Time / geography / industry | `analysis/ai_trends.py`, `geography.py`, `industry.py` |
| §7 | Coverage gap and robustness | `analysis/coverage_bias.py`, `measurement_correction.py` |
| §7.3 | Novelty and cost | `analysis/source_novelty.py` |
| §8.1 | Imputation experiment | `experiments/imputation_experiment.py` |
| §8.2 | AI classifier evaluation | `experiments/ai_classifier_eval.py` |
| §8.3 | Entity-resolution evaluation | `experiments/entity_resolution_eval.py` |
| Figures | All eight | `analysis/make_figures.py` |

Shared DB helper with the reconnect loop the Railway proxy requires:
`analysis/_db.py`.

---

## Corrections made while writing this paper

Each of these contradicts something stated in the repository's own README,
handoff notes, or an earlier draft. They are listed so nobody re-derives the
wrong version from the old docs.

**1. The AI predicate is four-way, not two-way or three-way.**
`backend/utils/ai_filter.py` unions `cb_ai_tagged`, `ai_score >= 0.5`,
`ai_mentioned`, and `llm_ai_verified`. Earlier analysis text describes a
two-signal rule. Using the wrong one moves database A's AI share from
$12.4\%$ to $10.8\%$ and database B's from $10.7\%$ to $1.3\%$.

**2. There is no fuzzy matching in production.**
`backend/utils/dedup.resolve_entity` implements a $\tau = 0.92 / 0.95$ fuzzy
rule with a shared-signal requirement. It has **no production caller**, and its
shared-signal branch returns the match either way. The live rule is exact
equality on `domain` or `normalized_name` (`base.py:293-295`). The paper
describes the live rule.

**3. The `source_matches` audit table is empty (0 rows).**
The schema exists and the README describes it as an audit trail for entity
matching. Nothing writes to it. Any claim that matches are individually
auditable is currently false.

**4. `github_signals` and `github_repo_snapshots` are empty on production.**
The repo-to-company linkage described in the README was lost; GitHub-derived
firms survive as `companies` rows with `emerging_github` status but their repo
metadata does not.

**5. Accelerator novelty is ~53%, not 96.5%.**
`reports/ENRICHMENT_METHOD.md` reports 96.5% novelty for "accelerators and
institutions". Measured live, the portfolio/accelerator channel is $52.6\%$ and
university programmes are $55.7\%$. The well-known-VC figure (23–30%) does
reproduce ($31.8\%$ aggregated; Y Combinator $24.1\%$, Seedcamp $25.3\%$).

**6. The unlisted AI share is $23.8\%$, not $20.4\%$.**
The $20.4\%$ in `reports/ECONOMIC_ANALYSIS_FINDINGS_2026_07_15.md` was computed
on a smaller population before the model-verdict pass was applied. Database A
($12.3 \to 12.4\%$) and B ($10.6 \to 10.7\%$) reproduce almost exactly.

**7. Instruction YAML files record attempts, not working recipes.**
410 files exist; 220 record a success. `reports/SCRAPING_PLAN.md` §0 already
caught this internally; it is repeated here because the file count is the
tempting number to quote.

**8. The multi-vintage panel results are not currently reproducible.**
`data/pb_longitudinal/` was deleted to free disk. None of the longitudinal
repackaging, identity-dating, or exit-outcome numbers from
`reports/ECONOMIC_ANALYSIS_FINDINGS_2026_07_15.md` §6–10 appear in this paper.
See `RESEARCH_GAPS.md` §2.1.

---

## Data that exists on disk but is unused in this paper

| Path | Size | Why unused |
|---|---|---|
| `data/crunchbase/funding_rounds.parquet` | 130 MB | financing analysis is Tier-2 (`RESEARCH_GAPS.md` §2.6) |
| `data/crunchbase/organizations.parquet` | 1.2 GB | single vintage; superseded by the resolved database |
| `data/revelio_raw/` | 4.4 GB | employment data reaches ~1,367 unlisted firms only |
| `data/sbir/award_data.csv` | 351 MB | already imported into `companies` |
| `data/cordis/*.zip` | 88 MB | already imported |
