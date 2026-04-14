"""
Domain registration scraper
Tracks new .ai domain registrations and validates them
"""
from typing import List, Dict, Optional
from loguru import logger
from datetime import datetime, timedelta
import asyncio

from .base_scraper import BaseScraper
from ..database.models import DataSource


class DomainScraper(BaseScraper):
    """Scraper for newly registered domains (especially .ai domains)"""

    def __init__(self):
        super().__init__(DataSource.DOMAIN_REGISTRATION)
        # You would need to integrate with a domain registration API
        # For now, we'll use a placeholder approach

    async def scrape(self) -> List[Dict]:
        """
        Scrape newly registered domains

        Note: In production, you would integrate with services like:
        - WhoisXML API (newlyRegisteredDomains endpoint)
        - DomainTools API
        - Or scrape from domain registration marketplaces

        Returns:
            List of scraped domain data
        """
        logger.info("Starting domain scraping...")
        job_id = self.create_scraping_job("domain_registration")

        results = []
        try:
            # Get recently registered .ai domains
            domains = await self._get_new_ai_domains()

            for domain_data in domains:
                domain = domain_data['domain']
                url = f"https://{domain}"

                # Skip if already scraped
                if self.is_url_already_scraped(url):
                    continue

                # Fetch the landing page
                html = await self.fetch_url(url)

                if html:
                    text = self.extract_text_from_html(html)

                    # Quick filter: only include if AI-related
                    if self.is_ai_related_url(url, text):
                        result = {
                            'url': url,
                            'domain': domain,
                            'name': self._extract_company_name(html, domain),
                            'landing_page_text': text,
                            'source': self.source,
                            'registration_date': domain_data.get('registration_date'),
                            'raw_html': html[:1000]  # Store first 1000 chars for debugging
                        }
                        results.append(result)
                        await self.mark_url_scraped(url, "success")
                        logger.info(f"Successfully scraped domain: {domain}")
                    else:
                        await self.mark_url_scraped(url, "skipped", "Not AI-related")
                        logger.debug(f"Skipped non-AI domain: {domain}")
                else:
                    await self.mark_url_scraped(url, "failed", "Could not fetch page")

                # Rate limiting
                await asyncio.sleep(0.5)

                # Limit per run
                if len(results) >= self.settings.MAX_SCRAPED_ITEMS_PER_RUN:
                    break

            self.update_scraping_job(job_id, "completed", len(domains), len(results))
            logger.info(f"Domain scraping completed: {len(results)} AI-related domains found")

        except Exception as e:
            logger.error(f"Domain scraping failed: {e}")
            self.update_scraping_job(job_id, "failed", error=str(e))

        return results

    async def _get_new_ai_domains(self) -> List[Dict]:
        """
        Get newly registered .ai domains

        In production, integrate with domain registration APIs.
        This is a placeholder implementation.

        Returns:
            List of domain data dictionaries
        """
        # Placeholder: In real implementation, call domain registration API
        # Example with WhoisXML API:
        # https://newly-registered-domains.whoisxmlapi.com/api/v1

        # For demonstration, return sample domains
        # In production, replace with actual API call
        sample_domains = [
            {
                'domain': 'example-ai-startup.ai',
                'registration_date': (datetime.now() - timedelta(days=2)).isoformat()
            }
        ]

        logger.warning("Using placeholder domain list. Integrate with domain registration API in production.")
        return []  # Return empty to avoid placeholder data

    async def _get_domains_from_api(self, api_key: str = None) -> List[Dict]:
        """
        Example integration with WhoisXML API

        Args:
            api_key: API key for WhoisXML

        Returns:
            List of newly registered domains
        """
        # Example implementation (requires WhoisXML API key)
        try:
            from datetime import date
            today = date.today()
            url = f"https://newly-registered-domains.whoisxmlapi.com/api/v1"

            params = {
                'apiKey': api_key or self.settings.WHOISXML_API_KEY,
                'date': today.isoformat(),
                'tlds': 'ai',  # Focus on .ai domains
                'mode': 'preview'  # or 'purchase' for full data
            }

            response = await self.session.get(url, params=params)
            data = response.json()

            domains = []
            for item in data.get('domainsList', []):
                domains.append({
                    'domain': item['domainName'],
                    'registration_date': item['firstSeen']
                })

            return domains

        except Exception as e:
            logger.error(f"Failed to fetch domains from API: {e}")
            return []

    def _extract_company_name(self, html: str, domain: str) -> str:
        """
        Extract company name from HTML

        Args:
            html: HTML content
            domain: Domain name as fallback

        Returns:
            Company name
        """
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            # Try various methods to find company name
            # 1. Look for og:site_name meta tag
            og_site = soup.find('meta', property='og:site_name')
            if og_site and og_site.get('content'):
                return og_site['content'].strip()

            # 2. Look for title tag
            title = soup.find('title')
            if title:
                # Clean up common patterns
                name = title.string.strip()
                name = name.split('|')[0].strip()
                name = name.split('-')[0].strip()
                return name

            # 3. Look for h1 with company name class
            h1 = soup.find('h1', class_=['company-name', 'brand', 'logo-text'])
            if h1:
                return h1.get_text().strip()

            # Fallback: use domain name
            return domain.replace('.ai', '').replace('-', ' ').title()

        except Exception as e:
            logger.error(f"Failed to extract company name: {e}")
            return domain
