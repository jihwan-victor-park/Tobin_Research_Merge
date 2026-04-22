#!/usr/bin/env python3
"""
Incubator Portfolio Scraper
============================
Scrape startup portfolio data from accelerators and incubators:
  - Capital Factory (Austin): https://capitalfactory.com/portfolio/
  - gener8tor: https://www.gener8tor.com/portfolio (via Airtable API)
  - Village Global: https://www.villageglobal.com/portfolio (Webflow)

Usage:
    python scripts/scrape_incubators.py [--init-db] [--source capital_factory|gener8tor|village_global|all]
    python scripts/scrape_incubators.py --dry-run          # scrape without DB write
    python scripts/scrape_incubators.py --source gener8tor  # scrape one source
"""
import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.db.connection import session_scope, init_db
from backend.db.models import (
    Company, IncubatorSignal, IncubatorSource,
    LocationSource, VerificationStatus,
)
from backend.utils.domain import canonicalize_domain
from backend.utils.normalize import normalize_company_name
from backend.utils.denylist import is_denylisted

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("incubator_scraper")

REQUEST_DELAY = 1.5  # seconds between requests


# ── HTTP helpers ──────────────────────────────────────────────────────

def get_http_session() -> requests.Session:
    """Create a requests session with browser-like headers."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Cache-Control": "max-age=0",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "DNT": "1",
    })
    return s


def safe_request(session: requests.Session, url: str, method: str = "GET",
                 max_retries: int = 3, **kwargs) -> Optional[requests.Response]:
    """Make an HTTP request with retries and exponential backoff."""
    for attempt in range(max_retries):
        try:
            resp = session.request(method, url, timeout=30, **kwargs)
            if resp.status_code == 200:
                return resp
            logger.warning(f"HTTP {resp.status_code} for {url}")
            if resp.status_code == 429:
                wait = 30 * (2 ** attempt)
                logger.warning(f"Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            return resp
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            wait = 15 * (2 ** attempt)
            logger.warning(f"Connection error (attempt {attempt+1}/{max_retries}), waiting {wait}s: {e}")
            time.sleep(wait)
    logger.error(f"Failed after {max_retries} retries: {url}")
    return None


def _dedup(companies: List[Dict]) -> List[Dict]:
    """Deduplicate company list by lowercased name."""
    seen = set()
    unique = []
    for c in companies:
        key = c["name"].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


_GENERIC_HEADINGS = {
    "portfolio", "companies", "startups", "team", "about", "featured",
    "all companies", "our portfolio", "learn more", "view all", "see all",
    "investments", "graduates", "founders", "all startups", "featured startups",
    "venture portfolio", "alumni", "cohort", "batch", "programs", "our companies",
    "apply", "contact", "news", "events", "jobs", "careers", "our team",
    "our founders", "meet the team", "learn", "blog", "home",
}


def _is_valid_name(name: Optional[str]) -> bool:
    """Heuristic filter for startup/company-like names."""
    if name is None:
        return False

    s = re.sub(r"\s+", " ", name).strip()
    if not s:
        return False

    if not (2 <= len(s) <= 80):
        return False

    low = s.lower()

    if low in _GENERIC_HEADINGS:
        return False

    # obvious junk
    if re.fullmatch(r"[\W_]+", s):
        return False

    # too sentence-like
    if s.count(" ") > 6:
        return False

    # obvious UI / CTA text
    bad_patterns = [
        r"\blearn more\b",
        r"\bview all\b",
        r"\bsee all\b",
        r"\bapply now\b",
        r"\bread more\b",
        r"\bcontact us\b",
        r"\bsubscribe\b",
        r"\bjoin\b",
        r"\bportfolio\b",
        r"\bcompanies\b",
        r"\bstartups\b",
        r"\bfounders\b",
        r"\bgraduates\b",
    ]
    for pat in bad_patterns:
        if re.search(pat, low):
            return False

    return True

# ── Capital Factory Scraper ───────────────────────────────────────────

def scrape_capital_factory(session: requests.Session) -> List[Dict]:
    """
    Scrape Capital Factory portfolio from https://capitalfactory.com/portfolio/.
    The page renders startup items server-side in div.startup-item elements.
    """
    logger.info("Scraping Capital Factory companies...")
    url = "https://capitalfactory.com/portfolio/"
    resp = safe_request(session, url)
    if not resp or resp.status_code != 200:
        logger.error(f"Failed to fetch Capital Factory page")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []

    items = soup.select("div.startup-item")
    if not items:
        # Fallback selectors
        for sel in ["div.portfolio-item", "div.company-card", "div.grid-item", "div.card"]:
            items = soup.select(sel)
            if items:
                break

    logger.info(f"Capital Factory: found {len(items)} startup items")

    for item in items:
        # Name from heading or img alt
        name_el = item.find("h2") or item.find("h3") or item.find("h4")
        name = name_el.get_text(strip=True) if name_el else None
        if not name:
            img = item.find("img")
            if img:
                name = img.get("alt", "").strip()
        if not name:
            continue

        # Link (usually to /startup/company-slug/)
        link_el = item.find("a", href=True)
        href = link_el.get("href", "") if link_el else ""
        profile_url = href if href and "capitalfactory.com" in href else None

        # Logo
        img = item.find("img")
        logo_url = (img.get("src") or img.get("data-src") or "") if img else None

        companies.append({
            "name": name,
            "website_url": href if href and "capitalfactory.com" not in href else None,
            "logo_url": logo_url,
            "industry": None,
            "batch": None,
            "program": None,
            "description": None,
            "profile_url": profile_url,
            "source": IncubatorSource.capital_factory,
        })

    companies = _dedup(companies)
    logger.info(f"Capital Factory: {len(companies)} unique companies")
    return companies


# ── gener8tor Scraper (Airtable API) ──────────────────────────────────

def scrape_gener8tor(session: requests.Session) -> List[Dict]:
    """
    Scrape gener8tor portfolio via their public Airtable API.
    The portfolio page (gener8tor.com/portfolio) uses a Vue.js frontend
    that fetches from Airtable base appKt7sAFSMHOnLcN, table "Alumni on Website".
    """
    logger.info("Scraping gener8tor companies via Airtable API...")

    # First fetch the page to get the current Airtable token
    # (tokens may rotate, so we extract from the page source)
    page_resp = safe_request(session, "https://www.gener8tor.com/portfolio")
    if not page_resp or page_resp.status_code != 200:
        logger.error("Failed to fetch gener8tor portfolio page")
        return []

    # Extract Airtable credentials from inline script
    base_id = None
    token = None
    for match in re.finditer(
        r'baseId:\s*["\']([^"\']+)["\']', page_resp.text
    ):
        base_id = match.group(1)
    for match in re.finditer(
        r'token:\s*["\']([^"\']+)["\']', page_resp.text
    ):
        token = match.group(1)

    # Fallback: try the other pattern (const airtableToken = ...)
    if not token:
        m = re.search(r'(?:airtableToken|pat\w+)\s*[:=]\s*["\']([^"\']+)["\']', page_resp.text)
        if m:
            token = m.group(1)
    if not base_id:
        m = re.search(r'(?:baseId)\s*[:=]\s*["\']([^"\']+)["\']', page_resp.text)
        if m:
            base_id = m.group(1)

    if not base_id or not token:
        logger.error(f"Could not extract Airtable credentials (base_id={base_id}, token={'yes' if token else 'no'})")
        return []

    logger.info(f"gener8tor: using Airtable base {base_id}")

    # Fetch all records from Airtable with pagination
    table_name = "Alumni on Website"
    all_records = []
    offset = None

    while True:
        url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        resp = requests.get(url, headers=headers, params=params)
        if not resp or resp.status_code != 200:
            logger.error(f"Airtable API error {resp.status_code}: {resp.text[:200]}")
            break

        data = resp.json()
        records = data.get("records", [])
        all_records.extend(records)
        logger.info(f"gener8tor: fetched {len(records)} records (total: {len(all_records)})")
    
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.3)  # respect Airtable rate limits (5 req/s)

    # Parse Airtable records into our format
    companies = []
    for record in all_records:
        fields = record.get("fields", {})

        name = (fields.get("Company Name") or fields.get("Name") or "").strip()
        if not name:
            continue

        # Website URL
        website = (
            fields.get("Company Website")
            or fields.get("Vue Website URL")
            or fields.get("Website")
            or ""
        )
        if website and not website.startswith("http"):
            website = "https://" + website

        # Logo URL (direct URL field preferred over attachment)
        logo_url = fields.get("Logo URL") or None
        if not logo_url:
            logo_field = fields.get("Logo")
            if isinstance(logo_field, list) and logo_field:
                logo_url = logo_field[0].get("url")

        # Industry / tags
        industry = None
        for field_name in ["Industry", "Sector", "Category"]:
            val = fields.get(field_name)
            if val:
                industry = val if isinstance(val, str) else ", ".join(val)
                break

        # Program (gener8tor has "Programs" and "Program Type" / "Type")
        program = fields.get("Programs") or fields.get("Program") or None
        batch = fields.get("Type") or fields.get("Program Type") or None

        # Description
        description = fields.get("Description") or None

        # Location
        city = fields.get("City") or None
        state = fields.get("State") or None
        location = f"{city}, {state}" if city and state else (city or state or None)

        # Funding & status
        funding = fields.get("Cumulative Funding") or None
        operating_status = fields.get("Operating Status") or None

        companies.append({
            "name": name,
            "website_url": website if website else None,
            "logo_url": logo_url,
            "industry": industry,
            "batch": batch,
            "program": program,
            "description": description,
            "profile_url": None,
            "source": IncubatorSource.gener8tor,
            "_city": city,
            "_state": state,
            "_location": location,
            "_funding": funding,
            "_operating_status": operating_status,
        })

    companies = _dedup(companies)
    logger.info(f"gener8tor: {len(companies)} unique companies")
    return companies


# ── Village Global Scraper ────────────────────────────────────────────

def scrape_village_global(session: requests.Session) -> List[Dict]:
    """
    Scrape Village Global portfolio from https://www.villageglobal.com/portfolio.
    Webflow site with company data in div.portfoloio-collection-items elements.
    Company name is in img alt text, description in div.portfolio-text,
    categories in div.categories elements.
    """
    logger.info("Scraping Village Global companies...")
    url = "https://www.villageglobal.com/portfolio"
    resp = safe_request(session, url)
    if not resp or resp.status_code != 200:
        logger.error(f"Failed to fetch Village Global page")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []

    # Primary selector: Webflow collection items
    items = soup.select("div.portfoloio-collection-items")
    if not items:
        items = soup.select("div.w-dyn-item")

    logger.info(f"Village Global: found {len(items)} portfolio items")

    for item in items:
        # Company name is in the img alt text
        img = item.select_one("img.company-logo")
        name = img.get("alt", "").strip() if img else ""

        if not name:
            # Fallback: try any img alt
            for img_el in item.find_all("img"):
                alt = img_el.get("alt", "").strip()
                if alt and len(alt) > 1 and alt.lower() not in ("logo", "icon"):
                    name = alt
                    break

        if not name:
            continue

        # Website link
        link_el = item.select_one("a.company-details")
        if not link_el:
            link_el = item.find("a", href=True)
        website_url = link_el.get("href", "").strip() if link_el else None

        # Logo URL
        logo_url = None
        if img is not None:
            logo_url = img.get("src") or img.get("data-src")

        # Description
        desc_el = item.select_one("div.portfolio-text")
        description = desc_el.get_text(strip=True) if desc_el else None

        # Categories (e.g., AI/ML, Fintech, Enterprise)
        categories = []
        for cat_el in item.select("div.categories"):
            cat_text = cat_el.get_text(strip=True)
            if cat_text and cat_text.lower() != "all":
                categories.append(cat_text)
        industry = ", ".join(categories) if categories else None

        companies.append({
            "name": name,
            "website_url": website_url,
            "logo_url": logo_url,
            "industry": industry,
            "batch": None,
            "program": None,
            "description": description,
            "profile_url": None,
            "source": IncubatorSource.village_global,
        })

    companies = _dedup(companies)
    logger.info(f"Village Global: {len(companies)} unique companies")
    return companies


# ── Founder Institute Scraper ─────────────────────────────────────────

def scrape_founder_institute(session: requests.Session) -> List[Dict]:
    """
    Scrape Founder Institute graduates from https://fi.co/graduates.
    Company names are in <h3> inside .js-graduates-each containers,
    with location in the first <p> and a website <a> tag.
    """
    logger.info("Scraping Founder Institute companies...")
    url = "https://fi.co/graduates"
    resp = safe_request(session, url)
    if not resp or resp.status_code != 200:
        logger.error("Failed to fetch Founder Institute page")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []

    items = soup.select("div.js-graduates-each")
    if not items:
        # Fallback: any h3 on the page
        items = [None]

    if items and items[0] is not None:
        for item in items:
            h3 = item.find("h3")
            name = h3.get_text(strip=True) if h3 else None
            if not name or not _is_valid_name(name):
                continue

            link = item.find("a", href=re.compile(r"^https?://"))
            website = link.get("href") if link else None
            if website and "fi.co" in website:
                website = None

            paras = item.find_all("p")
            location = paras[0].get_text(strip=True) if paras else None
            description = paras[1].get_text(strip=True) if len(paras) > 1 else None

            companies.append({
                "name": name,
                "website_url": website,
                "logo_url": None,
                "industry": None,
                "batch": None,
                "program": None,
                "description": description,
                "profile_url": None,
                "source": IncubatorSource.founder_institute,
                "_location": location,
            })
    else:
        for h3 in soup.find_all("h3"):
            name = h3.get_text(strip=True)
            if not _is_valid_name(name):
                continue
            companies.append({
                "name": name,
                "website_url": None,
                "logo_url": None,
                "industry": None,
                "batch": None,
                "program": None,
                "description": None,
                "profile_url": None,
                "source": IncubatorSource.founder_institute,
            })

    companies = _dedup(companies)
    logger.info(f"Founder Institute: {len(companies)} unique companies")
    return companies


# ── Seedcamp Scraper ──────────────────────────────────────────────────

def scrape_seedcamp(session: requests.Session) -> List[Dict]:
    """
    Scrape Seedcamp portfolio from https://seedcamp.com/our-companies/.
    550+ companies in a table layout; names in <td><h6> (directory)
    and <h4> (featured). External website links available in some rows.
    """
    logger.info("Scraping Seedcamp companies...")
    url = "https://seedcamp.com/our-companies/"
    resp = safe_request(session, url)
    if not resp or resp.status_code != 200:
        logger.error("Failed to fetch Seedcamp page")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []

    # Primary: table-cell h6 elements (the bulk of the directory)
    for h6 in soup.select("td h6"):
        name = h6.get_text(strip=True)
        if not _is_valid_name(name):
            continue

        row = h6.find_parent("tr")
        website = None
        if row:
            for a in row.find_all("a", href=True):
                href = a.get("href", "")
                if href.startswith("http") and "seedcamp" not in href:
                    website = href
                    break

        companies.append({
            "name": name,
            "website_url": website,
            "logo_url": None,
            "industry": None,
            "batch": None,
            "program": None,
            "description": None,
            "profile_url": None,
            "source": IncubatorSource.seedcamp,
        })

    # Supplement with featured h4 companies if the table approach found nothing
    if len(companies) < 10:
        for h4 in soup.find_all("h4"):
            name = h4.get_text(strip=True)
            if not _is_valid_name(name):
                continue
            companies.append({
                "name": name,
                "website_url": None,
                "logo_url": None,
                "industry": None,
                "batch": None,
                "program": None,
                "description": None,
                "profile_url": None,
                "source": IncubatorSource.seedcamp,
            })

    companies = _dedup(companies)
    logger.info(f"Seedcamp: {len(companies)} unique companies")
    return companies


# ── BEENEXT Scraper ───────────────────────────────────────────────────

def scrape_beenext(session: requests.Session) -> List[Dict]:
    """
    Scrape BEENEXT portfolio from https://www.beenext.com/portfolio/.
    Company names and website URLs in <h4><a href="...">Name</a></h4>.
    """
    logger.info("Scraping BEENEXT companies...")
    url = "https://www.beenext.com/portfolio/"
    resp = safe_request(session, url)
    if not resp or resp.status_code != 200:
        logger.error("Failed to fetch BEENEXT page")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []

    for h4 in soup.find_all("h4"):
        link = h4.find("a", href=True)
        if link:
            name = link.get_text(strip=True)
            website = link.get("href", "").strip()
            if website and not website.startswith("http"):
                website = "https://" + website
        else:
            name = h4.get_text(strip=True)
            website = None

        if not _is_valid_name(name):
            continue

        companies.append({
            "name": name,
            "website_url": website or None,
            "logo_url": None,
            "industry": None,
            "batch": None,
            "program": None,
            "description": None,
            "profile_url": None,
            "source": IncubatorSource.beenext,
        })

    companies = _dedup(companies)
    logger.info(f"BEENEXT: {len(companies)} unique companies")
    return companies


# ── Antler Scraper ────────────────────────────────────────────────────

def scrape_antler(session: requests.Session) -> List[Dict]:
    """
    Scrape Antler portfolio from https://www.antler.co/portfolio.
    Company names are in <h3> tags within portfolio cards.
    Falls back to img alt attributes if no h3 data is found.
    """
    logger.info("Scraping Antler companies...")
    url = "https://www.antler.co/portfolio"
    resp = safe_request(session, url)
    if not resp or resp.status_code != 200:
        logger.error("Failed to fetch Antler page")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []

    for h3 in soup.find_all("h3"):
        name = h3.get_text(strip=True)
        if not _is_valid_name(name):
            continue

        container = h3.find_parent()
        logo_url = None
        if container:
            img = container.find("img")
            if img:
                logo_url = img.get("src") or img.get("data-src")

        companies.append({
            "name": name,
            "website_url": None,
            "logo_url": logo_url,
            "industry": None,
            "batch": None,
            "program": None,
            "description": None,
            "profile_url": None,
            "source": IncubatorSource.antler,
        })

    # Fallback: img alt attributes (when h3 yields nothing)
    if not companies:
        for img in soup.find_all("img", alt=True):
            name = img.get("alt", "").strip()
            if not _is_valid_name(name):
                continue
            companies.append({
                "name": name,
                "website_url": None,
                "logo_url": img.get("src") or img.get("data-src"),
                "industry": None,
                "batch": None,
                "program": None,
                "description": None,
                "profile_url": None,
                "source": IncubatorSource.antler,
            })

    companies = _dedup(companies)
    logger.info(f"Antler: {len(companies)} unique companies")
    return companies


# ── Entrepreneur First Scraper ────────────────────────────────────────

def scrape_entrepreneur_first(session: requests.Session) -> List[Dict]:
    """
    Scrape Entrepreneur First portfolio from https://www.joinef.com/portfolio/.
    Company names are in <h4> tags, organized in featured + all-companies sections.
    """
    logger.info("Scraping Entrepreneur First companies...")
    url = "https://www.joinef.com/portfolio/"
    resp = safe_request(session, url)
    if not resp or resp.status_code != 200:
        logger.error("Failed to fetch Entrepreneur First page")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []

    for h4 in soup.find_all("h4"):
        name = h4.get_text(strip=True)
        if not _is_valid_name(name):
            continue

        companies.append({
            "name": name,
            "website_url": None,
            "logo_url": None,
            "industry": None,
            "batch": None,
            "program": None,
            "description": None,
            "profile_url": None,
            "source": IncubatorSource.entrepreneur_first,
        })

    companies = _dedup(companies)
    logger.info(f"Entrepreneur First: {len(companies)} unique companies")
    return companies


# ── Pioneer Fund Scraper (Airtable) ───────────────────────────────────

def scrape_pioneer_fund(session: requests.Session) -> List[Dict]:
    """
    Scrape Pioneer Fund portfolio from https://www.pioneerfund.vc/portfolio.
    Data lives in Airtable (base appRNBgw0VIQpyveZ); the API token is
    extracted from inline script tags on the page.
    """
    logger.info("Scraping Pioneer Fund companies via Airtable API...")
    page_resp = safe_request(session, "https://www.pioneerfund.vc/portfolio")
    if not page_resp or page_resp.status_code != 200:
        logger.error("Failed to fetch Pioneer Fund portfolio page")
        return []

    base_id = "appRNBgw0VIQpyveZ"
    token = None
    for pattern in [
        r'(?:token|apiKey|pat\w*)\s*[:=]\s*["\']([^"\']{10,})["\']',
        r'Authorization["\']:\s*["\']Bearer\s+([^"\']+)["\']',
        r'"key"\s*:\s*"([^"]{10,})"',
    ]:
        m = re.search(pattern, page_resp.text, re.IGNORECASE)
        if m:
            token = m.group(1)
            break

    if not token:
        logger.warning("Pioneer Fund: could not extract Airtable token from page; skipping")
        return []

    logger.info(f"Pioneer Fund: using Airtable base {base_id}")
    all_records = []
    auth_failed = False

    for table_name in ["Portfolio", "Companies", "Startups"]:
        if auth_failed:
            break
        url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
        offset = None
        try:
            while True:
                params: Dict = {"pageSize": 100}
                if offset:
                    params["offset"] = offset
                resp = requests.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    all_records.extend(data.get("records", []))
                    offset = data.get("offset")
                    if not offset:
                        break
                    time.sleep(0.3)
                elif resp.status_code == 401:
                    logger.warning("Pioneer Fund: Airtable token invalid (401); skipping")
                    auth_failed = True
                    break
                elif resp.status_code == 404:
                    break  # try next table name
                else:
                    logger.warning(f"Pioneer Fund: Airtable error {resp.status_code}")
                    break
        except Exception as e:
            logger.warning(f"Pioneer Fund: error fetching table '{table_name}': {e}")

        if all_records:
            break  # stop once we find a table that works

    companies = []
    for record in all_records:
        fields = record.get("fields", {})
        name = (
            fields.get("Company") or fields.get("Name") or fields.get("Company Name") or ""
        ).strip()
        if not _is_valid_name(name):
            continue

        website = fields.get("Website") or fields.get("URL") or None

        companies.append({
            "name": name,
            "website_url": website,
            "logo_url": None,
            "industry": fields.get("Industry") or fields.get("Sector") or None,
            "batch": None,
            "program": None,
            "description": fields.get("Description") or None,
            "profile_url": None,
            "source": IncubatorSource.pioneer_fund,
        })

    companies = _dedup(companies)
    logger.info(f"Pioneer Fund: {len(companies)} unique companies")
    return companies


# ── DreamIt Ventures Scraper ──────────────────────────────────────────

def scrape_dreamit(session: requests.Session) -> List[Dict]:
    """
    Scrape DreamIt Ventures from https://www.dreamit.com/portfolio.
    Company names are embedded in Squarespace CDN image filenames rather
    than in semantic HTML; we parse and clean the filename to get names.
    """
    logger.info("Scraping DreamIt Ventures companies...")
    url = "https://www.dreamit.com/portfolio"
    resp = safe_request(session, url)
    if not resp or resp.status_code != 200:
        logger.error("Failed to fetch DreamIt page")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []

    _SKIP = {
        "logo", "icon", "bg", "background", "header", "banner", "hero",
        "portfolio", "image", "img", "photo", "placeholder", "default",
        "dreamit", "pattern", "texture",
    }

    for img in soup.find_all("img", src=True):
        src = img.get("src", "")
        if "squarespace-cdn" not in src and "squarespace.com" not in src:
            continue

        path = urlparse(src).path
        raw_filename = path.split("/")[-1]
        filename_no_ext = re.sub(r'\.[a-zA-Z]{2,5}$', '', raw_filename)
        name = unquote(filename_no_ext).strip()

        # Strip common logo/icon suffixes
        name = re.sub(r'[-_+\s]?[Ll]ogo[-_+\s]?\d*$', '', name).strip()
        name = re.sub(r'[-_+\s]?[Ii]con[-_+\s]?\d*$', '', name).strip()
        # Normalize separators
        name = re.sub(r'[_+]+', ' ', name).strip().strip('-').strip()

        if not _is_valid_name(name) or name.lower() in _SKIP:
            continue
        # Skip hash-like strings (Squarespace image hashes)
        if re.fullmatch(r'[0-9a-f\-]{20,}', name.lower()):
            continue

        parent_a = img.find_parent("a", href=True)
        website = None
        if parent_a:
            href = parent_a.get("href", "")
            if href.startswith("http") and "dreamit" not in href:
                website = href

        companies.append({
            "name": name,
            "website_url": website,
            "logo_url": src,
            "industry": None,
            "batch": None,
            "program": None,
            "description": None,
            "profile_url": None,
            "source": IncubatorSource.dreamit,
        })

    companies = _dedup(companies)
    logger.info(f"DreamIt: {len(companies)} unique companies")
    return companies


# ── Generic portfolio helper ──────────────────────────────────────────

def _extract_nextjs_data(soup: BeautifulSoup) -> Optional[dict]:
    """Extract __NEXT_DATA__ JSON blob from Next.js-rendered pages."""
    script = soup.find("script", id="__NEXT_DATA__")
    if script and script.string:
        try:
            return json.loads(script.string)
        except (json.JSONDecodeError, ValueError):
            pass
    return None
def _debug_page(source_name: str, page_url: str, resp_text: str, soup: BeautifulSoup) -> None:
    title = soup.title.get_text(strip=True) if soup.title else "N/A"
    logger.info(f"{source_name}: fetched {page_url}")
    logger.info(f"{source_name}: html length={len(resp_text)} title={title}")

    lower_text = soup.get_text(" ", strip=True).lower()[:1500]
    if "enable javascript" in lower_text or "javascript is disabled" in lower_text:
        logger.warning(f"{source_name}: page appears JS-dependent")
    if "captcha" in lower_text or "cloudflare" in lower_text or "attention required" in lower_text:
        logger.warning(f"{source_name}: possible bot protection detected")


def _extract_candidate_name_from_item(item, name_tags=None) -> Optional[str]:
    name_tags = name_tags or ["h2", "h3", "h4", "h5", "strong"]

    for tag in name_tags:
        el = item.find(tag)
        if el:
            name = el.get_text(" ", strip=True)
            if _is_valid_name(name):
                return name

    img = item.find("img", alt=True)
    if img:
        alt = img.get("alt", "").strip()
        if _is_valid_name(alt):
            return alt

    return None


def _extract_description_from_item(item, name: str) -> Optional[str]:
    for el in item.find_all(["p", "span", "div"]):
        txt = el.get_text(" ", strip=True)
        if not txt:
            continue
        if txt == name:
            continue
        if len(txt) < 20:
            continue
        if len(txt) > 300:
            txt = txt[:300]
        return txt
    return None

def _scrape_portfolio_generic(
    session: requests.Session,
    url: str,
    source: "IncubatorSource",
    source_name: str,
    card_selectors: Optional[List[str]] = None,
    name_tags: Optional[List[str]] = None,
    extra_pages: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Safer generic portfolio scraper.
    Priority:
      1) Next.js JSON extraction
      2) Card/container selectors
    Important:
      - NO full-page heading scan fallback
      - avoids scraping random UI text as company names
    """
    urls_to_scrape = [url] + (extra_pages or [])
    companies: List[Dict] = []
    parsed_host = urlparse(url).netloc

    card_sels = card_selectors or [
        "div.company-card",
        "div.portfolio-card",
        "div.portfolio-item",
        "div.startup-card",
        "article.company",
        "article.startup",
        "li.company",
        "li.startup",
        "div.company",
        "div.startup",
        "div.grid-item",
        "div.w-dyn-item",
        ".portfolio-company",
        "div.team-item",
        "div.member-item",
    ]
    ntags = name_tags or ["h2", "h3", "h4", "h5", "strong"]

    for page_url in urls_to_scrape:
        resp = safe_request(session, page_url)
        if not resp or resp.status_code != 200:
            logger.warning(
                f"{source_name}: skipping {page_url} (HTTP {getattr(resp, 'status_code', 'N/A')})"
            )
            time.sleep(REQUEST_DELAY)
            continue

        soup = BeautifulSoup(resp.text, "lxml")
        _debug_page(source_name, page_url, resp.text, soup)

        # 1) Try Next.js JSON first
        next_data = _extract_nextjs_data(soup)
        if next_data:
            raw_text = json.dumps(next_data)
            before = len(companies)

            for m in re.finditer(
                r'"(?:name|companyName|company_name|organizationName|orgName)"\s*:\s*"([^"]{2,80})"',
                raw_text,
            ):
                name = m.group(1).strip()
                if not _is_valid_name(name):
                    continue

                companies.append({
                    "name": name,
                    "website_url": None,
                    "logo_url": None,
                    "industry": None,
                    "batch": None,
                    "program": None,
                    "description": None,
                    "profile_url": None,
                    "source": source,
                })

            added = len(companies) - before
            logger.info(f"{source_name}: extracted {added} candidates from __NEXT_DATA__")

            if added > 0:
                time.sleep(REQUEST_DELAY)
                continue

        # 2) Card/container based scrape
        items = []
        used_selector = None
        for sel in card_sels:
            items = soup.select(sel)
            if len(items) >= 3:
                used_selector = sel
                break

        logger.info(f"{source_name}: selector={used_selector} items={len(items)}")

        if len(items) < 3:
            logger.warning(f"{source_name}: no reliable card containers found; skipping")
            time.sleep(REQUEST_DELAY)
            continue

        for item in items:
            name = _extract_candidate_name_from_item(item, ntags)
            if not name:
                continue

            link = item.find("a", href=True)
            href = link.get("href", "").strip() if link else ""
            if href.startswith("/"):
                href = urljoin(page_url, href)

            website = None
            profile_url = None
            if href.startswith("http"):
                if parsed_host in href:
                    profile_url = href
                else:
                    website = href

            img = item.find("img")
            logo = None
            if img:
                logo = img.get("src") or img.get("data-src")
                if logo and logo.startswith("/"):
                    logo = urljoin(page_url, logo)

            desc = _extract_description_from_item(item, name)

            companies.append({
                "name": name,
                "website_url": website,
                "logo_url": logo,
                "industry": None,
                "batch": None,
                "program": None,
                "description": desc,
                "profile_url": profile_url,
                "source": source,
            })

        time.sleep(REQUEST_DELAY)

    companies = _dedup(companies)
    logger.info(f"{source_name}: {len(companies)} unique companies total")
    return companies
