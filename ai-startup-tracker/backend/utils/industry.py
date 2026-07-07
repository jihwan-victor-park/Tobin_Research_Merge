"""
Canonical industry vertical taxonomy.

16 categories that cover both Crunchbase (49 groups) and PitchBook (~50 groups)
with a single shared vocabulary. Used by the backfill script and dashboard.
"""
from __future__ import annotations

CANONICAL_VERTICALS = [
    "Software & IT",
    "Healthcare",
    "Biotech & Pharma",
    "Financial Services",
    "E-commerce & Retail",
    "Media & Marketing",
    "Education",
    "Energy & CleanTech",
    "Hardware & Manufacturing",
    "Transportation",
    "Real Estate",
    "Food & AgTech",
    "Security & Privacy",
    "Data & Analytics",
    "Professional Services",
    "Consumer & Lifestyle",
    "Social Impact",
]

# ── Crunchbase category_groups_list → canonical ───────────────────────

CB_TO_CANONICAL: dict[str, str | None] = {
    # Software & IT
    "Software":                     "Software & IT",
    "Information Technology":       "Software & IT",
    "Apps":                         "Software & IT",
    "Mobile":                       "Software & IT",
    "Internet Services":            "Software & IT",

    # Healthcare
    "Health Care":                  "Healthcare",

    # Biotech & Pharma
    "Biotechnology":                "Biotech & Pharma",
    "Science and Engineering":      "Biotech & Pharma",

    # Financial Services
    "Financial Services":           "Financial Services",
    "Lending and Investments":      "Financial Services",
    "Blockchain and Cryptocurrency":"Financial Services",

    # E-commerce & Retail
    "Commerce and Shopping":        "E-commerce & Retail",
    "Consumer Goods":               "E-commerce & Retail",
    "Clothing and Apparel":         "E-commerce & Retail",

    # Media & Marketing
    "Media and Entertainment":      "Media & Marketing",
    "Advertising":                  "Media & Marketing",
    "Content and Publishing":       "Media & Marketing",
    "Video":                        "Media & Marketing",
    "Music and Audio":              "Media & Marketing",
    "Sports":                       "Media & Marketing",

    # Education
    "Education":                    "Education",

    # Energy & CleanTech
    "Energy":                       "Energy & CleanTech",
    "Sustainability":               "Energy & CleanTech",
    "Natural Resources":            "Energy & CleanTech",

    # Hardware & Manufacturing
    "Hardware":                     "Hardware & Manufacturing",
    "Manufacturing":                "Hardware & Manufacturing",
    "Consumer Electronics":         "Hardware & Manufacturing",

    # Transportation
    "Transportation":               "Transportation",

    # Real Estate
    "Real Estate":                  "Real Estate",

    # Food & AgTech
    "Food and Beverage":            "Food & AgTech",

    # Security & Privacy
    "Privacy and Security":         "Security & Privacy",

    # Data & Analytics
    "Data and Analytics":           "Data & Analytics",

    # Professional Services
    "Professional Services":        "Professional Services",
    "Administrative Services":      "Professional Services",
    "Design":                       "Professional Services",
    "Government and Military":      "Professional Services",

    # Consumer & Lifestyle
    "Community and Lifestyle":      "Consumer & Lifestyle",
    "Travel and Tourism":           "Consumer & Lifestyle",
    "Events":                       "Consumer & Lifestyle",

    # Social Impact
    "Social Impact":                "Social Impact",

    # Skip — too generic or AI-specific (cb_ai_tagged handles AI)
    "Artificial Intelligence (AI)": None,
    "Other":                        None,
}

# ── PitchBook PrimaryIndustryGroup → canonical ────────────────────────

PB_GROUP_TO_CANONICAL: dict[str, str | None] = {
    # Software & IT
    "Software":                             "Software & IT",
    "IT Services":                          "Software & IT",
    "Communications and Networking":        "Software & IT",

    # Healthcare
    "Healthcare Services":                  "Healthcare",
    "Healthcare Devices and Supplies":      "Healthcare",
    "Healthcare Technology Systems":        "Healthcare",

    # Biotech & Pharma
    "Pharmaceuticals and Biotechnology":    "Biotech & Pharma",

    # Financial Services
    "Other Financial Services":             "Financial Services",
    "Capital Markets/Institutions":         "Financial Services",
    "Insurance":                            "Financial Services",

    # E-commerce & Retail
    "Retail":                               "E-commerce & Retail",
    "Consumer Non-Durables":                "E-commerce & Retail",
    "Consumer Durables":                    "E-commerce & Retail",
    "Apparel and Accessories":              "E-commerce & Retail",

    # Media & Marketing
    "Media":                                "Media & Marketing",

    # Education
    "Education":                            "Education",

    # Energy & CleanTech
    "Other Energy":                         "Energy & CleanTech",
    "Exploration, Production and Refining": "Energy & CleanTech",
    "Environmental Services":               "Energy & CleanTech",

    # Hardware & Manufacturing
    "Computer Hardware":                    "Hardware & Manufacturing",
    "Commercial Products":                  "Hardware & Manufacturing",
    "Metals, Minerals and Mining":          "Hardware & Manufacturing",
    "Chemicals and Gases":                  "Hardware & Manufacturing",

    # Transportation
    "Transportation":                       "Transportation",
    "Commercial Transportation":            "Transportation",

    # Real Estate
    "Real Estate":                          "Real Estate",

    # Food & AgTech
    "Food and Beverage":                    "Food & AgTech",
    "Agriculture":                          "Food & AgTech",

    # Professional Services
    "Commercial Services":                  "Professional Services",
    "Services (Non-Financial)":             "Professional Services",
    "Government":                           "Professional Services",

    # Consumer & Lifestyle
    "Restaurants, Hotels and Leisure":      "Consumer & Lifestyle",

    # Skip — too vague
    "Other Business Products and Services": None,
}


def map_cb_categories(raw: str | None) -> list[str]:
    """Map a CB category_groups_list string to canonical verticals (deduped, ordered)."""
    if not raw:
        return []
    seen: dict[str, None] = {}
    for group in raw.split(","):
        canonical = CB_TO_CANONICAL.get(group.strip())
        if canonical and canonical not in seen:
            seen[canonical] = None
    return list(seen)


def map_pb_category(group: str | None) -> list[str]:
    """Map a PB PrimaryIndustryGroup string to canonical verticals."""
    if not group:
        return []
    canonical = PB_GROUP_TO_CANONICAL.get(group.strip())
    return [canonical] if canonical else []
