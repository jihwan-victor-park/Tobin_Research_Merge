"""
Expand site inventory from ~103 to ~150 sites.

For each new domain:
  1. Creates a YAML stub in data/scrape_instructions/
  2. Makes an HTTP probe to classify scrapeability:
       easy_candidate  — clean HTML, no JS wall, no auth
       challenging     — JS-rendered, bot-blocked, login required, or error

Run from ai-startup-tracker/:
    python scripts/expand_inventory.py
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

YAML_DIR = Path(__file__).parent.parent / "data" / "scrape_instructions"
TIMEOUT = 12
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ── New sites to add ──────────────────────────────────────────────────────
# (domain, seed_url, category)
NEW_SITES: list[tuple[str, str, str]] = [
    # ── VC Portfolios ─────────────────────────────────────────────────────
    ("benchmark.com",           "https://www.benchmark.com/portfolio/",                    "vc_portfolio"),
    ("firstround.com",          "https://firstround.com/portfolio/",                       "vc_portfolio"),
    ("kleinerperkins.com",      "https://www.kleinerperkins.com/portfolio/",               "vc_portfolio"),
    ("indexventures.com",       "https://www.indexventures.com/portfolio/",                "vc_portfolio"),
    ("sparkcapital.com",        "https://www.sparkcapital.com/portfolio/",                 "vc_portfolio"),
    ("usv.com",                 "https://www.usv.com/portfolio/",                          "vc_portfolio"),
    ("insightpartners.com",     "https://www.insightpartners.com/portfolio/",              "vc_portfolio"),
    ("ivp.com",                 "https://ivp.com/portfolio/",                              "vc_portfolio"),
    ("battery.com",             "https://www.battery.com/portfolio/",                      "vc_portfolio"),
    ("balderton.com",           "https://www.balderton.com/portfolio/",                    "vc_portfolio"),
    ("atomico.com",             "https://www.atomico.com/portfolio/",                      "vc_portfolio"),
    ("khoslaventures.com",      "https://www.khoslaventures.com/portfolio/",               "vc_portfolio"),
    ("redpoint.com",            "https://www.redpoint.com/portfolio/",                     "vc_portfolio"),
    ("gv.com",                  "https://www.gv.com/portfolio/",                           "vc_portfolio"),
    ("crv.com",                 "https://www.crv.com/portfolio/",                          "vc_portfolio"),
    ("felicis.com",             "https://www.felicis.com/portfolio",                       "vc_portfolio"),

    # ── University / Research Incubators ──────────────────────────────────
    ("atdc.org",                "https://atdc.org/companies/",                             "university_incubator"),
    ("zli.umich.edu",           "https://zli.umich.edu/student-startups/",                 "university_incubator"),
    ("tech.cornell.edu",        "https://tech.cornell.edu/programs/",                      "university_incubator"),
    ("polskycenter.uchicago.edu","https://polskycenter.uchicago.edu/portfolio/",            "university_incubator"),
    ("entrepreneurship.duke.edu","https://entrepreneurship.duke.edu/startups/",             "university_incubator"),
    ("engine.xyz",              "https://engine.xyz/companies/",                           "university_incubator"),
    ("enterprise.cam.ac.uk",    "https://www.enterprise.cam.ac.uk/companies/",             "university_incubator"),
    ("oxfordsciencesinnovation.com","https://www.oxfordsciencesinnovation.com/companies/",  "university_incubator"),
    ("imperialenterprises.co.uk","https://www.imperialenterprises.co.uk/portfolio/",        "university_incubator"),
    ("whartonentrepreneurship.org","https://entrepreneurship.wharton.upenn.edu/startups/",  "university_incubator"),

    # ── Accelerators ──────────────────────────────────────────────────────
    ("angelpad.com",            "https://angelpad.com/companies/",                         "accelerator"),
    ("boost.vc",                "https://www.boost.vc/portfolio/",                         "accelerator"),
    ("vilcap.com",              "https://vilcap.com/portfolio/",                           "accelerator"),
    ("rockhealth.com",          "https://rockhealth.com/companies/",                       "accelerator"),
    ("betaworks.com",           "https://betaworks.com/portfolio/",                        "accelerator"),
    ("indiebio.co",             "https://indiebio.co/portfolio/",                          "accelerator"),
    ("mattervc.com",            "https://mattervc.com/portfolio/",                         "accelerator"),
    ("launchaccelerator.co",    "https://www.launchaccelerator.co/companies/",             "accelerator"),
    ("techcrunch.com",          "https://techcrunch.com/startups/",                        "discovery_aggregator"),
    ("village-capital.com",     "https://vilcap.com/ventures/",                            "accelerator"),
    ("500.co",                  "https://500.co/companies",                                "accelerator"),  # already have but seed url differs

    # ── Government Programs ────────────────────────────────────────────────
    ("sbir.gov",                "https://www.sbir.gov/sbirsearch/award/all",               "government_program"),
    ("eic.ec.europa.eu",        "https://eic.ec.europa.eu/eic-funding/eic-accelerator_en", "government_program"),
    ("enterprise.gov.sg",       "https://www.enterprise.gov.sg/grow-your-business/",       "government_program"),
    ("startupindia.gov.in",     "https://www.startupindia.gov.in/content/sih/en/recognized-startups.html", "government_program"),
    ("nzte.govt.nz",            "https://www.nzte.govt.nz/",                               "government_program"),

    # ── Discovery Aggregators ─────────────────────────────────────────────
    ("producthunt.com",         "https://www.producthunt.com/",                            "discovery_aggregator"),
    ("f6s.com",                 "https://www.f6s.com/companies/",                          "discovery_aggregator"),
    ("growjo.com",              "https://growjo.com/",                                     "discovery_aggregator"),
    ("signal.nfx.com",          "https://signal.nfx.com/investors",                       "discovery_aggregator"),

    # Two more to reach 150
    ("initialized.com",         "https://www.initialized.com/portfolio/",                  "vc_portfolio"),
    ("ycombinator.com",         "https://www.ycombinator.com/companies",                   "accelerator"),  # will skip (exists)
    ("svangel.com",             "https://svangel.com/portfolio/",                          "vc_portfolio"),
]

# Remove sites that already have a YAML (e.g. 500.co)
_existing = {p.stem for p in YAML_DIR.glob("*.yaml")}


def _check_url(url: str) -> tuple[int, str, str] | None:
    """Returns (status, content_type, body) or None on network error."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        return r.status_code, r.headers.get("Content-Type", ""), r.text[:8000]
    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError,
            requests.exceptions.Timeout):
        return None
    except Exception:
        return None