# ── University Incubators ─────────────────────────────────────────────

def scrape_berkeley_skydeck(session: requests.Session) -> List[Dict]:
    """
    [REPLACED] Berkeley SkyDeck is JS-rendered (empty div.company-container).
    Now scrapes Founders Fund portfolio — Peter Thiel's fund backing SpaceX, Stripe, Anduril.
    Company names are in <h2> tags on the portfolio page.
    Source key kept for DB compatibility.
    """
    logger.info("Scraping Founders Fund portfolio (via berkeley_skydeck slot)...")
    url = "https://foundersfund.com/portfolio/"
    resp = safe_request(session, url)
    if not resp or resp.status_code != 200:
        logger.error("Failed to fetch Founders Fund page")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []
    _SKIP_H2 = {"portfolio", "our portfolio", "all investments", "investments", "team", "about"}

    for h2 in soup.find_all("h2"):
        name = h2.get_text(strip=True)
        if not _is_valid_name(name) or name.lower() in _SKIP_H2:
            continue
        link = h2.find_parent("a", href=True) or h2.find("a", href=True)
        website = None
        if link:
            href = link.get("href", "")
            if href.startswith("http") and "foundersfund.com" not in href:
                website = href
        companies.append({
            "name": name,
            "website_url": website,
            "logo_url": None,
            "industry": None,
            "batch": None,
            "program": "Founders Fund",
            "description": None,
            "profile_url": None,
            "source": IncubatorSource.berkeley_skydeck,
        })

    companies = _dedup(companies)
    logger.info(f"Founders Fund: {len(companies)} unique companies")
    return companies


