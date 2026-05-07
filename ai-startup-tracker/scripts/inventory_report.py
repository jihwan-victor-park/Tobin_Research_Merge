"""
Inventory report: how many sites have we analyzed, by type and scrapeability.

Run from ai-startup-tracker/:
    python scripts/inventory_report.py
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import yaml

# ── Category definitions ──────────────────────────────────────────────────
# Six buckets matching Victor's site_health.category column.
DOMAIN_CATEGORIES: dict[str, str] = {
    # ── University / research incubators ─────────────────────────────────
    "berkeley.edu":                   "university_incubator",
    "skydeck.berkeley.edu":           "university_incubator",
    "startx.com":                     "university_incubator",   # Stanford StartX
    "innovationlabs.harvard.edu":     "university_incubator",
    "kellercenter.princeton.edu":     "university_incubator",
    "alliance.rice.edu":              "university_incubator",
    "entrepreneurship.mit.edu":       "university_incubator",
    "startups.columbia.edu":          "university_incubator",
    "web.startx.com":                 "university_incubator",  # Stanford StartX (registry subdomain)

    # ── Accelerators ──────────────────────────────────────────────────────
    "500.co":                         "accelerator",
    "alchemistaccelerator.com":       "accelerator",
    "antler.co":                      "accelerator",
    "astrolabs.com":                  "accelerator",
    "beondeck.com":                   "accelerator",
    "brinc.io":                       "accelerator",
    "capitalfactory.com":             "accelerator",
    "dreamit.com":                    "accelerator",
    "eranyc.com":                     "accelerator",
    "fi.co":                          "accelerator",   # Founder Institute
    "flat6labs.com":                  "accelerator",
    "gener8tor.com":                  "accelerator",
    "h-farm.com":                     "accelerator",
    "hax.co":                         "accelerator",
    "jfdi.asia":                      "accelerator",
    "joinef.com":                     "accelerator",  # Entrepreneur First
    "masschallenge.org":              "accelerator",
    "neo.com":                        "accelerator",
    "plugandplaytechcenter.com":      "accelerator",
    "rockstart.com":                  "accelerator",
    "seedcamp.com":                   "accelerator",
    "seedstars.com":                  "accelerator",
    "sosv.com":                       "accelerator",
    "sparklabs.co.kr":                "accelerator",
    "startupbootcamp.org":            "accelerator",
    "stationf.co":                    "accelerator",
    "sting.co":                       "accelerator",
    "surgeahead.com":                 "accelerator",
    "techstars.com":                  "accelerator",
    "turn8.co":                       "accelerator",
    "wayra.com":                      "accelerator",
    "ycombinator.com":                "accelerator",

    # ── VC portfolios ─────────────────────────────────────────────────────
    "8vc.com":                        "vc_portfolio",
    "a16z.com":                       "vc_portfolio",
    "accel.com":                      "vc_portfolio",
    "allvp.vc":                       "vc_portfolio",
    "beenext.com":                    "vc_portfolio",
    "bvp.com":                        "vc_portfolio",   # Bessemer
    "foundersfund.com":               "vc_portfolio",
    "generalcatalyst.com":            "vc_portfolio",
    "greylock.com":                   "vc_portfolio",
    "lsvp.com":                       "vc_portfolio",   # Lightspeed
    "nea.com":                        "vc_portfolio",
    "nxtp.vc":                        "vc_portfolio",
    "pioneerfund.vc":                 "vc_portfolio",
    "sequoiacap.com":                 "vc_portfolio",
    "venturesplatform.com":           "vc_portfolio",
    "villageglobal.com":              "vc_portfolio",

    # ── Government programs ───────────────────────────────────────────────
    "parallel18.com":                 "government_program",   # Puerto Rico
    "startupchile.org":               "government_program",

    # ── Discovery aggregators ─────────────────────────────────────────────
    "ai-startups.org":                "discovery_aggregator",
    "aitoolhunt.com":                 "discovery_aggregator",
    "aitools.fyi":                    "discovery_aggregator",
    "alternativeto.net":              "discovery_aggregator",
    "appsruntheworld.com":            "discovery_aggregator",
    "betalist.com":                   "discovery_aggregator",
    "cbinsights.com":                 "discovery_aggregator",
    "crozdesk.com":                   "discovery_aggregator",
    "crunchbase.com":                 "discovery_aggregator",
    "dang.ai":                        "discovery_aggregator",
    "dealroom.co":                    "discovery_aggregator",
    "futurepedia.io":                 "discovery_aggregator",
    "g2.com":                         "discovery_aggregator",
    "getapp.com":                     "discovery_aggregator",
    "insidr.ai":                      "discovery_aggregator",
    "killerstartups.com":             "discovery_aggregator",
    "launched.io":                    "discovery_aggregator",
    "launchingnext.com":              "discovery_aggregator",
    "lmarks.com":                     "discovery_aggregator",
    "microlaunch.net":                "discovery_aggregator",
    "nationalstartupsdirectory.com":  "discovery_aggregator",
    "openvc.app":                     "discovery_aggregator",
    "pitchbook.com":                  "discovery_aggregator",
    "saasaitools.com":                "discovery_aggregator",
    "saasworthy.com":                 "discovery_aggregator",
    "softwareworld.co":               "discovery_aggregator",
    "sourceforge.net":                "discovery_aggregator",
    "stackshare.io":                  "discovery_aggregator",
    "startup88.com":                  "discovery_aggregator",
    "startupbase.io":                 "discovery_aggregator",
    "startupguys.net":                "discovery_aggregator",
    "startupinspire.com":             "discovery_aggregator",
    "startupjohn.com":                "discovery_aggregator",
    "startupranking.com":             "discovery_aggregator",
    "startups.gallery":               "discovery_aggregator",
    "startupstash.com":               "discovery_aggregator",
    "startuptabs.com":                "discovery_aggregator",
    "thehub.io":                      "discovery_aggregator",
    "theresanaiforthat.com":          "discovery_aggregator",
    "toolify.ai":                     "discovery_aggregator",
    "topai.tools":                    "discovery_aggregator",
    "topstartups.io":                 "discovery_aggregator",
    "tracxn.com":                     "discovery_aggregator",
    "wellfound.com":                  "discovery_aggregator",
    "producthunt.com":                "discovery_aggregator",
    "f6s.com":                        "discovery_aggregator",
    "growjo.com":                     "discovery_aggregator",
    "signal.nfx.com":                 "discovery_aggregator",
    "techcrunch.com":                 "discovery_aggregator",

    # ── VC Portfolios (new) ───────────────────────────────────────────────
    "benchmark.com":                  "vc_portfolio",
    "firstround.com":                 "vc_portfolio",
    "kleinerperkins.com":             "vc_portfolio",
    "indexventures.com":              "vc_portfolio",
    "sparkcapital.com":               "vc_portfolio",
    "usv.com":                        "vc_portfolio",
    "insightpartners.com":            "vc_portfolio",
    "ivp.com":                        "vc_portfolio",
    "battery.com":                    "vc_portfolio",
    "balderton.com":                  "vc_portfolio",
    "atomico.com":                    "vc_portfolio",
    "khoslaventures.com":             "vc_portfolio",
    "redpoint.com":                   "vc_portfolio",
    "gv.com":                         "vc_portfolio",
    "crv.com":                        "vc_portfolio",
    "felicis.com":                    "vc_portfolio",
    "initialized.com":                "vc_portfolio",
    "svangel.com":                    "vc_portfolio",

    # ── University Incubators (new) ───────────────────────────────────────
    "atdc.org":                       "university_incubator",
    "zli.umich.edu":                  "university_incubator",
    "tech.cornell.edu":               "university_incubator",
    "polskycenter.uchicago.edu":      "university_incubator",
    "entrepreneurship.duke.edu":      "university_incubator",
    "engine.xyz":                     "university_incubator",
    "enterprise.cam.ac.uk":           "university_incubator",
    "oxfordsciencesinnovation.com":   "university_incubator",
    "imperialenterprises.co.uk":      "university_incubator",
    "whartonentrepreneurship.org":    "university_incubator",

    # ── Accelerators (new) ────────────────────────────────────────────────
    "angelpad.com":                   "accelerator",
    "boost.vc":                       "accelerator",
    "vilcap.com":                     "accelerator",
    "village-capital.com":            "accelerator",
    "rockhealth.com":                 "accelerator",
    "betaworks.com":                  "accelerator",
    "indiebio.co":                    "accelerator",
    "mattervc.com":                   "accelerator",
    "launchaccelerator.co":           "accelerator",

    # ── Government Programs (new) ─────────────────────────────────────────
    "sbir.gov":                       "government_program",
    "eic.ec.europa.eu":               "government_program",
    "enterprise.gov.sg":              "government_program",
    "startupindia.gov.in":            "government_program",
    "nzte.govt.nz":                   "government_program",
}

# Domains with a dedicated easy scraper (from registry.py)
EASY_SCRAPER_DOMAINS = {
    "ycombinator.com",
    "techstars.com",
    "alchemistaccelerator.com",
    "seedcamp.com",
    "capitalfactory.com",
    "eranyc.com",
    "villageglobal.com",
    "antler.co",
    "innovationlabs.harvard.edu",
    "web.startx.com",
    "kellercenter.princeton.edu",
    "alliance.rice.edu",
    "joinef.com",
    "skydeck.berkeley.edu",
    "startups.columbia.edu",
    "entrepreneurship.mit.edu",
    "crunchbase.com",
}

# Record counts ≤ this from the agentic run are flagged as challenging
CHALLENGING_THRESHOLD = 5

CATEGORY_LABELS = {
    "university_incubator":  "University / Research Incubator",
    "accelerator":           "Accelerator",
    "vc_portfolio":          "VC Portfolio",
    "government_program":    "Government Program",
    "discovery_aggregator":  "Discovery Aggregator",
    "other":                 "Other",
}

CATEGORY_ORDER = [
    "university_incubator",
    "accelerator",
    "vc_portfolio",
    "government_program",
    "discovery_aggregator",
    "other",
]


def load_yaml_sites(yaml_dir: Path) -> list[dict]:
    sites = []
    for f in sorted(yaml_dir.glob("*.yaml")):
        d = yaml.safe_load(f.read_text())
        ls = d.get("last_success") or {}
        record_count = ls.get("record_count", 0) if ls else 0
        domain = d["domain"]
        sites.append({
            "domain": domain,
            "record_count": record_count,
            "has_last_success": bool(ls and record_count > 0),
            "probe_result": d.get("probe_result"),  # set by expand_inventory.py
            "probe_reason": d.get("probe_reason", ""),
        })
    return sites


def classify_site(domain: str, record_count: int,
                  probe_result: str | None = None,
                  probe_reason: str = "") -> tuple[str, str, str]:
    """Returns (category, scrapeability, scrapeability_reason)."""
    category = DOMAIN_CATEGORIES.get(domain, "other")

    if domain in EASY_SCRAPER_DOMAINS:
        scrapeability = "easy"
        reason = "dedicated scraper (API / HTML / parquet)"
    elif record_count > CHALLENGING_THRESHOLD:
        scrapeability = "agentic"
        reason = f"AI agent extracted {record_count} records"
    elif record_count > 0:
        scrapeability = "challenging"
        reason = f"AI agent only extracted {record_count} record(s) — limited or JS-heavy"
    elif probe_result == "easy_candidate":
        # New site: not yet scraped by AI, but HTTP probe says it's accessible
        scrapeability = "agentic"
        reason = f"not yet scraped — HTTP probe: accessible ({probe_reason})"
    elif probe_result == "challenging":
        scrapeability = "challenging"
        reason = f"HTTP probe: {probe_reason}"
    else:
        scrapeability = "challenging"
        reason = "no successful extraction recorded"

    return category, scrapeability, reason


def update_yaml_category(yaml_dir: Path, domain: str, category: str) -> None:
    path = yaml_dir / f"{domain}.yaml"
    if not path.exists():
        return
    data = yaml.safe_load(path.read_text())
    if data.get("category") == category:
        return
    data["category"] = category
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True))


def main() -> None:
    yaml_dir = Path(__file__).parent.parent / "data" / "scrape_instructions"
    yaml_sites = load_yaml_sites(yaml_dir)

    # Sites in the easy-scraper registry but NOT in the YAML dir
    yaml_domains = {s["domain"] for s in yaml_sites}
    registry_only = [
        {"domain": d, "record_count": -1, "has_last_success": True}
        for d in EASY_SCRAPER_DOMAINS
        if d not in yaml_domains
    ]

    all_sites = yaml_sites + registry_only

    # Classify and (optionally) update YAMLs
    rows = []
    for site in all_sites:
        domain = site["domain"]
        cat, scrape, reason = classify_site(
            domain, site["record_count"],
            site.get("probe_result"), site.get("probe_reason", ""),
        )
        rows.append({
            "domain": domain,
            "category": cat,
            "scrapeability": scrape,
            "reason": reason,
        })
        if domain in yaml_domains:
            update_yaml_category(yaml_dir, domain, cat)

    # ── Print report ──────────────────────────────────────────────────────
    total = len(rows)
    easy = sum(1 for r in rows if r["scrapeability"] == "easy")
    agentic = sum(1 for r in rows if r["scrapeability"] == "agentic")
    challenging = sum(1 for r in rows if r["scrapeability"] == "challenging")

    print("=" * 62)
    print("  AI STARTUP SCRAPER — SITE INVENTORY")
    print("=" * 62)
    print(f"\n  Total websites analyzed: {total}")
    print()

    # ── By category ───────────────────────────────────────────────────────
    print("  BY TYPE")
    print("  " + "-" * 44)
    cat_counts: dict[str, int] = {}
    for r in rows:
        cat_counts[r["category"]] = cat_counts.get(r["category"], 0) + 1
    for cat in CATEGORY_ORDER:
        count = cat_counts.get(cat, 0)
        if count:
            label = CATEGORY_LABELS[cat]
            bar = "█" * count
            print(f"  {label:<32} {count:>3}  {bar}")
    print()

    # ── By scrapeability ──────────────────────────────────────────────────
    print("  SCRAPEABILITY")
    print("  " + "-" * 44)
    print(f"  Easy  (dedicated scraper)      {easy:>3}  {'█' * easy}")
    print(f"  Agentic (AI extracted >5 recs) {agentic:>3}  {'█' * agentic}")
    print(f"  Challenging (AI struggled)     {challenging:>3}  {'█' * challenging}")
    print()

    # ── Challenging sites detail ───────────────────────────────────────────
    hard_rows = [r for r in rows if r["scrapeability"] == "challenging"]
    if hard_rows:
        print("  CHALLENGING SITES (AI had difficulty):")
        print("  " + "-" * 44)
        for r in sorted(hard_rows, key=lambda x: x["domain"]):
            print(f"  {r['domain']:<36}  {r['reason']}")
        print()

    # ── Full site list by category ─────────────────────────────────────────
    print("  ALL SITES BY CATEGORY")
    print("  " + "-" * 44)
    by_cat: dict[str, list] = {c: [] for c in CATEGORY_ORDER}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    for cat in CATEGORY_ORDER:
        sites_in_cat = by_cat.get(cat, [])
        if not sites_in_cat:
            continue
        print(f"\n  [{CATEGORY_LABELS[cat]}]")
        for r in sorted(sites_in_cat, key=lambda x: x["domain"]):
            badge = {"easy": "✓", "agentic": "~", "challenging": "✗"}[r["scrapeability"]]
            print(f"    {badge} {r['domain']}")

    print("\n  (✓ = easy scraper  ~ = AI agent worked  ✗ = challenging)")
    print("=" * 62)


if __name__ == "__main__":
    main()