def _analyse(status: int, ct: str, body: str) -> tuple[str, str] | None:
    """Classify a successful response. Returns None if this URL should be skipped (404)."""
    if status == 404:
        return None  # caller will try next URL
    if status in (401, 403, 407):
        return "challenging", f"HTTP {status} — auth/bot block"
    if status >= 500:
        return "challenging", f"HTTP {status} — server error"
    if "application/json" in ct:
        return "easy_candidate", "JSON API response"

    js_markers = [
        "__NEXT_DATA__", "window.__INITIAL_STATE__", "React.createElement",
        "ng-app", "data-reactroot", "nuxt", "__nuxt",
        "<noscript>You need to enable JavaScript</noscript>",
        "Enable JavaScript", "JavaScript is required",
    ]
    auth_markers = ["log in", "login", "sign in", "sign-in", "create an account",
                    "please authenticate"]

    body_lower = body.lower()
    js_heavy = any(m.lower() in body_lower for m in js_markers)
    auth_wall = any(m in body_lower for m in auth_markers)

    if auth_wall and len(body) < 5000:
        return "challenging", "login/auth wall detected"
    if js_heavy:
        text_content = re.sub(r"<[^>]+>", " ", body)
        words = len(text_content.split())
        if words < 150:
            return "challenging", "JS-rendered SPA with little static content"
        return "easy_candidate", f"JS framework but {words} words of static content"

    links = len(re.findall(r"<a\s", body, re.IGNORECASE))
    if links > 20:
        return "easy_candidate", f"clean HTML with {links} links"
    return "easy_candidate", f"static HTML (HTTP {status})"


