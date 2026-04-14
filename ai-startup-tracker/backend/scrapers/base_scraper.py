"""
Base scraper class with common functionality
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from urllib.parse import urlparse
import re
from bs4 import BeautifulSoup
from loguru import logger
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..database.models import DataSource, ScrapedURL, ScrapingJob
from ..database.connection import get_db_session
from ..config import get_settings


class BaseScraper(ABC):
    """Abstract base class for all scrapers"""

    def __init__(self, source: DataSource):
        self.source = source
        self.settings = get_settings()
        self.session = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )

    @abstractmethod
    async def scrape(self) -> List[Dict]:
        """
        Main scraping method to be implemented by each scraper

        Returns:
            List of dictionaries containing scraped data
        """
        pass

    async def close(self):
        """Close HTTP session"""
        await self.session.aclose()

    def extract_domain(self, url: str) -> str:
        """Extract clean domain from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path
            # Remove www. prefix
            domain = re.sub(r'^www\.', '', domain)
            return domain.lower()
        except Exception as e:
            logger.error(f"Failed to extract domain from {url}: {e}")
            return ""

    def clean_text(self, text: str) -> str:
        """Clean and normalize text content"""
        if not text:
            return ""

        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove special characters but keep basic punctuation
        text = re.sub(r'[^\w\s.,!?-]', '', text)
        return text.strip()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_url(self, url: str) -> Optional[str]:
        """
        Fetch URL content with retry logic

        Args:
            url: URL to fetch

        Returns:
            HTML content or None if failed
        """
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def extract_text_from_html(self, html: str, max_length: int = 5000) -> str:
        """
        Extract clean text from HTML, removing scripts, styles, etc.

        Args:
            html: HTML content
            max_length: Maximum length of extracted text

        Returns:
            Cleaned text content
        """
        try:
            soup = BeautifulSoup(html, 'lxml')

            # Remove script, style, and other non-content tags
            for tag in soup(['script', 'style', 'meta', 'link', 'noscript', 'header', 'footer', 'nav']):
                tag.decompose()

            # Extract text from main content areas
            main_content = soup.find(['main', 'article']) or soup.body or soup

            text = main_content.get_text(separator=' ', strip=True)
            text = self.clean_text(text)

            # Truncate if too long
            if len(text) > max_length:
                text = text[:max_length] + "..."

            return text
        except Exception as e:
            logger.error(f"Failed to extract text from HTML: {e}")
            return ""

    def is_ai_related_url(self, url: str, text: str = "") -> bool:
        """
        Quick heuristic check if URL/text is AI-related

        Args:
            url: URL to check
            text: Optional text content to check

        Returns:
            True if likely AI-related
        """
        ai_keywords = [
            'ai', 'artificial intelligence', 'machine learning', 'ml',
            'deep learning', 'neural', 'llm', 'gpt', 'nlp',
            'computer vision', 'robotics', 'automation', 'chatbot',
            'generative', 'transformer', 'diffusion'
        ]

        # Check URL
        url_lower = url.lower()
        if any(keyword in url_lower for keyword in ['ai.', '/ai/', '-ai-', 'artificial', 'ml.', 'mlops']):
            return True

        # Check text content
        if text:
            text_lower = text.lower()
            keyword_count = sum(1 for keyword in ai_keywords if keyword in text_lower)
            # If multiple AI keywords found, likely AI-related
            if keyword_count >= 2:
                return True

        return False

    async def mark_url_scraped(self, url: str, status: str = "success", error: str = None):
        """
        Mark URL as scraped in database

        Args:
            url: URL that was scraped
            status: Status of scraping (success, failed, skipped)
            error: Optional error message
        """
        try:
            with get_db_session() as session:
                scraped = ScrapedURL(
                    url=url,
                    source=self.source,
                    status=status,
                    error_message=error
                )
                session.add(scraped)
                logger.debug(f"Marked {url} as scraped with status: {status}")
        except Exception as e:
            logger.error(f"Failed to mark URL as scraped: {e}")

    def is_url_already_scraped(self, url: str) -> bool:
        """
        Check if URL was already scraped

        Args:
            url: URL to check

        Returns:
            True if already scraped
        """
        try:
            with get_db_session() as session:
                exists = session.query(ScrapedURL).filter(
                    ScrapedURL.url == url,
                    ScrapedURL.source == self.source
                ).first()
                return exists is not None
        except Exception as e:
            logger.error(f"Failed to check if URL scraped: {e}")
            return False

    def create_scraping_job(self, job_type: str) -> Optional[int]:
        """
        Create a new scraping job record

        Args:
            job_type: Type of scraping job

        Returns:
            Job ID or None
        """
        try:
            with get_db_session() as session:
                job = ScrapingJob(
                    job_type=job_type,
                    status="running"
                )
                session.add(job)
                session.flush()
                job_id = job.id
                logger.info(f"Created scraping job {job_id} for {job_type}")
                return job_id
        except Exception as e:
            logger.error(f"Failed to create scraping job: {e}")
            return None

    def update_scraping_job(
        self,
        job_id: int,
        status: str,
        items_processed: int = 0,
        items_added: int = 0,
        error: str = None
    ):
        """
        Update scraping job status

        Args:
            job_id: Job ID to update
            status: New status
            items_processed: Number of items processed
            items_added: Number of items added to DB
            error: Optional error message
        """
        try:
            with get_db_session() as session:
                job = session.query(ScrapingJob).filter(ScrapingJob.id == job_id).first()
                if job:
                    job.status = status
                    job.items_processed = items_processed
                    job.items_added = items_added
                    job.error_message = error
                    if status in ["completed", "failed"]:
                        from datetime import datetime
                        job.completed_at = datetime.utcnow()
                    logger.info(f"Updated scraping job {job_id}: {status}")
        except Exception as e:
            logger.error(f"Failed to update scraping job: {e}")
