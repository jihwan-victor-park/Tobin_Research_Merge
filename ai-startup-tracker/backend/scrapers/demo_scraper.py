"""
Demo scraper that reads URLs from demo_urls.txt
Perfect for demos without paid APIs - uses only free tools
"""
from typing import List, Dict
import requests
from bs4 import BeautifulSoup
from loguru import logger
import time
from urllib.parse import urlparse


class DemoScraper:
    """Scrape startups from a demo URL list file"""

    def __init__(self, demo_file: str = "demo_urls.txt"):
        self.demo_file = demo_file
        self.source = "demo_list"

    def _extract_company_name(self, url: str, soup: BeautifulSoup) -> str:
        """Extract company name from URL or page title"""
        # Try to get from page title
        title = soup.find('title')
        if title:
            title_text = title.get_text().strip()
            # Clean up common patterns
            for suffix in [' - ', ' | ', ' – ']:
                if suffix in title_text:
                    title_text = title_text.split(suffix)[0]
            return title_text

        # Fallback to domain name
        domain = urlparse(url).netloc
        name = domain.replace('www.', '').split('.')[0]
        return name.title()

    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract description from meta tags or first paragraph"""
        # Try meta description
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            return meta_desc['content'].strip()

        meta_og_desc = soup.find('meta', {'property': 'og:description'})
        if meta_og_desc and meta_og_desc.get('content'):
            return meta_og_desc['content'].strip()

        # Try first paragraph
        first_p = soup.find('p')
        if first_p:
            return first_p.get_text().strip()[:300]

        return ""

    def _scrape_single_url(self, url: str) -> Dict:
        """Scrape a single URL and extract startup info"""
        try:
            logger.info(f"📥 Scraping: {url}")

            # Request the page
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract text content (remove scripts and styles)
            for script in soup(["script", "style"]):
                script.decompose()

            text_content = soup.get_text(separator='\n', strip=True)

            # Extract metadata
            name = self._extract_company_name(url, soup)
            description = self._extract_description(soup)

            result = {
                'name': name,
                'url': url,
                'description': description,
                'landing_page_text': text_content[:5000],  # First 5000 chars
                'source': self.source,
                'founder_names': []
            }

            logger.info(f"✅ Scraped: {name}")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to scrape {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error processing {url}: {e}")
            return None

    async def scrape(self) -> List[Dict]:
        """
        Read URLs from demo_urls.txt and scrape each one

        Returns:
            List of startup dictionaries
        """
        logger.info(f"🚀 Demo Scraper: Reading URLs from {self.demo_file}")

        try:
            # Read URLs from file
            with open(self.demo_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Filter out comments and empty lines
            urls = [
                line.strip()
                for line in lines
                if line.strip() and not line.strip().startswith('#')
            ]

            logger.info(f"📋 Found {len(urls)} URLs to scrape")

            results = []
            for i, url in enumerate(urls, 1):
                logger.info(f"[{i}/{len(urls)}] Processing {url}")

                result = self._scrape_single_url(url)
                if result:
                    results.append(result)

                # Be polite - add small delay between requests
                time.sleep(1)

            logger.info(f"✅ Demo scraping complete: {len(results)} startups collected")

            return results

        except FileNotFoundError:
            logger.error(f"❌ Demo file not found: {self.demo_file}")
            logger.info("Create a demo_urls.txt file with one URL per line")
            return []

        except Exception as e:
            logger.error(f"❌ Demo scraper failed: {e}")
            return []


async def run_demo_scraper() -> List[Dict]:
    """
    Convenience function to run demo scraper

    Returns:
        List of scraped startups
    """
    scraper = DemoScraper()
    return await scraper.scrape()


if __name__ == "__main__":
    import asyncio

    async def main():
        results = await run_demo_scraper()
        print(f"\n📊 Results: {len(results)} startups")
        for r in results:
            print(f"  - {r['name']}: {r['url']}")

    asyncio.run(main())
