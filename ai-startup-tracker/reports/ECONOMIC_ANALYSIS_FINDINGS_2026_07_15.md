# Economic Analysis & Founder Data — Findings (updated 2026-07-15)

Scope: the "hidden" company population (in our DB but NOT covered by
Crunchbase or PitchBook) plus the Revelio-derived founder/exec dataset.
All numbers pulled from the Railway production DB unless noted.

---

## 1. Population sizing

| Population | Count | Note |
|---|---|---|
| Total companies (Railway) | 986,326 | |
| Hidden (not CB, not PB) | 54,731 | incl. Victor's 7,681 NIH/NSF grant firms (100% US) |
| Hidden *and* not on LinkedIn/Revelio | ~44,000 (94.7% of pre-grant 46,567) | the "truly invisible" cut |
| Crunchbase | 650,200 | |
| PitchBook | 281,395 | |

Note the hidden bucket grew from 46,567 → 54,731 mid-session when Victor's
SBIR/STTR grant importer landed on Railway. Those 7,681 grant firms are 100%
US and pull the hidden US geographic share from 40.4% → 59.6% — treat them as
a distinct US-skewed sub-population, not organic scraper/GitHub geography.

---

## 2. Headline findings (talking points)

### 2a. Hidden companies are ahead of the AI-adoption curve, and accelerating
AI-share of the hidden population by founding year vs the whole DB:

| Year | Hidden AI% | Whole-DB AI% |
|---|---|---|
| 2018 | 24.1% | 15.9% |
| 2020 | 19.7% | 17.3% |
| 2022 | 22.4% | 18.9% |
| 2023 | 31.9% | 43.4% |
| 2025 | 51.3% | 58.3% |

In the early years the hidden layer runs *above* the institutional average —
scraped/GitHub sources catch AI-native startups before commercial databases
index them. Overall, AI's share of new-company formation went ~9% (2014) →
58% (2025). That tripling-plus is the paper's spine and holds across the
enriched data.

### 2b. Hidden AI-adoption (20.7%) exceeds both institutional sources
| Bucket | Companies | AI% |
|---|---|---|
| Hidden | 54,731 | **20.7%** |
| Crunchbase | 650,200 | 12.3% |
| PitchBook | 281,395 | 10.6% |

The companies commercial databases miss are *disproportionately* AI-native —
a direct "coverage bias" argument for the paper.

### 2c. Survival proxy reveals a source-quality split
Domain-liveness (a survival PROXY — see caveats §4):

| Source | Domain-live rate |
|---|---|
| GitHub-discovered | **90.3%** (8,099/8,966) |
| Scraper (accelerator/VC pages) | **76.2%** (7,749/10,171) |

GitHub-sourced companies are much more "alive" (an active repo implies an
active company); scraper-sourced portfolios include more defunct alumni.
Survival is stable-to-rising across cohorts (76–96% live) with no collapse in
older cohorts — a hint the scraped sources skew toward survivors (dead firms
fall off portfolio pages).

### 2d. Hidden companies are structurally different in sector mix
Share of each bucket by vertical (top hidden verticals):

| Vertical | Hidden | CB | PB |
|---|---|---|---|
| Software & IT | 21.7% | 33.9% | 14.7% |
| Financial Services | 10.4% | 3.3% | 7.4% |
| Healthcare | 9.4% | 3.2% | 8.6% |
| Media & Marketing | 7.4% | 5.3% | 6.7% |
| Professional Services | 5.4% | **13.8%** | 16.5% |
| Biotech & Pharma | 3.4% | **9.7%** | 3.2% |

Hidden skews consumer/software/fintech and is far under-weight in Professional
Services and Biotech — the kind of firm that has a website + GitHub but never
files the paperwork that lands it in Crunchbase.

---

## 3. Founder / exec dataset (Revelio-derived)

Built via the Cowork pipeline (`scripts/build_founder_profiles.py`); a local
parquet, **still growing** as more shards process.

| Metric | Value |
|---|---|
| Rows | 335,842 |
| Distinct companies | 204,475 |
| Distinct people | 325,739 |
| Degree populated | 11.7% |
| University populated | 27.9% |
| Gender predicted | 26.8% |

### Usable content where populated
- **Field of study**: Engineering (14,063) and Business (11,340) dominate,
  then Economics (2,232), Finance (1,488) — a real technical-vs-business split.
