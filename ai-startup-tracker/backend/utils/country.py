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
    # EU nomenclature deviates from ISO 3166-1 for Greece: CORDIS and Eurostat
    # write EL, not GR. Without this the code reaches the DB as a bare "EL".
    "el": "Greece",
    "cy": "Cyprus",
    "si": "Slovenia",
    "sk": "Slovakia",
    "lu": "Luxembourg",
    "is": "Iceland",
    "mt": "Malta",
    "md": "Moldova",
    "ma": "Morocco",
    "tn": "Tunisia",
    "jo": "Jordan",
    "gh": "Ghana",
    "zm": "Zambia",
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


# ── Regions ──────────────────────────────────────────────────────────
#
# Per-country counts get thin fast outside the top twenty, which makes a
# country-level breakdown mostly noise for the long tail. Grouping gives the
# same data a denominator big enough to say something. Two levels are kept
# because they answer different questions: REGION separates places that behave
# differently as startup ecosystems (Israel does not belong with Egypt just
# because both are geographically near), while CONTINENT is the coarse cut for
# a headline chart.
_REGION: dict[str, str] = {}


def _reg(region: str, *countries: str) -> None:
    for c in countries:
        _REGION[c] = region


_reg("North America", "United States", "Canada")
_reg("Latin America", "Mexico", "Brazil", "Argentina", "Chile", "Colombia",
     "Peru", "Uruguay", "Ecuador", "Bolivia", "Venezuela", "Panama",
     "Costa Rica", "Guatemala", "Jamaica", "Dominican Republic", "Puerto Rico",
     "Paraguay", "Honduras", "El Salvador", "Nicaragua", "Cuba", "Trinidad and Tobago")
_reg("Western Europe", "United Kingdom", "Ireland", "France", "Germany",
     "Netherlands", "Belgium", "Switzerland", "Austria", "Luxembourg", "Monaco",
     "Liechtenstein")
_reg("Northern Europe", "Sweden", "Norway", "Denmark", "Finland", "Iceland",
     "Estonia", "Latvia", "Lithuania")
_reg("Southern Europe", "Spain", "Portugal", "Italy", "Greece", "Malta",
     "Cyprus", "San Marino", "Andorra")
_reg("Central & Eastern Europe", "Poland", "Czech Republic", "Slovakia",
     "Hungary", "Romania", "Bulgaria", "Croatia", "Slovenia", "Serbia",
     "Bosnia and Herzegovina", "North Macedonia", "Montenegro", "Albania",
     "Kosovo", "Ukraine", "Belarus", "Moldova", "Russia")
_reg("Middle East", "Israel", "United Arab Emirates", "Saudi Arabia", "Qatar",
     "Kuwait", "Bahrain", "Oman", "Jordan", "Lebanon", "Turkey", "Iran", "Iraq",
     "Palestine", "Yemen", "Syria")
_reg("North Africa", "Egypt", "Morocco", "Tunisia", "Algeria", "Libya", "Sudan")
_reg("Sub-Saharan Africa", "Nigeria", "Kenya", "South Africa", "Ghana",
     "Ethiopia", "Uganda", "Tanzania", "Rwanda", "Senegal", "Cameroon",
     "Ivory Coast", "Zambia", "Zimbabwe", "Botswana", "Namibia", "Mozambique",
     "Angola", "Benin", "Mali", "Malawi", "Mauritius", "Madagascar",
     "Burkina Faso", "Somalia", "Congo", "Democratic Republic of the Congo")
_reg("East Asia", "China", "Japan", "South Korea", "Taiwan", "Hong Kong",
     "Macau", "Mongolia", "North Korea")
_reg("South Asia", "India", "Pakistan", "Bangladesh", "Sri Lanka", "Nepal",
     "Bhutan", "Maldives", "Afghanistan")
_reg("Southeast Asia", "Singapore", "Indonesia", "Malaysia", "Thailand",
     "Vietnam", "Philippines", "Myanmar", "Cambodia", "Laos", "Brunei")
_reg("Central Asia & Caucasus", "Kazakhstan", "Uzbekistan", "Georgia",
     "Armenia", "Azerbaijan", "Kyrgyzstan", "Tajikistan", "Turkmenistan")
_reg("Oceania", "Australia", "New Zealand", "Fiji", "Papua New Guinea")

_CONTINENT: dict[str, str] = {
    "North America": "Americas",
    "Latin America": "Americas",
    "Western Europe": "Europe",
    "Northern Europe": "Europe",
    "Southern Europe": "Europe",
    "Central & Eastern Europe": "Europe",
    "Middle East": "Asia",
    "East Asia": "Asia",
    "South Asia": "Asia",
    "Southeast Asia": "Asia",
    "Central Asia & Caucasus": "Asia",
    "North Africa": "Africa",
    "Sub-Saharan Africa": "Africa",
    "Oceania": "Oceania",
}


def country_region(raw: str | None) -> str | None:
    """Region for a raw country string, or None when the value is not a country.

    The country column holds plenty of things that are not countries — US
    states, bare city names, stray coordinates — so this returns None rather
    than inventing a region for them, and a caller counting regions will simply
    not count those rows.
    """
    norm = normalize_country(raw)
    if not norm or norm not in GLOBE_COUNTRIES:
        return None
    return _REGION.get(norm)


def country_continent(raw: str | None) -> str | None:
    region = country_region(raw)
    return _CONTINENT.get(region) if region else None


def unmapped_countries(raw_values: list[str]) -> set[str]:
    """Recognised countries that no region covers — the maintenance list."""
    missing = set()
    for v in raw_values:
        norm = normalize_country(v)
        if norm and norm in GLOBE_COUNTRIES and norm not in _REGION:
            missing.add(norm)
    return missing
