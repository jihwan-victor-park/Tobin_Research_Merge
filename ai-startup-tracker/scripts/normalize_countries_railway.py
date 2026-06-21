"""
Comprehensive country normalizer targeting the Railway production DB.

Handles: ISO-2/ISO-3 codes, city names, typos, multi-country strings,
junk values (zip codes, addresses, emoji, etc.), territory -> parent country.
"""
from __future__ import annotations
import re
import sys
from sqlalchemy import create_engine, text

RAILWAY_URL = "postgresql://postgres:DcnTzVMncslQyHdpliCQpWcWugfJdutm@viaduct.proxy.rlwy.net:19473/railway"

# ── Explicit mapping (raw DB value -> canonical name, or None to NULL) ────────
MAPPING: dict[str, str | None] = {
    # ISO-2 codes
    "US": "United States",
    "USA": "United States",
    "UK": "United Kingdom",
    "GB": "United Kingdom",
    "DE": "Germany",
    "FR": "France",
    "IN": "India",
    "CA": "Canada",
    "AU": "Australia",
    "JP": "Japan",
    "BR": "Brazil",
    "CN": "China",
    "KR": "South Korea",
    "SG": "Singapore",
    "IL": "Israel",
    "SE": "Sweden",
    "CH": "Switzerland",
    "NL": "Netherlands",
    "ES": "Spain",
    "IT": "Italy",
    "PL": "Poland",
    "BE": "Belgium",
    "DK": "Denmark",
    "NO": "Norway",
    "FI": "Finland",
    "AT": "Austria",
    "IE": "Ireland",
    "NZ": "New Zealand",
    "MX": "Mexico",
    "ZA": "South Africa",
    "NG": "Nigeria",
    "KE": "Kenya",
    "PH": "Philippines",
    "TH": "Thailand",
    "VN": "Vietnam",
    "EG": "Egypt",
    "TR": "Turkey",
    "RU": "Russia",
    "UA": "Ukraine",
    "HK": "Hong Kong",
    "TW": "Taiwan",
    "AE": "United Arab Emirates",
    "SA": "Saudi Arabia",
    "AR": "Argentina",
    "CL": "Chile",
    "CO": "Colombia",
    "PE": "Peru",
    "ID": "Indonesia",
    "MY": "Malaysia",
    "PK": "Pakistan",
    "BD": "Bangladesh",
    "PT": "Portugal",
    "CZ": "Czech Republic",
    "RO": "Romania",
    "HU": "Hungary",
    "GR": "Greece",
    "BG": "Bulgaria",
    "HR": "Croatia",
    "SK": "Slovakia",
    "SI": "Slovenia",
    "LT": "Lithuania",
    "LV": "Latvia",
    "EE": "Estonia",
    "IS": "Iceland",
    "LU": "Luxembourg",
    "CY": "Cyprus",
    "MT": "Malta",
    "RS": "Serbia",
    "GE": "Georgia",
    "AM": "Armenia",
    "AZ": "Azerbaijan",
    "KZ": "Kazakhstan",
    "UZ": "Uzbekistan",
    "MN": "Mongolia",
    "LB": "Lebanon",
    "JO": "Jordan",
    "KW": "Kuwait",
    "QA": "Qatar",
    "BH": "Bahrain",
    "OM": "Oman",
    "MA": "Morocco",
    "GH": "Ghana",
    "SN": "Senegal",
    "CM": "Cameroon",
    "TZ": "Tanzania",
    "UG": "Uganda",
    "ET": "Ethiopia",
    "ZM": "Zambia",
    "MK": "North Macedonia",
    "AL": "Albania",
    "ME": "Montenegro",
    "BA": "Bosnia and Herzegovina",
    "XK": "Kosovo",
    "LI": "Liechtenstein",
    "GI": "Gibraltar",
    "IM": "Isle of Man",
    "JE": "Jersey",
    "GG": "Guernsey",
    "MO": "Macao",
    "KY": "Cayman Islands",
    "PR": "United States",  # Puerto Rico -> US territory
    "BM": "Bermuda",
    "AI": "Anguilla",

    # ISO-3 codes seen in DB
    "PAK": "Pakistan",
    "BWA": "Botswana",
    "MMR": "Myanmar",
    "AND": "Andorra",
    "PAN": "Panama",
    "BAH": "Bahrain",
    "MTQ": "Martinique",
    "COM": None,            # ambiguous ISO-3 for Comoros; too few rows to be sure

    # Alternate spellings / common variants
    "Switerland": "Switzerland",
    "Iran!": "Iran",
    "Maroc": "Morocco",
    "dhaka": "Bangladesh",
    "NEPAL": "Nepal",
    "myanmar": "Myanmar",
    "Puerto Rico": "United States",
    "Cayman Islands": "Cayman Islands",
    "Macao": "Macao",
    "Hong Kong SAR": "Hong Kong",
    "Korea, Republic of": "South Korea",
    "Korea": "South Korea",
    "Viet Nam": "Vietnam",
    "Czech Republic": "Czech Republic",
    "Czechia": "Czech Republic",
    "Macedonia": "North Macedonia",
    "Palestine": "Palestine",
    "Kosovo": "Kosovo",

    # Cities / states / regions that slipped in  -> map to country or NULL
    "San Francisco": "United States",
    "Berkeley": "United States",
    "Texas": "United States",
    "UTAH": "United States",
    "D.C.": "United States",
    "Michigan": "United States",
    "New york": "United States",
    "michigan": "United States",
    "CDMX": "Mexico",
    "Yucatan": "Mexico",
    "Sinaloa": "Mexico",
    "São Paulo": "Brazil",
    "Rio de Janeiro": "Brazil",
    "Rio de Janeiro (RJ)": "Brazil",
    "Mato Grosso": "Brazil",
    "Paraíba": "Brazil",
    "Bavaria": "Germany",
    "Cologne & Hamburg": "Germany",
    "Berlin & Munich": "Germany",
    "Piemonte": "Italy",
    "Cantabria": "Spain",
    "New South Wales": "Australia",
    "Victoria": "Australia",
    "Marlborough": "New Zealand",
    "Kazan": "Russia",
    "Kremenchug": "Ukraine",
    "Chernihiv": "Ukraine",
    "Saraburi": "Thailand",
    "Thu Duc": "Vietnam",
    "Malang City": "Indonesia",
    "Hunan Province": "China",
    "Tainan": "Taiwan",
    "Kaohsiung City": "Taiwan",
    "Niigata Prefecture": "Japan",
    "Shiga": "Japan",
    "Karnataka 560001": "India",
    "karnataka": "India",
    "Sindh": "Pakistan",
    "Rajshahi": "Bangladesh",
    "Chitwan": "Nepal",
    "Bhutan": "Bhutan",
    "Hooghly": "India",
    "guntur": "India",
    "Roorkee-Uttarakhand": "India",
    "La Marsa": "Tunisia",
    "Biskra": "Algeria",
    "Apeldoorn": "Netherlands",
    "Barendrecht": "Netherlands",
    "Tg-Mures": "Romania",
    "Ruda Śląska": "Poland",
    "Novi Sad & San Francisco": "Serbia",
    "Sofia & London": "Bulgaria",
    "Stockholm & Hamburg": "Sweden",
    "Tel Aviv & London": "Israel",
    "London & Bombay": "United Kingdom",
    "London, UK": "United Kingdom",
    "Georgia metropolitan area": "United States",
    "Ümraniye": "Turkey",
    "Mazandaran": "Iran",
    "Kaohsiung City": "Taiwan",

    # Multi-country / region strings -> NULL (can't assign one country)
    "AU, AT, BH and 44 more": None,
    "AR, BR, CL and 16 more": None,
    "DE, FR, IT and 191 more": None,
    "GB and US": None,
    "San Francisco, Wroclaw": None,
    "Baltic and East European": None,
    "Middle East": None,
    "Volta street 13": None,

    # Junk / addresses / zip codes -> NULL
    "Earth's Core Sector": None,
    "CA ☀️": None,
    "CA 94703": None,
    "MA 02139": None,
    "FL 33162": None,
    "H3A 1X1": None,
    "NJ Area": None,
    "NY 10007": None,
    "New York 10591": None,
    "po box 321": None,
    "Near  by Woolf University(SFO International Airport)": None,
    "Bidborough House": None,
    "prev DC.": None,

    # "Thailand (Open to Remote)" style -> strip suffix
    "Thailand (Open to Remote)": "Thailand",

    # Territories kept as-is (they're legitimate research units)
    "Isle of Man": "Isle of Man",
    "Jersey": "Jersey",
    "Guernsey": "Guernsey",
    "Macao": "Macao",
    "Bermuda": "Bermuda",
    "Anguilla": "Anguilla",
    "Gibraltar": "Gibraltar",
}

