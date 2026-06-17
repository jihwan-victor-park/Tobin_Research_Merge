"""
One-time fix for messy country values from merged Railway GitHub companies.
Maps ISO3 codes, US states, cities, variants → canonical country names.
Nulls out genuinely unresolvable junk.
Run against Railway with:
  DATABASE_URL=<railway_url> PYTHONPATH=. python scripts/fix_railway_countries.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.db.connection import get_engine
from sqlalchemy import text

# ISO 3166-1 alpha-3 → country name
ISO3 = {
    "GBR": "United Kingdom", "IND": "India", "CAN": "Canada", "DEU": "Germany",
    "CHN": "China", "JPN": "Japan", "FRA": "France", "ITA": "Italy",
    "BRA": "Brazil", "KOR": "South Korea", "ESP": "Spain", "ISR": "Israel",
    "AUS": "Australia", "NLD": "Netherlands", "CHE": "Switzerland", "ROM": "Romania",
    "SGP": "Singapore", "SWE": "Sweden", "LKA": "Sri Lanka", "TUR": "Turkey",
    "ARE": "United Arab Emirates", "MEX": "Mexico", "POL": "Poland", "RUS": "Russia",
    "HKG": "Hong Kong", "DNK": "Denmark", "BEL": "Belgium", "SVK": "Slovakia",
    "CYP": "Cyprus", "TWN": "Taiwan", "COL": "Colombia", "FIN": "Finland",
    "AUT": "Austria", "ZAF": "South Africa", "IRL": "Ireland", "SAU": "Saudi Arabia",
    "LUX": "Luxembourg", "PRT": "Portugal", "CZE": "Czech Republic", "TUN": "Tunisia",
    "IDN": "Indonesia", "ARG": "Argentina", "CHL": "Chile", "UKR": "Ukraine",
    "NOR": "Norway", "HUN": "Hungary", "EST": "Estonia", "NZL": "New Zealand",
    "NGA": "Nigeria", "MYS": "Malaysia", "VNM": "Vietnam", "GRC": "Greece",
    "THA": "Thailand", "BLR": "Belarus", "ISL": "Iceland", "BGR": "Bulgaria",
    "LTU": "Lithuania", "MLT": "Malta", "EGY": "Egypt", "TTO": "Trinidad and Tobago",
    "NPL": "Nepal", "CYM": "Cayman Islands", "KEN": "Kenya", "CRI": "Costa Rica",
    "PHL": "Philippines", "HRV": "Croatia", "SRB": "Serbia", "DOM": "Dominican Republic",
    "LVA": "Latvia", "GTM": "Guatemala", "BHR": "Bahrain", "SVN": "Slovenia",
    "DZA": "Algeria", "BGD": "Bangladesh", "KHM": "Cambodia", "MUS": "Mauritius",
    "OMN": "Oman", "URY": "Uruguay", "BIH": "Bosnia and Herzegovina", "LBN": "Lebanon",
    "LIE": "Liechtenstein", "SLV": "El Salvador", "AZE": "Azerbaijan", "MAR": "Morocco",
    "PER": "Peru", "MKD": "North Macedonia", "SYC": "Seychelles", "KAZ": "Kazakhstan",
    "ARM": "Armenia", "PRY": "Paraguay", "VEN": "Venezuela", "GIB": "Gibraltar",
    "ALB": "Albania", "MDA": "Moldova", "GHA": "Ghana", "KNA": "Saint Kitts and Nevis",
    "JOR": "Jordan", "ECU": "Ecuador", "RWA": "Rwanda", "ZWE": "Zimbabwe",
    "KGZ": "Kyrgyzstan", "MDG": "Madagascar", "NAM": "Namibia", "QAT": "Qatar",
    "BLZ": "Belize", "BMU": "Bermuda", "HTI": "Haiti", "NIC": "Nicaragua",
    "GAB": "Gabon", "SDN": "Sudan", "SEN": "Senegal", "SLE": "Sierra Leone",
    "ETH": "Ethiopia", "TCD": "Chad", "TJK": "Tajikistan", "UGA": "Uganda",
    "AGO": "Angola", "AFG": "Afghanistan", "KWT": "Kuwait", "LBY": "Libya",
    "COD": "Democratic Republic of the Congo", "CMR": "Cameroon", "BFA": "Burkina Faso",
    "BEN": "Benin", "MOZ": "Mozambique", "MNG": "Mongolia", "MNE": "Montenegro",
    "BTN": "Bhutan", "GEO": "Georgia", "HND": "Honduras", "MAC": "Macao",
    "JEY": "Jersey", "IMN": "Isle of Man", "LCA": "Saint Lucia", "AIA": "Anguilla",
    "ATG": "Antigua and Barbuda", "BRN": "Brunei", "BRB": "Barbados", "GUY": "Guyana",
    "MLI": "Mali", "LSO": "Lesotho", "PSE": "Palestine", "MDV": "Maldives",
    "PNG": "Papua New Guinea", "PRI": "Puerto Rico", "TAN": "Tanzania",
    "SOM": "Somalia", "SYR": "Syria", "IRQ": "Iraq", "IRN": "Iran",
    "GR": "Greece", "SA": "Saudi Arabia", "HU": "Hungary",
}

# US states / territories → United States
US_STATES = {
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
    "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
    "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma",
    "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming", "DC", "Bay Area", "NYC",
    "LA", "SF", "Silicon Valley", "New England",
    # Canadian provinces → Canada handled separately
}

CA_PROVINCES = {
    "Ontario", "British Columbia", "Quebec", "Alberta", "Manitoba",
    "Saskatchewan", "Nova Scotia", "New Brunswick", "BC", "ON", "QC", "AB", "NB",
}

# City → country (cities that appear as country values)
CITY_TO_COUNTRY = {
    # Germany
    "Berlin": "Germany", "Munich": "Germany", "München": "Germany",
    "Cologne": "Germany", "Hamburg": "Germany", "Frankfurt": "Germany",
    "Stuttgart": "Germany", "Darmstadt": "Germany", "Heidelberg": "Germany",
    "Landshut": "Germany", "Potsdam": "Germany", "Münster": "Germany",
    "Saarbrücken": "Germany", "Ulm": "Germany", "Großrinderfeld": "Germany",
    # UK
    "London": "United Kingdom", "Peterborough": "United Kingdom",
    "Northern Ireland": "United Kingdom",
    # France
    "Paris": "France", "Lyon": "France",
    # South Korea
    "Seoul": "South Korea",
    # China
    "Beijing": "China", "Shanghai": "China", "Shenzhen": "China",
    "Chengdu": "China", "Xiamen": "China", "Sichuan": "China",
    "Shanxi": "China", "Liaoning": "China", "Yunnan": "China",
    "Hunan": "China", "Swatow": "China",
    # Czech Republic
    "Prague": "Czech Republic",
    # Spain
    "Barcelona": "Spain", "Madrid": "Spain",
    # Romania
    "Bucharest": "Romania",
    # Sweden
    "Stockholm": "Sweden",
    # Switzerland
    "Zurich": "Switzerland", "Zug": "Switzerland",
    # Israel
    "Tel Aviv": "Israel", "Petah Tikva": "Israel",
    # Turkey
    "Istanbul": "Turkey",
    # Ireland
    "Dublin": "Ireland",
    # Bulgaria
    "Sofia": "Bulgaria",
    # Estonia
    "Tallinn": "Estonia",
    # Latvia
    "Riga": "Latvia",
    # Lithuania
    "Vilnius": "Lithuania",
    # Serbia
    "Belgrade": "Serbia", "Novi Sad": "Serbia",
    # Croatia
    "Zagreb": "Croatia",
    # Slovakia
    "Bratislava": "Slovakia",
    # Poland
    "Warsaw": "Poland", "Kraków": "Poland", "Wroclaw": "Poland",
    # Kazakhstan
    "Almaty": "Kazakhstan", "Astana": "Kazakhstan",
    # Italy
    "Bologna": "Italy", "Rome": "Italy", "Milan": "Italy",
    "Sicily": "Italy", "Erba": "Italy",
    # Australia
    "Sydney": "Australia", "Brisbane": "Australia", "Melbourne": "Australia",
    # India
    "Bengaluru": "India", "Bangalore": "India", "Delhi": "India",
    "Mumbai": "India", "Chennai": "India", "Pune": "India",
    "Kolkata": "India", "KOLKATA": "India", "Sunnyvale": "United States",
    # Pakistan
    "Lahore": "Pakistan", "Karachi": "Pakistan",
    # Bangladesh
    "Dhaka": "Bangladesh",
    # Ethiopia
    "Addis Ababa": "Ethiopia",
    # Nigeria
    "Lagos": "Nigeria",
    # Ghana
    "Accra": "Ghana",
    # South Africa
    "Johannesburg": "South Africa", "Cape Town": "South Africa",
    # Russia
    "Saint-Petersburg": "Russia", "Moscow": "Russia",
    "Krasnodar": "Russia", "Rostov-on-Don": "Russia",
    # Belarus
    "Minsk": "Belarus",
    # Vietnam
    "Ho Chi Minh City": "Vietnam", "Ha Noi": "Vietnam",
    # Portugal
    "Lisbon": "Portugal",
    # Austria
    "Upper Austria": "Austria", "Vienna": "Austria",
    # Montenegro
    "Podgorica": "Montenegro",
    # Egypt
    "Giza": "Egypt", "Alexandria": "Egypt",
    # Tunisia
    "sfax": "Tunisia",
    # Bosnia
    "Sarajevo": "Bosnia and Herzegovina",
    # Argentina
    "Buenos Aires": "Argentina",
}

# Indian states → India
INDIA_STATES = {
    "Maharashtra", "Karnataka", "Gujarat", "Punjab", "Uttar Pradesh",
    "Bihar", "West Bengal", "Assam", "Odisha", "ODISHA", "Telangana",
    "Tamil Nadu", "TamilNadu", "Tamilnadu", "Andhra Pradesh", "Haryana",
    "Chhattisgarh", "Jharkhand", "Madhya Predesh", "Jammu and Kashmir",
    "Kashmir", "Kerala", "Rajasthan", "Uttarakhand", "Uttrakhand",
    "UTTAR PRADESH", "Uttar Pradesh.", "up(india)",
}

# Chinese provinces → China
CHINA_PROVINCES = {
    "Zhejiang", "Fujian", "Guangdong", "Jiangsu", "Shandong",
    "Heilongjiang", "Anhui", "Henan", "Hubei", "Hunan Province",
    "Mato Grosso",  # this is Brazil actually, will be overridden below
}

# Explicit variants and aliases
ALIASES = {
    # Country name variants
    "The Netherlands": "Netherlands", "the Netherlands": "Netherlands",
    "Netherland": "Netherlands", "Nederland": "Netherlands",
    "Brasil": "Brazil", "España": "Spain",
    "Türkiye": "Turkey", "Turkiye": "Turkey", "TÜRKİYE": "Turkey",
    "Việt Nam": "Vietnam", "Viet Nam": "Vietnam",
    "Republic of Korea": "South Korea", "Korea Republic": "South Korea",
    "S. Korea": "South Korea",
    "Russian Federation": "Russia", "Russian": "Russia",
    "People's Republic of China": "China", "PRC": "China",
    "Mainland China": "China", "ROC": "Taiwan",
    "Romania": "Romania",  # keep as-is but "ROM" → Romania above
    "Kazakhstan": "Kazakhstan", "Azerbaijan": "Azerbaijan",
    "Uzbekistan": "Uzbekistan", "Cambodia": "Cambodia", "Myanmar": "Myanmar",
    "Ivory Coast": "Côte d'Ivoire",
    "Puerto Rico": "Puerto Rico",
    "Tunisia": "Tunisia", "Iran": "Iran", "Iraq": "Iraq",
    "Seychelles": "Seychelles", "Cayman Islands": "Cayman Islands",
    "South Sudan": "South Sudan", "Trinidad and Tobago": "Trinidad and Tobago",
    "Dominican Republic": "Dominican Republic", "Rwanda": "Rwanda",
    "Malawi": "Malawi", "Mauritius": "Mauritius", "Bahrain": "Bahrain",
    "Costa Rica": "Costa Rica", "Paraguay": "Paraguay",
    "Chad": "Chad", "Moldova": "Moldova", "Eswatini": "Eswatini",
    "Democratic Republic of the Congo": "Democratic Republic of the Congo",
    "Congo, Democratic Republic": "Democratic Republic of the Congo",
    "Macedonia": "North Macedonia",
    "Ukraine 🇺🇦": "Ukraine", "Kiyv": "Ukraine",
    "U.S": "United States", "U.S.": "United States",
    "U.S.A": "United States", "USA 🌴 🇺🇸": "United States",
    "USA.": "United States", "US.": "United States",
    "Canada ❄️": "Canada", "B.C. Canada": "Canada",
    "Ontario - Canada": "Canada", "Quebec": "Canada", "Québec": "Canada",
    "Australia.": "Australia", "Indonesia.": "Indonesia",
    "Bangladesh.": "Bangladesh", "Bharat (India)": "India",
    "Ind": "India", "Spain.": "Spain", "France.": "France",
    "Mexico.": "Mexico", "Chile.": "Chile", "Texas.": "Texas",
    "Sri Lanka.": "Sri Lanka",
    "Aotearoa": "New Zealand",
    "Turkiye": "Turkey",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
}

# Values to null out (too vague or completely unresolvable)
NULL_VALUES = {
    "North America", "Europe", "Asia", "Africa", "Latin America", "MENA",
    "Earth", "Universe", "Milky Way", "Earth's Core Sector",
    "Sun System", "the only planet inhabited by robots",
    "Sol", "Worldwide", "Other", "Remote", "North", "South",
    "Arch Linux", "UCL", "Tsinghua University",
    "University of Colorado Boulder", "University of Ljubljana",
    "University of Toronto", "127.0.0.1", "11.27507",
    "LON 11.568161)", "NP", "WB", "MP", "SP", "RN", "MG", "VIC", "QLD",
    "NSW", "PA", "PE", "AB", "NBO", "UM", "GR",  # ambiguous state codes
    "hantingqu", "narephat", "Moth(Dhani)", "Musuru", "Ilala",
    "Vim", "Ярославль",
    "PA; Southern California",  # already handled by normalize_countries.py
    "Alexandria / Cairo",  # ambiguous — already normalized
}


def build_mapping(raw_values: list[str]) -> dict[str, str | None]:
    mapping = {}
    for v in raw_values:
        stripped = v.strip()

        # Explicit null
        if stripped in NULL_VALUES:
            mapping[v] = None
            continue

        # Direct alias
        if stripped in ALIASES:
            mapping[v] = ALIASES[stripped]
            continue

        # ISO3
        if stripped in ISO3:
            mapping[v] = ISO3[stripped]
            continue

        # City → country
        if stripped in CITY_TO_COUNTRY:
            mapping[v] = CITY_TO_COUNTRY[stripped]
            continue

        # US states
        if stripped in US_STATES:
            mapping[v] = "United States"
            continue

        # Canadian provinces
        if stripped in CA_PROVINCES:
            mapping[v] = "Canada"
            continue

        # Indian states
        if stripped in INDIA_STATES:
            mapping[v] = "India"
            continue

        # Heuristics for suffixed junk
        lower = stripped.lower()
        if any(x in lower for x in ["usa", "u.s.", " us,", "united states"]):
            mapping[v] = "United States"
            continue
        if "canada" in lower:
            mapping[v] = "Canada"
            continue
        if "india" in lower:
            mapping[v] = "India"
            continue
        if "china" in lower or "prov. china" in lower:
            mapping[v] = "China"
            continue
        if "brazil" in lower or "brasil" in lower or "brazil" in lower:
            mapping[v] = "Brazil"
            continue
        if "germany" in lower:
            mapping[v] = "Germany"
            continue
        if "italy" in lower or "(italy)" in lower:
            mapping[v] = "Italy"
            continue
        if "netherlands" in lower:
            mapping[v] = "Netherlands"
            continue
        if "vietnam" in lower or "việt" in lower:
            mapping[v] = "Vietnam"
            continue
        if "korea" in lower:
            mapping[v] = "South Korea"
            continue
        if "nigeria" in lower:
            mapping[v] = "Nigeria"
            continue
        if "turkey" in lower or "türk" in lower:
            mapping[v] = "Turkey"
            continue
        if "switzerland" in lower:
            mapping[v] = "Switzerland"
            continue
        if "japan" in lower:
            mapping[v] = "Japan"
            continue
        if "spain" in lower or "españa" in lower:
            mapping[v] = "Spain"
            continue
        if "france" in lower:
            mapping[v] = "France"
            continue
        if "australia" in lower:
            mapping[v] = "Australia"
            continue
        if "indonesia" in lower:
            mapping[v] = "Indonesia"
            continue
        if "sri lanka" in lower:
            mapping[v] = "Sri Lanka"
            continue
        if "singapore" in lower:
            mapping[v] = "Singapore"
            continue
        if "ukraine" in lower:
            mapping[v] = "Ukraine"
            continue
        if "russia" in lower or "russian" in lower:
            mapping[v] = "Russia"
            continue
        if "mexico" in lower:
            mapping[v] = "Mexico"
            continue
        if "bangladesh" in lower:
            mapping[v] = "Bangladesh"
            continue
        if "pakistan" in lower:
            mapping[v] = "Pakistan"
            continue
        if "poland" in lower:
            mapping[v] = "Poland"
            continue
        if "sweden" in lower:
            mapping[v] = "Sweden"
            continue
        if "norway" in lower:
            mapping[v] = "Norway"
            continue
        if "denmark" in lower:
            mapping[v] = "Denmark"
            continue
        if "finland" in lower:
            mapping[v] = "Finland"
            continue
        if "belgium" in lower:
            mapping[v] = "Belgium"
            continue
        if "austria" in lower:
            mapping[v] = "Austria"
            continue
        if "hungary" in lower:
            mapping[v] = "Hungary"
            continue
        if "ukraine" in lower:
            mapping[v] = "Ukraine"
            continue
        if "egypt" in lower:
            mapping[v] = "Egypt"
            continue
        if "kenya" in lower:
            mapping[v] = "Kenya"
            continue
        if "ghana" in lower:
            mapping[v] = "Ghana"
            continue
        if "ethiopia" in lower:
            mapping[v] = "Ethiopia"
            continue
        if "serbia" in lower:
            mapping[v] = "Serbia"
            continue
        if "croatia" in lower:
            mapping[v] = "Croatia"
            continue
        if "chile" in lower:
            mapping[v] = "Chile"
            continue
        if "argentina" in lower:
            mapping[v] = "Argentina"
            continue
        if "colombia" in lower:
            mapping[v] = "Colombia"
            continue
        if "peru" in lower:
            mapping[v] = "Peru"
            continue

        # Looks like a zip code, coordinate, or other pure junk
        if stripped.replace(" ", "").replace("-", "").replace(".", "").isdigit():
            mapping[v] = None
            continue
        if len(stripped) <= 2 and stripped.isupper():
            mapping[v] = None  # unrecognized 2-letter code
            continue

        # No mapping found — leave unchanged
    return mapping


def main():
    engine = get_engine()

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT DISTINCT country FROM companies "
            "WHERE country IS NOT NULL AND country != ''"
        )).all()

    from backend.utils.country import GLOBE_COUNTRIES
    valid = set(GLOBE_COUNTRIES)
    bad = [r[0] for r in rows if r[0] not in valid]
    print(f"Unrecognized country values: {len(bad)}")

    mapping = build_mapping(bad)
    changes = {k: v for k, v in mapping.items() if v != k}
    nulls = [k for k, v in changes.items() if v is None]
    updates = {k: v for k, v in changes.items() if v is not None}

    print(f"Will update: {len(updates)}, will null: {len(nulls)}, unchanged: {len(bad) - len(changes)}")

    with engine.begin() as conn:
        for orig, normed in updates.items():
            conn.execute(text("UPDATE companies SET country = :n WHERE country = :o"),
                         {"n": normed, "o": orig})
        if nulls:
            conn.execute(text("UPDATE companies SET country = NULL WHERE country = ANY(:bad)"),
                         {"bad": nulls})

    with engine.connect() as conn:
        count = conn.execute(text(
            "SELECT COUNT(DISTINCT country) FROM companies "
            "WHERE country IS NOT NULL AND country != ''"
        )).scalar()
        print(f"Distinct countries after fix: {count}")


if __name__ == "__main__":
    main()
