#!/usr/bin/env python3
"""
International Incubator Portfolio Scraper
==========================================
Scrapes startup portfolio data from international accelerators/incubators
listed in ai-startup-tracker/international_incubators.csv.

Each scraper injects the incubator's known country/city so the DB stores
location info even for companies without a website.

Usage:
    python scripts/scrape_international_incubators.py --dry-run
    python scripts/scrape_international_incubators.py --source rockstart
    python scripts/scrape_international_incubators.py --init-db
"""
import argparse
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _ROOT)

from backend.db.connection import session_scope, init_db
from backend.db.models import (
    Company, IncubatorSignal, IncubatorSource,
    LocationSource, VerificationStatus,
)
from backend.utils.domain import canonicalize_domain
from backend.utils.normalize import normalize_company_name

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("intl_incubator_scraper")

REQUEST_DELAY = 1.5


# ── HTTP helpers ────────────────────────────────────────────────────────

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
    })
    return s


def _get(session: requests.Session, url: str, retries: int = 3, **kwargs) -> Optional[requests.Response]:
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=25, **kwargs)
            if resp.status_code == 200:
                return resp
            logger.warning(f"HTTP {resp.status_code}: {url}")
            if resp.status_code == 429:
                time.sleep(30 * (2 ** attempt))
                continue
            return resp
        except requests.exceptions.ConnectionError as e:
            err_str = str(e)
            if "NameResolutionError" in err_str or "nodename nor servname" in err_str:
                logger.warning(f"DNS failure (skipping retries): {url}")
                return None
            wait = 10 * (2 ** attempt)
            logger.warning(f"Connection error (attempt {attempt+1}/{retries}): {e}")
            time.sleep(wait)
        except requests.exceptions.Timeout as e:
            wait = 10 * (2 ** attempt)
            logger.warning(f"Timeout (attempt {attempt+1}/{retries}): {e}")
            time.sleep(wait)
    logger.error(f"Failed: {url}")
    return None


_JUNK = {
    "portfolio", "companies", "startups", "team", "about", "featured",
    "all companies", "our portfolio", "learn more", "view all", "see all",
    "investments", "graduates", "founders", "alumni", "cohort", "batch",
    "apply", "contact", "news", "events", "jobs", "careers", "industries",
    "company type", "search", "other", "filter", "industry",
}
_BAD_PATS = re.compile(
    r"\b(learn more|view all|see all|apply now|read more|contact us|subscribe"
    r"|portfolio|companies|startups|founders|graduates)\b",
    re.IGNORECASE,
)


def _valid(name: Optional[str]) -> bool:
    if not name:
        return False
    s = re.sub(r"\s+", " ", name).strip()
    if not (2 <= len(s) <= 80):
        return False
    if s.lower() in _JUNK:
        return False
    if re.fullmatch(r"[\W_]+", s):
        return False
    if s.count(" ") > 6:
        return False
    if _BAD_PATS.search(s):
        return False
    return True


def _dedup(companies: List[Dict]) -> List[Dict]:
    seen, unique = set(), []
    for c in companies:
        k = c["name"].lower().strip()
        if k and k not in seen:
            seen.add(k)
            unique.append(c)
    return unique


def _rec(name: str, source: IncubatorSource, country: str, city: str, **kw) -> Dict:
    return {
        "name": name,
        "website_url": kw.get("website_url"),
        "logo_url": kw.get("logo_url"),
        "industry": kw.get("industry"),
        "batch": kw.get("batch"),
        "program": kw.get("program"),
        "description": kw.get("description"),
        "profile_url": kw.get("profile_url"),
        "source": source,
        "_country": country,
        "_city": city,
    }


# ── Scrapers ─────────────────────────────────────────────────────────────

