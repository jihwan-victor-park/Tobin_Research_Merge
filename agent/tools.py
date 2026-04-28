"""
Tool definitions and implementations for the scraping agent.

Three tools:
  fetch_url            — fetch a URL, clean HTML, detect backend patterns
  read_instruction_library — look up known patterns for a domain
  save_companies       — validate and upsert company records to the database
"""

import json
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.db import get_connection, init_db, insert_company

INSTRUCTION_LIBRARY_PATH = Path(__file__).resolve().parent.parent / "docs" / "instruction_library.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Signatures to detect common API backends in page source
BACKEND_PATTERNS = {
    "algolia": ["algolia", "algolianet", "x-algolia-application-id"],
    "typesense": ["typesense", "a1.typesense.net"],
    "wordpress_ajax": ["admin-ajax.php", "wp-admin"],
    "react": ["__NEXT_DATA__", "react-root", "_reactRootContainer"],
    "vue": ["v-bind", "v-for", ":src", "vue.js", "vuejs"],
    "angular": ["ng-app", "ng-controller", "angular.js"],
}


def fetch_url(url: str) -> dict:
    """
    Fetch a URL, clean the HTML, and detect backend patterns.

    Returns a dict with:
      success, url, raw_html_length, cleaned_text, detected_patterns, links, error
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        return {
            "success": False,
            "url": url,
            "raw_html_length": 0,
            "cleaned_text": "",
            "detected_patterns": [],
            "links": [],
            "error": str(e),
        }

    raw_html = response.text
    raw_lower = raw_html.lower()

    # Detect backend signatures
    detected_patterns = [
        backend
        for backend, signatures in BACKEND_PATTERNS.items()
        if any(sig.lower() in raw_lower for sig in signatures)
    ]

    # Parse with BeautifulSoup before cleaning to extract links
    soup = BeautifulSoup(raw_html, "html.parser")

    # Extract same-domain absolute links before stripping tags
    from urllib.parse import urljoin, urlparse
    base_domain = urlparse(url).netloc
    seen = set()
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"].strip())
        parsed = urlparse(href)
        # Keep only http(s) same-domain links, deduplicated, capped at 50
        if parsed.scheme in ("http", "https") and parsed.netloc == base_domain and href not in seen:
            seen.add(href)
            links.append(href)
            if len(links) >= 50:
                break

    # Clean HTML — strip noise tags
    for tag in soup(["script", "style", "nav", "header", "footer", "meta", "link"]):
        tag.decompose()
    cleaned_text = " ".join(soup.get_text(separator=" ", strip=True).split())

    return {
        "success": True,
        "url": url,
        "raw_html_length": len(raw_html),
        "cleaned_text": cleaned_text[:8000],  # cap to avoid flooding context window
        "detected_patterns": detected_patterns,
        "links": links,
        "error": None,
    }


def read_instruction_library(domain: str) -> dict:
    """
    Load docs/instruction_library.json and find entries matching the domain.

    Returns:
      found (bool), entries (list), suggestion (plain text summary for Claude)
    """
    try:
        with open(INSTRUCTION_LIBRARY_PATH, "r") as f:
            library = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return {
            "found": False,
            "entries": [],
            "suggestion": f"Could not load instruction library: {e}",
        }

    # Match entries where domain appears in the library entry's domain field
    domain_clean = domain.lower().replace("https://", "").replace("http://", "").split("/")[0]
    matches = [
        entry for entry in library
        if entry.get("domain") and (
            entry["domain"].lower() in domain_clean
            or domain_clean in entry["domain"].lower()
        )
    ]

    if not matches:
        return {
            "found": False,
            "entries": [],
            "suggestion": f"No known patterns for '{domain}'. This is an unseen site — scout mode recommended.",
        }

    approved = [e for e in matches if e.get("status") == "approved"]
    flagged = [e for e in matches if e.get("status") == "flagged"]

    suggestion_parts = [f"Found {len(matches)} entry/entries for '{domain}'."]
    if approved:
        s = approved[0]
        suggestion_parts.append(
            f"Approved scraper exists: {s['scraper']} — backend: {s['backend']}, approach: {s['approach']}. "
            f"Notes: {s['notes']}"
        )
    if flagged:
        suggestion_parts.append(
            f"Site is flagged: {flagged[0]['notes']}"
        )

    return {
        "found": True,
        "entries": matches,
        "suggestion": " ".join(suggestion_parts),
    }


def save_companies(companies: list, source: str) -> dict:
    """
    Validate and upsert a list of company dicts into the database.

    Each company must have at minimum a 'name' field.
    Returns: success, saved_count, error_count, errors
    """
    if not isinstance(companies, list):
        return {
            "success": False,
            "saved_count": 0,
            "error_count": 1,
            "errors": ["companies must be a list"],
        }

    saved_count = 0
    errors = []

    conn = get_connection()
    init_db(conn)

    for i, company in enumerate(companies):
        if not isinstance(company, dict):
            errors.append(f"Item {i}: not a dict")
            continue
        if not company.get("name"):
            errors.append(f"Item {i}: missing required field 'name'")
            continue

        try:
            insert_company(conn, {**company, "source": source})
            saved_count += 1
        except Exception as e:
            errors.append(f"Item {i} ({company.get('name', '?')}): {e}")

    conn.commit()
    conn.close()

    return {
        "success": len(errors) == 0,
        "saved_count": saved_count,
        "error_count": len(errors),
        "errors": errors,
    }


# --- Tool definitions for the Claude API ---

TOOL_DEFINITIONS = [
    {
        "name": "fetch_url",
        "description": (
            "Fetch a URL using requests with a realistic User-Agent. "
            "Cleans the HTML by stripping scripts/styles. "
            "Detects backend patterns (algolia, typesense, wordpress, react, vue). "
            "Returns raw HTML length, cleaned text (capped at 8000 chars), detected patterns, "
            "and a links list of up to 50 unique same-domain absolute hrefs found on the page. "
            "Use the links list to find sub-pages to follow — do not guess URL patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL to fetch.",
                }
            },
            "required": ["url"],
        },
    },
    {
        "name": "read_instruction_library",
        "description": (
            "Look up known scraping patterns for a domain in the instruction library. "
            "Returns matching entries and a plain-text suggestion describing the recommended approach."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "The domain to look up, e.g. 'ycombinator.com' or 'techstars.com'.",
                }
            },
            "required": ["domain"],
        },
    },
    {
        "name": "save_companies",
        "description": (
            "Validate and upsert a list of company records into the database. "
            "Each company must have at minimum a 'name' field. "
            "Returns saved_count, error_count, and any errors."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "companies": {
                    "type": "array",
                    "description": "List of company dicts. Each must have 'name'. Optional: description, website, batch, founded_year, uses_ai, tags, location.",
                    "items": {"type": "object"},
                },
                "source": {
                    "type": "string",
                    "description": "Source identifier, e.g. 'yc', 'techstars', 'mit_deltav'.",
                },
            },
            "required": ["companies", "source"],
        },
    },
]


def dispatch_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool call by name and return the result as a JSON string."""
    if tool_name == "fetch_url":
        result = fetch_url(**tool_input)
    elif tool_name == "read_instruction_library":
        result = read_instruction_library(**tool_input)
    elif tool_name == "save_companies":
        result = save_companies(**tool_input)
    else:
        result = {"error": f"Unknown tool: {tool_name}"}

    return json.dumps(result)