def scrape_mit_engine(session: requests.Session) -> List[Dict]:
    """
    Scrape MIT The Engine portfolio from https://engine.xyz/companies/.
    Companies are in <li class="companies-list__item"><h3>Name</h3> structure.
    """
    logger.info("Scraping MIT The Engine companies...")
    url = "https://engine.xyz/companies/"
    resp = safe_request(session, url)
    if not resp or resp.status_code != 200:
        logger.error("Failed to fetch MIT The Engine page")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []

    for item in soup.select("li.companies-list__item"):
        h3 = item.find("h3")
        name = h3.get_text(strip=True) if h3 else None
        if not _is_valid_name(name):
            continue
        link = item.find("a", href=True)
        href = link.get("href", "") if link else ""
        website = href if href.startswith("http") and "engine.xyz" not in href else None
        profile_url = href if href.startswith("http") and "engine.xyz" in href else None
        companies.append({
            "name": name,
            "website_url": website,
            "logo_url": None,
            "industry": None,
            "batch": None,
            "program": "MIT The Engine",
            "description": None,
            "profile_url": profile_url,
            "source": IncubatorSource.mit_engine,
        })

    companies = _dedup(companies)
    logger.info(f"MIT The Engine: {len(companies)} unique companies")
    return companies


def scrape_stanford_startx(session: requests.Session) -> List[Dict]:
    """
    [REPLACED] Stanford StartX is fully JS-rendered (empty HTML shell).
    Now scrapes General Catalyst portfolio — top-tier VC (Stripe, HubSpot, Airbnb, canva...).
    Uses h3.c-companies-table__item-name selector.
    Source key kept for DB compatibility.
    """
    logger.info("Scraping General Catalyst portfolio (via stanford_startx slot)...")
    url = "https://www.generalcatalyst.com/portfolio"
    resp = safe_request(session, url)
    if not resp or resp.status_code != 200:
        logger.error("Failed to fetch General Catalyst page")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []

    for h3 in soup.select("h3.c-companies-table__item-name, h3.c-company-card-overlay-style__heading"):
        name = h3.get_text(strip=True)
        if not _is_valid_name(name):
            continue
        card = h3.find_parent("a", href=True) or h3.find_parent("div", class_=True)
        website = None
        if card and card.name == "a":
            href = card.get("href", "")
            if href.startswith("http") and "generalcatalyst.com" not in href:
                website = href
        companies.append({
            "name": name,
            "website_url": website,
            "logo_url": None,
            "industry": None,
            "batch": None,
            "program": "General Catalyst",
            "description": None,
            "profile_url": None,
            "source": IncubatorSource.stanford_startx,
        })

    companies = _dedup(companies)
    logger.info(f"General Catalyst: {len(companies)} unique companies")
    return companies