def scrape_era_nyc(session: requests.Session) -> List[Dict]:
    """ERA NYC — New York, USA
    Company names are in <h2> tags at /companies/.
    """
    logger.info("Scraping ERA NYC...")
    url = "https://www.eranyc.com/companies/"
    resp = _get(session, url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []
    for h2 in soup.find_all("h2"):
        name = h2.get_text(strip=True)
        if _valid(name):
            companies.append(_rec(name, IncubatorSource.era_nyc, "USA", "New York"))

    companies = _dedup(companies)
    logger.info(f"ERA NYC: {len(companies)} companies")
    return companies


def scrape_ventures_platform(session: requests.Session) -> List[Dict]:
    """Ventures Platform — Lagos, Nigeria
    Company names in img[alt] within .portfolio-container-section.
    """
    logger.info("Scraping Ventures Platform...")
    resp = _get(session, "https://venturesplatform.com/portfolio")
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    section = soup.select_one(".portfolio-container-section")
    if not section:
        logger.warning("Ventures Platform: portfolio section not found")
        return []

    companies = []
    for img in section.find_all("img", alt=True):
        name = img.get("alt", "").strip()
        if _valid(name):
            parent = img.find_parent("a", href=True)
            website = parent.get("href") if parent and parent.get("href", "").startswith("http") else None
            companies.append(_rec(name, IncubatorSource.ventures_platform, "Nigeria", "Lagos",
                                  website_url=website, logo_url=img.get("src")))

    companies = _dedup(companies)
    logger.info(f"Ventures Platform: {len(companies)} companies")
    return companies


def scrape_parallel18(session: requests.Session) -> List[Dict]:
    """Parallel18 — San Juan, Puerto Rico
    Companies in .startup_item cards with h2 names.
    """
    logger.info("Scraping Parallel18...")
    resp = _get(session, "https://parallel18.com/p18-startups/")
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    items = soup.select(".startup_item")
    if not items:
        logger.warning("Parallel18: .startup_item not found")
        return []

    companies = []
    for item in items:
        h = item.find(["h2", "h3", "h4", "h5", "strong"])
        name = h.get_text(strip=True) if h else None
        if not _valid(name):
            continue
        # Industry from next sibling text
        industry = None
        sibs = item.find_all("p")
        if sibs:
            industry = sibs[0].get_text(strip=True)[:100] if sibs[0].get_text(strip=True) else None
        desc_el = item.select_one(".startup_description")
        desc = desc_el.get_text(" ", strip=True)[:300] if desc_el else None
        companies.append(_rec(name, IncubatorSource.parallel18, "Puerto Rico", "San Juan",
                              industry=industry, description=desc))

    companies = _dedup(companies)
    logger.info(f"Parallel18: {len(companies)} companies")
    return companies


def scrape_rockstart(session: requests.Session) -> List[Dict]:
    """Rockstart — Amsterdam, Netherlands
    Companies in .elementor-post elements at /portfolio/.
    """
    logger.info("Scraping Rockstart...")
    resp = _get(session, "https://rockstart.com/portfolio/")
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    items = soup.select(".elementor-post")
    if not items:
        logger.warning("Rockstart: .elementor-post not found")
        return []

    companies = []
    for item in items:
        h = item.find(["h2", "h3", "h4", "h5"])
        name = h.get_text(strip=True) if h else None
        if not _valid(name):
            continue
        link = item.find("a", href=True)
        href = link.get("href", "") if link else ""
        website = href if href.startswith("http") and "rockstart" not in href else None
        profile = href if href.startswith("http") and "rockstart" in href else None
        companies.append(_rec(name, IncubatorSource.rockstart, "Netherlands", "Amsterdam",
                              website_url=website, profile_url=profile))

    companies = _dedup(companies)
    logger.info(f"Rockstart: {len(companies)} companies")
    return companies


def scrape_hax(session: requests.Session) -> List[Dict]:
    """HAX — Shenzhen, China / San Francisco
    Company names in <h3> tags on the homepage.
    Filters out monetary/stats values.
    """
    logger.info("Scraping HAX...")
    resp = _get(session, "https://hax.co/")
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []
    _STATS = re.compile(r"^\$|^\d+[,\d]*[BMK]?$|%|email|monthly|get ")

    for h3 in soup.find_all("h3"):
        name = h3.get_text(strip=True)
        if not _valid(name):
            continue
        if _STATS.search(name.lower()):
            continue
        companies.append(_rec(name, IncubatorSource.hax, "China", "Shenzhen"))

    companies = _dedup(companies)
    logger.info(f"HAX: {len(companies)} companies")
    return companies


def scrape_surge(session: requests.Session) -> List[Dict]:
    """Surge — Singapore (Sequoia's SE Asia program, now Peak XV)
    Companies in .column-Item elements; name is 'Link - [Name] ...'
    """
    logger.info("Scraping Surge (Peak XV)...")
    resp = _get(session, "https://surge.peakxv.com/startups/")
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    items = soup.select(".column-Item")
    if not items:
        logger.warning("Surge: .column-Item not found")
        return []

    companies = []
    for item in items:
        text = item.get_text(" ", strip=True)
        # Format: "Link - CompanyName Description..."
        m = re.match(r"Link\s*-\s*([A-Za-z0-9][^\n]{1,50?})(?:\s{2,}|\s+[A-Z][a-z]{2,})", text)
        if m:
            name = m.group(1).strip()
        else:
            # fallback: first word group after "Link -"
            m2 = re.match(r"Link\s*-\s*(\S+(?:\s+\S+){0,3})", text)
            name = m2.group(1).strip() if m2 else None
        if not _valid(name):
            continue
        link = item.find("a", href=True)
        href = link.get("href", "") if link else ""
        website = href if href.startswith("http") and "peakxv" not in href and "surge" not in href else None
        companies.append(_rec(name, IncubatorSource.surge, "Singapore", "Singapore",
                              website_url=website))

    companies = _dedup(companies)
    logger.info(f"Surge: {len(companies)} companies")
    return companies


def scrape_sparklabs(session: requests.Session) -> List[Dict]:
    """SparkLabs — Seoul, South Korea
    Extracts ASCII company name from Korean portfolio page links.
    """
    logger.info("Scraping SparkLabs...")
    resp = _get(session, "https://sparklabs.co.kr/kr/portfolio")
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "portfolio/" not in href or "sparklabs" not in href:
            continue
        slug = href.rstrip("/").split("/")[-1]
        if not slug or slug == "portfolio":
            continue

        link_text = a.get_text(" ", strip=True)
        # Extract ASCII/Latin portion before Korean characters
        ascii_part = re.match(r"^([A-Za-z0-9][A-Za-z0-9\s\-\&\.]+)", link_text)
        if ascii_part:
            name = ascii_part.group(1).strip()
        else:
            name = slug.replace("-", " ").title()

        if _valid(name) and name.lower() not in seen:
            seen.add(name.lower())
            companies.append(_rec(name, IncubatorSource.sparklabs, "South Korea", "Seoul",
                                  profile_url=href))

    companies = _dedup(companies)
    logger.info(f"SparkLabs: {len(companies)} companies")
    return companies


def scrape_sting(session: requests.Session) -> List[Dict]:
    """Sting — Stockholm, Sweden
    Each .filters5_feed_item has a hidden <a href="/companies/slug">.
    Extract name from the slug (reliably avoids bleeding into descriptions).
    """
    logger.info("Scraping Sting Stockholm...")
    resp = _get(session, "https://sting.co/companies")
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    items = soup.select(".filters5_feed_item")
    if not items:
        logger.warning("Sting: .filters5_feed_item not found")
        return []

    companies = []
    for item in items:
        # The hidden link carries the slug: /companies/novabirth
        link = item.find("a", href=re.compile(r"^/companies/"))
        slug = link.get("href", "").split("/companies/")[-1].strip("/") if link else None
        if not slug:
            continue
        name = slug.replace("-", " ").title()
        if not _valid(name):
            continue

        profile_url = urljoin("https://sting.co", link.get("href", ""))

        # Logo from img src filename
        img = item.find("img", src=True)
        logo = img.get("src") if img else None

        companies.append(_rec(name, IncubatorSource.sting_stockholm, "Sweden", "Stockholm",
                              logo_url=logo, profile_url=profile_url))

    companies = _dedup(companies)
    logger.info(f"Sting: {len(companies)} companies")
    return companies


def scrape_nxtp_ventures(session: requests.Session) -> List[Dict]:
    """NXTP Ventures — Buenos Aires, Argentina
    Company names extracted from SVG/PNG image filenames in portfolio.
    """
    logger.info("Scraping NXTP Ventures...")
    resp = _get(session, "https://www.nxtp.vc/portfolio")
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []
    seen = set()
    _SKIP_SUFFIXES = {"linkedin", "website", "icon", "logo", "arrow", "close", "linkedin", "back"}

    for img in soup.find_all("img", src=True):
        src = img.get("src", "")
        if "website-files" not in src:
            continue
        # Extract filename: last segment after final underscore
        path = urlparse(src).path
        raw = unquote(path.split("/")[-1])
        raw = re.sub(r"\.[a-z]{2,5}$", "", raw, flags=re.IGNORECASE)
        # Remove leading hash segment (Webflow CDN adds a hash_name format)
        parts = raw.split("_")
        fname = parts[-1] if len(parts) > 1 else raw
        # Strip trailing numbers/version suffixes
        fname = re.sub(r"[-_]?\d+$", "", fname).strip("-_")
        # Normalize to title case
        name = fname.replace("-", " ").strip()

        if not name or name.lower() in _SKIP_SUFFIXES:
            continue
        if name.lower() in seen or not _valid(name):
            continue
        seen.add(name.lower())
        companies.append(_rec(name, IncubatorSource.nxtp_ventures, "Argentina", "Buenos Aires"))

    companies = _dedup(companies)
    logger.info(f"NXTP Ventures: {len(companies)} companies")
    return companies


def _generic_scrape(
    session: requests.Session,
    urls: List[str],
    source: IncubatorSource,
    source_name: str,
    country: str,
    city: str,
    card_selectors: Optional[List[str]] = None,
) -> List[Dict]:
    """Fallback generic scraper with heading scan."""
    card_sels = card_selectors or [
        "div.company-card", "div.portfolio-card", "div.portfolio-item",
        "div.startup-card", "article.company", "article.startup",
        "li.company", "li.startup", "div.w-dyn-item",
    ]
    for url in urls:
        resp = _get(session, url)
        if not resp:
            time.sleep(REQUEST_DELAY)
            continue

        soup = BeautifulSoup(resp.text, "lxml")
        host = urlparse(url).netloc
        companies: List[Dict] = []

        # Try Next.js JSON
        script = soup.find("script", id="__NEXT_DATA__")
        if script and script.string:
            try:
                raw = json.dumps(json.loads(script.string))
                for m in re.finditer(
                    r'"(?:name|companyName|company_name|organizationName)"\s*:\s*"([^"]{2,80})"',
                    raw,
                ):
                    name = m.group(1).strip()
                    if _valid(name):
                        companies.append(_rec(name, source, country, city))
                if companies:
                    companies = _dedup(companies)
                    logger.info(f"{source_name}: {len(companies)} from __NEXT_DATA__")
                    return companies
            except Exception:
                pass

        # Try card selectors
        items = []
        for sel in card_sels:
            items = soup.select(sel)
            if len(items) >= 3:
                break

        if len(items) >= 3:
            for item in items:
                h = (item.find("h2") or item.find("h3") or item.find("h4")
                     or item.find("h5") or item.find("strong"))
                name = h.get_text(strip=True) if h else None
                if not name:
                    img = item.find("img", alt=True)
                    name = img.get("alt", "").strip() if img else None
                if not _valid(name):
                    continue
                link = item.find("a", href=True)
                href = link.get("href", "") if link else ""
                if href.startswith("/"):
                    href = urljoin(url, href)
                website = href if href.startswith("http") and host not in href else None
                profile = href if href.startswith("http") and host in href else None
                companies.append(_rec(name, source, country, city,
                                      website_url=website, profile_url=profile))
            if companies:
                companies = _dedup(companies)
                logger.info(f"{source_name}: {len(companies)} from card selectors at {url}")
                return companies

        # Heading scan fallback
        headings = soup.find_all(["h3", "h4"])
        if len(headings) >= 5:
            for h in headings:
                name = h.get_text(strip=True)
                if _valid(name):
                    companies.append(_rec(name, source, country, city))
            if companies:
                companies = _dedup(companies)
                logger.info(f"{source_name}: {len(companies)} from heading scan at {url}")
                return companies

        time.sleep(REQUEST_DELAY)

    logger.warning(f"{source_name}: 0 companies found")
    return []


# ── Remaining scrapers using the generic helper ────────────────────────

def scrape_startup_chile(session: requests.Session) -> List[Dict]:
    """Start-Up Chile — Santiago, Chile"""
    logger.info("Scraping Start-Up Chile...")
    return _generic_scrape(
        session,
        ["https://www.startupchile.org/startups/", "https://www.startupchile.org/"],
        IncubatorSource.startup_chile, "Start-Up Chile", "Chile", "Santiago",
        card_selectors=["div.startup-item", "div.company-card", "article.startup",
                        "div.w-dyn-item", "article", "div.post"],
    )


def scrape_flat6labs(session: requests.Session) -> List[Dict]:
    """Flat6Labs — Cairo, Egypt"""
    logger.info("Scraping Flat6Labs...")
    return _generic_scrape(
        session,
        ["https://flat6labs.com/", "https://www.flat6labs.com/"],
        IncubatorSource.flat6labs, "Flat6Labs", "Egypt", "Cairo",
        card_selectors=["div.startup-card", "div.company-card", "article.startup",
                        "div.w-dyn-item", "li.startup"],
    )


def scrape_wayra(session: requests.Session) -> List[Dict]:
    """Wayra — Madrid, Spain"""
    logger.info("Scraping Wayra...")
    return _generic_scrape(
        session,
        ["https://startups.telefonica.com/", "https://www.wayra.com/"],
        IncubatorSource.wayra, "Wayra", "Spain", "Madrid",
        card_selectors=["div.startup-card", "div.company-card", "div.portfolio-item",
                        "article.startup", "div.w-dyn-item"],
    )


def scrape_allvp(session: requests.Session) -> List[Dict]:
    """ALLVP / Hi Ventures — Mexico City, Mexico"""
    logger.info("Scraping ALLVP (Hi Ventures)...")
    return _generic_scrape(
        session,
        ["https://allvp.vc/portfolio", "https://www.hi.vc/portfolio",
         "https://allvp.vc/", "https://www.hi.vc/"],
        IncubatorSource.allvp, "ALLVP", "Mexico", "Mexico City",
        card_selectors=["div.portfolio-item", "div.company-card", "div.w-dyn-item",
                        "article.company"],
    )


def scrape_seedstars(session: requests.Session) -> List[Dict]:
    """Seedstars — Geneva, Switzerland"""
    logger.info("Scraping Seedstars...")
    return _generic_scrape(
        session,
        ["https://www.seedstars.com/companies/",
         "https://www.seedstars-international.vc/portfolio",
         "https://www.seedstars.com/"],
        IncubatorSource.seedstars, "Seedstars", "Switzerland", "Geneva",
        card_selectors=["div.company-card", "div.portfolio-item", "div.w-dyn-item",
                        "article.startup", "div.startup-card"],
    )


def scrape_station_f(session: requests.Session) -> List[Dict]:
    """Station F — Paris, France"""
    logger.info("Scraping Station F...")
    return _generic_scrape(
        session,
        ["https://stationf.co/startups", "https://stationf.co/companies/"],
        IncubatorSource.station_f, "Station F", "France", "Paris",
        card_selectors=["div.startup-card", "div.company-card", "div.w-dyn-item",
                        "article.startup"],
    )


def scrape_startupbootcamp(session: requests.Session) -> List[Dict]:
    """Startupbootcamp — London, UK"""
    logger.info("Scraping Startupbootcamp...")
    return _generic_scrape(
        session,
        ["https://www.startupbootcamp.org/startups/portfolio-companies",
         "https://www.startupbootcamp.org/"],
        IncubatorSource.startupbootcamp, "Startupbootcamp", "UK", "London",
        card_selectors=["div.startup-card", "div.company-card", "article.startup",
                        "div.portfolio-item", "div.w-dyn-item"],
    )


def scrape_h_farm(session: requests.Session) -> List[Dict]:
    """H-Farm — Venice, Italy"""
    logger.info("Scraping H-Farm...")
    return _generic_scrape(
        session,
        ["https://www.h-farm.com/en/portfolio/", "https://www.h-farm.com/en/"],
        IncubatorSource.h_farm, "H-Farm", "Italy", "Venice",
        card_selectors=["div.portfolio-item", "div.company-card", "article.startup",
                        "div.w-dyn-item"],
    )


def scrape_brinc(session: requests.Session) -> List[Dict]:
    """BRINC — Hong Kong"""
    logger.info("Scraping BRINC...")
    return _generic_scrape(
        session,
        ["https://brinc.io/portfolio/", "https://brinc.io/companies/",
         "https://brinc.io/"],
        IncubatorSource.brinc, "BRINC", "Hong Kong", "Hong Kong",
        card_selectors=["div.portfolio-item", "div.company-card", "div.w-dyn-item",
                        "article.company"],
    )


def scrape_astrolabs(session: requests.Session) -> List[Dict]:
    """AstroLabs — Dubai, UAE"""
    logger.info("Scraping AstroLabs...")
    return _generic_scrape(
        session,
        ["https://astrolabs.com/companies/", "https://astrolabs.com/portfolio/",
         "https://astrolabs.com/"],
        IncubatorSource.astrolabs, "AstroLabs", "UAE", "Dubai",
        card_selectors=["div.company-card", "div.portfolio-item", "div.w-dyn-item",
                        "article.company"],
    )


def scrape_grindstone(session: requests.Session) -> List[Dict]:
    """Grindstone Accelerator — Cape Town, South Africa"""
    logger.info("Scraping Grindstone...")
    return _generic_scrape(
        session,
        ["https://grindstoneaccelerator.co.za/portfolio/",
         "https://grindstoneaccelerator.co.za/"],
        IncubatorSource.grindstone, "Grindstone", "South Africa", "Cape Town",
        card_selectors=["div.portfolio-item", "div.company-card", "article.startup",
                        "div.w-dyn-item", "article"],
    )


# ── DB upsert ──────────────────────────────────────────────────────────

def upsert_companies(records: List[Dict]) -> Dict[str, int]:
    stats = {"new_companies": 0, "updated_companies": 0,
             "new_signals": 0, "updated_signals": 0}

    with session_scope() as db:
        now = datetime.now(timezone.utc)

        for rec in records:
            name = rec["name"].strip()
            if not name:
                continue

            source: IncubatorSource = rec["source"]
            norm = normalize_company_name(name)
            domain = canonicalize_domain(rec["website_url"]) if rec.get("website_url") else None
            country = rec.get("_country")
            city = rec.get("_city")

            company = None
            if domain:
                company = db.query(Company).filter(Company.domain == domain).first()
            if not company and norm:
                company = db.query(Company).filter(Company.normalized_name == norm).first()

            if company:
                company.last_seen_at = now
                company.updated_at = now
                if not company.incubator_source:
                    company.incubator_source = source
                if domain and not company.domain:
                    company.domain = domain
                if city and not company.city:
                    company.city = city
                if country and not company.country:
                    company.country = country
                    company.location_source = LocationSource.unknown
                stats["updated_companies"] += 1
            else:
                company = Company(
                    name=name, domain=domain, normalized_name=norm,
                    incubator_source=source,
                    verification_status=VerificationStatus.emerging_github,
                    country=country, city=city,
                    location_source=LocationSource.unknown if country else None,
                    first_seen_at=now, last_seen_at=now,
                    created_at=now, updated_at=now,
                )
                db.add(company)
                db.flush()
                stats["new_companies"] += 1

            existing = db.query(IncubatorSignal).filter(
                IncubatorSignal.source == source,
                IncubatorSignal.company_name_raw == name,
            ).first()

            loc_str = ", ".join(filter(None, [city, country]))
            desc = rec.get("description") or ""
            if loc_str:
                desc = f"{desc} | Location: {loc_str}".strip(" |")
            desc = desc or None

            if existing:
                existing.website_url = rec.get("website_url") or existing.website_url
                existing.logo_url = rec.get("logo_url") or existing.logo_url
                existing.industry = rec.get("industry") or existing.industry
                existing.batch = rec.get("batch") or existing.batch
                existing.program = rec.get("program") or existing.program
                existing.description = desc or existing.description
                existing.profile_url = rec.get("profile_url") or existing.profile_url
                existing.collected_at = now
                stats["updated_signals"] += 1
            else:
                db.add(IncubatorSignal(
                    company_id=company.id, source=source,
                    company_name_raw=name,
                    website_url=rec.get("website_url"),
                    logo_url=rec.get("logo_url"),
                    industry=rec.get("industry"),
                    batch=rec.get("batch"),
                    program=rec.get("program"),
                    description=desc,
                    profile_url=rec.get("profile_url"),
                    collected_at=now,
                ))
                stats["new_signals"] += 1

    return stats


def save_report(records: List[Dict], stats: Dict[str, int]) -> str:
    report_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, f"intl_incubator_{datetime.now().strftime('%Y-%m-%d')}.json")
    by_src: Dict[str, List] = {}
    for rec in records:
        by_src.setdefault(rec["source"].value, []).append({
            "name": rec["name"],
            "website_url": rec.get("website_url"),
            "country": rec.get("_country"),
            "city": rec.get("_city"),
        })
    with open(path, "w") as f:
        json.dump({
            "run_metadata": {"collected_at": datetime.now(timezone.utc).isoformat(),
                             "total": len(records)},
            "totals": stats,
            "by_source": {src: {"count": len(items), "companies": items}
                          for src, items in by_src.items()},
        }, f, indent=2, default=str)
    logger.info(f"Report: {path}")
    return path