- **Degree**: Bachelor 26,248 / Master 8,428 / MBA 3,034 / Doctor 1,770.
- **Gender**: 77,520 M / 18,097 F (~81/19) — a publishable diversity figure
  IF the proxy-inference caveat is stated.

### THE founder caveat (do not skip)
Revelio's role field is `role_k1500`, a ~1,500-bucket occupation taxonomy with
**no "founder" or "CEO" category**. The top role values are `directors`
(115,625), `technology officer` (74,860), `md` (45,373), `officer` (30,205).
So this is a **senior-officer-near-founding** dataset, NOT verified founders.
Every downstream claim must carry that caveat.

### Founder data barely reaches the hidden population
Only ~1,367 of 54,731 hidden companies have any founder row — because
Revelio IS LinkedIn, so LinkedIn-invisible companies are Revelio-invisible.
The founder dataset and the hidden dataset are near-disjoint; founder analysis
illuminates the CB/PB companies, not the hidden ones.

---

## 4. Issues with running the econ analysis on ONLY hidden companies

These are the methodological problems a reviewer will raise. They are real and
should shape how the hidden-only results are framed (descriptive/suggestive,
not causal).

### 4a. Catastrophic missingness on the key variable (founding year)
Only **8.3%** of hidden companies (4,537 / 54,731) have a founding year at all.
Any formation-timeline or cohort analysis on the hidden population is running
on <1-in-12 companies — a small, non-random slice.

### 4b. The missingness is NOT random — it is correlated with the outcome
The founded_year subsample is biased on the very thing we measure:

| Subgroup | AI% |
|---|---|
| Hidden WITH founded_year | 27.5% |
| Hidden WITHOUT founded_year | 20.1% |

And by domain presence (which drives the survival proxy):

| Subgroup | AI% |
|---|---|
| Hidden WITH domain | 28.0% |
| Hidden WITHOUT domain | 16.8% |

Companies we could enrich are systematically more AI-heavy than those we
couldn't. So the enriched subsample **overstates** AI adoption relative to the
true hidden population. This is selection-on-observables, and it biases exactly
the headline number.

### 4c. Coverage is uneven ACROSS sources, confounding source comparisons
founded_year coverage: scraper 20.1% vs GitHub 4.1%. Any hidden-only
founding-year finding is really dominated by scraper companies, even though
GitHub is the larger source (40,356 vs 14,375). Source-level comparisons on
enriched fields are apples-to-oranges.

### 4d. No denominator / no true universe
Hidden companies are whatever our scrapers and GitHub scan happened to find —
not a defined sampling frame. We cannot compute rates "per capita" or claim
representativeness of any real economy. It is a convenience sample, so
hidden-only levels (e.g. "X% are AI") are not population estimates.

### 4e. Survival is a proxy, not an outcome
`domain_status` = "did the domain respond to an HTTP request today." Parked
domains read as live; lapsed-but-operating firms read as dead; the 65% with no
domain can't be checked at all. It is directional, not a survival rate, and
should never be reported as one.

### 4f. No economic depth at all
Zero funding, headcount, or verified exit data for the hidden population
(funding_signals is 100% PitchBook + 200 news rows). So "economic analysis"
here means formation timing + sector mix + a survival proxy + an AI flag —
descriptive structure, not firm performance or outcomes.

### 4g. Grant-firm contamination
The 7,681 NIH/NSF grant firms (100% US, less AI-heavy) are now inside the
hidden bucket and distort geography (US 40%→60%) and dilute AI% (22.8%→20.7%).
Report them as a separate source row or the hidden geography is misleading.

### What the hidden-only analysis CAN legitimately support
- A **coverage-bias argument**: what the standard databases systematically miss
  (skews AI-native, consumer/software, recent-vintage) — this is robust because
  it is a *relative* comparison, not a level estimate.
- **Descriptive structure** of the pre-institutional layer, clearly labeled as
  a convenience sample with the missingness caveats above.

### Recommended framing
Use hidden companies for the *comparison* story (hidden vs CB vs PB), not for
standalone level estimates. Where a founding-year or survival figure is quoted,
state the coverage (8.3% / 35%) and the selection bias (§4b) inline.

---

## 4h. Enriching the CB/PB/LinkedIn-invisible scraper companies (13,139)