def probe(seed_url: str) -> tuple[str, str]:
    """
    Try the seed URL then common portfolio path variants.
    Returns (scrapeability, reason).
    """
    from urllib.parse import urlparse
    parsed = urlparse(seed_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    # URL candidates: seed first, then common portfolio paths, then root
    path_variants = ["/portfolio", "/companies", "/investments", "/portfolio/",
                     "/companies/", "/our-companies", "/"]
    candidates = [seed_url]
    for p in path_variants:
        candidate = base + p
        if candidate != seed_url:
            candidates.append(candidate)

    working_url = None
    for url in candidates:
        result = _check_url(url)
        if result is None:
            # network error on this URL — try next but track the type of failure
            continue
        status, ct, body = result
        analysis = _analyse(status, ct, body)
        if analysis is None:
            continue  # 404 — try next path
        # Got a real answer
        working_url = url
        scrapeability, reason = analysis
        if working_url != seed_url:
            reason += f" (found at {working_url})"
        return scrapeability, reason

    # All paths failed or timed out
    result = _check_url(base + "/")
    if result is None:
        return "challenging", "connection refused / DNS failure / timeout"
    status, _, _ = result
    if status == 404:
        return "challenging", "site returns 404 on all portfolio paths"
    return "challenging", f"no accessible portfolio page found (root HTTP {status})"


def make_stub(domain: str, seed_url: str, category: str,
              scrapeability: str, reason: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "version": 1,
        "domain": domain,
        "category": category,
        "created_at": now,
        "updated_at": now,
        "seed_urls": [seed_url],
        "preferred_strategy": "single_page_extract",
        "fallback_order": ["single_page_extract", "subpage_discovery", "pagination_probe"],
        "subpage_hints": [],
        "pagination_hints": [],
        "quality_expectation_min_records": 1,
        "probe_result": scrapeability,
        "probe_reason": reason,
        "last_success": None,
        "notes": None,
    }


def main() -> None:
    added = 0
    skipped = 0
    results: list[tuple[str, str, str, str]] = []  # domain, category, scrapeability, reason

    for domain, seed_url, category in NEW_SITES:
        if domain in _existing:
            print(f"  skip  {domain} (already exists)")
            skipped += 1
            continue

        print(f"  probe {domain} ...", end=" ", flush=True)
        scrapeability, reason = probe(seed_url)
        badge = "✓" if scrapeability == "easy_candidate" else "✗"
        print(f"{badge} {scrapeability}  ({reason})")

        stub = make_stub(domain, seed_url, category, scrapeability, reason)
        out = YAML_DIR / f"{domain}.yaml"
        out.write_text(yaml.dump(stub, default_flow_style=False, sort_keys=False, allow_unicode=True))
        results.append((domain, category, scrapeability, reason))
        added += 1
        time.sleep(0.4)  # polite crawl delay

    total_yaml = len(list(YAML_DIR.glob("*.yaml")))
    easy = sum(1 for _, _, s, _ in results if s == "easy_candidate")
    hard = sum(1 for _, _, s, _ in results if s == "challenging")

    print()
    print("=" * 56)
    print(f"  Added {added} new sites  (skipped {skipped} duplicates)")
    print(f"  Total YAML inventory: {total_yaml} sites")
    print(f"  New sites — easy candidate: {easy}  |  challenging: {hard}")
    print("=" * 56)


if __name__ == "__main__":
    main()