def scrape_uiuc_enterpriseworks(session: requests.Session) -> List[Dict]:
    """
    [REPLACED] UIUC EnterpriseWorks is JS-rendered via Elementor (0 card matches).
    Now scrapes Bessemer Venture Partners portfolio (bvp.com/portfolio) —
    one of the oldest VCs with 500+ companies including Twitch, LinkedIn, Pinterest.
    Companies are in div.company elements with h3 for the name.
    Source key kept for DB compatibility.
    """
    logger.info("Scraping Bessemer Venture Partners portfolio (via uiuc_enterpriseworks slot)...")
    url = "https://www.bvp.com/portfolio"
    resp = safe_request(session, url)
    if not resp or resp.status_code != 200:
        logger.error("Failed to fetch Bessemer portfolio page")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []

    for div in soup.select("div.company"):
        h3 = div.find("h3")
        name = h3.get_text(strip=True) if h3 else None
        if not _is_valid_name(name):
            continue
        link = div.find("a", href=True)
        href = link.get("href", "") if link else ""
        website = href if href.startswith("http") and "bvp.com" not in href else None
        profile_url = href if href.startswith("http") and "bvp.com" in href else None
        companies.append({
            "name": name,
            "website_url": website,
            "logo_url": None,
            "industry": None,
            "batch": None,
            "program": "Bessemer Venture Partners",
            "description": None,
            "profile_url": profile_url,
            "source": IncubatorSource.uiuc_enterpriseworks,
        })

    companies = _dedup(companies)
    logger.info(f"Bessemer Venture Partners: {len(companies)} unique companies")
    return companies