# ── Regex-based cleanup applied to anything not in MAPPING ────────────────────
def _clean(raw: str) -> str | None:
    s = raw.strip()

    # Strip trailing parenthetical like "(Open to Remote)"
    s = re.sub(r"\s*\(.*?\)\s*$", "", s).strip()

    # Zip/postal codes: purely numeric or alphanumeric short codes
    if re.fullmatch(r"[A-Z]{0,2}\d[\dA-Z ]{2,8}", s):
        return None

    # Pure lowercase city-like strings with no spaces → NULL (e.g. "dhaka", "guntur")
    # Already handled explicitly above, but catch stragglers
    if s == s.lower() and len(s) > 0 and " " not in s:
        return None

    return s if s else None


def build_mapping(raw_values: list[str]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for raw in raw_values:
        if raw in MAPPING:
            canonical = MAPPING[raw]
        else:
            canonical = _clean(raw)
        if canonical != raw:
            result[raw] = canonical
    return result


def main(dry_run: bool = False):
    engine = create_engine(RAILWAY_URL)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT country FROM companies WHERE country IS NOT NULL ORDER BY country")
        ).fetchall()

    raw_values = [r[0] for r in rows]
    mapping = build_mapping(raw_values)

    changes = {k: v for k, v in mapping.items() if v != k}
    nulls   = {k for k, v in changes.items() if v is None}
    updates = {k: v for k, v in changes.items() if v is not None}

    print(f"{'DRY RUN — ' if dry_run else ''}Found {len(changes)} values to change "
          f"({len(updates)} remap, {len(nulls)} → NULL)\n")

    print("── Remaps ──────────────────────────────────────────────")
    for old, new in sorted(updates.items()):
        print(f"  {old!r:45s} → {new!r}")

    print("\n── → NULL ───────────────────────────────────────────────")
    for old in sorted(nulls):
        print(f"  {old!r}")

    if dry_run:
        print("\n(dry run — no changes written)")
        return

    with engine.begin() as conn:
        for old, new in updates.items():
            conn.execute(
                text("UPDATE companies SET country = :new WHERE country = :old"),
                {"new": new, "old": old},
            )
        for old in nulls:
            conn.execute(
                text("UPDATE companies SET country = NULL WHERE country = :old"),
                {"old": old},
            )

    # Verify
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT COUNT(DISTINCT country) FROM companies WHERE country IS NOT NULL")
        ).scalar()
    print(f"\nDone. Distinct country values now: {n}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
