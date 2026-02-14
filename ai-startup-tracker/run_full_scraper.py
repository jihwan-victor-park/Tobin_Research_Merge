#!/usr/bin/env python3
"""
Run the Full Global Scraper with all 12+ sources
This bypasses database requirements for standalone scraping
"""
import sys
from pathlib import Path

# Prevent database imports
sys.path.insert(0, str(Path(__file__).parent))

# Direct import of aggregator scraper
from backend.scrapers.aggregator_scraper import AggregatorScraper
import json


def main():
    """Run full global scraper"""
    print("\n🌍 Starting Full Global Scraper with 12+ sources...")
    print("⏳ This will take 5-10 minutes to complete.\n")

    # Initialize and run scraper
    scraper = AggregatorScraper()
    results = scraper.scrape_all()

    # Save results
    output_dir = Path(__file__).parent / "data"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "global_startups_full.json"

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Analysis
    print("\n" + "=" * 80)
    print("📊 DETAILED ANALYSIS")
    print("=" * 80)

    # Source breakdown
    sources = {}
    for r in results:
        source = r.get('source', 'Unknown')
        sources[source] = sources.get(source, 0) + 1

    print("\n📋 Breakdown by Source:")
    for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
        print(f"   {source:.<40} {count:>3} startups")

    # Regional breakdown
    asia_keywords = ['China', 'India', 'Japan', 'Korea', 'Singapore', 'Asia',
                     'Indonesia', 'Vietnam', 'Thailand', 'Malaysia', 'Philippines',
                     'Taiwan', 'Hong Kong']
    europe_keywords = ['UK', 'Germany', 'France', 'Spain', 'Italy', 'Netherlands',
                       'Sweden', 'Europe', 'Finland', 'Denmark', 'Belgium', 'Austria',
                       'Switzerland', 'Poland', 'Ireland', 'Portugal']

    asia_count = sum(1 for r in results if r.get('location') and
                    any(k in str(r.get('location', '')) for k in asia_keywords))
    europe_count = sum(1 for r in results if r.get('location') and
                      any(k in str(r.get('location', '')) for k in europe_keywords))

    print("\n🌍 Regional Distribution:")
    print(f"   🌏 Asia:              {asia_count:>3} startups")
    print(f"   🇪🇺 Europe:           {europe_count:>3} startups")
    print(f"   🌎 Americas & Other:  {len(results) - asia_count - europe_count:>3} startups")

    # Samples
    print("\n" + "=" * 80)
    print("🎯 SAMPLE STARTUPS (First 10)")
    print("=" * 80)
    for i, startup in enumerate(results[:10], 1):
        print(f"\n{i}. {startup['name']}")
        print(f"   Source: {startup['source']}")
        print(f"   Location: {startup.get('location', 'Not specified')}")
        print(f"   Description: {startup['description'][:100]}...")

    print("\n" + "=" * 80)
    print("✨ SCRAPING COMPLETE!")
    print("=" * 80)
    print(f"📊 Total: {len(results)} startups from {len(sources)} sources")
    print(f"💾 Data saved to: {output_file}")
    print("=" * 80)

    # Goal check
    if len(results) >= 50:
        print(f"\n🎉 SUCCESS! Collected {len(results)} startups (goal: 50+)")
    else:
        print(f"\n⚠️  Collected {len(results)} startups (goal: 50+)")
        print("💡 Some sources may have failed. Check logs above for details.")

    print("\n🚀 Ready to analyze your global startup data!")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Scraping interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Check your internet connection")
        print("2. Some websites may be blocking scrapers")
        print("3. Try running: pip install loguru")
        sys.exit(1)
