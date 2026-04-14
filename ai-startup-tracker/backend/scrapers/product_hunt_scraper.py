"""
Product Hunt scraper
Scrapes new AI-related products from Product Hunt
"""
from typing import List, Dict
from loguru import logger
import asyncio
from datetime import datetime

from .base_scraper import BaseScraper
from ..database.models import DataSource


class ProductHuntScraper(BaseScraper):
    """Scraper for Product Hunt new products"""

    def __init__(self):
        super().__init__(DataSource.PRODUCT_HUNT)
        self.api_base = "https://api.producthunt.com/v2/api/graphql"

    async def scrape(self) -> List[Dict]:
        """
        Scrape Product Hunt for new AI products

        Returns:
            List of scraped product data
        """
        logger.info("Starting Product Hunt scraping...")
        job_id = self.create_scraping_job("product_hunt")

        results = []
        try:
            # Note: Product Hunt requires OAuth authentication
            # For this example, we'll use their public data
            products = await self._scrape_product_hunt_page()

            for product in products:
                url = product.get('url')
                if not url or self.is_url_already_scraped(url):
                    continue

                # Fetch the product's landing page
                html = await self.fetch_url(url)

                if html:
                    text = self.extract_text_from_html(html)

                    # Check if AI-related
                    description = product.get('tagline', '') + ' ' + text
                    if self.is_ai_related_url(url, description):
                        result = {
                            'url': url,
                            'domain': self.extract_domain(url),
                            'name': product.get('name'),
                            'description': product.get('tagline'),
                            'landing_page_text': text,
                            'source': self.source,
                            'source_url': product.get('product_hunt_url'),
                            'upvotes': product.get('votes_count', 0),
                            'launch_date': product.get('featured_at'),
                            'tags': product.get('topics', [])
                        }
                        results.append(result)
                        await self.mark_url_scraped(url, "success")
                        logger.info(f"Successfully scraped Product Hunt product: {product.get('name')}")
                    else:
                        await self.mark_url_scraped(url, "skipped", "Not AI-related")
                else:
                    await self.mark_url_scraped(url, "failed", "Could not fetch page")

                await asyncio.sleep(1)  # Rate limiting

                if len(results) >= self.settings.MAX_SCRAPED_ITEMS_PER_RUN:
                    break

            self.update_scraping_job(job_id, "completed", len(products), len(results))
            logger.info(f"Product Hunt scraping completed: {len(results)} AI products found")

        except Exception as e:
            logger.error(f"Product Hunt scraping failed: {e}")
            self.update_scraping_job(job_id, "failed", error=str(e))

        return results

    async def _scrape_product_hunt_page(self) -> List[Dict]:
        """
        Scrape Product Hunt page directly (without API)

        Note: In production, use Product Hunt API with proper authentication

        Returns:
            List of product data
        """
        products = []

        try:
            # Scrape the main page
            url = "https://www.producthunt.com/"
            html = await self.fetch_url(url)

            if not html:
                return products

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            # Find product cards (structure may change)
            # This is a simplified example
            product_links = soup.find_all('a', href=lambda x: x and '/posts/' in x)

            for link in product_links[:50]:  # Limit to 50 products
                product_url = 'https://www.producthunt.com' + link['href']
                products.append({
                    'product_hunt_url': product_url,
                    'name': link.get_text(strip=True)
                })

            # For each product, scrape details
            for product in products[:20]:  # Limit detail scraping
                details = await self._scrape_product_details(product['product_hunt_url'])
                product.update(details)

        except Exception as e:
            logger.error(f"Failed to scrape Product Hunt page: {e}")

        return products

    async def _scrape_product_details(self, product_url: str) -> Dict:
        """
        Scrape individual product details from Product Hunt

        Args:
            product_url: Product Hunt product URL

        Returns:
            Product details dictionary
        """
        try:
            html = await self.fetch_url(product_url)
            if not html:
                return {}

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            # Extract product website URL
            website_link = soup.find('a', {'data-test': 'post-cta-link'})
            url = website_link['href'] if website_link else None

            # Extract tagline
            tagline = soup.find('h2')
            tagline_text = tagline.get_text(strip=True) if tagline else ""

            # Extract topics/tags
            topics = []
            topic_elements = soup.find_all('a', href=lambda x: x and '/topics/' in x)
            for topic in topic_elements:
                topics.append(topic.get_text(strip=True))

            return {
                'url': url,
                'tagline': tagline_text,
                'topics': topics,
                'featured_at': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to scrape product details: {e}")
            return {}

    async def _use_product_hunt_api(self, api_token: str) -> List[Dict]:
        """
        Example implementation using Product Hunt GraphQL API

        Args:
            api_token: Product Hunt API token

        Returns:
            List of products
        """
        # GraphQL query for today's products
        query = """
        query {
          posts(order: NEWEST) {
            edges {
              node {
                id
                name
                tagline
                url
                votesCount
                featuredAt
                topics {
                  edges {
                    node {
                      name
                    }
                  }
                }
              }
            }
          }
        }
        """

        headers = {
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json'
        }

        try:
            response = await self.session.post(
                self.api_base,
                json={'query': query},
                headers=headers
            )
            data = response.json()

            products = []
            for edge in data.get('data', {}).get('posts', {}).get('edges', []):
                node = edge['node']
                products.append({
                    'name': node['name'],
                    'url': node['url'],
                    'tagline': node['tagline'],
                    'votes_count': node['votesCount'],
                    'featured_at': node['featuredAt'],
                    'topics': [t['node']['name'] for t in node['topics']['edges']],
                    'product_hunt_url': f"https://www.producthunt.com/posts/{node['id']}"
                })

            return products

        except Exception as e:
            logger.error(f"Failed to use Product Hunt API: {e}")
            return []
