#!/usr/bin/env python3
"""
Geocode Startup Locations
Adds latitude/longitude coordinates to existing startups
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database.connection import get_db_session
from backend.database.models import Startup
from decimal import Decimal


# Comprehensive location coordinates database
LOCATION_COORDS = {
    # North America - Countries
    'USA': (37.0902, -95.7129),
    'United States': (37.0902, -95.7129),
    'US': (37.0902, -95.7129),
    'Canada': (56.1304, -106.3468),
    'Mexico': (23.6345, -102.5528),

    # North America - Cities
    'San Francisco': (37.7749, -122.4194),
    'SF': (37.7749, -122.4194),
    'New York': (40.7128, -74.0060),
    'NY': (40.7128, -74.0060),
    'Los Angeles': (34.0522, -118.2437),
    'LA': (34.0522, -118.2437),
    'Seattle': (47.6062, -122.3321),
    'Boston': (42.3601, -71.0589),
    'Austin': (30.2672, -97.7431),
    'Chicago': (41.8781, -87.6298),
    'Miami': (25.7617, -80.1918),
    'Denver': (39.7392, -104.9903),
    'Portland': (45.5152, -122.6784),
    'Toronto': (43.6532, -79.3832),
    'Vancouver': (49.2827, -123.1207),
    'Montreal': (45.5017, -73.5673),

    # Europe - Countries
    'UK': (55.3781, -3.4360),
    'United Kingdom': (55.3781, -3.4360),
    'England': (52.3555, -1.1743),
    'Germany': (51.1657, 10.4515),
    'France': (46.2276, 2.2137),
    'Spain': (40.4637, -3.7492),
    'Italy': (41.8719, 12.5674),
    'Netherlands': (52.1326, 5.2913),
    'Sweden': (60.1282, 18.6435),
    'Switzerland': (46.8182, 8.2275),
    'Austria': (47.5162, 14.5501),
    'Belgium': (50.5039, 4.4699),
    'Denmark': (56.2639, 9.5018),
    'Finland': (61.9241, 25.7482),
    'Norway': (60.4720, 8.4689),
    'Poland': (51.9194, 19.1451),
    'Ireland': (53.4129, -8.2439),
    'Portugal': (39.3999, -8.2245),

    # Europe - Cities
    'London': (51.5074, -0.1278),
    'Berlin': (52.5200, 13.4050),
    'Paris': (48.8566, 2.3522),
    'Amsterdam': (52.3676, 4.9041),
    'Stockholm': (59.3293, 18.0686),
    'Copenhagen': (55.6761, 12.5683),
    'Madrid': (40.4168, -3.7038),
    'Barcelona': (41.3851, 2.1734),
    'Rome': (41.9028, 12.4964),
    'Milan': (45.4642, 9.1900),
    'Zurich': (47.3769, 8.5417),
    'Brussels': (50.8503, 4.3517),
    'Vienna': (48.2082, 16.3738),
    'Munich': (48.1351, 11.5820),
    'Dublin': (53.3498, -6.2603),
    'Lisbon': (38.7223, -9.1393),
    'Helsinki': (60.1699, 24.9384),
    'Oslo': (59.9139, 10.7522),
    'Warsaw': (52.2297, 21.0122),

    # Asia - Countries
    'China': (35.8617, 104.1954),
    'India': (20.5937, 78.9629),
    'Japan': (36.2048, 138.2529),
    'South Korea': (35.9078, 127.7669),
    'Korea': (35.9078, 127.7669),
    'Singapore': (1.3521, 103.8198),
    'Indonesia': (-0.7893, 113.9213),
    'Thailand': (15.8700, 100.9925),
    'Vietnam': (14.0583, 108.2772),
    'Malaysia': (4.2105, 101.9758),
    'Philippines': (12.8797, 121.7740),
    'Taiwan': (23.6978, 120.9605),
    'Hong Kong': (22.3193, 114.1694),
    'Israel': (31.0461, 34.8516),
    'UAE': (23.4241, 53.8478),

    # Asia - Cities
    'Beijing': (39.9042, 116.4074),
    'Shanghai': (31.2304, 121.4737),
    'Shenzhen': (22.5431, 114.0579),
    'Hangzhou': (30.2741, 120.1551),
    'Mumbai': (19.0760, 72.8777),
    'Bangalore': (12.9716, 77.5946),
    'Delhi': (28.7041, 77.1025),
    'Hyderabad': (17.3850, 78.4867),
    'Tokyo': (35.6762, 139.6503),
    'Seoul': (37.5665, 126.9780),
    'Bangkok': (13.7563, 100.5018),
    'Ho Chi Minh': (10.8231, 106.6297),
    'Saigon': (10.8231, 106.6297),
    'Manila': (14.5995, 120.9842),
    'Jakarta': (6.2088, 106.8456),
    'Kuala Lumpur': (3.1390, 101.6869),
    'Tel Aviv': (32.0853, 34.7818),
    'Dubai': (25.2048, 55.2708),
    'Abu Dhabi': (24.4539, 54.3773),

    # Oceania
    'Australia': (-25.2744, 133.7751),
    'New Zealand': (-40.9006, 174.8860),
    'Sydney': (-33.8688, 151.2093),
    'Melbourne': (-37.8136, 144.9631),
    'Brisbane': (-27.4698, 153.0251),
    'Auckland': (-36.8485, 174.7633),

    # Latin America
    'Brazil': (-14.2350, -51.9253),
    'Argentina': (-38.4161, -63.6167),
    'Chile': (-35.6751, -71.5430),
    'Colombia': (4.5709, -74.2973),
    'Peru': (-9.1900, -75.0152),
    'Sao Paulo': (-23.5505, -46.6333),
    'Buenos Aires': (-34.6037, -58.3816),
    'Santiago': (-33.4489, -70.6693),
    'Bogota': (4.7110, -74.0721),
    'Lima': (-12.0464, -77.0428),

    # Africa
    'South Africa': (-30.5595, 22.9375),
    'Nigeria': (9.0820, 8.6753),
    'Kenya': (-0.0236, 37.9062),
    'Egypt': (26.8206, 30.8025),
    'Cape Town': (-33.9249, 18.4241),
    'Lagos': (6.5244, 3.3792),
    'Nairobi': (-1.2864, 36.8172),
    'Cairo': (30.0444, 31.2357),

    # Middle East
    'Saudi Arabia': (23.8859, 45.0792),
    'Turkey': (38.9637, 35.2433),
    'Iran': (32.4279, 53.6880),
    'Riyadh': (24.7136, 46.6753),
    'Istanbul': (41.0082, 28.9784),
    'Ankara': (39.9334, 32.8597),
}


def geocode_location(country, city):
    """Get lat/long for a location"""
    # Try city first (more specific)
    if city and city in LOCATION_COORDS:
        return LOCATION_COORDS[city]

    # Try country
    if country and country in LOCATION_COORDS:
        return LOCATION_COORDS[country]

    # Try case-insensitive match
    if city:
        for key, coords in LOCATION_COORDS.items():
            if key.lower() == city.lower():
                return coords

    if country:
        for key, coords in LOCATION_COORDS.items():
            if key.lower() == country.lower():
                return coords

    return None, None


def update_startup_coordinates(session):
    """Add lat/long to all startups missing coordinates"""
    print("\n🗺️  Geocoding startup locations...")

    # Get startups without coordinates
    startups = session.query(Startup).filter(
        (Startup.latitude == None) | (Startup.longitude == None)
    ).all()

    print(f"   Found {len(startups)} startups needing geocoding")

    updated_count = 0
    not_found_count = 0

    for startup in startups:
        lat, lon = geocode_location(startup.country, startup.city)

        if lat is not None and lon is not None:
            startup.latitude = Decimal(str(lat))
            startup.longitude = Decimal(str(lon))
            updated_count += 1

            if updated_count % 20 == 0:
                print(f"   ✅ Geocoded {updated_count} startups...")
        else:
            not_found_count += 1
            location = startup.city or startup.country or "Unknown"
            print(f"   ⚠️  No coordinates for: {startup.name} ({location})")

    session.commit()

    print(f"\n📊 Geocoding Summary:")
    print(f"   ✅ Updated: {updated_count}")
    print(f"   ❌ Not Found: {not_found_count}")

    return updated_count, not_found_count


def main():
    """Main geocoding function"""
    print("=" * 80)
    print("🌍 GEOCODING STARTUP LOCATIONS")
    print("=" * 80)

    with get_db_session() as session:
        updated, not_found = update_startup_coordinates(session)

    print("\n" + "=" * 80)
    print("✨ GEOCODING COMPLETE!")
    print("=" * 80)

    if updated > 0:
        print("\n✅ Startups now have coordinates for the map!")
        print("   Refresh your dashboard to see them plotted.")

    if not_found > 0:
        print(f"\n⚠️  {not_found} locations couldn't be geocoded.")
        print("   You can add them to LOCATION_COORDS in this script.")

    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
