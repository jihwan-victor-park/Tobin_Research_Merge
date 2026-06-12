"""
Shared country normalization utilities.

Used by both the FastAPI backend (main.py) and the Streamlit dashboard
(frontend/pipeline_dashboard.py) to map raw DB country strings to canonical
full country names and to count only real countries (not city/state strings).
"""
from __future__ import annotations

_COUNTRY_ALIASES: dict[str, str] = {
    # Full-name aliases
    "usa": "United States",
    "us": "United States",
    "united states": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "united kingdom": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "uae": "United Arab Emirates",
    "south korea": "South Korea",
    "republic of korea": "South Korea",
    "korea": "South Korea",
    "china, people's republic of": "China",
    "israel (state of)": "Israel",
    "czechia": "Czech Republic",
    "czech republic": "Czech Republic",
    "taiwan, province of china": "Taiwan",
    "hong kong sar": "Hong Kong",
    "viet nam": "Vietnam",
    "south africa": "South Africa",
    "saudi arabia": "Saudi Arabia",
    "new zealand": "New Zealand",
    # ISO 2-letter codes → full names (for PitchBook/Crunchbase imports)
    "us": "United States",
    "gb": "United Kingdom",
    "in": "India",
    "de": "Germany",
    "ca": "Canada",
    "fr": "France",
    "sg": "Singapore",
    "au": "Australia",
    "il": "Israel",
    "kr": "South Korea",
    "se": "Sweden",
    "nl": "Netherlands",
    "br": "Brazil",
    "cn": "China",
    "jp": "Japan",
    "ch": "Switzerland",
    "es": "Spain",
    "it": "Italy",
    "ie": "Ireland",
    "dk": "Denmark",
    "no": "Norway",
    "fi": "Finland",
    "be": "Belgium",
    "at": "Austria",
    "pl": "Poland",
    "pt": "Portugal",
    "hk": "Hong Kong",
    "tw": "Taiwan",
    "ae": "United Arab Emirates",
    "ru": "Russia",
    "tr": "Turkey",
    "ua": "Ukraine",
    "mx": "Mexico",
    "ar": "Argentina",
    "co": "Colombia",
    "cl": "Chile",
    "ng": "Nigeria",
    "za": "South Africa",
    "ke": "Kenya",
    "eg": "Egypt",
    "id": "Indonesia",
    "my": "Malaysia",
    "th": "Thailand",
    "vn": "Vietnam",
    "ph": "Philippines",
    "nz": "New Zealand",
    "ee": "Estonia",
    "lv": "Latvia",
    "lt": "Lithuania",
    "cz": "Czech Republic",
    "hu": "Hungary",
    "ro": "Romania",
    "gr": "Greece",
    "bg": "Bulgaria",
    "hr": "Croatia",
    "rs": "Serbia",
    "sa": "Saudi Arabia",
    "qa": "Qatar",
    "kw": "Kuwait",
    "pk": "Pakistan",
    "bd": "Bangladesh",
}

# Full country names that have coordinates on the globe — used to filter out
# city/state strings masquerading as countries in the DB.
GLOBE_COUNTRIES: frozenset[str] = frozenset({
    "United States", "United Kingdom", "Canada", "India", "Israel",
    "Germany", "France", "Australia", "Singapore", "Netherlands",
    "Sweden", "Switzerland", "Brazil", "Spain", "Finland", "Denmark",
    "Norway", "Japan", "South Korea", "China", "Estonia", "Poland",
    "Ireland", "Mexico", "Colombia", "Nigeria", "South Africa", "Kenya",
    "Egypt", "United Arab Emirates", "Pakistan", "Bangladesh", "Indonesia",
    "Portugal", "Italy", "Austria", "Belgium", "Czech Republic", "Romania",
    "Ukraine", "Turkey", "Argentina", "Chile", "New Zealand", "Philippines",
    "Vietnam", "Thailand", "Malaysia", "Hong Kong", "Taiwan", "Greece",
    "Hungary", "Latvia", "Lithuania", "Russia",
    "Peru", "Ghana", "Panama", "Uganda", "Ecuador", "Morocco",
    "Croatia", "Jamaica", "Senegal", "Tanzania", "Uruguay",
    "Armenia", "Jordan", "Bolivia", "Ethiopia", "Luxembourg",
    "Venezuela", "Saudi Arabia", "Qatar", "Kuwait", "Georgia",
    "North Macedonia", "Montenegro", "Iceland", "Belarus",
    "Sri Lanka", "Nepal", "Mongolia", "Lebanon", "Cyprus",
    "Kosovo", "Slovakia", "Bulgaria", "South Africa", "Egypt",
    "Algeria", "Namibia", "Benin", "Cameroon", "Zambia",
    "Slovenia", "Serbia", "Hong Kong", "Taiwan",
})


def normalize_country(raw: str | None) -> str | None:
    """Map raw DB country string to canonical full country name.

    Returns None for empty/None input. For strings not in the alias map,
    returns the cleaned string as-is (which may be a city name — callers
    should filter against GLOBE_COUNTRIES to confirm it's a real country).
    """
    if not raw:
        return None
    cleaned = raw.split(";")[0].split("/")[0].strip()
    lower = cleaned.lower()
    return _COUNTRY_ALIASES.get(lower, cleaned)


def count_distinct_countries(raw_values: list[str]) -> int:
    """Count how many distinct recognized countries appear in a list of raw DB values."""
    seen: set[str] = set()
    for v in raw_values:
        norm = normalize_country(v)
        if norm and norm in GLOBE_COUNTRIES:
            seen.add(norm)
    return len(seen)