# ── Registry & CLI ────────────────────────────────────────────────────

SCRAPERS = {
    # Americas
    "era_nyc":           scrape_era_nyc,
    "startup_chile":     scrape_startup_chile,
    "parallel18":        scrape_parallel18,
    "wayra":             scrape_wayra,
    "nxtp_ventures":     scrape_nxtp_ventures,
    "allvp":             scrape_allvp,
    # Europe
    "seedstars":         scrape_seedstars,
    "station_f":         scrape_station_f,
    "startupbootcamp":   scrape_startupbootcamp,
    "h_farm":            scrape_h_farm,
    "sting_stockholm":   scrape_sting,
    "rockstart":         scrape_rockstart,
    # Asia / Pacific
    "hax":               scrape_hax,
    "surge":             scrape_surge,
    "brinc":             scrape_brinc,
    "sparklabs":         scrape_sparklabs,
    # MENA
    "flat6labs":         scrape_flat6labs,
    "astrolabs":         scrape_astrolabs,
    # Africa
    "grindstone":        scrape_grindstone,
    "ventures_platform": scrape_ventures_platform,
}


def main():
    parser = argparse.ArgumentParser(description="International Incubator Scraper")
    parser.add_argument("--source", default="all",
                        choices=list(SCRAPERS.keys()) + ["all"])
    parser.add_argument("--init-db", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.init_db:
        init_db()

    sess = _session()
    records: List[Dict] = []
    sources = list(SCRAPERS.keys()) if args.source == "all" else [args.source]

    for name in sources:
        try:
            logger.info(f"── {name} ──")
            r = SCRAPERS[name](sess)
            logger.info(f"{name}: ✓ {len(r)} companies")
            records.extend(r)
        except Exception as e:
            logger.error(f"Failed {name}: {e}", exc_info=True)
        time.sleep(REQUEST_DELAY)

    if not records:
        logger.warning("No companies scraped!")
        return

    logger.info(f"Total: {len(records)} companies from {len(sources)} sources")

    if args.dry_run:
        counts = Counter(r["source"].value for r in records)
        logger.info("── Dry run summary ──")
        for src, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            logger.info(f"  {src:30s}: {cnt:4d}")
        logger.info("── Samples ──")
        for rec in records[:20]:
            loc = f"{rec.get('_city','?')}, {rec.get('_country','?')}"
            logger.info(f"  [{rec['source'].value}] {rec['name']!r:40s} [{loc}]")
    else:
        stats = upsert_companies(records)
        report = save_report(records, stats)
        logger.info("=" * 55)
        logger.info("International Scrape Complete!")
        logger.info(f"  New companies:     {stats['new_companies']}")
        logger.info(f"  Updated companies: {stats['updated_companies']}")
        logger.info(f"  New signals:       {stats['new_signals']}")
        logger.info(f"  Updated signals:   {stats['updated_signals']}")
        logger.info(f"  Report: {report}")
        logger.info("=" * 55)


if __name__ == "__main__":
    main()