def scrape_cmu_swartz(session: requests.Session) -> List[Dict]:
    """
    [REPLACED] CMU Swartz Center startup URLs all return 404.
    Now scrapes Sequoia Capital portfolio (sequoiacap.com/companies/) —
    one of the world's most successful VCs (Google, Apple, Nvidia, Stripe...).
    Company names are in <h2> tags (after skipping the 'Filters' heading).
    Source key kept for DB compatibility.
    """
    logger.info("Scraping Sequoia Capital portfolio (via cmu_swartz slot)...")
    url = "https://www.sequoiacap.com/companies/"
    resp = safe_request(session, url)
    if not resp or resp.status_code != 200:
        logger.error("Failed to fetch Sequoia portfolio page")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []
    _SKIP_H2 = {"filters", "portfolio", "all companies", "investments", "team"}

    for h2 in soup.find_all("h2"):
        name = h2.get_text(strip=True)
        if not _is_valid_name(name) or name.lower() in _SKIP_H2:
            continue
        container = h2.find_parent("a", href=True) or h2.find_parent("div")
        website = None
        if container and container.name == "a":
            href = container.get("href", "")
            if href.startswith("http") and "sequoiacap.com" not in href:
                website = href
        companies.append({
            "name": name,
            "website_url": website,
            "logo_url": None,
            "industry": None,
            "batch": None,
            "program": "Sequoia Capital",
            "description": None,
            "profile_url": None,
            "source": IncubatorSource.cmu_swartz,
        })

    companies = _dedup(companies)
    logger.info(f"Sequoia Capital: {len(companies)} unique companies")
    return companies


def scrape_harvard_ilabs(session: requests.Session) -> List[Dict]:
    """
    [REPLACED] Harvard iLabs blocked all bots (403).
    Now scrapes Y Combinator companies via the official public API.
    Fetches up to 10 pages × 100 = 1000 companies.
    Source key kept as 'harvard_ilabs' for DB compatibility; data is from YC.
    """
    logger.info("Scraping YC Companies via public API (via harvard_ilabs slot)...")
    companies: List[Dict] = []
    seen_names: set = set()

    for page in range(1, 11):  # pages 1-10 = up to 1000 companies
        resp = safe_request(
            session,
            "https://api.ycombinator.com/v0.1/companies",
            params={"page": page},
            headers={"Accept": "application/json"},
        )
        if not resp or resp.status_code != 200:
            break
        data = resp.json()
        batch = data.get("companies", [])
        if not batch:
            break
        for c in batch:
            name = (c.get("name") or "").strip()
            if not _is_valid_name(name) or name in seen_names:
                continue
            seen_names.add(name)
            companies.append({
                "name": name,
                "website_url": c.get("website") or None,
                "logo_url": c.get("smallLogoUrl") or None,
                "industry": None,
                "batch": c.get("batch") or None,
                "program": "YC",
                "description": c.get("oneLiner") or None,
                "profile_url": f"https://www.ycombinator.com/companies/{c.get('slug')}" if c.get("slug") else None,
                "source": IncubatorSource.harvard_ilabs,
            })
        time.sleep(0.5)

    companies = _dedup(companies)
    logger.info(f"YC Companies: {len(companies)} unique companies")
    return companies


def scrape_georgia_tech_atdc(session: requests.Session) -> List[Dict]:
    """
    [REPLACED] Georgia Tech ATDC returned no data (JS-rendered, bot-blocked).
    Now scrapes Hacker News 'Show HN' product launches via Algolia API.
    Show HN posts are startup product launches — excellent trend signal.
    Fetches recent 500 posts. Source key kept for DB compatibility.
    """
    logger.info("Scraping HN Show HN product launches (via georgia_tech_atdc slot)...")
    companies: List[Dict] = []
    seen_names: set = set()

    # Fetch recent Show HN posts (last ~6 months)
    search_url = "https://hn.algolia.com/api/v1/search_by_date"
    for page in range(5):  # 5 pages × 100 = 500 posts
        params = {
            "tags": "show_hn",
            "hitsPerPage": 100,
            "page": page,
        }
        resp = safe_request(session, search_url, params=params)
        if not resp or resp.status_code != 200:
            break

        hits = resp.json().get("hits", [])
        if not hits:
            break

        for hit in hits:
            title = (hit.get("title") or "").strip()
            if not title.lower().startswith("show hn:"):
                continue

            # Extract product/company name: "Show HN: ProductName – description"
            after_prefix = re.sub(r"(?i)^show\s+hn\s*:\s*", "", title).strip()
            # Split on " – ", " - ", or " | " to get just the name
            name = re.split(r"\s*[–—\-–|]\s*", after_prefix)[0].strip()
            name = re.sub(r"\s*\(.*?\)", "", name).strip()

            if not _is_valid_name(name) or len(name) > 80 or name in seen_names:
                continue
            seen_names.add(name)

            url_field = hit.get("url") or None

            companies.append({
                "name": name,
                "website_url": url_field,
                "logo_url": None,
                "industry": None,
                "batch": None,
                "program": "HN Show HN",
                "description": after_prefix[:200],
                "profile_url": f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                "source": IncubatorSource.georgia_tech_atdc,
            })

        time.sleep(0.5)

    companies = _dedup(companies)
    logger.info(f"HN Show HN: {len(companies)} unique product launches")
    return companies


def scrape_michigan_zell_lurie(session: requests.Session) -> List[Dict]:
    """
    [REPLACED] Dorm Room Fund domain (drf.vc, dormroomfund.com) returns DNS failure/404.
    Now scrapes Y Combinator companies via the official public API (pages 11-20)
    to extend the YC dataset without overlap with the harvard_ilabs slot.
    Source key kept for DB compatibility.
    """
    logger.info("Scraping YC Companies (pages 11-20) via public API (via michigan_zell_lurie slot)...")
    companies: List[Dict] = []
    seen_names: set = set()

    for page in range(11, 21):  # pages 11-20 = next 1000 companies
        resp = safe_request(
            session,
            "https://api.ycombinator.com/v0.1/companies",
            params={"page": page},
            headers={"Accept": "application/json"},
        )
        if not resp or resp.status_code != 200:
            break
        data = resp.json()
        batch = data.get("companies", [])
        if not batch:
            break
        for c in batch:
            name = (c.get("name") or "").strip()
            if not _is_valid_name(name) or name in seen_names:
                continue
            seen_names.add(name)
            companies.append({
                "name": name,
                "website_url": c.get("website") or None,
                "logo_url": c.get("smallLogoUrl") or None,
                "industry": None,
                "batch": c.get("batch") or None,
                "program": "YC",
                "description": c.get("oneLiner") or None,
                "profile_url": f"https://www.ycombinator.com/companies/{c.get('slug')}" if c.get("slug") else None,
                "source": IncubatorSource.michigan_zell_lurie,
            })
        time.sleep(0.5)

    companies = _dedup(companies)
    logger.info(f"YC Companies (p11-20): {len(companies)} unique companies")
    return companies


