#!/usr/bin/env python3
"""
Fix Startup Locations
- Add default locations for startups without location data
- Extract locations from descriptions
- Set coordinates for mapping
"""
import sys
import os
from pathlib import Path
import re
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database.connection import get_db_session
from backend.database.models import Startup

# Location extraction patterns
CITY_PATTERNS = {
    r'\b(San Francisco|SF)\b': ('USA', 'San Francisco', 37.7749, -122.4194),
    r'\b(New York|NYC|NY)\b': ('USA', 'New York', 40.7128, -74.0060),
    r'\b(Los Angeles|LA)\b': ('USA', 'Los Angeles', 34.0522, -118.2437),
    r'\b(Seattle)\b': ('USA', 'Seattle', 47.6062, -122.3321),
    r'\b(Boston)\b': ('USA', 'Boston', 42.3601, -71.0589),
    r'\b(Austin)\b': ('USA', 'Austin', 30.2672, -97.7431),
    r'\b(Chicago)\b': ('USA', 'Chicago', 41.8781, -87.6298),
    r'\b(London)\b': ('UK', 'London', 51.5074, -0.1278),
    r'\b(Berlin)\b': ('Germany', 'Berlin', 52.5200, 13.4050),
    r'\b(Paris)\b': ('France', 'Paris', 48.8566, 2.3522),
    r'\b(Singapore)\b': ('Singapore', 'Singapore', 1.3521, 103.8198),
    r'\b(Bangalore)\b': ('India', 'Bangalore', 12.9716, 77.5946),
    r'\b(Beijing)\b': ('China', 'Beijing', 39.9042, 116.4074),
    r'\b(Shanghai)\b': ('China', 'Shanghai', 31.2304, 121.4737),
    r'\b(Tokyo)\b': ('Japan', 'Tokyo', 35.6762, 139.6503),
    r'\b(Seoul)\b': ('South Korea', 'Seoul', 37.5665, 126.9780),
    r'\b(Tel Aviv)\b': ('Israel', 'Tel Aviv', 32.0853, 34.7818),
    r'\b(Toronto)\b': ('Canada', 'Toronto', 43.6532, -79.3832),
    r'\b(Sydney)\b': ('Australia', 'Sydney', -33.8688, 151.2093),
    r'\b(Amsterdam)\b': ('Netherlands', 'Amsterdam', 52.3676, 4.9041),
}

# Default location for tech startups (Silicon Valley)
DEFAULT_LOCATION = ('USA', 'San Francisco', 37.7749, -122.4194)


def extract_location_from_text(text):
    """Try to extract location from description or landing page text"""
    if not text:
        return None

    text_lower = text.lower()

    # Try to find city mentions
    for pattern, (country, city, lat, lon) in CITY_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return country, city, lat, lon

    return None


def fix_startup_locations(session):
    """Add locations to startups without location data"""
    print("\n🗺️  Fixing startup locations...")

    # Get startups without location
    startups = session.query(Startup).filter(
        (Startup.country == None) | (Startup.city == None)
    ).all()

    print(f"   Found {len(startups)} startups without locations")

    extracted_count = 0
    default_count = 0

    for startup in startups:
        # Try to extract from description
        location_data = extract_location_from_text(startup.description)
        if not location_data:
            location_data = extract_location_from_text(startup.landing_page_text)

        if location_data:
            # Found location in text!
            country, city, lat, lon = location_data
            startup.country = country
            startup.city = city
            startup.latitude = Decimal(str(lat))
            startup.longitude = Decimal(str(lon))
            extracted_count += 1
        else:
            # Use default (Silicon Valley for tech startups)
            country, city, lat, lon = DEFAULT_LOCATION
            startup.country = country
            startup.city = city
            startup.latitude = Decimal(str(lat))
            startup.longitude = Decimal(str(lon))
            default_count += 1

        if (extracted_count + default_count) % 20 == 0:
            print(f"   ✅ Processed {extracted_count + default_count} startups...")

    session.commit()

    print(f"\n📊 Location Fix Summary:")
    print(f"   ✅ Extracted from text: {extracted_count}")
    print(f"   🏢 Default (SF): {default_count}")

    return extracted_count, default_count


def main():
    """Main location fix function"""
    print("=" * 80)
    print("🌍 FIXING STARTUP LOCATIONS")
    print("=" * 80)
    print("\nThis script will:")
    print("  1. Extract locations from startup descriptions")
    print("  2. Set default location (San Francisco) for unknown startups")
    print("  3. Add coordinates for map visualization")
    print()

    with get_db_session() as session:
        extracted, defaulted = fix_startup_locations(session)

    print("\n" + "=" * 80)
    print("✨ LOCATION FIX COMPLETE!")
    print("=" * 80)

    total = extracted + defaulted
    if total > 0:
        print(f"\n✅ Updated {total} startups with locations!")
        print("   📊 Your dashboard map will now show:")
        if extracted > 0:
            print(f"      - {extracted} with extracted locations")
        if defaulted > 0:
            print(f"      - {defaulted} with default location (San Francisco)")
        print("\n   🔄 Refresh your dashboard to see them on the map!")

    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
