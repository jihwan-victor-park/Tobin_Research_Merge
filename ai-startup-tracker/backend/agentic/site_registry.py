"""
Load registered scrape targets from data/generallists.md and data/international_incubators-1.csv.
Returns a deduped list of {name, url, country, city} dicts with valid portfolio URLs only.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List


def _data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


def _parse_md(path: Path) -> List[Dict[str, str]]:
    """Parse generallists.md: '1. Name - https://url'"""
    sites: List[Dict[str, str]] = []
    pattern = re.compile(r"^\d+\.\s+(.+?)\s*-\s*(https?://\S+)")
    for line in path.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line.strip())
        if m:
            sites.append({
                "name": m.group(1).strip(),
                "url": m.group(2).strip(),
                "country": "",
                "city": "",
            })
    return sites


def _parse_csv(path: Path) -> List[Dict[str, str]]:
    """Parse international_incubators-1.csv.

    - If portfolio_url exists → use it directly
    - If no portfolio_url but has_portfolio_page=Yes → use website URL
      (the agent will find the portfolio subpage automatically)
    - If has_portfolio_page=No → skip entirely
    """
    sites: List[Dict[str, str]] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            portfolio_url = (row.get("portfolio_url") or "").strip()
            website = (row.get("website") or "").strip()
            has_page = (row.get("has_portfolio_page") or "").strip().lower()

            if portfolio_url:
                url = portfolio_url
            elif has_page == "yes" and website:
                url = website
            else:
                continue  # no portfolio page at all

            sites.append({
                "name": (row.get("program_name") or "").strip(),
                "url": url,
                "country": (row.get("country") or "").strip(),
                "city": (row.get("city") or "").strip(),
            })
    return sites


def load_registered_sites() -> List[Dict[str, str]]:
    """Load all sites with portfolio URLs from MD + CSV files, deduped by URL."""
    sites: List[Dict[str, str]] = []

    md_path = _data_dir() / "generallists.md"
    if md_path.exists():
        sites.extend(_parse_md(md_path))

    csv_path = _data_dir() / "international_incubators-1.csv"
    if csv_path.exists():
        sites.extend(_parse_csv(csv_path))

    # Dedup by URL (keep first occurrence)
    seen: set[str] = set()
    deduped: List[Dict[str, str]] = []
    for s in sites:
        url = s["url"].rstrip("/")
        if url not in seen:
            seen.add(url)
            deduped.append(s)
    return deduped