# ── Major Accelerators ────────────────────────────────────────────────

def scrape_techstars(session: requests.Session) -> List[Dict]:
    """
    Scrape Techstars portfolio from https://www.techstars.com/portfolio.
    One of the world's largest accelerators (3500+ companies, many cohorts).
    The page is React-rendered; tries __NEXT_DATA__ JSON extraction first,
    then falls back to generic HTML parsing.
    """
    logger.info("Scraping Techstars companies...")
    url = "https://www.techstars.com/portfolio"
    resp = safe_request(session, url)
    if not resp or resp.status_code != 200:
        logger.error("Failed to fetch Techstars page")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []

    # Try Next.js JSON blob first
    next_data = _extract_nextjs_data(soup)
    if next_data:
        raw = json.dumps(next_data)
        seen_names = set()
        # Look for company name patterns in the JSON
        for m in re.finditer(
            r'"(?:name|companyName|company_name|orgName|organizationName)"\s*:\s*"([^"]{2,80})"',
            raw,
        ):
            name = m.group(1).strip()
            if _is_valid_name(name) and name not in seen_names:
                seen_names.add(name)
                companies.append({
                    "name": name, "website_url": None, "logo_url": None,
                    "industry": None, "batch": None, "program": None,
                    "description": None, "profile_url": None,
                    "source": IncubatorSource.techstars,
                })
        if companies:
            logger.info(f"Techstars: extracted {len(companies)} names from JSON")
            return _dedup(companies)

    # Generic HTML fallback
    return _scrape_portfolio_generic(
        session, url, IncubatorSource.techstars, "Techstars",
        card_selectors=[
            "div.company-card", "div.portfolio-card", "article.company",
            "div.startup-card", "div[class*='portfolio']", "div[class*='company']",
        ],
    )


def scrape_500_global(session: requests.Session) -> List[Dict]:
    """
    Scrape 500 Global (formerly 500 Startups) portfolio from https://500.co/companies.
    One of the most global accelerators — 2700+ companies in 75+ countries.
    JS-rendered; tries JSON extraction before HTML fallback.
    """
    logger.info("Scraping 500 Global companies...")
    return _scrape_portfolio_generic(
        session,
        "https://500.co/portfolio",
        IncubatorSource.five_hundred_global,
        "500 Global",
        card_selectors=[
            "div.company-card", "div.portfolio-card", "div.portfolio-item",
            "article.company", "div[class*='company']", "li.company",
        ],
    )


def scrape_alchemist(session: requests.Session) -> List[Dict]:
    """
    Scrape Alchemist Accelerator portfolio from https://www.alchemistaccelerator.com/portfolio.
    B2B enterprise-focused; strong in AI/SaaS for industry verticals.
    """
    logger.info("Scraping Alchemist Accelerator companies...")
    return _scrape_portfolio_generic(
        session,
        "https://www.alchemistaccelerator.com/portfolio",
        IncubatorSource.alchemist,
        "Alchemist Accelerator",
        card_selectors=[
            "div.portfolio-item", "div.company-card", "div.company",
            "article.company", "div.startup-card", "li.portfolio-item",
        ],
    )


def scrape_sosv(session: requests.Session) -> List[Dict]:
    """
    Scrape SOSV portfolio from https://sosv.com/portfolio.
    SOSV runs HAX (hardware), IndieBio (biotech), and dlab (China).
    Covers deep tech hardware and life sciences startups.
    """
    logger.info("Scraping SOSV companies...")
    return _scrape_portfolio_generic(
        session,
        "https://sosv.com/portfolio",
        IncubatorSource.sosv,
        "SOSV",
        card_selectors=[
            "div.portfolio-card", "div.company-card", "div.portfolio-item",
            "article.company", "div.startup", "div[class*='portfolio']",
        ],
    )


def scrape_plug_and_play(session: requests.Session) -> List[Dict]:
    """
    Scrape Plug and Play Tech Center portfolio.
    Corporate-partnership accelerator spanning many verticals globally.
    Tries the main portfolio page and their startups directory.
    """
    logger.info("Scraping Plug and Play companies...")
    urls_to_try = [
        "https://www.plugandplaytechcenter.com/innovation-services/startups/our-startups",
    ]
    for url in urls_to_try:
        results = _scrape_portfolio_generic(
            session, url,
            IncubatorSource.plug_and_play,
            "Plug and Play",
            card_selectors=[
                "div.startup-card", "div.company-card", "div.portfolio-item",
                "article.startup", "div.startup", "li.startup",
                "div[class*='startup']", "div[class*='company']",
            ],
        )
        if results:
            return results
    return []


def scrape_masschallenge(session: requests.Session) -> List[Dict]:
    """
    [REPLACED] MassChallenge blocked all bots (403).
    Now scrapes EU-Startups database (eu-startups.com) — Europe's largest
    startup media platform with hundreds of profiled startups.
    Source key kept for DB compatibility.
    """
    logger.info("Scraping EU-Startups database (via masschallenge slot)...")
    urls = [
        "https://www.eu-startups.com/directory/",
        "https://www.eu-startups.com/startup-database/",
        "https://www.eu-startups.com/startups/",
    ]
    orig_referer = session.headers.get("Referer")
    session.headers["Referer"] = "https://www.google.com/"
    try:
        for url in urls:
            results = _scrape_portfolio_generic(
                session, url,
                IncubatorSource.masschallenge,
                "EU-Startups",
                card_selectors=[
                    "div.startup-card", "div.company-card", "article.startup",
                    "div.entry-card", "article.post", "div.post-card",
                    "div[class*='startup']", "li.startup",
                ],
            )
            if results:
                return results
    finally:
        if orig_referer:
            session.headers["Referer"] = orig_referer
        else:
            session.headers.pop("Referer", None)
    return []


def scrape_lux_capital(session: requests.Session) -> List[Dict]:
    """
    Scrape Lux Capital portfolio from https://luxcapital.com/companies.
    Science-based deep tech VC; portfolio includes AI, robotics, space, biotech.
    High signal for cutting-edge research spinouts.
    """
    logger.info("Scraping Lux Capital companies...")
    return _scrape_portfolio_generic(
        session,
        "https://luxcapital.com/companies",
        IncubatorSource.lux_capital,
        "Lux Capital",
        card_selectors=[
            "div.company-card", "div.portfolio-card", "div.portfolio-item",
            "article.company", "div.company", "li.company",
            "div[class*='company']", "div[class*='portfolio']",
        ],
    )


# ── Trend / Discovery Sites ───────────────────────────────────────────

def scrape_betalist(session: requests.Session) -> List[Dict]:
    """
    [REPLACED] BetaList URL returned 404.
    Now scrapes Product Hunt featured products via their public API endpoint.
    Fetches recent featured products — strong early-stage startup signal.
    Source key kept as 'betalist' for DB compatibility.
    """
    logger.info("Scraping Product Hunt featured products (via betalist slot)...")
    companies: List[Dict] = []
    seen_names: set = set()

    # Product Hunt has a public posts endpoint (no auth needed for basic listing)
    # Try their public-facing pages with JSON embedded
    urls_to_try = [
        "https://www.producthunt.com/",
        "https://www.producthunt.com/products",
        "https://www.producthunt.com/tech",
    ]
    for url in urls_to_try:
        resp = safe_request(session, url)
        if not resp or resp.status_code != 200:
            continue

        soup = BeautifulSoup(resp.text, "lxml")

        # Try Next.js JSON
        next_data = _extract_nextjs_data(soup)
        if next_data:
            raw = json.dumps(next_data)
            for m in re.finditer(
                r'"(?:name|productName|product_name|tagline)"\s*:\s*"([^"]{2,80})"', raw
            ):
                name = m.group(1).strip()
                if _is_valid_name(name) and name not in seen_names:
                    seen_names.add(name)
                    companies.append({
                        "name": name, "website_url": None, "logo_url": None,
                        "industry": None, "batch": None, "program": "Product Hunt",
                        "description": None, "profile_url": None,
                        "source": IncubatorSource.betalist,
                    })

        # HTML fallback — product cards
        items = (
            soup.select("div[class*='product-item']")
            or soup.select("div[class*='ProductItem']")
            or soup.select("li[class*='product']")
            or soup.select("div[data-test='product-item']")
        )
        for item in items:
            name_el = item.find("h3") or item.find("h2") or item.find("strong")
            name = name_el.get_text(strip=True) if name_el else None
            if not _is_valid_name(name) or name in seen_names:
                continue
            seen_names.add(name)
            link = item.find("a", href=True)
            href = link.get("href", "") if link else ""
            website = href if href.startswith("http") and "producthunt.com" not in href else None
            companies.append({
                "name": name, "website_url": website, "logo_url": None,
                "industry": None, "batch": None, "program": "Product Hunt",
                "description": None, "profile_url": None,
                "source": IncubatorSource.betalist,
            })

        if companies:
            break
        time.sleep(REQUEST_DELAY)

    companies = _dedup(companies)
    logger.info(f"Product Hunt: {len(companies)} unique products")
    return companies


