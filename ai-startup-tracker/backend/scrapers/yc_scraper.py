"""
Y Combinator scraper
Scrapes new companies from YC's directory and launch posts
"""
from typing import List, Dict
from loguru import logger
import asyncio
from datetime import datetime

from .base_scraper import BaseScraper
from ..database.models import DataSource


class YCombinatorScraper(BaseScraper):
    """Scraper for Y Combinator companies"""

    def __init__(self):
        super().__init__(DataSource.YC)
        self.yc_directory_url = "https://www.ycombinator.com/companies"
        self.yc_launches_url = "https://www.ycombinator.com/launches"

    async def scrape(self) -> List[Dict]:
        """
        Scrape Y Combinator for new AI companies

        Returns:
            List of scraped company data
        """
        logger.info("Starting Y Combinator scraping...")
        job_id = self.create_scraping_job("yc")

        results = []
        try:
            # Scrape both directory and launches
            companies = await self._scrape_yc_directory()
            launches = await self._scrape_yc_launches()

            all_companies = companies + launches

            for company in all_companies:
                url = company.get('url')
                if not url or self.is_url_already_scraped(url):
                    continue

                # Fetch the company's landing page
                html = await self.fetch_url(url)

                if html:
                    text = self.extract_text_from_html(html)

                    # Check if AI-related
                    description = company.get('description', '') + ' ' + text
                    if self.is_ai_related_url(url, description):
                        result = {
                            'url': url,
                            'domain': self.extract_domain(url),
                            'name': company.get('name'),
                            'description': company.get('description'),
                            'landing_page_text': text,
                            'source': self.source,
                            'source_url': company.get('yc_url'),
                            'yc_batch': company.get('batch'),
                            'tags': company.get('tags', []),
                            'founder_names': company.get('founders', [])
                        }
                        results.append(result)
                        await self.mark_url_scraped(url, "success")
                        logger.info(f"Successfully scraped YC company: {company.get('name')}")
                    else:
                        await self.mark_url_scraped(url, "skipped", "Not AI-related")
                else:
                    await self.mark_url_scraped(url, "failed", "Could not fetch page")

                await asyncio.sleep(1)  # Rate limiting

                if len(results) >= self.settings.MAX_SCRAPED_ITEMS_PER_RUN:
                    break

            self.update_scraping_job(job_id, "completed", len(all_companies), len(results))
            logger.info(f"YC scraping completed: {len(results)} AI companies found")

        except Exception as e:
            logger.error(f"YC scraping failed: {e}")
            self.update_scraping_job(job_id, "failed", error=str(e))

        return results

    async def _scrape_yc_directory(self) -> List[Dict]:
        """
        Scrape YC directory page

        Returns:
            List of company data
        """
        companies = []

        try:
            # YC directory with AI filter
            url = f"{self.yc_directory_url}?tags=Artificial+Intelligence"
            html = await self.fetch_url(url)

            if not html:
                return companies

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            # YC uses React, so we need to parse the rendered content
            # or use their API endpoint if available

            # Look for company cards
            company_elements = soup.find_all('a', href=lambda x: x and '/companies/' in x)

            for element in company_elements[:100]:  # Limit to 100
                company_path = element.get('href')
                if company_path and company_path.startswith('/companies/'):
                    company_slug = company_path.split('/')[-1]
                    yc_url = f"https://www.ycombinator.com{company_path}"

                    # Get company details from the directory page
                    company_data = await self._scrape_yc_company_page(yc_url)
                    if company_data:
                        companies.append(company_data)

                await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Failed to scrape YC directory: {e}")

        return companies

    async def _scrape_yc_company_page(self, yc_url: str) -> Dict:
        """
        Scrape individual YC company page

        Args:
            yc_url: YC company profile URL

        Returns:
            Company data dictionary
        """
        try:
            html = await self.fetch_url(yc_url)
            if not html:
                return {}

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            # Extract company name
            name = ""
            name_elem = soup.find('h1')
            if name_elem:
                name = name_elem.get_text(strip=True)

            # Extract website URL
            url = ""
            website_link = soup.find('a', string=lambda x: x and 'Visit' in x)
            if website_link:
                url = website_link.get('href')

            # Extract description
            description = ""
            desc_elem = soup.find('p', class_='description')
            if desc_elem:
                description = desc_elem.get_text(strip=True)

            # Extract batch
            batch = ""
            batch_elem = soup.find('span', string=lambda x: x and ('W' in x or 'S' in x) and any(c.isdigit() for c in str(x)))
            if batch_elem:
                batch = batch_elem.get_text(strip=True)

            # Extract tags
            tags = []
            tag_elements = soup.find_all('span', class_='tag')
            for tag in tag_elements:
                tags.append(tag.get_text(strip=True))

            # Extract founders
            founders = []
            founder_elements = soup.find_all('a', href=lambda x: x and '/founders/' in x)
            for founder in founder_elements:
                founders.append(founder.get_text(strip=True))

            return {
                'name': name,
                'url': url,
                'description': description,
                'batch': batch,
                'tags': tags,
                'founders': founders,
                'yc_url': yc_url
            }

        except Exception as e:
            logger.error(f"Failed to scrape YC company page: {e}")
            return {}

    async def _scrape_yc_launches(self) -> List[Dict]:
        """
        Scrape YC Launch posts (new company announcements)

        Returns:
            List of company data from launches
        """
        companies = []

        try:
            html = await self.fetch_url(self.yc_launches_url)
            if not html:
                return companies

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            # Find launch posts
            launch_elements = soup.find_all('a', href=lambda x: x and '/launches/' in x)

            for element in launch_elements[:50]:  # Limit to 50 launches
                launch_path = element.get('href')
                if launch_path:
                    launch_url = f"https://www.ycombinator.com{launch_path}"
                    launch_data = await self._scrape_launch_post(launch_url)
                    if launch_data and launch_data.get('url'):
                        companies.append(launch_data)

                await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Failed to scrape YC launches: {e}")

        return companies

    async def _scrape_launch_post(self, launch_url: str) -> Dict:
        """
        Scrape individual launch post

        Args:
            launch_url: Launch post URL

        Returns:
            Company data from launch
        """
        try:
            html = await self.fetch_url(launch_url)
            if not html:
                return {}

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            # Extract company name from title
            name = ""
            title = soup.find('h1')
            if title:
                name = title.get_text(strip=True)

            # Extract company website
            url = ""
            website_link = soup.find('a', string=lambda x: x and 'Website' in str(x))
            if website_link:
                url = website_link.get('href')

            # Extract description from launch post
            description = ""
            content = soup.find('div', class_='launch-content')
            if content:
                description = content.get_text(strip=True)[:500]  # First 500 chars

            return {
                'name': name,
                'url': url,
                'description': description,
                'yc_url': launch_url,
                'batch': 'Latest',  # Recent launch
                'tags': ['launch']
            }

        except Exception as e:
            logger.error(f"Failed to scrape launch post: {e}")
            return {}

    async def _use_yc_api(self) -> List[Dict]:
        """
        Alternative: Use YC's unofficial API if available

        Returns:
            List of companies
        """
        # YC doesn't have a public API, but they have JSON endpoints
        # Example: https://www.ycombinator.com/companies/export.json

        try:
            url = "https://www.ycombinator.com/companies/export.json"
            response = await self.session.get(url)
            data = response.json()

            companies = []
            for company in data:
                # Filter for AI-related companies
                tags = company.get('tags', [])
                if 'Artificial Intelligence' in tags or 'Machine Learning' in tags:
                    companies.append({
                        'name': company.get('name'),
                        'url': company.get('website'),
                        'description': company.get('one_liner'),
                        'batch': company.get('batch'),
                        'tags': tags,
                        'yc_url': f"https://www.ycombinator.com/companies/{company.get('slug')}"
                    })

            return companies

        except Exception as e:
            logger.error(f"Failed to use YC API: {e}")
            return []
