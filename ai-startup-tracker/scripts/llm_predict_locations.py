#!/usr/bin/env python3
"""
LLM-Powered Location Prediction
Uses Groq LLM to intelligently predict startup locations from descriptions
"""
import sys
import os
from pathlib import Path
import re
from decimal import Decimal
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database.connection import get_db_session
from backend.database.models import Startup
from backend.intelligence.llm_analyzer import get_llm_analyzer
from backend.config import get_settings

# Comprehensive location coordinates
LOCATION_COORDS = {
    # North America
    'USA': (37.0902, -95.7129), 'United States': (37.0902, -95.7129),
    'San Francisco': (37.7749, -122.4194), 'New York': (40.7128, -74.0060),
    'Los Angeles': (34.0522, -118.2437), 'Seattle': (47.6062, -122.3321),
    'Boston': (42.3601, -71.0589), 'Austin': (30.2672, -97.7431),
    'Chicago': (41.8781, -87.6298), 'Toronto': (43.6532, -79.3832),
    'Canada': (56.1304, -106.3468),

    # Europe
    'UK': (55.3781, -3.4360), 'United Kingdom': (55.3781, -3.4360),
    'London': (51.5074, -0.1278), 'Berlin': (52.5200, 13.4050),
    'Paris': (48.8566, 2.3522), 'Amsterdam': (52.3676, 4.9041),
    'Germany': (51.1657, 10.4515), 'France': (46.2276, 2.2137),
    'Netherlands': (52.1326, 5.2913), 'Stockholm': (59.3293, 18.0686),
    'Sweden': (60.1282, 18.6435), 'Switzerland': (46.8182, 8.2275),
    'Spain': (40.4637, -3.7492), 'Italy': (41.8719, 12.5674),

    # Asia
    'China': (35.8617, 104.1954), 'India': (20.5937, 78.9629),
    'Japan': (36.2048, 138.2529), 'Singapore': (1.3521, 103.8198),
    'South Korea': (35.9078, 127.7669), 'Korea': (35.9078, 127.7669),
    'Beijing': (39.9042, 116.4074), 'Shanghai': (31.2304, 121.4737),
    'Bangalore': (12.9716, 77.5946), 'Mumbai': (19.0760, 72.8777),
    'Delhi': (28.7041, 77.1025), 'Tokyo': (35.6762, 139.6503),
    'Seoul': (37.5665, 126.9780), 'Hong Kong': (22.3193, 114.1694),
    'Taiwan': (23.6978, 120.9605), 'Thailand': (15.8700, 100.9925),
    'Vietnam': (14.0583, 108.2772), 'Indonesia': (-0.7893, 113.9213),

    # Middle East
    'Israel': (31.0461, 34.8516), 'Tel Aviv': (32.0853, 34.7818),
    'Dubai': (25.2048, 55.2708), 'UAE': (23.4241, 53.8478),

    # Oceania
    'Australia': (-25.2744, 133.7751), 'Sydney': (-33.8688, 151.2093),
    'New Zealand': (-40.9006, 174.8860),

    # Latin America
    'Brazil': (-14.2350, -51.9253), 'Sao Paulo': (-23.5505, -46.6333),
    'Argentina': (-38.4161, -63.6167), 'Buenos Aires': (-34.6037, -58.3816),
    'Mexico': (23.6345, -102.5528),

    # Africa
    'South Africa': (-30.5595, 22.9375), 'Cape Town': (-33.9249, 18.4241),
    'Nigeria': (9.0820, 8.6753), 'Kenya': (-0.0236, 37.9062),
}


def predict_location_with_llm(llm_analyzer, startup):
    """Use LLM to predict startup location"""

    prompt = f"""Analyze this startup and predict its likely location (city and country).

Startup Information:
- Name: {startup.name}
- Description: {startup.description[:500]}
- URL: {startup.url}
- Source: {startup.source.value}

Consider:
1. Company name (geographic indicators, local references)
2. Description content (mentions of cities, regions, or local markets)
3. URL domain (.com vs .co.uk vs .de etc)
4. Source platform (GitHub, Hacker News, TechCrunch)
5. Industry patterns (e.g., fintech often in NYC/London, AI in SF/Beijing)

Respond with ONLY a JSON object in this exact format (no other text):
{{"city": "City Name", "country": "Country Name", "confidence": 0.X, "reasoning": "brief explanation"}}

If uncertain, default to major tech hubs: San Francisco, New York, London, Berlin, Singapore, Bangalore, Beijing.
"""

    try:
        response = llm_analyzer.analyze_with_llm(prompt, max_tokens=200)

        # Extract JSON from response
        json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return result.get('city'), result.get('country'), float(result.get('confidence', 0.5)), result.get('reasoning', '')
    except Exception as e:
        print(f"      ❌ LLM error: {e}")

    return None, None, 0.0, ""