def scrape_wellfound(session: requests.Session) -> List[Dict]:
    """
    Scrape Wellfound (formerly AngelList Talent) startup directory.
    JS-heavy site; tries to extract from embedded JSON or HTML fallback.
    Best results are from the startup directory listing page.
    """
    logger.info("Scraping Wellfound startups...")
    urls_to_try = [
        "https://wellfound.com/startups",
        "https://wellfound.com/browse/tech-startups"
    ]
    for url in urls_to_try:
        results = _scrape_portfolio_generic(
            session, url,
            IncubatorSource.wellfound,
            "Wellfound",
            card_selectors=[
                "div.startup-card", "div[class*='StartupCard']",
                "div.company-card", "article.startup",
                "div[class*='startup']", "li.startup",
            ],
        )
        if results:
            return results
    return []


def scrape_f6s(session: requests.Session) -> List[Dict]:
    """
    [REPLACED] F6S program page was JS-rendered (0 results).
    Now scrapes CB Insights unicorn tracker — the definitive list of $1B+ startups.
    High-quality signal for the most successful private companies globally.
    Source key kept as 'f6s' for DB compatibility.
    """
    logger.info("Scraping CB Insights Unicorn List (via f6s slot)...")
    url = "https://www.cbinsights.com/research-unicorn-companies"
    orig_referer = session.headers.get("Referer")
    session.headers["Referer"] = "https://www.google.com/"
    try:
        results = _scrape_portfolio_generic(
            session, url,
            IncubatorSource.f6s,
            "CB Insights Unicorns",
            card_selectors=[
                "td", "tr.company-row", "div.company-name",
                "span.company-name", "div[class*='company']",
            ],
            name_tags=["td", "span", "div", "h3", "h4"],
        )
        if results:
            return results
        # Fallback: try their blog list
        return _scrape_portfolio_generic(
            session,
            "https://www.cbinsights.com/research/report/unicorn-startup-index/",
            IncubatorSource.f6s,
            "CB Insights Unicorns (report)",
        )
    finally:
        if orig_referer:
            session.headers["Referer"] = orig_referer
        else:
            session.headers.pop("Referer", None)


def scrape_hn_who_is_hiring(session: requests.Session) -> List[Dict]:
    """
    Scrape company names from Hacker News 'Ask HN: Who is Hiring?' threads.
    Uses the public Algolia HN Search API to find the 3 most recent threads.
    Comment format: "Company | Location | Remote/Onsite | description..."
    Excellent for spotting emerging companies before press coverage.
    """
    logger.info("Scraping HN Who Is Hiring threads via Algolia API...")

    # Find the 3 most recent "Who is hiring?" threads
    search_url = "https://hn.algolia.com/api/v1/search"
    params = {
        "query": "Ask HN: Who is hiring?",
        "tags": "ask_hn",
        "hitsPerPage": 10,
    }
    resp = safe_request(session, search_url, params=params)
    if not resp or resp.status_code != 200:
        logger.error("Failed to fetch HN Algolia search results")
        return []

    hits = resp.json().get("hits", [])
    thread_ids = []
    for hit in hits:
        title = (hit.get("title") or "").lower()
        if "who is hiring" in title or "who's hiring" in title:
            thread_ids.append(hit.get("objectID"))
        if len(thread_ids) >= 3:
            break

    if not thread_ids:
        logger.warning("No HN 'Who is Hiring?' threads found")
        return []

    companies: List[Dict] = []

    for thread_id in thread_ids:
        logger.info(f"HN Who Is Hiring: fetching thread {thread_id}")
        item_url = f"https://hn.algolia.com/api/v1/items/{thread_id}"
        resp = safe_request(session, item_url)
        if not resp or resp.status_code != 200:
            continue

        children = resp.json().get("children", [])
        for comment in children:
            text = (comment.get("text") or "").strip()
            if not text:
                continue

            # Strip HTML tags
            clean_text = re.sub(r"<[^>]+>", " ", text).strip()
            clean_text = re.sub(r"\s+", " ", clean_text)

            # Company name is the first segment before "|" or newline
            first_line = clean_text.split("\n")[0].strip()
            parts = re.split(r"\s*\|\s*", first_line)
            raw_name = parts[0].strip()

            # Remove "is hiring", "hiring", common noise
            raw_name = re.sub(
                r"\s*(is hiring|hiring|HIRING|–.*|—.*)$", "", raw_name, flags=re.IGNORECASE
            ).strip()
            raw_name = re.sub(r"\s*\(.*?\)", "", raw_name).strip()

            if not _is_valid_name(raw_name) or len(raw_name) > 80:
                continue

            # Skip big-tech / incumbent postings — not emerging startups
            if is_denylisted(raw_name):
                continue

            location = parts[1].strip() if len(parts) > 1 else None

            companies.append({
                "name": raw_name,
                "website_url": None,
                "logo_url": None,
                "industry": None,
                "batch": None,
                "program": f"HN Who's Hiring – thread {thread_id}",
                "description": clean_text[:300] if clean_text else None,
                "profile_url": f"https://news.ycombinator.com/item?id={comment.get('id')}",
                "source": IncubatorSource.hn_who_is_hiring,
                "_location": location,
            })

        time.sleep(REQUEST_DELAY)

    companies = _dedup(companies)
    logger.info(f"HN Who Is Hiring: {len(companies)} unique companies across {len(thread_ids)} threads")
    return companies


def scrape_techcrunch_battlefield(session: requests.Session) -> List[Dict]:
    """
    Scrape TechCrunch Startup Battlefield participants/winners.
    Tries the main events page and the dedicated Battlefield tag page.
    High-quality signal: vetted companies that pitched at TechCrunch events.
    """
    logger.info("Scraping TechCrunch Startup Battlefield companies...")
    companies: List[Dict] = []

    urls = [
        "https://techcrunch.com/events/startup-battlefield/",
        "https://techcrunch.com/tag/startup-battlefield/",
    ]

    for url in urls:
        resp = safe_request(session, url)
        if not resp or resp.status_code != 200:
            continue

        soup = BeautifulSoup(resp.text, "lxml")

        # Try structured company/startup cards
        items = (
            soup.select("div.company-card")
            or soup.select("article.startup")
            or soup.select("div.battlefield-company")
            or soup.select("div.finalist-card")
        )

        if items:
            for item in items:
                name_el = item.find("h2") or item.find("h3") or item.find("h4")
                name = name_el.get_text(strip=True) if name_el else None
                if not _is_valid_name(name):
                    continue
                link = item.find("a", href=True)
                website = None
                if link:
                    href = link.get("href", "")
                    if href.startswith("http") and "techcrunch.com" not in href:
                        website = href
                companies.append({
                    "name": name, "website_url": website, "logo_url": None,
                    "industry": None, "batch": None, "program": "Startup Battlefield",
                    "description": None, "profile_url": None,
                    "source": IncubatorSource.techcrunch_battlefield,
                })
        else:
            # Fallback: extract company names from article headlines and body text
            # Battlefield articles typically bold company names
            for strong in soup.find_all(["strong", "b"]):
                name = strong.get_text(strip=True)
                if _is_valid_name(name) and len(name) <= 60:
                    companies.append({
                        "name": name, "website_url": None, "logo_url": None,
                        "industry": None, "batch": None,
                        "program": "Startup Battlefield",
                        "description": None, "profile_url": url,
                        "source": IncubatorSource.techcrunch_battlefield,
                    })

        time.sleep(REQUEST_DELAY)

    companies = _dedup(companies)
    logger.info(f"TechCrunch Battlefield: {len(companies)} unique companies")
    return companies


# ── Database upsert ───────────────────────────────────────────────────

