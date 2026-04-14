"""
MIT delta v Scraper — fetches the past teams page, cleans the HTML,
and uses Claude Haiku to extract structured company data by cohort year.

Why Claude for extraction here:
  Unlike YC/Techstars which expose structured APIs, MIT delta v is a
  standard WordPress page. The data is server-rendered HTML — companies
  are listed by year cohort with no consistent CSS class pattern to
  reliably target with BeautifulSoup selectors. Claude reads the
  natural-language structure and extracts it correctly.

Note: This page lists names only — descriptions and websites are not
present in the HTML, so those fields will be null for most companies.
"""

import json
import os
import re
import sys
from pathlib import Path

import anthropic
import requests
from bs4 import BeautifulSoup

# Allow importing db from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.db import get_connection, get_stats, init_db, insert_company

# --- Config ---
URL = "https://entrepreneurship.mit.edu/accelerator/past-teams/"
MODEL = "claude-haiku-4-5-20251001"
SOURCE = "mit_deltav"

# Haiku pricing (per token) as of 2024
INPUT_TOKEN_COST = 0.00000025
OUTPUT_TOKEN_COST = 0.00000125

SYSTEM_PROMPT = (
    "You are a data extraction assistant. "
    "Extract all startup companies from this MIT delta v accelerator page. "
    "The page lists companies by year cohort. "
    "Return ONLY a valid JSON array where each object has: "
    "name (string), batch_year (integer), description (string or null if not present), "
    "website (string or null). "
    "No markdown fences, no preamble."
)

AI_KEYWORDS = [
    "artificial intelligence",
    "machine learning",
    "large language model",
    "llm",
    "generative ai",
    "generative",
    "gpt",
    "neural network",
    "deep learning",
    "nlp",
    "natural language processing",
    "computer vision",
    "data science",
    "autonomous",
    "robotics",
    "predictive",
    "recommendation engine",
    "ai",
]


def fetch_and_clean(url: str) -> str:
    """Fetch page HTML and strip noise tags, returning compact text."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "meta", "link"]):
        tag.decompose()

    return " ".join(soup.get_text(separator=" ", strip=True).split())


def extract_with_claude(cleaned_html: str, api_key: str) -> tuple[list[dict], int, int]:
    """
    Send cleaned HTML to Claude Haiku for extraction.
    Returns (companies, input_tokens, output_tokens).
    """
    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Extract companies from:\n\n{cleaned_html}"}],
    )

    raw = message.content[0].text
    input_tokens = message.usage.input_tokens
    output_tokens = message.usage.output_tokens

    # Strip markdown fences in case Claude adds them despite instructions
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    try:
        companies = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"ERROR: Claude returned invalid JSON.\nReason: {e}")
        print(f"Raw response (first 500 chars):\n{raw[:500]}")
        sys.exit(1)

    if not isinstance(companies, list):
        print(f"ERROR: Expected a JSON array but got {type(companies).__name__}.")
        sys.exit(1)

    return companies, input_tokens, output_tokens


def detect_ai(company: dict) -> bool:
    """Word-boundary keyword check against name and description."""
    text = " ".join(filter(None, [
        company.get("name", ""),
        company.get("description", ""),
    ]))
    return any(
        re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE)
        for kw in AI_KEYWORDS
    )


def normalize(company: dict) -> dict:
    """Map Claude's output to our shared schema."""
    return {
        "name": company.get("name"),
        "description": company.get("description"),
        "founded_year": None,  # not available on this page
        "batch": str(company["batch_year"]) if company.get("batch_year") else None,
        "website": company.get("website"),
        "uses_ai": detect_ai(company),
        "tags": [],
        "industries": [],
        "location": "Cambridge, MA, USA",  # all delta v companies are MIT-based
        "team_size": None,
        "status": None,
        "stage": None,
        "source": SOURCE,
        "extra": {},
    }


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.")
        sys.exit(1)

    # Step 1: Fetch and clean the page
    print(f"Fetching {URL} ...")
    cleaned = fetch_and_clean(URL)
    print(f"  Cleaned content: {len(cleaned):,} characters")

    # Step 2: Extract with Claude Haiku
    print(f"Sending to {MODEL} for extraction ...")
    raw_companies, input_tokens, output_tokens = extract_with_claude(cleaned, api_key)
    print(f"  Extracted {len(raw_companies)} companies")
    print(f"  Tokens used: {input_tokens:,} input / {output_tokens:,} output")

    cost = input_tokens * INPUT_TOKEN_COST + output_tokens * OUTPUT_TOKEN_COST
    print(f"  Estimated cost: ${cost:.6f}")

    # Step 3: Normalize to shared schema
    companies = [normalize(c) for c in raw_companies]

    # Step 4: Upsert into database
    print("Writing to database ...")
    conn = get_connection()
    init_db(conn)
    for company in companies:
        insert_company(conn, company)
    conn.commit()
    conn.close()

    # Step 5: Summary
    ai_count = sum(1 for c in companies if c["uses_ai"])
    print(f"\n  Total found    : {len(raw_companies)}")
    print(f"  Total upserted : {len(companies)}")
    print(f"  Uses AI        : {ai_count} ({ai_count / len(companies) * 100:.1f}%)" if companies else "")

    # Step 6: 3 sample records
    print("\n--- 3 sample records ---")
    for s in companies[:3]:
        print(json.dumps(s, indent=2))

    # Step 7: Full DB stats
    conn = get_connection()
    get_stats(conn)
    conn.close()


if __name__ == "__main__":
    main()
