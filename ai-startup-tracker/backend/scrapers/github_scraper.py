"""
GitHub scraper
Tracks new ML/AI repositories and their owners (potential startups)
"""
from typing import List, Dict
from loguru import logger
import asyncio
from datetime import datetime, timedelta

from .base_scraper import BaseScraper
from ..database.models import DataSource


class GithubScraper(BaseScraper):
    """Scraper for GitHub ML/AI repositories and owners"""

    def __init__(self):
        super().__init__(DataSource.GITHUB)
        self.github_api = "https://api.github.com"
        self.github_token = self.settings.GITHUB_TOKEN  # From environment

    async def scrape(self) -> List[Dict]:
        """
        Scrape GitHub for new AI/ML repositories

        Returns:
            List of repository owner data (potential startups)
        """
        logger.info("Starting GitHub scraping...")
        job_id = self.create_scraping_job("github")

        results = []
        try:
            # Search for recently created AI/ML repos
            repos = await self._search_ai_repositories()

            for repo in repos:
                owner = repo.get('owner', {})
                owner_type = owner.get('type')

                # Focus on Organization accounts (likely companies)
                if owner_type != 'Organization':
                    continue

                owner_login = owner.get('login')
                owner_url = await self._get_owner_website(owner_login)

                if not owner_url or self.is_url_already_scraped(owner_url):
                    continue

                # Fetch the owner's website
                html = await self.fetch_url(owner_url)

                if html:
                    text = self.extract_text_from_html(html)

                    # Verify it's AI-related
                    if self.is_ai_related_url(owner_url, text):
                        result = {
                            'url': owner_url,
                            'domain': self.extract_domain(owner_url),
                            'name': owner.get('login'),
                            'description': repo.get('description', ''),
                            'landing_page_text': text,
                            'source': self.source,
                            'source_url': owner.get('html_url'),
                            'github_org': owner_login,
                            'github_repo': repo.get('name'),
                            'github_stars': repo.get('stargazers_count', 0),
                            'github_created': repo.get('created_at'),
                            'tags': ['opensource', 'github']
                        }
                        results.append(result)
                        await self.mark_url_scraped(owner_url, "success")
                        logger.info(f"Successfully scraped GitHub org: {owner_login}")
                    else:
                        await self.mark_url_scraped(owner_url, "skipped", "Not AI-related")
                else:
                    await self.mark_url_scraped(owner_url, "failed", "Could not fetch page")

                await asyncio.sleep(1)  # GitHub rate limiting

                if len(results) >= self.settings.MAX_SCRAPED_ITEMS_PER_RUN:
                    break

            self.update_scraping_job(job_id, "completed", len(repos), len(results))
            logger.info(f"GitHub scraping completed: {len(results)} AI orgs found")

        except Exception as e:
            logger.error(f"GitHub scraping failed: {e}")
            self.update_scraping_job(job_id, "failed", error=str(e))

        return results

    async def _search_ai_repositories(self) -> List[Dict]:
        """
        Search GitHub for recently created AI/ML repositories

        Returns:
            List of repository data
        """
        repos = []

        try:
            # Calculate date for recent repos (last 7 days)
            since_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

            # Search queries for AI/ML repos
            search_queries = [
                f"machine learning created:>{since_date}",
                f"artificial intelligence created:>{since_date}",
                f"deep learning created:>{since_date}",
                f"neural network created:>{since_date}",
                f"llm created:>{since_date}",
                f"gpt created:>{since_date}"
            ]

            headers = {}
            if self.github_token:
                headers['Authorization'] = f'token {self.github_token}'

            for query in search_queries:
                url = f"{self.github_api}/search/repositories"
                params = {
                    'q': query,
                    'sort': 'stars',
                    'order': 'desc',
                    'per_page': 30
                }

                response = await self.session.get(url, params=params, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    repos.extend(data.get('items', []))

                # Rate limiting
                await asyncio.sleep(2)

            # Remove duplicates
            seen = set()
            unique_repos = []
            for repo in repos:
                repo_id = repo.get('id')
                if repo_id not in seen:
                    seen.add(repo_id)
                    unique_repos.append(repo)

            return unique_repos

        except Exception as e:
            logger.error(f"Failed to search GitHub repositories: {e}")
            return []

    async def _get_owner_website(self, owner_login: str) -> str:
        """
        Get organization's website from GitHub API

        Args:
            owner_login: GitHub organization login

        Returns:
            Website URL or empty string
        """
        try:
            url = f"{self.github_api}/orgs/{owner_login}"
            headers = {}
            if self.github_token:
                headers['Authorization'] = f'token {self.github_token}'

            response = await self.session.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                blog = data.get('blog', '')

                # Clean up URL
                if blog:
                    if not blog.startswith('http'):
                        blog = 'https://' + blog
                    return blog

            return ""

        except Exception as e:
            logger.error(f"Failed to get owner website: {e}")
            return ""

    async def _track_founding_engineers(self) -> List[Dict]:
        """
        Alternative approach: Track job postings for 'Founding Engineer' positions
        This can indicate stealth startups

        Returns:
            List of potential stealth startup data
        """
        # This would require integration with job boards or LinkedIn
        # Placeholder for future implementation
        logger.info("Founding engineer tracking not yet implemented")
        return []
