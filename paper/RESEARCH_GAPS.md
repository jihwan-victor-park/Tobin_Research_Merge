# Research gaps

Three tiers. Tier 1 items change what the paper is allowed to claim; Tier 2
items would make it materially stronger; Tier 3 is beyond this paper.

Status labels used across the project: **EXISTING** (was already implemented) ·
**IMPLEMENTED** (added in this research pass) · **VERIFIED** (implemented and
reproduced against live data) · **PROPOSED** (designed, not built).

---

## Tier 1 — required before the paper is final

### 1.1 Human-adjudicated gold sets  *(PROPOSED — sampling done, labels missing)*
Every precision, recall and $F_1$ figure, and the whole measurement-error
correction, currently rests on a **model-adjudicated** reference label. Two
files are exported and waiting:

| File | Rows | What to label |
|---|---|---|
| `results/64_ai_gold_set_for_authors.csv` | 150 | `human_label` ∈ {0,1}: is AI central to what this firm builds or sells? |
| `results/54_er_adjudication_sample.csv` | 215 | `same_company` ∈ {0,1}: are these two names the same firm? |

Both have `labeller` columns. Alastair and Jihwan should label independently,
report inter-rater agreement (Cohen's κ), and adjudicate disagreements. Then
re-run `experiments/ai_classifier_eval.py` and
`analysis/measurement_correction.py` against the human labels.

**Why it is Tier 1:** the corrected gap against Database B
(`+5.9pp [−3.08, 13.64]`) does not currently clear zero, and the interval is
dominated by the 200-per-bucket validation sample rather than by the population
counts. Labelling more firms is the cheapest way to resolve it. 200 per bucket
was chosen for cost; 500 per bucket would roughly halve the interval width.

### 1.2 Re-resolve the database with a corrected normaliser  *(PROPOSED)*
`normalize_company_name` strips `ai`, `io`, `labs`, `tech`, `technologies`,
`systems`, `software` as company suffixes, which merges `Compose.ai` into
`Compose` and `K-Scale Labs` into `Scale AI`. This accounts for 54.6% of all
name-collision exposure and is AI-correlated (10.0% of collision groups mix an
AI-marked with a non-AI-marked firm).

The fix is one line — remove the brand-carrying tokens from
`COMPANY_SUFFIXES`. The consequence is not one line: re-resolution changes
every count in the paper. Sequence it as (a) fix the normaliser, (b) rebuild
keys into a shadow table, (c) diff against the live keys, (d) re-run all of
`analysis/`, (e) report how much each headline moved.

Expected direction: the current merge deletes AI-named firms, so the coverage
gap should widen, not narrow.

### 1.3 Decide what to do about the post-2020 cohorts  *(EXISTING problem, no fix yet)*
The observed denominator falls from 54,150 (2015 cohort) to 2,531 (2025), and
the fraction of firms with recorded financing rises from 17.3% to 43.0%. The
paper currently handles this by refusing to interpret the count series or the
post-2020 concentration rise. A better answer would be an explicit
observability model — e.g. estimate the register's entry hazard from the
first-seen distribution of older cohorts and reweight — but that needs a
vintage panel we no longer have on disk (§2.1).

---

## Tier 2 — would strengthen the paper

### 2.1 Restore the multi-vintage panels  *(EXISTING, then lost)*
Earlier project work built a 641,442-firm panel across two vintages of
Database B and four vintages of Database A, producing results on AI
repackaging, identity dating, and exit outcomes (see
`reports/ECONOMIC_ANALYSIS_FINDINGS_2026_07_15.md` §6–10). The raw snapshot
files under `data/pb_longitudinal/` were deleted to free disk and **none of
those numbers could be re-verified in this pass**, so none appear in the paper.
Re-downloading them from the shared folder would restore: a genuine
before/after design around late 2022, the entry-hazard model in §1.3, and the
exit-outcome analysis.

Note that the earlier work had already corrected itself twice (a "6%
repackaging" figure that was really a floor of ~50%, and an `llm`-matches-
`enrollment` substring bug). Any restored analysis should be re-derived, not
copied.

### 2.2 An exposure-based design  *(PROPOSED)*
`bena2025prompted` construct industry exposure to generative AI from the task
composition of model queries and use cross-industry variation. Our data has
sector, country, and founding year for 900K+ firms, so the same design is
mechanically feasible:
$$Y_{cst} = \beta\,(\text{Exposure}_{s} \times \text{Post}_t) + \alpha_c + \gamma_s + \delta_t + \varepsilon_{cst}.$$
The obstacle is not the regression, it is that observability is itself a
function of treatment — recently founded AI firms are indexed faster. Do not
run this until §1.3 is resolved.

### 2.3 Coverage against an external reference  *(PROPOSED)*
For countries with a public business register, compute
$\text{CoverageRatio}_c = P_{\text{ours}}(c)/P_{\text{reference}}(c)$. This
would convert the paper's relative statements into calibrated ones and permit
reweighting toward a population quantity. Candidate references: national
statistical office business demography series.

### 2.4 Learned entity resolution  *(PROPOSED)*
With the labelled pairs from §1.1, replace exact-key matching with
$M(i,j) = w_n S_n + w_d S_d + w_l S_l + w_o S_o$ and choose $\tau$ on a
precision-constrained frontier, following the evaluation discipline in
`abramitzky2021linking`. Note this is a *second-order* improvement: §1.2 must
come first, because a learned matcher fed a normaliser that deletes "AI" learns
the same error.

### 2.5 Enlarge the imputation experiment  *(IMPLEMENTED at n=400)*
`experiments/imputation_experiment.py` currently runs 400 firms in two modes.
Worth adding: a second model family (does the prior differ by vendor?), a
temperature sweep, and a variant where the true value *is* present in the text
(does the grounded instruction cost recall?). The last one matters — the paper
argues for the grounded rule and has not measured its cost.

### 2.6 Financing analysis  *(PROPOSED)*
`data/crunchbase/funding_rounds.parquet` is on disk (130 MB) and unused in this
paper. It supports $\text{FundingShare}^{AI}_t$, round-size distributions, and
graduation rates by AI status — a genuine economic outcome rather than a
formation count. Coverage caveat: only 17.2% of firms in the resolved dataset
carry a `total_raised` value.

---

## Tier 3 — future research

- **Founder composition.** The employment-derived dataset reaches only ~1,367
  of the unlisted firms (it is built from professional profiles, which unlisted
  firms lack by construction), so founder analysis illuminates the covered
  population only. An earlier internal comparison found a gender-gap result
  that *contradicts* a register-derived one; neither is cited in the paper
  until reconciled.
- **Investor and co-founder networks.** Relational data exists
  (269,181 financing records) but investor names are absent from the resolved
  store — only counts survive. Network analysis needs a re-import.
- **Source-reliability model.** $R_s = \alpha C_s + \beta A_s + \gamma U_s$ over
  completeness, cross-source agreement, and update reliability. Not
  implemented; do not describe as if it were.
- **Non-English sources.** The collection system is English-first. Coverage of
  Chinese, Japanese, and Korean ecosystems runs through English-language
  portfolio pages, which is a plausible source of the East Asia share decline
  reported in §6.2 and is not currently separable from indexing lag.