def get_coordinates(city, country):
    """Get lat/long for location"""
    # Try city first
    if city and city in LOCATION_COORDS:
        return LOCATION_COORDS[city]

    # Try country
    if country and country in LOCATION_COORDS:
        return LOCATION_COORDS[country]

    # Try case-insensitive
    for key, coords in LOCATION_COORDS.items():
        if city and key.lower() == city.lower():
            return coords
        if country and key.lower() == country.lower():
            return coords

    # Default to San Francisco (tech hub)
    return (37.7749, -122.4194)


def predict_all_locations(session, llm_analyzer, limit=None):
    """Predict locations for all startups"""
    print("\n🤖 Using Groq LLM to predict startup locations...")

    # Get startups with default location (SF) - these need better predictions
    startups = session.query(Startup).filter(
        Startup.country == 'USA',
        Startup.city == 'San Francisco'
    ).all()

    if limit:
        startups = startups[:limit]

    print(f"   Found {len(startups)} startups to analyze")
    print(f"   Model: {llm_analyzer.model}")
    print()

    updated_count = 0
    failed_count = 0

    for idx, startup in enumerate(startups, 1):
        try:
            print(f"   [{idx}/{len(startups)}] Analyzing: {startup.name[:50]}...")

            city, country, confidence, reasoning = predict_location_with_llm(llm_analyzer, startup)

            if city and country and confidence > 0.5:
                # Get coordinates
                lat, lon = get_coordinates(city, country)

                # Update startup
                startup.city = city[:100]
                startup.country = country[:100]
                startup.latitude = Decimal(str(lat))
                startup.longitude = Decimal(str(lon))

                # Store reasoning in metadata
                if not startup.extra_metadata:
                    startup.extra_metadata = {}
                startup.extra_metadata['location_prediction'] = {
                    'city': city,
                    'country': country,
                    'confidence': confidence,
                    'reasoning': reasoning,
                    'method': 'llm'
                }

                updated_count += 1
                print(f"      ✅ Predicted: {city}, {country} (confidence: {confidence:.1%})")
                print(f"      💡 {reasoning[:100]}...")

                # Commit in batches
                if updated_count % 10 == 0:
                    session.commit()
                    print(f"\n   💾 Saved batch of 10 predictions...\n")
            else:
                failed_count += 1
                print(f"      ⚠️  Low confidence, keeping default")

        except Exception as e:
            print(f"      ❌ Error: {e}")
            failed_count += 1
            continue

    # Final commit
    session.commit()

    print(f"\n📊 LLM Prediction Summary:")
    print(f"   ✅ Updated: {updated_count}")
    print(f"   ⚠️  Failed/Low Confidence: {failed_count}")

    return updated_count, failed_count


def main():
    """Main LLM prediction function"""
    print("=" * 80)
    print("🤖 LLM-POWERED LOCATION PREDICTION")
    print("=" * 80)
    print("\nThis script uses Groq LLM to intelligently predict startup locations")
    print("based on company descriptions, names, and URLs.")
    print()

    # Check if API key is set
    try:
        settings = get_settings()
        if not settings.GROQ_API_KEY or settings.GROQ_API_KEY == 'dummy_key':
            print("❌ Error: GROQ_API_KEY not set in .env file")
            print("\nTo use LLM predictions:")
            print("  1. Get a free API key from: https://console.groq.com")
            print("  2. Add to .env file: GROQ_API_KEY=your_key_here")
            print("\nFor now, startups will keep their default locations.")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error loading settings: {e}")
        sys.exit(1)

    # Initialize LLM analyzer
    try:
        llm_analyzer = get_llm_analyzer()
        print(f"✅ Connected to Groq API")
        print(f"   Model: {llm_analyzer.model}")
    except Exception as e:
        print(f"❌ Error initializing LLM: {e}")
        sys.exit(1)

    # Ask for confirmation
    print("\n⚠️  Note: This will use Groq API credits (free tier: 30 req/min)")
    response = input("\nProceed with LLM prediction? (y/n): ")
    if response.lower() != 'y':
        print("Cancelled.")
        sys.exit(0)

    # Ask for limit
    limit_input = input("\nHow many startups to analyze? (Enter number or 'all'): ")
    limit = None if limit_input.lower() == 'all' else int(limit_input)

    print()

    with get_db_session() as session:
        updated, failed = predict_all_locations(session, llm_analyzer, limit)

    print("\n" + "=" * 80)
    print("✨ LLM PREDICTION COMPLETE!")
    print("=" * 80)

    if updated > 0:
        print(f"\n✅ Successfully predicted locations for {updated} startups!")
        print("   🗺️  Your dashboard map now shows more accurate locations")
        print("   🔄 Refresh your dashboard to see the updates")

    if failed > 0:
        print(f"\n⚠️  {failed} predictions failed or had low confidence")
        print("   These startups kept their default locations")

    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Prediction interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