Ways to add data to the ~13K companies our scrapers found that are on none of
the three major sources. Two free/in-DB paths were executed
(`scripts/enrich_hidden_from_scraped.py`):

- **cohort_year (DONE)** — decoded accelerator `batch` labels (Techstars
  '2019', YC 'W26'/'S23', 'Spring 2026') into a year for **2,414 companies**
  that had no founded_year. It's a FOUNDING-YEAR PROXY (batch runs slightly
  after founding), stored in a separate `cohort_year` column. Effective
  founding-year coverage of the hidden population rose **8.3% → 12.7%**
  (COALESCE(founded_year, cohort_year)). Sections 9a/9b now use the COALESCE.
- **TLD → country (DEAD END, verified)** — 0 usable results. The 12,825
  country-NULL hidden companies with a domain overwhelmingly use branded
  gTLDs (.com 5,798 / .ai 1,145 / .io 1,089 / .app / .dev / .co), which the
  high-confidence ccTLD map deliberately excludes as non-geographic. Country
  cannot be inferred from TLD for this startup-heavy population.

- **grant_first_award_year (DONE)** — extracted "first award YYYY" from the
  SBIR/STTR grant firms' descriptions (Victor's import_gov_grants.py wrote them)
  for **7,681 companies**. A founding-year PROXY (deep-tech firms win their
  first federal grant near founding). Combined effective founding-year coverage
  (COALESCE founded_year > cohort_year > grant_first_award_year) jumped
  **12.7% → 26.7%** (14,632 of 54,731). Formation timeline now covers 13,813.

Free founding-year levers evaluated (2026-07-15):
| Lever | Yield | Status |
|---|---|---|
| Revelio domain match (0A) | ~3,100 | done |
| Accelerator cohort_year | 2,414 | done |
| SBIR first-award year | 7,681 | done |
| Accelerator batch-number → year | ~494 | not done (needs per-accelerator cadence table) |
| Description "founded in YYYY" mining | ~47 | not worth it (thin scraped blurbs) |
| Wayback first-capture | ~unknown | skipped — archive.org rate-limits (~15hr crawl) |
| Certificate Transparency (crt.sh) | unknown | untested (likely same rate-limit fate) |
| GitHub repo created_at | 0 reachable | blocked — github_signals empty, repo linkage lost |
| Homepage re-scrape (Tavily+Claude) | up to ~9K | not done (~$70; also fills country + founder names) |

The ~32% with no domain and no accelerator/grant signal remain near-unreachable
for free.

## 4i. STRICT re-cut: not in ANY of the three sources (52,276)

Sections 9–13 re-scoped from "not CB/PB" (54,731) to the strict "not in
Crunchbase, PitchBook, OR LinkedIn" population (52,276), operationalised as
`verification_status NOT IN (cb/pb/cb_pb) AND naics_code IS NULL` (naics_code
is set only by the Revelio/LinkedIn domain match, so its absence = not matched
to LinkedIn). The comparison sections add a distinct `hidden_on_li` bucket
(2,455 — not CB/PB but DID match LinkedIn) so those stragglers aren't folded in.

**Strict-population results (Railway, 7/15):**
- **AI-adoption (the robust headline):** hidden **20.4%** vs CB 12.3%, PB 10.6%
  (and hidden_on_li 26.3%). Computable for 100% of the population, so this
  relative gap is the strongest, most defensible finding.
- **Geography:** hidden is **60.8% US** (vs CB 34%, PB 50%) — but this is
  driven by the SBIR/NSF grant firms (100% US), not organic.
- **Founding-year distribution:** hidden skews hard to 2019–2025 (10–12% of the
  bucket per recent year, vs CB collapsing after 2021) — recency the standard
  databases haven't caught up to.
- **Verticals:** hidden over-indexes Healthcare (10.1% vs CB 3.2%), Financial
  Services (9.5% vs 3.3%), Education, Data & Analytics, Energy; under-indexes
  Professional Services (4.7% vs 13.8%) and Biotech.

**The composition caveat (critical):** of the ~11,935 strict-hidden companies
with an effective founding year, **64% (7,637) are SBIR/NSF grant firms**, only
3,850 scraper and 448 GitHub. So any founding-year or geography finding on the
"invisible" population is really dominated by US federal-grant deep-tech firms —
a specific, selected sub-population. Section 9a now splits source 3-way
(scraper / grant / github) so this is explicit. AI-adoption is the exception:
it needs no founding-year/geography enrichment, so it's not subject to this bias.

