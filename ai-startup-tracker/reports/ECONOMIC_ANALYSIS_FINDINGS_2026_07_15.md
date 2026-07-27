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

## 5. Data state / provenance

- All enrichment synced to Railway: founded_year (non-CB/PB 3.0%→9.7% of the
  domained subset), naics_code, normalized country, domain_status.
- Committed analysis CSVs: `output/01-13_*.csv` (regenerated against Railway,
  labeled 7/15). Excludes the 60MB `08_ai_companies_full.csv`.
- Founder pipeline + parquet committed for Victor's visibility (see the
  founder commit). role_k1500 caveat (§3) applies.
- Reproduce: `python3 scripts/research_analysis.py` (points at DATABASE_URL;
  set it to RAILWAY_DATABASE_URL for the complete superset).
