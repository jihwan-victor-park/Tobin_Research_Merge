"""
Feed Loader — loads URLs from various sources (CSV, markdown, instruction library)
and registers unknown ones for scraping.

Sources:
  1. international_incubators CSV (40+ accelerators)
  2. generallists.md (markdown list of URLs)
  3. instruction_library.json (Alastair's site patterns)
  4. scrape_schedule/registered_sites.yaml
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import List, Set

import yaml

from backend.orchestrator.health import HealthMonitor
from backend.utils.domain import canonicalize_domain

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def load_urls_from_csv(csv_path: Path) -> List[dict]:
    """Load URLs from the international incubators CSV."""
    if not csv_path.exists():
        logger.warning(f"CSV not found: {csv_path}")
        return []

    entries = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("url") or row.get("website") or row.get("URL") or row.get("Website")
            name = row.get("name") or row.get("Name") or row.get("incubator")
            if url:
                entries.append({"url": url.strip(), "name": name, "source": "csv"})

    logger.info(f"Loaded {len(entries)} URLs from {csv_path.name}")
    return entries


def load_urls_from_markdown(md_path: Path) -> List[dict]:
    """Load URLs from a markdown file (expects lines with URLs)."""
    if not md_path.exists():
        logger.warning(f"Markdown not found: {md_path}")
        return []

    import re
    url_pattern = re.compile(r"https?://[^\s\)\"'>]+")

    entries = []
    with open(md_path, encoding="utf-8") as f:
        for line in f:
            urls = url_pattern.findall(line)
            for url in urls:
                entries.append({"url": url.strip(), "name": None, "source": "markdown"})

    logger.info(f"Loaded {len(entries)} URLs from {md_path.name}")
    return entries


def load_urls_from_instruction_library(json_path: Path) -> List[dict]:
    """Load URLs from Alastair's instruction_library.json."""
    if not json_path.exists():
        logger.warning(f"Instruction library not found: {json_path}")
        return []

    with open(json_path, encoding="utf-8") as f:
        library = json.load(f)

    entries = []
    items = library if isinstance(library, list) else library.get("entries", [])
    for item in items:
        url = item.get("url") or item.get("seed_url")
        name = item.get("name") or item.get("domain")
        if url:
            entries.append({"url": url.strip(), "name": name, "source": "instruction_library"})

    logger.info(f"Loaded {len(entries)} URLs from instruction library")
    return entries


def load_urls_from_yaml(yaml_path: Path) -> List[dict]:
    """Load URLs from the scrape schedule YAML."""
    if not yaml_path.exists():
        logger.warning(f"YAML not found: {yaml_path}")
        return []

    with open(yaml_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    entries = []
    sites = config.get("sites", [])
    for site in sites:
        url = site.get("url")
        name = site.get("name")
        if url:
            entries.append({"url": url.strip(), "name": name, "source": "yaml"})

    logger.info(f"Loaded {len(entries)} URLs from {yaml_path.name}")
    return entries


def discover_new_sites() -> List[dict]:
    """
    Load all URL sources, deduplicate, and return only those not yet
    registered in site_health.
    """
    all_entries = []

    # Load from all sources
    csv_files = list(DATA_DIR.glob("*incubator*.csv"))
    for csv_path in csv_files:
        all_entries.extend(load_urls_from_csv(csv_path))

    md_path = DATA_DIR / "generallists.md"
    all_entries.extend(load_urls_from_markdown(md_path))

    json_path = DATA_DIR / "instruction_library.json"
    all_entries.extend(load_urls_from_instruction_library(json_path))

    yaml_path = DATA_DIR / "scrape_schedule" / "registered_sites.yaml"
    all_entries.extend(load_urls_from_yaml(yaml_path))

    # Deduplicate by domain
    seen_domains: Set[str] = set()
    unique_entries = []
    for entry in all_entries:
        domain = canonicalize_domain(entry["url"])
        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            entry["domain"] = domain
            unique_entries.append(entry)

    logger.info(f"Total unique domains across all sources: {len(unique_entries)}")
    return unique_entries


def register_new_sites():
    """Discover new sites and register them for scraping."""
    entries = discover_new_sites()
    health = HealthMonitor()

    registered = 0
    for entry in entries:
        health.register_site(
            domain=entry["domain"],
            url=entry["url"],
            difficulty="hard",  # default to hard until a dedicated scraper is written
        )
        registered += 1

    logger.info(f"Registered {registered} new sites for discovery")
