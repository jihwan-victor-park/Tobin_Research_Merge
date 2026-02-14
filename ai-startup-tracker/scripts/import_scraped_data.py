#!/usr/bin/env python3
"""
Import Scraped Data into Database
Bridges the gap between JSON scraper output and the database
"""
import sys
import os
from pathlib import Path
import json
from urllib.parse import urlparse
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database.connection import get_db_session, init_db
from backend.database.models import Startup, DataSource, StartupStatus, ReviewStatus
from sqlalchemy import text


def extract_domain(url):
    """Extract domain from URL"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except:
        return url[:100]  # Fallback


def map_source_to_enum(source_text):
    """Map scraper source names to DataSource enum"""
    source_mapping = {
        'Hacker News': DataSource.HACKERNEWS,
        'GitHub Trending': DataSource.GITHUB,
        'GitHub': DataSource.GITHUB,
        'Product Hunt': DataSource.PRODUCT_HUNT,
        'Y Combinator': DataSource.YC,
        'Y Combinator (Asia)': DataSource.YC,
        'TechCrunch': DataSource.HACKERNEWS,  # Use HACKERNEWS as fallback for news
        'Crunchbase': DataSource.HACKERNEWS,
        'Tech in Asia': DataSource.HACKERNEWS,
        'EU-Startups': DataSource.HACKERNEWS,
        'Indie Hackers': DataSource.HACKERNEWS,
        'F6S': DataSource.HACKERNEWS,
        'BetaList': DataSource.BETALIST,
    }
    return source_mapping.get(source_text, DataSource.HACKERNEWS)


def parse_location(location_text):
    """Parse location text into country and city"""
    if not location_text:
        return None, None

    # Simple parsing - can be enhanced
    parts = location_text.split(',')
    if len(parts) >= 2:
        city = parts[0].strip()
        country = parts[-1].strip()
        return country, city
    else:
        # Just country
        return location_text.strip(), None


def import_json_file(json_path, session):
    """Import startups from JSON file into database"""
    print(f"\n📂 Loading data from: {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"   Found {len(data)} startups in file")

    added_count = 0
    skipped_count = 0
    error_count = 0

    for idx, item in enumerate(data, 1):
        try:
            # Check if URL already exists
            url = item.get('url', '')
            if not url:
                print(f"   ⚠️  Skipping item {idx}: No URL")
                skipped_count += 1
                continue

            existing = session.query(Startup).filter(Startup.url == url).first()
            if existing:
                skipped_count += 1
                continue

            # Extract domain
            domain = extract_domain(url)

            # Map source
            source_text = item.get('source', 'Unknown')
            source_enum = map_source_to_enum(source_text)

            # Parse location
            location = item.get('location')
            country, city = parse_location(location)

            # Create startup record
            startup = Startup(
                name=item.get('name', 'Unknown')[:255],
                url=url[:512],
                domain=domain[:255],
                description=item.get('description', '')[:5000],
                source=source_enum,
                source_url=url[:512],

                # Location
                country=country[:100] if country else None,
                city=city[:100] if city else None,

                # Metadata
                discovered_date=datetime.utcnow(),
                status=StartupStatus.ACTIVE,
                review_status=ReviewStatus.PENDING,

                # Scores (set defaults, will be analyzed later)
                relevance_score=0.75,  # Default medium relevance
                confidence_score=0.70,  # Default medium confidence
                emergence_score=50.0,  # Default medium emergence

                # Additional data
                landing_page_text=item.get('landing_page_text', '')[:10000],
                founder_names=item.get('founder_names', []),

                # Store original source in metadata
                extra_metadata={
                    'original_source': source_text,
                    'launch_date': item.get('launch_date'),
                    'scraped_at': datetime.utcnow().isoformat()
                }
            )

            session.add(startup)
            added_count += 1

            # Commit in batches
            if added_count % 50 == 0:
                session.commit()
                print(f"   ✅ Imported {added_count} startups...")

        except Exception as e:
            print(f"   ❌ Error importing item {idx}: {e}")
            error_count += 1
            continue

    # Final commit
    session.commit()

    print(f"\n📊 Import Summary:")
    print(f"   ✅ Added: {added_count}")
    print(f"   ⏭️  Skipped (duplicates): {skipped_count}")
    print(f"   ❌ Errors: {error_count}")

    return added_count, skipped_count, error_count


def main():
    """Main import function"""
    print("=" * 80)
    print("📥 IMPORTING SCRAPED DATA INTO DATABASE")
    print("=" * 80)

    # Initialize database
    print("\n🔧 Initializing database...")
    try:
        init_db()
        print("   ✅ Database initialized")
    except Exception as e:
        print(f"   ⚠️  Database already initialized or error: {e}")

    # Find JSON files
    data_dir = Path(__file__).parent.parent / "data"
    json_files = [
        data_dir / "global_startups_full.json",
        data_dir / "test_results.json",
        data_dir / "global_startups.json",
    ]

    total_added = 0
    total_skipped = 0
    total_errors = 0

    with get_db_session() as session:
        for json_file in json_files:
            if json_file.exists():
                print(f"\n{'='*80}")
                print(f"Processing: {json_file.name}")
                print('='*80)

                added, skipped, errors = import_json_file(json_file, session)
                total_added += added
                total_skipped += skipped
                total_errors += errors
            else:
                print(f"\n⚠️  File not found: {json_file.name}")

    # Final summary
    print("\n" + "=" * 80)
    print("🎉 IMPORT COMPLETE!")
    print("=" * 80)
    print(f"📊 Overall Summary:")
    print(f"   ✅ Total Added: {total_added}")
    print(f"   ⏭️  Total Skipped: {total_skipped}")
    print(f"   ❌ Total Errors: {total_errors}")
    print("=" * 80)

    if total_added > 0:
        print("\n✨ Your dashboard is now ready!")
        print("Run: streamlit run frontend/dashboard.py")
    else:
        print("\n⚠️  No new startups were added.")
        print("This might mean:")
        print("  - All startups were already in the database")
        print("  - No JSON files found in data/ directory")
        print("  - Run the scraper first: python run_full_scraper.py")

    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Import interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