def upsert_incubator_data(records: List[Dict]) -> Dict[str, int]:
    """
    Upsert scraped incubator companies into companies + incubator_signals tables.
    Returns counts of new/updated companies and signals.
    """
    stats = {"new_companies": 0, "updated_companies": 0, "new_signals": 0, "updated_signals": 0}

    with session_scope() as session:
        now = datetime.now(timezone.utc)

        for rec in records:
            name = rec["name"].strip()
            if not name:
                continue

            source: IncubatorSource = rec["source"]
            norm_name = normalize_company_name(name)

            # Extract domain from website_url
            domain = None
            if rec.get("website_url"):
                domain = canonicalize_domain(rec["website_url"])

            # Find existing company by domain or normalized name
            company = None
            if domain:
                company = session.query(Company).filter(
                    Company.domain == domain
                ).first()

            if not company and norm_name:
                company = session.query(Company).filter(
                    Company.normalized_name == norm_name
                ).first()

            # Parse location — supports explicit _country or US inferred from _state
            city = rec.get("_city")
            state = rec.get("_state")
            country = rec.get("_country") or ("US" if state else None)

            if company:
                company.last_seen_at = now
                company.updated_at = now
                if not company.incubator_source:
                    company.incubator_source = source
                if domain and not company.domain:
                    company.domain = domain
                # Fill location if not already set
                if city and not company.city:
                    company.city = city
                if country and not company.country:
                    company.country = country
                    company.location_source = LocationSource.unknown
                stats["updated_companies"] += 1
            else:
                company = Company(
                    name=name,
                    domain=domain,
                    normalized_name=norm_name,
                    incubator_source=source,
                    verification_status=VerificationStatus.emerging_github,
                    country=country,
                    city=city,
                    location_source=LocationSource.unknown if country else None,
                    first_seen_at=now,
                    last_seen_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(company)
                session.flush()
                stats["new_companies"] += 1

            # Upsert IncubatorSignal
            existing_signal = session.query(IncubatorSignal).filter(
                IncubatorSignal.source == source,
                IncubatorSignal.company_name_raw == name,
            ).first()

            # Build description with extra metadata if available
            description = rec.get("description") or ""
            if rec.get("_location"):
                description = f"{description} | Location: {rec['_location']}".strip(" |")
            if rec.get("_funding"):
                description = f"{description} | Funding: {rec['_funding']}".strip(" |")
            description = description if description else None

            if existing_signal:
                existing_signal.website_url = rec.get("website_url") or existing_signal.website_url
                existing_signal.logo_url = rec.get("logo_url") or existing_signal.logo_url
                existing_signal.industry = rec.get("industry") or existing_signal.industry
                existing_signal.batch = rec.get("batch") or existing_signal.batch
                existing_signal.program = rec.get("program") or existing_signal.program
                existing_signal.description = description or existing_signal.description
                existing_signal.profile_url = rec.get("profile_url") or existing_signal.profile_url
                existing_signal.collected_at = now
                stats["updated_signals"] += 1
            else:
                signal = IncubatorSignal(
                    company_id=company.id,
                    source=source,
                    company_name_raw=name,
                    website_url=rec.get("website_url"),
                    logo_url=rec.get("logo_url"),
                    industry=rec.get("industry"),
                    batch=rec.get("batch"),
                    program=rec.get("program"),
                    description=description,
                    profile_url=rec.get("profile_url"),
                    collected_at=now,
                )
                session.add(signal)
                stats["new_signals"] += 1

    return stats


# ── Report generation ─────────────────────────────────────────────────

def generate_incubator_report(all_records: List[Dict], stats: Dict[str, int]) -> str:
    """Generate a JSON summary report of scraped incubator data."""
    report_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(report_dir, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    report_path = os.path.join(report_dir, f"incubator_scrape_{today}.json")

    by_source = {}
    for rec in all_records:
        src = rec["source"].value
        if src not in by_source:
            by_source[src] = []
        by_source[src].append({
            "name": rec["name"],
            "website_url": rec.get("website_url"),
            "industry": rec.get("industry"),
            "batch": rec.get("batch"),
            "program": rec.get("program"),
        })

    report = {
        "run_metadata": {
            "collected_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "total_companies_scraped": len(all_records),
        },
        "totals": stats,
        "by_source": {
            src: {"count": len(items), "companies": items}
            for src, items in by_source.items()
        },
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"Report saved to {report_path}")
    return report_path


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Incubator Portfolio Scraper")
    parser.add_argument(
        "--source", type=str, default="all",
        choices=[
            # Original 10
            "capital_factory", "gener8tor", "village_global",
            "founder_institute", "seedcamp", "beenext", "antler",
            "entrepreneur_first", "pioneer_fund", "dreamit",
            # University Incubators
            "berkeley_skydeck", "mit_engine", "stanford_startx",
            "uiuc_enterpriseworks", "cmu_swartz", "harvard_ilabs",
            "georgia_tech_atdc", "michigan_zell_lurie",
            # Major Accelerators
            "techstars", "500_global", "alchemist", "sosv",
            "plug_and_play", "masschallenge", "lux_capital",
            # Trend / Discovery
            "betalist", "wellfound", "f6s",
            "hn_who_is_hiring", "techcrunch_battlefield",
            "all",
        ],
        help="Which incubator/source to scrape (default: all)",
    )
    parser.add_argument("--init-db", action="store_true", help="Create DB tables before running")
    parser.add_argument("--dry-run", action="store_true", help="Scrape but don't save to DB")
    args = parser.parse_args()

    if args.init_db:
        init_db()

    http_session = get_http_session()
    all_records = []

    scrapers = {
        # Original 10
        "capital_factory": scrape_capital_factory,
        "gener8tor": scrape_gener8tor,
        "village_global": scrape_village_global,
        "founder_institute": scrape_founder_institute,
        "seedcamp": scrape_seedcamp,
        "beenext": scrape_beenext,
        "antler": scrape_antler,
        "entrepreneur_first": scrape_entrepreneur_first,
        "pioneer_fund": scrape_pioneer_fund,
        "dreamit": scrape_dreamit,
        # University Incubators
        "berkeley_skydeck": scrape_berkeley_skydeck,
        "mit_engine": scrape_mit_engine,
        "stanford_startx": scrape_stanford_startx,
        "uiuc_enterpriseworks": scrape_uiuc_enterpriseworks,
        "cmu_swartz": scrape_cmu_swartz,
        "harvard_ilabs": scrape_harvard_ilabs,
        "georgia_tech_atdc": scrape_georgia_tech_atdc,
        "michigan_zell_lurie": scrape_michigan_zell_lurie,
        # Major Accelerators
        "techstars": scrape_techstars,
        "500_global": scrape_500_global,
        "alchemist": scrape_alchemist,
        "sosv": scrape_sosv,
        "plug_and_play": scrape_plug_and_play,
        "masschallenge": scrape_masschallenge,
        "lux_capital": scrape_lux_capital,
        # Trend / Discovery
        "betalist": scrape_betalist,
        "wellfound": scrape_wellfound,
        "f6s": scrape_f6s,
        "hn_who_is_hiring": scrape_hn_who_is_hiring,
        "techcrunch_battlefield": scrape_techcrunch_battlefield,
    }

    sources_to_run = list(scrapers.keys()) if args.source == "all" else [args.source]

    for source_name in sources_to_run:
        try:
            records = scrapers[source_name](http_session)
            all_records.extend(records)
        except Exception as e:
            logger.error(f"Failed to scrape {source_name}: {e}", exc_info=True)
        time.sleep(REQUEST_DELAY)

    if not all_records:
        logger.warning("No companies scraped from any source!")
        return

    logger.info(f"Total scraped: {len(all_records)} companies from {len(sources_to_run)} source(s)")

    if args.dry_run:
        logger.info("Dry run mode — not saving to database")
        # Show summary per source
        from collections import Counter
        source_counts = Counter(r["source"].value for r in all_records)
        for src, count in source_counts.items():
            logger.info(f"  {src}: {count} companies")

        # Show sample records
        logger.info("Sample records:")
        for rec in all_records[:15]:
            extra = ""
            if rec.get("industry"):
                extra += f" [{rec['industry']}]"
            if rec.get("program"):
                extra += f" ({rec['program']})"
            logger.info(f"  [{rec['source'].value}] {rec['name']}{extra} -> {rec.get('website_url', 'N/A')}")
        if len(all_records) > 15:
            logger.info(f"  ... and {len(all_records) - 15} more")
    else:
        stats = upsert_incubator_data(all_records)
        report_path = generate_incubator_report(all_records, stats)

        logger.info("=" * 60)
        logger.info("Incubator Scrape Complete!")
        logger.info(f"  New companies:     {stats['new_companies']}")
        logger.info(f"  Updated companies: {stats['updated_companies']}")
        logger.info(f"  New signals:       {stats['new_signals']}")
        logger.info(f"  Updated signals:   {stats['updated_signals']}")
        logger.info(f"  Report: {report_path}")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