## 5. Data state / provenance

- All enrichment synced to Railway: founded_year (non-CB/PB 3.0%→9.7% of the
  domained subset), naics_code, normalized country, domain_status.
- Committed analysis CSVs: `output/01-13_*.csv` (regenerated against Railway,
  labeled 7/15). Excludes the 60MB `08_ai_companies_full.csv`.
- Founder pipeline + parquet committed for Victor's visibility (see the
  founder commit). role_k1500 caveat (§3) applies.
- Reproduce: `python3 scripts/research_analysis.py` (points at DATABASE_URL;
  set it to RAILWAY_DATABASE_URL for the complete superset).

---

## 6. LONGITUDINAL: AI repackaging (PitchBook 2021 -> 2025) — added 2026-08-09

Turned the cross-sectional data longitudinal using the PitchBook **2021** and
**2025** company snapshots (shared Dropbox), joined on **CompanyID** (exact,
no fuzzy matching). Scripts: `scripts/pb_longitudinal_repackaging.py` (panel +
sample classify) and `scripts/ai_repackaging.py` (the diff-classifier). Raw
snapshots are git-ignored under `data/pb_longitudinal/`.

**Panel: 641,442 companies present in both 2021 and 2025.**
- AI-language prevalence: **3.8% (2021) -> 4.7% (2025)**
- **7,648 companies ADDED AI language**; 22,340 were AI in both; 2,206 DROPPED it.

**Repackaging breakdown (LLM diff-classifier, 150-company sample of the added-AI pool):**
| class | share (n=2,000) | meaning |
|---|---|---|
| repackaged_to_ai | **18.1%** | genuine business-model pivot to AI |
| added_ai_feature | 34.5% | AI added as a feature, core unchanged |
| born_ai | 10.5% | was AI in 2021 (keyword pre-filter missed it) |
| ai_washing | 3.4% | marketing only — TEXT-ALONE FLOOR (needs hiring triangulation) |
| no_ai_change | 33.5% | keyword false-positive, no real change |

Stable across sample sizes (150 -> 2,000). Of the ~7,648 added-AI companies:
~18% genuine pivots (~1,380), ~35% added-feature (~2,640), ~3% washing.
Per-company results: output/22_pb_repackaging_sample.csv. Real pivots: Samba
Tech (video->AI infra), Perfit 3D (3D scanning->AI marketplace), Enki (learning
app->enterprise AI coaching), Artivatic.ai (data API->AI insurance).

Real pivots surfaced: Taktify (neurotech->AI), emotion3D (3D imaging->AI),
Transparency Life Sciences (clinical trials->AI-driven), Ayyeka (monitoring->edge AI).

**Caveats:** (1) ai_washing 2% is a floor — text alone can't separate washing
from real pivots; the Revelio hiring signal (0 vs many ML hires) resolves it and
should be layered in. (2) The real repackaging rate should be computed on
LLM-confirmed added-AI (excl. the 32% keyword false-positives + 13% already-AI).
(3) 150-sample => ~+/-7%; scale up for precision. (4) Covers PitchBook (commercial)
only; hidden companies aren't in PB, so their 'before' needs Wayback.

**Next:** scale the classify sample; layer Revelio hiring triangulation; add the
2023 Crunchbase snapshot as a third point; Wayback for the hidden companies.

**Triangulation (anti-washing, free — `--triangulate`):** of the 7,648 added-AI
companies, 72% show REAL activity (headcount grew or raised more capital
2021->2025), 28% show none (flat/shrank, no new raise). The text-only classifier
flagged just 3.4% washing — but 28% added AI language with no growth behind it.
Key finding: **text under-detects washing; most AI-repackaging claims are not
matched by real growth.** (No-activity is a strong signal, not proof — PB data
can lag and a real pivot may not have grown yet.)

---

## 7. EXIT OUTCOMES (Crunchbase 2023) — added 2026-08-09

Unlocked the survival/exit gap using the CB 2023 dump's `status` field +
acquisitions/ipos tables, matched to our companies by domain. Script:
`scripts/match_cb_exits.py`; aggregate in `output/23_exit_outcomes.csv`.

