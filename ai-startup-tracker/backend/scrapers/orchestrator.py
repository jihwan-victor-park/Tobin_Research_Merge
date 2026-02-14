"""
Scraping orchestrator - manages all scrapers and schedules runs
"""
import asyncio
from typing import List, Dict
from loguru import logger
from datetime import datetime

from .domain_scraper import DomainScraper
from .product_hunt_scraper import ProductHuntScraper
from .yc_scraper import YCombinatorScraper
from .github_scraper import GithubScraper
from ..database.models import Startup, DataSource
from ..database.connection import get_db_session
from ..config import get_settings


class ScrapingOrchestrator:
    """Orchestrates all scraping operations"""

    def __init__(self):
        self.settings = get_settings()
        self.scrapers = [
            DomainScraper(),
            ProductHuntScraper(),
            YCombinatorScraper(),
            GithubScraper()
        ]

    async def run_all_scrapers(self) -> Dict[str, int]:
        """
        Run all scrapers in parallel

        Returns:
            Dictionary with scraping statistics
        """
        logger.info("Starting scraping orchestrator...")
        start_time = datetime.now()

        # Run all scrapers concurrently
        tasks = [scraper.scrape() for scraper in self.scrapers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        total_scraped = 0
        total_saved = 0
        stats = {}

        for scraper, result in zip(self.scrapers, results):
            scraper_name = scraper.__class__.__name__

            if isinstance(result, Exception):
                logger.error(f"{scraper_name} failed: {result}")
                stats[scraper_name] = {'error': str(result)}
            else:
                scraped_count = len(result)
                saved_count = await self._save_scraped_data(result)

                total_scraped += scraped_count
                total_saved += saved_count

                stats[scraper_name] = {
                    'scraped': scraped_count,
                    'saved': saved_count
                }
                logger.info(f"{scraper_name}: {scraped_count} scraped, {saved_count} saved")

        # Close all scrapers
        for scraper in self.scrapers:
            await scraper.close()

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Scraping completed in {elapsed:.2f}s. Total: {total_scraped} scraped, {total_saved} saved")

        return {
            'total_scraped': total_scraped,
            'total_saved': total_saved,
            'elapsed_seconds': elapsed,
            'scrapers': stats
        }

    async def _save_scraped_data(self, data: List[Dict]) -> int:
        """
        Save scraped data to database

        Args:
            data: List of scraped data dictionaries

        Returns:
            Number of items saved
        """
        saved_count = 0

        try:
            with get_db_session() as session:
                for item in data:
                    # Check if URL already exists
                    existing = session.query(Startup).filter(
                        Startup.url == item['url']
                    ).first()

                    if existing:
                        logger.debug(f"Startup already exists: {item['url']}")
                        continue

                    # Create new startup entry
                    startup = Startup(
                        name=item.get('name', ''),
                        url=item['url'],
                        domain=item['domain'],
                        description=item.get('description'),
                        landing_page_text=item.get('landing_page_text'),
                        source=item['source'],
                        source_url=item.get('source_url'),
                        discovered_date=datetime.now()
                    )

                    # Add optional fields
                    if 'founder_names' in item:
                        startup.founder_names = item['founder_names']

                    if 'tags' in item:
                        startup.primary_tags = item['tags']

                    session.add(startup)
                    saved_count += 1

                session.commit()

        except Exception as e:
            logger.error(f"Failed to save scraped data: {e}")

        return saved_count

    async def run_single_scraper(self, scraper_name: str) -> Dict:
        """
        Run a single scraper by name

        Args:
            scraper_name: Name of scraper class

        Returns:
            Scraping statistics
        """
        scraper_map = {
            'domain': DomainScraper(),
            'product_hunt': ProductHuntScraper(),
            'yc': YCombinatorScraper(),
            'github': GithubScraper()
        }

        scraper = scraper_map.get(scraper_name.lower())
        if not scraper:
            raise ValueError(f"Unknown scraper: {scraper_name}")

        logger.info(f"Running {scraper.__class__.__name__}...")

        result = await scraper.scrape()
        saved_count = await self._save_scraped_data(result)

        await scraper.close()

        return {
            'scraper': scraper.__class__.__name__,
            'scraped': len(result),
            'saved': saved_count
        }


async def main():
    """Main entry point for running scrapers"""
    orchestrator = ScrapingOrchestrator()
    stats = await orchestrator.run_all_scrapers()
    logger.info(f"Final stats: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
