# Enrichment Source Landscape — where to find GOOD info on invisible startups

Empirically tested 2026-08-03 against real companies in our DB. Answers: for the
startups invisible to Crunchbase/PitchBook/LinkedIn, what public data actually
exists, per field, and is it free?

## TL;DR

The invisible population is **not uniformly data-poor** — it splits by type, and
each type has a different best source. The **single biggest free win is NIH
RePORTER + NSF** for grant firms (returns founder names, funding, years, sector —
tested, works, no key). Everything else falls to paid Tavily+LLM (Victor's
`enrich_fields.py`) because the companies have no rich native source.

## Population types (AI-hidden = 10,675; strict-hidden = 52,276)

| Type | Count (strict) | Best source | Free? |
|---|---|---|---|
| Grant firms (SBIR/NSF) | 7,681 | **NIH RePORTER + NSF APIs** | ✅ free |
| Accelerator alums | 13,139 | own homepage / accelerator page | mixed |
| VC-portfolio & directory scrapes | ~31,000 | Tavily → homepage → LLM | ❌ paid |
| GitHub-sourced | ~0 here | (n/a — corrected: this bucket is VC scrapes, not GitHub) | — |

## Tested sources (real probes)

### ✅ NIH RePORTER — the standout free source (grant firms)
`POST https://api.reporter.nih.gov/v2/projects/search` — no key, JSON, fast.
Probe (Minerva Biotechnologies) returned, in one call:
- **Founder** = ContactPiName `BAMDAD, CYNTHIA C.` (founder data for a company NOT on LinkedIn)
- **Funding** = per-award amounts ($181K–$458K)
- **Founding-year signal** = all fiscal years (2002–2014 → earliest ≈ founding)
- **Sector / what-they-do** = project titles (stem cells, nanoparticles, neurodegenerative)

Fills **founders + funding + founding year + sector** for grant firms, free.
`scripts/import_gov_grants.py` already calls this API but only kept "first award
year" — it **discards the PI name and amounts**. Extending it is the concrete
free win (see Recommendations).

### ✅ NSF Award API (grant firms)
`https://api.nsf.gov/services/v1/awards.json` — no key; returns PI names +
amounts + dates. Same shape as NIH; `import_gov_grants.py` already uses it.

### ⚠️ crt.sh — Certificate Transparency (founding-year proxy, domained cos)
`https://crt.sh/?q=DOMAIN&output=json` — earliest cert ≈ site launch. Probe:
`dbml-lang.org → 2019` (worked), `epr-labs.com → timeout`. Works but **slow/flaky**
like Wayback — background/overnight only, not a bulk synchronous lever.

### ⚠️ USPTO PatentsView — inventors(=founders) + dates + tech (deep-tech cos)
New API `https://search.patentsview.org/api/v1/patent/` now **requires a free API
key** (legacy `api.patentsview.org` is deprecated → returns HTML). Would give
inventor names (founders) + filing dates + CPC tech class. Deferred pending a key.

### ⚠️ Wayback Machine (founding-year proxy) — built, rate-limited
`scripts/wayback_founding_year.py`. archive.org rate-limits hard (~15h for the
full set). Resumable/overnight only.

### 💲 Tavily + LLM (the general case) — paid, Victor's pipeline
`scripts/enrich_fields.py` (`web`/`deep` stages). The only option for the ~31K
VC/directory scrapes (no native source, 68% have no domain). ~$0.005/search +
LLM. This is the paid path deferred under the "free-first" decision.

## Field × source routing (what to use for each field)

| Field | Grant firms | Accelerator alums | VC/directory scrapes |
|---|---|---|---|
| Founders | **NIH/NSF PI name** (free) | homepage / source page | Tavily deep (paid) |
| Founding year | NIH/NSF earliest FY (free) + our proxies | accelerator cohort (have) | crt.sh/Wayback (bg) → Tavily |
| Funding | **NIH/NSF award $** (free) | news pipeline | Tavily deep (paid, weak) |
| Sector / AI-application | project titles → LLM, or description → LLM classify | LLM classify (have desc) | LLM classify (need desc first) |
| Domain | — (usually no site) | homepage / source page | Tavily (paid) — 68% missing |
| Location | NIH/NSF org (free) | homepage | homepage / Tavily |

## Recommendations (priority order)

1. **Extend `import_gov_grants.py` to capture PI names + award amounts** (free) →
   fills founders + funding + year + sector for grant firms. Reuses the API calls
   it already makes. Even at 232 AI grant firms now, it's founder data for an
   otherwise-founder-less population; scales to 7,681 if scope broadens.
2. **crt.sh / Wayback as a background founding-year job** for domained companies
   (both proxies, both slow — run unattended, never blocking).
3. **PatentsView** — register a free API key, then inventors + tech for deep-tech
   grant firms.
4. **Tavily+LLM (`enrich_fields.py`)** — the paid path, only for the VC/directory
   scrapes that have no free native source; gate on cost per the plan.

## What is genuinely unreachable (the floor)
VC/directory scrapes with no domain, no grant, no patent, no press — some
thousands of name-only rows. No free source reaches them; even paid Tavily has
low yield. This is the true data floor of the invisible population.