**577,921 of our companies matched CB 2023 by domain.** Overall: 33,310
acquired, 10,914 IPO, 16,726 closed (7.7% acq+ipo exit rate among matched).

| bucket | matched | acquired | ipo | closed | exit% |
|---|---|---|---|---|---|
| Commercial AI | 66,001 | 5,954 | 721 | 5,085 | 10.1% |
| Commercial non-AI | 103,556 | 26,299 | 5,651 | 7,439 | 30.9% |
| Hidden AI | 1,272 | 123 | 138 | 63 | 20.5% |

CAVEATS: (1) AI-vs-non-AI exit gap is confounded by AGE — non-AI companies are
older and have had more years to exit; a cohort-matched comparison is needed.
(2) CB status is a 2023 snapshot (exits only through 2023). (3) Hidden companies
barely match CB (they're hidden by definition), so exit data covers commercial.
The CB dump also has people/degrees (founders) + funding_rounds — more to mine.

### 6b. Repackaging by sector and founding cohort (added 2026-08-09)
output/24_repackaging_by_sector.csv, 25_repackaging_by_cohort.csv.

By sector (of PB companies in the 2021->2025 panel):
| sector | added-AI rate | washing rate (of added) |
|---|---|---|
| Information Technology | 2.5% (highest) | 16% |
| Healthcare | 1.2% | 11% |
| Financial Services | 0.7% | 15% |
| B2B products/services | 0.7% | 20% (highest washing) |
| Consumer (B2C) | 0.3% | 11% |

-> IT repackages around AI the most; B2B-services has the highest AI-washing
rate (added AI language, no headcount/funding growth behind it).

By founding cohort (added-AI rate, monotonic with recency):
pre-2010 0.7% | 2010-15 1.6% | 2016-20 3.0% | 2021+ 4.0% (small n).
-> Younger companies repackage ~4x more than pre-2010 firms.

## 8. Repackaging x exit outcomes (added 2026-08-09)
Joined the PB 2021->2025 transition groups to CB 2023 exit status by domain.
output/26_repackaging_vs_exit.csv.

| group | exit% (acq+ipo) | closed% |
|---|---|---|
| never_ai | 24.3 | 12.5 |
| dropped_ai | 17.5 | 2.0 |
| added_ai (repackaged) | 16.1 | 3.4 |
| born_ai | 15.8 | 10.0 |

Standout: companies that REPACKAGED to AI have a much lower CLOSURE rate (3.4%)
than never-AI (12.5%) or born-AI (10%) — consistent with repackaging as a
survival move.

HEAVY CAVEAT: exit% is age-confounded — never_ai is full of older, mature firms
with more years to exit; a cohort-matched comparison is required before any
causal reading. Also CB status is 2023 while AI is measured through 2025
(temporal ordering muddy). Directional/suggestive only.

### 8b. Cohort-MATCHED (removes the age confound) — added 2026-08-09
output/27_repackaging_exit_cohort_matched.csv. Within founding cohort,
repackaged (added_ai) vs never_ai:

| cohort | closed% repackaged | closed% never-AI | exit% repackaged | exit% never-AI |
|---|---|---|---|---|
| pre-2010 | 6.5 | 13.7 | 24.7 | 29.6 |
| 2010-15 | 3.5 | 17.8 | 15.3 | 14.5 |
| 2016-21 | 2.2 | 6.6 | 6.2 | 8.7 |

FINDING (robust to age): repackaged firms CLOSE at 3-5x lower rates than never-AI
firms of the SAME vintage, in every cohort. Exit (acq/ipo) rates are comparable
within cohort — the earlier "never-AI exits more" was age confounding.

CAVEAT (survivorship in the measurement): to ADD AI language by 2025 a company
had to still be active enough to update its PitchBook profile — so "added_ai" is
partly conditioned on survival, which mechanically depresses its closure rate.
This is association, not causation; a proper design needs the exact date AI was
added and a company still-alive-in-2021 baseline.

## 9. Wayback repackaging for HIDDEN companies — informative negative (2026-08-10)
scripts/wayback_repackaging.py reconstructs hidden companies' homepage text at
~2021 and ~2025 from the Internet Archive to detect repackaging (they aren't in
CB/PB, so no snapshot panel exists for them).

RESULT: ~88% of sampled hidden AI companies have NO archived 2021 homepage —
they didn't exist / weren't online / weren't crawled in 2021. The hidden AI
population is predominantly recent, born-AI firms, not repackagers. Only ~12%
have both a 2021 and 2025 snapshot, too few and too self-selected for a reliable
hidden-repackaging estimate.

TAKEAWAY: AI repackaging is a COMMERCIAL / established-company phenomenon (well
captured by the PitchBook 2021->2025 panel, section 6). It is NOT meaningfully
measurable for the hidden population via Wayback because those companies mostly
post-date the 2021 baseline. Consistent with the hidden layer skewing to
2019-2025 formation and higher AI-adoption (sections 2a/2b). The tool remains
useful for the minority of older hidden firms and is checkpointed/resumable
(output/28_wayback_repackaging.csv).

## 10. AI-IDENTITY CHANGE STUDY — Crunchbase 2023→2026 panel (added 2026-08-10)
The core question refocused to: for AI companies specifically, WHEN did they
acquire their AI identity and HOW did their self-description change? Built on the
full Crunchbase 2023 / 2024 / 2025 / 2026 dumps (funding/investor/people tables
loaded from the shared Dropbox; git-ignored under data/pb_longitudinal/). AI is
defined by CB's OWN category taxonomy (category_list / category_groups_list) so
the definition is uniform across dumps and covers companies added after our
Railway import. Panel joined on the stable org uuid (98% of 2023 orgs persist).

### 10a. Funding trajectories — AI startups graduate more (scripts/funding_trajectories_cb.py; CSVs 30-32)
Real CB round history (538K rounds / 273K funded orgs). Of seed entrants, AI
companies reach Series A 23.2% vs 18.8% (non-AI), Series B 10.5% vs 8.9%, C 5.3%
vs 4.8%; median 2 vs 1 rounds; AI higher in every founding cohort. (This is the
one AI-vs-non-AI cut; the rest of section 10 is AI-only per the refocus.)
NB: Railway funding_signals could NOT support this — it stores ~1 summary deal
per company (95.6% single-round) and investor names are absent (a count only);
the CB funding_rounds/investments tables were required. See memory
project_vc_behavior_data_limits.

### 10b. Investor side (scripts/investor_network_cb.py; CSVs 30-33, CB2023)
874K investment links tagged by portfolio-company AI status. Top AI backers:
Techstars, Y Combinator, NSF, a16z, Sequoia. 276 AI-specialist investors (>50%
of portfolio AI). AI rounds are more syndicated (2.52 vs 2.14 investors/round,
more leads). AI share of new investments rose 9%→20% (2010-2020). Caveat: the
CB2023 dump ends 2023-03 (pre-generative-AI surge).

### 10c. When did AI companies adopt the AI identity? (scripts/cb_ai_identity_panel.py; CSVs 34-36)
Of 175,746 AI companies in CB 2026: 21% already AI by 2023, ~6% repackaged
(non-AI in 2023 → AI later), 15% new to CB in 2024/2025, 58% new to CB in 2026.
Among companies PRESENT since 2023, 22% repackaged into an AI identity.
Repackagers came from Software / IT / SaaS / Image Recognition / Semantic Search
/ SEO / Advertising. Repackaging is U-shaped by age: 2020+ (36%) and pre-2010
(32%) pivot most.
CAVEAT (important): the 2026 export is a larger, API-style dump (5.4M orgs, richer
AI subcategories incl. "Generative AI"/"Foundational AI") vs 3.8M in 2025, so the
"58% new to CB in 2026" is inflated by coverage + taxonomy expansion, NOT pure
formation. The repackaging rate (measured on the stable present-since-2023 base)
is the robust number.

### 10d. How AI companies rewrote their descriptions (scripts/cb_ai_description_evolution.py; CSVs 37-38)
For AI companies with both 2023 and 2026 CB descriptions (n=35,226): repackagers
rewrote their description 53% of the time and added AI language 30% (vs 14% / 2%
for already-AI firms) — repackaging is real repositioning, not just a tag flip.
Newly-added generative-AI vocabulary 2023→2026, led by AGENTS (598 companies, up
from 114 at 2025), generative ai (363), llm (193), copilot (93), gpt/chatgpt
(90), RAG (52). The jump in "agents" is the clearest fingerprint of the 2025→2026
agentic-AI turn in how companies describe themselves.

### 10e. Genuine pivot vs AI-washing (scripts/classify_repackagers_cb.py; CSVs 39-40)
LLM diff-classifier (Haiku, n=500, 100% parse) on category-repackagers' real
2023→2026 descriptions: 20% repackaged_to_ai, 15% added_ai_feature (=35%
GENUINE), 1% ai_washing, 13% born_ai, 52% no_ai_change.
KEY METHODOLOGICAL FINDING: category-tag "repackaging" OVERSTATES genuine AI
adoption ~3x. Half the companies CB tagged AI show NO AI in their description
text at all (tag noise / stale text), and only ~a third show a genuine pivot or
feature. Explicit text-level AI-washing is rare (1%). Always validate a category
tag against the description text.

### 10f. Wayback exact-month dating — independent corroboration (scripts/wayback_ai_event_study.py; CSV 29)
Binary-searches the Internet Archive snapshot timeline to date the exact month
PB "added-AI" companies first showed AI on their homepage. Partial crawl (~101
dated of 576, archive.org throttling → many retryable cdx_failed): dated homepage
AI-adoption events split ~50/50 before/after ChatGPT (Nov 2022) with the single
largest cluster in 2023 — independently corroborating the CB identity-dating that
AI-identity adoption peaks post-ChatGPT. 19% already showed AI on the homepage in
2019 (website led the PB description). Resumable/checkpointed.

### 10g. Pre-ChatGPT baseline via PitchBook 2021 -> CB bridge (scripts/pb_cb_unified_panel.py; CSVs 41-42) — READ THE CAVEAT
Bridges PitchBook 2021 to CB 2023/2025 on domain (no shared ID; 241K overlap,
188,050 matched across all three). A naive read says "43% of today's AI companies
were already AI in 2021 (pre-ChatGPT)" — this is TRUE but MISLEADING; do not use
it as a headline. Two confounds, verified:
  1. SELECTION: the panel is BY CONSTRUCTION only firms already tracked by
     PitchBook in 2021 (established companies). It excludes the entire post-2021
     formation wave — which is where the generative-AI companies actually are.
  2. DEFINITION: "AI in 2021" is ~99% decades-old "artificial intelligence"
     (3.9%) + "machine learning" (2.1%) language, which predates ChatGPT. Clean
     GENERATIVE-AI phrases (generative ai / large language model, no 'llm'
     substring) were 0.007% in 2021 -> 0.011% (2023) -> 0.079% (2025) — i.e.
     essentially zero pre-ChatGPT. (An earlier 0.48% "generative 2021" figure was
     a bug: substring 'llm' matching words like enro-LLM-ent.)
Within this established set, AI/ML language is FLAT-TO-DECLINING (AI 3.9->3.5%,
ML 2.1->1.5%). CORRECT reading: the AI *label* is old; incumbents barely changed
their descriptions; the explosion of "AI companies" is driven by new-company
formation + category re-tagging, NOT incumbents pivoting their text. Reinforces
10c-10e rather than contradicting them.

### 10h. Who founds AI companies (scripts/cb_ai_founders.py; CSVs 43-46)
CB people/jobs/degrees, AI-scoped: 30,806 distinct AI-company founders across
18,481 AI companies. AI founders are more credentialed/technical than non-AI:
PhD 20.5% vs 10.8%, bachelor-only 33% vs 47%, larger teams (1.72 vs 1.39). Top
fields Computer Science / EE / Physics / Math; top schools Stanford, MIT, Tel
Aviv, Berkeley, Harvard, CMU, Technion (Israel prominent). LESS likely serial
(3.1% vs 11.9% — first-time-founder wave) and slightly less female (10.0% vs
13.4% — NB contradicts the Revelio "no gender gap" aggregate; different source/
definition, reconcile before citing). Aggregates only, no names.

### 10i. Data provenance (section 10)
CB 2023/2024/2025 = flat bulk parquet dumps; CB 2026 = API-style nested export
(normalized to flat schema on load; description text carried inline). All under
data/pb_longitudinal/ (git-ignored); only aggregates + a 500-row verdict sample
committed. cb_status (CB-2023 exit outcome) written to Railway per company.
