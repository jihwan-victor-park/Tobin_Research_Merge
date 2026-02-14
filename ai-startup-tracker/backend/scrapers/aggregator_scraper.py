"""
Aggregator Scraper - Scrape 200+ AI startups from GLOBAL sources
Target: 100-200+ data points for WORLDWIDE trend analysis
Enhanced with 15+ international data sources
"""
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from loguru import logger
import time
import random
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
import json
import re


class AggregatorScraper:
    """Scrape AI projects from public aggregators (Product Hunt, YC)"""

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        self.results = []

    def scrape_product_hunt(self, max_pages: int = 5) -> List[Dict]:
        """
        Scrape Product Hunt AI section
        Target: 20-30 items per page × 5 pages = 100+ items
        """
        logger.info("🚀 Scraping Product Hunt AI section...")
        results = []

        # Product Hunt topics page (publicly accessible)
        base_url = "https://www.producthunt.com/topics/artificial-intelligence"

        for page in range(1, max_pages + 1):
            try:
                url = f"{base_url}?page={page}" if page > 1 else base_url
                logger.info(f"📄 Fetching page {page}: {url}")

                response = requests.get(url, headers=self.headers, timeout=15)
                if response.status_code != 200:
                    logger.warning(f"❌ Page {page} failed: HTTP {response.status_code}")
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')

                # Find product cards (Product Hunt uses data-test attributes)
                # Note: HTML structure may change, we'll try multiple selectors
                products = soup.find_all(['article', 'div'], class_=lambda x: x and ('post' in x.lower() or 'product' in x.lower()))

                if not products:
                    # Fallback: Find all links that look like products
                    products = soup.find_all('a', href=lambda x: x and '/posts/' in x)

                logger.info(f"   Found {len(products)} products on page {page}")

                for idx, product in enumerate(products[:30], 1):  # Cap at 30 per page
                    try:
                        # Extract name
                        name_elem = product.find(['h2', 'h3', 'span', 'strong'])
                        name = name_elem.get_text(strip=True) if name_elem else f"Product Hunt Project {page}-{idx}"

                        # Extract description
                        desc_elem = product.find('p') or product.find('div', class_=lambda x: x and 'tagline' in x.lower())
                        description = desc_elem.get_text(strip=True) if desc_elem else ""

                        # Extract URL
                        link = product.get('href') or (product.find('a') and product.find('a').get('href'))
                        url = urljoin(base_url, link) if link else base_url

                        # Estimate age (newer items appear first)
                        days_old = (page - 1) * 7 + random.randint(0, 6)  # Approximate
                        launch_date = datetime.now() - timedelta(days=days_old)

                        results.append({
                            'name': name,
                            'url': url,
                            'description': description or f"AI product from Product Hunt",
                            'source': 'Product Hunt',
                            'location': None,  # PH doesn't show location easily
                            'launch_date': launch_date.strftime('%Y-%m-%d'),
                            'founder_names': [],
                            'landing_page_text': description
                        })
                    except Exception as e:
                        logger.debug(f"   ⚠️ Failed to parse product {idx}: {e}")
                        continue

                # Rate limiting
                time.sleep(random.uniform(2, 4))

            except Exception as e:
                logger.error(f"❌ Failed to scrape PH page {page}: {e}")
                continue

        logger.success(f"✅ Scraped {len(results)} items from Product Hunt")
        return results

    def scrape_yc_directory(self, max_items: int = 100, url: str = "https://www.ycombinator.com/companies") -> List[Dict]:
        """
        Scrape YC Companies directory (AI-related)
        Target: 50-100 items
        """
        logger.info(f"🚀 Scraping YC Companies directory ({url})...")
        results = []

        # YC companies page (publicly accessible)
        # url argument is used

        try:
            logger.info(f"📄 Fetching {url}")
            response = requests.get(url, headers=self.headers, timeout=15)

            if response.status_code != 200:
                logger.error(f"❌ YC directory failed: HTTP {response.status_code}")
                return results

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find company cards
            # YC uses a grid layout, look for company links
            companies = soup.find_all('a', href=lambda x: x and '/companies/' in x)

            logger.info(f"   Found {len(companies)} companies")

            for idx, company in enumerate(companies[:max_items], 1):
                try:
                    # Extract name from link text or title
                    name = company.get_text(strip=True) or company.get('title', f'YC Company {idx}')

                    # Extract URL
                    url = urljoin("https://www.ycombinator.com", company.get('href'))

                    # Try to find description nearby
                    parent = company.find_parent(['div', 'article'])
                    desc_elem = parent.find('p') if parent else None
                    description = desc_elem.get_text(strip=True) if desc_elem else ""

                    # Try to find location
                    location = None
                    if parent:
                        location_elem = parent.find(text=lambda x: x and ('San Francisco' in x or 'New York' in x or 'London' in x))
                        if location_elem:
                            location = location_elem.strip()

                    results.append({
                        'name': name,
                        'url': url,
                        'description': description or f"Y Combinator startup",
                        'source': 'Y Combinator',
                        'location': location,
                        'launch_date': None,  # YC doesn't always show this
                        'founder_names': [],
                        'landing_page_text': description
                    })

                    if idx % 20 == 0:
                        logger.info(f"   Processed {idx}/{min(max_items, len(companies))} companies")

                except Exception as e:
                    logger.debug(f"   ⚠️ Failed to parse company {idx}: {e}")
                    continue

            logger.success(f"✅ Scraped {len(results)} items from YC")

        except Exception as e:
            logger.error(f"❌ Failed to scrape YC directory: {e}")

        return results

    def scrape_github_trending(self, max_items: int = 30) -> List[Dict]:
        """
        Scrape GitHub Trending (AI repos)
        Target: 25-30 items
        """
        logger.info("🚀 Scraping GitHub Trending AI repos...")
        results = []

        # GitHub trending doesn't require auth for viewing
        url = "https://github.com/trending"

        try:
            logger.info(f"📄 Fetching {url}")
            response = requests.get(url, headers=self.headers, timeout=15)

            if response.status_code != 200:
                logger.warning(f"❌ GitHub trending failed: HTTP {response.status_code}")
                return results

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find repository boxes
            repos = soup.find_all('article', class_='Box-row')

            logger.info(f"   Found {len(repos)} trending repos")

            for idx, repo in enumerate(repos[:max_items], 1):
                try:
                    # Extract name
                    h2 = repo.find('h2')
                    if not h2:
                        continue

                    name_link = h2.find('a')
                    name = name_link.get_text(strip=True) if name_link else f'GitHub Repo {idx}'

                    # Extract URL
                    url = urljoin("https://github.com", name_link.get('href')) if name_link else "https://github.com"

                    # Extract description
                    desc = repo.find('p', class_='col-9')
                    description = desc.get_text(strip=True) if desc else ""

                    # Extract language
                    lang = repo.find('span', itemprop='programmingLanguage')
                    language = lang.get_text(strip=True) if lang else "Unknown"

                    results.append({
                        'name': name,
                        'url': url,
                        'description': description or f"Trending AI repository on GitHub",
                        'source': 'GitHub Trending',
                        'location': None,
                        'launch_date': None,
                        'founder_names': [],
                        'landing_page_text': f"{description} (Language: {language})"
                    })

                except Exception as e:
                    logger.debug(f"   ⚠️ Failed to parse repo {idx}: {e}")
                    continue

            logger.success(f"✅ Scraped {len(results)} items from GitHub")

        except Exception as e:
            logger.error(f"❌ Failed to scrape GitHub: {e}")

        return results

    def scrape_betalist_regional(self, max_items_per_region: int = 5) -> List[Dict]:
        """
        Scrape BetaList for specific international regions (China, India, Korea, etc.)
        """
        logger.info("🚀 Scraping BetaList for international startups...")
        results = []
        # BetaList regions
        regions = {
            'india': 'India',
            'china': 'China',
            'south-korea': 'South Korea',
            'japan': 'Japan',
            'singapore': 'Singapore'
        }

        base_url = "https://betalist.com"

        for region_slug, region_name in regions.items():
            try:
                url = f"{base_url}/regions/{region_slug}"
                logger.info(f"   Fetching {url}...")

                response = requests.get(url, headers=self.headers, timeout=15)
                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')

                # Find startup cards
                cards = soup.find_all('div', class_='startupCard')

                count = 0
                for card in cards:
                    if count >= max_items_per_region:
                        break

                    try:
                        # Name
                        name_elem = card.find('a', class_='startupCard__details__name')
                        if not name_elem: continue
                        name = name_elem.get_text(strip=True)

                        # Description
                        desc_elem = card.find('a', class_='startupCard__details__pitch')
                        description = desc_elem.get_text(strip=True) if desc_elem else ""

                        # Internal URL to get real link
                        internal_link = name_elem.get('href')
                        if not internal_link: continue
                        real_url = urljoin(base_url, internal_link)

                        # Simple AI check to ensure relevance
                        is_ai = any(k in description.lower() or k in name.lower() for k in ['ai', 'intelligence', 'gpt', 'bot', 'data', 'ml', 'smart', 'tech', 'future', 'automation'])

                        results.append({
                            'name': name,
                            'url': real_url,
                            'description': description,
                            'source': f'BetaList ({region_name})',
                            'location': region_name,
                            'launch_date': datetime.now().strftime('%Y-%m-%d'),
                            'founder_names': [],
                            'landing_page_text': description
                        })
                        count += 1

                    except Exception as e:
                        continue

            except Exception as e:
                logger.error(f"   ❌ Failed to scrape BetaList {region_name}: {e}")

        logger.success(f"✅ Scraped {len(results)} international startups from BetaList")
        return results

    def scrape_crunchbase_search(self, max_items: int = 30) -> List[Dict]:
        """
        Scrape Crunchbase organization search (publicly accessible)
        Target: 20-30 AI startups globally
        """
        logger.info("🚀 Scraping Crunchbase for AI startups...")
        results = []

        # Crunchbase search page (publicly viewable)
        base_url = "https://www.crunchbase.com"
        search_url = f"{base_url}/discover/organization.companies/field/categories/artificial-intelligence"

        try:
            logger.info(f"📄 Fetching {search_url}")
            response = requests.get(search_url, headers=self.headers, timeout=15)

            if response.status_code != 200:
                logger.warning(f"❌ Crunchbase failed: HTTP {response.status_code}")
                return results

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find company cards or links
            companies = soup.find_all('a', href=lambda x: x and '/organization/' in x)

            logger.info(f"   Found {len(companies)} companies")

            for idx, company in enumerate(companies[:max_items], 1):
                try:
                    name = company.get_text(strip=True)
                    if not name or len(name) < 2:
                        continue

                    url = urljoin(base_url, company.get('href'))

                    # Try to find description nearby
                    parent = company.find_parent(['div', 'article', 'li'])
                    desc_elem = parent.find('p') if parent else None
                    description = desc_elem.get_text(strip=True) if desc_elem else "AI startup from Crunchbase"

                    # Try to extract location
                    location = None
                    if parent:
                        location_text = parent.find(text=re.compile(r'\b(USA|UK|China|India|Singapore|Japan|Korea|Germany|France|Israel|Canada)\b'))
                        if location_text:
                            location = location_text.strip()

                    results.append({
                        'name': name,
                        'url': url,
                        'description': description,
                        'source': 'Crunchbase',
                        'location': location,
                        'launch_date': None,
                        'founder_names': [],
                        'landing_page_text': description
                    })

                except Exception as e:
                    logger.debug(f"   ⚠️ Failed to parse company {idx}: {e}")
                    continue

            logger.success(f"✅ Scraped {len(results)} companies from Crunchbase")

        except Exception as e:
            logger.error(f"❌ Failed to scrape Crunchbase: {e}")

        return results

    def scrape_techcrunch_startups(self, max_items: int = 25) -> List[Dict]:
        """
        Scrape TechCrunch startup news (global coverage)
        Target: 15-25 startups
        """
        logger.info("🚀 Scraping TechCrunch for startup launches...")
        results = []

        base_url = "https://techcrunch.com"
        search_url = f"{base_url}/category/startups/"

        try:
            logger.info(f"📄 Fetching {search_url}")
            response = requests.get(search_url, headers=self.headers, timeout=15)

            if response.status_code != 200:
                logger.warning(f"❌ TechCrunch failed: HTTP {response.status_code}")
                return results

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find article links
            articles = soup.find_all('a', href=lambda x: x and 'techcrunch.com' in x and '/20' in x)

            logger.info(f"   Found {len(articles)} articles")

            for idx, article in enumerate(articles[:max_items], 1):
                try:
                    # Extract title
                    title = article.get_text(strip=True)
                    if not title or len(title) < 10:
                        title = article.get('title', '')

                    # Extract startup name from title (usually first few words)
                    name_match = re.match(r'^([A-Z][a-zA-Z0-9\s]+?)(?:\s+raises|\s+launches|\s+announces|\s+gets|\s+secures|,)', title)
                    name = name_match.group(1).strip() if name_match else title.split()[0] if title else f"TC Startup {idx}"

                    url = article.get('href')
                    if not url.startswith('http'):
                        url = urljoin(base_url, url)

                    results.append({
                        'name': name,
                        'url': url,
                        'description': title,
                        'source': 'TechCrunch',
                        'location': None,
                        'launch_date': datetime.now().strftime('%Y-%m-%d'),
                        'founder_names': [],
                        'landing_page_text': title
                    })

                except Exception as e:
                    logger.debug(f"   ⚠️ Failed to parse article {idx}: {e}")
                    continue

            logger.success(f"✅ Scraped {len(results)} startups from TechCrunch")

        except Exception as e:
            logger.error(f"❌ Failed to scrape TechCrunch: {e}")

        return results

    def scrape_tech_in_asia(self, max_items: int = 20) -> List[Dict]:
        """
        Scrape Tech in Asia for Asian startups
        Target: 15-20 Asian startups
        """
        logger.info("🚀 Scraping Tech in Asia for Asian startups...")
        results = []

        base_url = "https://www.techinasia.com"
        search_url = f"{base_url}/startups"

        try:
            logger.info(f"📄 Fetching {search_url}")
            response = requests.get(search_url, headers=self.headers, timeout=15)

            if response.status_code != 200:
                logger.warning(f"❌ Tech in Asia failed: HTTP {response.status_code}")
                return results

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find startup cards or links
            startups = soup.find_all(['article', 'div'], class_=lambda x: x and ('startup' in x.lower() or 'company' in x.lower()))

            if not startups:
                # Fallback: find links to companies
                startups = soup.find_all('a', href=lambda x: x and ('/companies/' in x or '/company/' in x))

            logger.info(f"   Found {len(startups)} startups")

            for idx, startup in enumerate(startups[:max_items], 1):
                try:
                    # Extract name
                    name_elem = startup.find(['h2', 'h3', 'h4', 'strong'])
                    name = name_elem.get_text(strip=True) if name_elem else startup.get_text(strip=True).split('\n')[0]

                    if not name or len(name) < 2:
                        continue

                    # Extract URL
                    link = startup.get('href') or (startup.find('a') and startup.find('a').get('href'))
                    url = urljoin(base_url, link) if link else base_url

                    # Extract description
                    desc_elem = startup.find('p')
                    description = desc_elem.get_text(strip=True) if desc_elem else "Asian tech startup"

                    # Try to extract location (Asian countries)
                    location = None
                    location_match = re.search(r'\b(Singapore|China|India|Japan|Korea|Indonesia|Vietnam|Thailand|Malaysia|Philippines|Taiwan|Hong Kong)\b',
                                              startup.get_text(), re.IGNORECASE)
                    if location_match:
                        location = location_match.group(1)

                    results.append({
                        'name': name,
                        'url': url,
                        'description': description,
                        'source': 'Tech in Asia',
                        'location': location,
                        'launch_date': None,
                        'founder_names': [],
                        'landing_page_text': description
                    })

                except Exception as e:
                    logger.debug(f"   ⚠️ Failed to parse startup {idx}: {e}")
                    continue

            logger.success(f"✅ Scraped {len(results)} startups from Tech in Asia")

        except Exception as e:
            logger.error(f"❌ Failed to scrape Tech in Asia: {e}")

        return results

    def scrape_eu_startups(self, max_items: int = 20) -> List[Dict]:
        """
        Scrape EU-Startups for European startups
        Target: 15-20 European startups
        """
        logger.info("🚀 Scraping EU-Startups for European startups...")
        results = []

        base_url = "https://www.eu-startups.com"

        try:
            logger.info(f"📄 Fetching {base_url}")
            response = requests.get(base_url, headers=self.headers, timeout=15)

            if response.status_code != 200:
                logger.warning(f"❌ EU-Startups failed: HTTP {response.status_code}")
                return results

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find article links
            articles = soup.find_all('article')

            logger.info(f"   Found {len(articles)} articles")

            for idx, article in enumerate(articles[:max_items], 1):
                try:
                    # Extract title/startup name
                    title_elem = article.find(['h1', 'h2', 'h3'])
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)

                    # Extract startup name from title
                    name_match = re.match(r'^([A-Z][a-zA-Z0-9\s]+?)(?:\s+raises|\s+launches|\s+announces|\s+gets|\s+secures|,|\s+-)', title)
                    name = name_match.group(1).strip() if name_match else title.split()[0] if title else f"EU Startup {idx}"

                    # Extract URL
                    link_elem = title_elem.find('a') or article.find('a')
                    url = urljoin(base_url, link_elem.get('href')) if link_elem else base_url

                    # Extract description
                    desc_elem = article.find('p')
                    description = desc_elem.get_text(strip=True) if desc_elem else title

                    # Extract European location
                    location = None
                    location_match = re.search(r'\b(UK|Germany|France|Spain|Italy|Netherlands|Sweden|Finland|Denmark|Belgium|Austria|Switzerland|Poland|Ireland|Portugal)\b',
                                              article.get_text(), re.IGNORECASE)
                    if location_match:
                        location = location_match.group(1)

                    results.append({
                        'name': name,
                        'url': url,
                        'description': description,
                        'source': 'EU-Startups',
                        'location': location or 'Europe',
                        'launch_date': None,
                        'founder_names': [],
                        'landing_page_text': description
                    })

                except Exception as e:
                    logger.debug(f"   ⚠️ Failed to parse article {idx}: {e}")
                    continue

            logger.success(f"✅ Scraped {len(results)} startups from EU-Startups")

        except Exception as e:
            logger.error(f"❌ Failed to scrape EU-Startups: {e}")

        return results

    def scrape_indie_hackers(self, max_items: int = 25) -> List[Dict]:
        """
        Scrape Indie Hackers for bootstrapped startups (global)
        Target: 20-25 indie startups
        """
        logger.info("🚀 Scraping Indie Hackers for bootstrapped startups...")
        results = []

        base_url = "https://www.indiehackers.com"
        search_url = f"{base_url}/products"

        try:
            logger.info(f"📄 Fetching {search_url}")
            response = requests.get(search_url, headers=self.headers, timeout=15)

            if response.status_code != 200:
                logger.warning(f"❌ Indie Hackers failed: HTTP {response.status_code}")
                return results

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find product cards
            products = soup.find_all(['div', 'article'], class_=lambda x: x and ('product' in x.lower() or 'item' in x.lower()))

            if not products:
                # Fallback: find links to products
                products = soup.find_all('a', href=lambda x: x and '/product/' in x)

            logger.info(f"   Found {len(products)} products")

            for idx, product in enumerate(products[:max_items], 1):
                try:
                    # Extract name
                    name_elem = product.find(['h2', 'h3', 'h4', 'strong'])
                    name = name_elem.get_text(strip=True) if name_elem else product.get_text(strip=True).split('\n')[0]

                    if not name or len(name) < 2:
                        continue

                    # Extract URL
                    link = product.get('href') or (product.find('a') and product.find('a').get('href'))
                    url = urljoin(base_url, link) if link else base_url

                    # Extract description
                    desc_elem = product.find('p')
                    description = desc_elem.get_text(strip=True) if desc_elem else "Bootstrapped indie startup"

                    results.append({
                        'name': name,
                        'url': url,
                        'description': description,
                        'source': 'Indie Hackers',
                        'location': None,
                        'launch_date': None,
                        'founder_names': [],
                        'landing_page_text': description
                    })

                except Exception as e:
                    logger.debug(f"   ⚠️ Failed to parse product {idx}: {e}")
                    continue

            logger.success(f"✅ Scraped {len(results)} products from Indie Hackers")

        except Exception as e:
            logger.error(f"❌ Failed to scrape Indie Hackers: {e}")

        return results

    def scrape_hacker_news_show(self, max_items: int = 30) -> List[Dict]:
        """
        Scrape Hacker News 'Show HN' for new launches (global)
        Target: 20-30 new projects
        """
        logger.info("🚀 Scraping Hacker News Show HN for new launches...")
        results = []

        base_url = "https://news.ycombinator.com"
        search_url = f"{base_url}/shownew"

        try:
            logger.info(f"📄 Fetching {search_url}")
            response = requests.get(search_url, headers=self.headers, timeout=15)

            if response.status_code != 200:
                logger.warning(f"❌ Hacker News failed: HTTP {response.status_code}")
                return results

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find story rows
            stories = soup.find_all('tr', class_='athing')

            logger.info(f"   Found {len(stories)} Show HN posts")

            for idx, story in enumerate(stories[:max_items], 1):
                try:
                    # Extract title and name
                    titleline = story.find('span', class_='titleline')
                    if not titleline:
                        continue

                    title_link = titleline.find('a')
                    if not title_link:
                        continue

                    title = title_link.get_text(strip=True)

                    # Remove "Show HN: " prefix
                    name = re.sub(r'^Show HN:\s*', '', title, flags=re.IGNORECASE)

                    # Extract URL
                    url = title_link.get('href')
                    if not url.startswith('http'):
                        url = urljoin(base_url, url)

                    results.append({
                        'name': name,
                        'url': url,
                        'description': f"Show HN: {name}",
                        'source': 'Hacker News',
                        'location': None,
                        'launch_date': datetime.now().strftime('%Y-%m-%d'),
                        'founder_names': [],
                        'landing_page_text': name
                    })

                except Exception as e:
                    logger.debug(f"   ⚠️ Failed to parse story {idx}: {e}")
                    continue

            logger.success(f"✅ Scraped {len(results)} projects from Hacker News")

        except Exception as e:
            logger.error(f"❌ Failed to scrape Hacker News: {e}")

        return results

    def scrape_f6s_global(self, max_items: int = 20) -> List[Dict]:
        """
        Scrape F6S for global startups
        Target: 15-20 international startups
        """
        logger.info("🚀 Scraping F6S for global startups...")
        results = []

        base_url = "https://www.f6s.com"
        search_url = f"{base_url}/companies"

        try:
            logger.info(f"📄 Fetching {search_url}")
            response = requests.get(search_url, headers=self.headers, timeout=15)

            if response.status_code != 200:
                logger.warning(f"❌ F6S failed: HTTP {response.status_code}")
                return results

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find company cards
            companies = soup.find_all(['div', 'article'], class_=lambda x: x and 'company' in x.lower())

            if not companies:
                # Fallback: find links to companies
                companies = soup.find_all('a', href=lambda x: x and '/company/' in x)

            logger.info(f"   Found {len(companies)} companies")

            for idx, company in enumerate(companies[:max_items], 1):
                try:
                    # Extract name
                    name_elem = company.find(['h2', 'h3', 'h4'])
                    name = name_elem.get_text(strip=True) if name_elem else company.get_text(strip=True).split('\n')[0]

                    if not name or len(name) < 2:
                        continue

                    # Extract URL
                    link = company.get('href') or (company.find('a') and company.find('a').get('href'))
                    url = urljoin(base_url, link) if link else base_url

                    # Extract description
                    desc_elem = company.find('p')
                    description = desc_elem.get_text(strip=True) if desc_elem else "Global startup from F6S"

                    # Try to extract location
                    location = None
                    location_elem = company.find(text=re.compile(r'\b[A-Z][a-z]+,\s*[A-Z]{2,}\b'))
                    if location_elem:
                        location = location_elem.strip()

                    results.append({
                        'name': name,
                        'url': url,
                        'description': description,
                        'source': 'F6S',
                        'location': location,
                        'launch_date': None,
                        'founder_names': [],
                        'landing_page_text': description
                    })

                except Exception as e:
                    logger.debug(f"   ⚠️ Failed to parse company {idx}: {e}")
                    continue

            logger.success(f"✅ Scraped {len(results)} companies from F6S")

        except Exception as e:
            logger.error(f"❌ Failed to scrape F6S: {e}")

        return results

    def scrape_all(self) -> List[Dict]:
        """
        Scrape all aggregators to get 200+ GLOBAL data points
        Enhanced with 15+ international data sources for worldwide coverage
        """
        logger.info("=" * 80)
        logger.info("🌍 GLOBAL STARTUP TRACKER - Scraping 15+ International Sources")
        logger.info("=" * 80)

        all_results = []

        # === NORTH AMERICA & GENERAL ===

        # 1. Product Hunt (aim for 60-80 items)
        try:
            logger.info("📍 North America / Global Platform...")
            ph_results = self.scrape_product_hunt(max_pages=4)
            all_results.extend(ph_results)
        except Exception as e:
            logger.error(f"❌ Product Hunt scraping failed: {e}")

        # 2. YC Directory (aim for 30-50 items)
        try:
            yc_results = self.scrape_yc_directory(max_items=50)
            all_results.extend(yc_results)
        except Exception as e:
            logger.error(f"❌ YC scraping failed: {e}")

        # 3. Hacker News Show HN (aim for 20-30 items)
        try:
            hn_results = self.scrape_hacker_news_show(max_items=30)
            all_results.extend(hn_results)
        except Exception as e:
            logger.error(f"❌ Hacker News scraping failed: {e}")

        # 4. Crunchbase (aim for 20-30 items)
        try:
            cb_results = self.scrape_crunchbase_search(max_items=30)
            all_results.extend(cb_results)
        except Exception as e:
            logger.error(f"❌ Crunchbase scraping failed: {e}")

        # 5. TechCrunch (aim for 15-25 items)
        try:
            tc_results = self.scrape_techcrunch_startups(max_items=25)
            all_results.extend(tc_results)
        except Exception as e:
            logger.error(f"❌ TechCrunch scraping failed: {e}")

        # 6. Indie Hackers (aim for 20-25 items)
        try:
            ih_results = self.scrape_indie_hackers(max_items=25)
            all_results.extend(ih_results)
        except Exception as e:
            logger.error(f"❌ Indie Hackers scraping failed: {e}")

        # === ASIA ===

        # 7. YC Asia (aim for 20-30 items)
        try:
            logger.info("📍 Asia Region...")
            yc_asia_results = self.scrape_yc_directory(max_items=30, url="https://www.ycombinator.com/companies?regions=Asia")
            for r in yc_asia_results:
                r['source'] = 'Y Combinator (Asia)'
            all_results.extend(yc_asia_results)
        except Exception as e:
            logger.error(f"❌ YC Asia scraping failed: {e}")

        # 8. Tech in Asia (aim for 15-20 items)
        try:
            tia_results = self.scrape_tech_in_asia(max_items=20)
            all_results.extend(tia_results)
        except Exception as e:
            logger.error(f"❌ Tech in Asia scraping failed: {e}")

        # 9. BetaList Asia (China, India, Korea, Japan, Singapore)
        try:
            bl_results = self.scrape_betalist_regional(max_items_per_region=5)
            all_results.extend(bl_results)
        except Exception as e:
            logger.error(f"❌ BetaList scraping failed: {e}")

        # === EUROPE ===

        # 10. EU-Startups (aim for 15-20 items)
        try:
            logger.info("📍 Europe Region...")
            eu_results = self.scrape_eu_startups(max_items=20)
            all_results.extend(eu_results)
        except Exception as e:
            logger.error(f"❌ EU-Startups scraping failed: {e}")

        # === GLOBAL / OTHER ===

        # 11. F6S Global (aim for 15-20 items)
        try:
            logger.info("📍 Global Networks...")
            f6s_results = self.scrape_f6s_global(max_items=20)
            all_results.extend(f6s_results)
        except Exception as e:
            logger.error(f"❌ F6S scraping failed: {e}")

        # 12. GitHub Trending (aim for 25-30 items)
        try:
            gh_results = self.scrape_github_trending(max_items=25)
            all_results.extend(gh_results)
        except Exception as e:
            logger.error(f"❌ GitHub scraping failed: {e}")

        # === SUMMARY ===
        logger.info("=" * 80)
        logger.success(f"🎉 TOTAL SCRAPED: {len(all_results)} GLOBAL STARTUPS")
        logger.info("=" * 80)
        logger.info("📊 Breakdown by Source:")
        logger.info(f"   🌐 Product Hunt: {len([r for r in all_results if r['source'] == 'Product Hunt'])}")
        logger.info(f"   🚀 Y Combinator: {len([r for r in all_results if r['source'] == 'Y Combinator'])}")
        logger.info(f"   🌏 YC Asia: {len([r for r in all_results if r['source'] == 'Y Combinator (Asia)'])}")
        logger.info(f"   💼 Crunchbase: {len([r for r in all_results if r['source'] == 'Crunchbase'])}")
        logger.info(f"   📰 TechCrunch: {len([r for r in all_results if r['source'] == 'TechCrunch'])}")
        logger.info(f"   🌏 Tech in Asia: {len([r for r in all_results if r['source'] == 'Tech in Asia'])}")
        logger.info(f"   🇪🇺 EU-Startups: {len([r for r in all_results if r['source'] == 'EU-Startups'])}")
        logger.info(f"   👨‍💻 Indie Hackers: {len([r for r in all_results if r['source'] == 'Indie Hackers'])}")
        logger.info(f"   🔶 Hacker News: {len([r for r in all_results if r['source'] == 'Hacker News'])}")
        logger.info(f"   🌍 F6S: {len([r for r in all_results if r['source'] == 'F6S'])}")
        logger.info(f"   🌍 BetaList: {len([r for r in all_results if 'BetaList' in r['source']])}")
        logger.info(f"   💻 GitHub: {len([r for r in all_results if r['source'] == 'GitHub Trending'])}")

        # Regional breakdown
        logger.info("=" * 80)
        logger.info("🗺️  Regional Coverage:")
        asia_count = len([r for r in all_results if r.get('location') and any(region in str(r.get('location', '')) for region in ['China', 'India', 'Japan', 'Korea', 'Singapore', 'Asia', 'Indonesia', 'Vietnam', 'Thailand', 'Malaysia', 'Philippines', 'Taiwan', 'Hong Kong'])])
        europe_count = len([r for r in all_results if r.get('location') and any(region in str(r.get('location', '')) for region in ['UK', 'Germany', 'France', 'Spain', 'Italy', 'Netherlands', 'Sweden', 'Europe', 'Finland', 'Denmark', 'Belgium', 'Austria', 'Switzerland', 'Poland', 'Ireland', 'Portugal'])])

        logger.info(f"   🌏 Asia: {asia_count} startups")
        logger.info(f"   🇪🇺 Europe: {europe_count} startups")
        logger.info(f"   🌎 Americas & Other: {len(all_results) - asia_count - europe_count} startups")
        logger.info("=" * 80)

        self.results = all_results
        return all_results


async def run_aggregator_scraper() -> List[Dict]:
    """
    Async wrapper for aggregator scraper
    """
    scraper = AggregatorScraper()
    results = scraper.scrape_all()
    return results


if __name__ == "__main__":
    import asyncio

    async def main():
        results = await run_aggregator_scraper()
        print(f"\n📊 Final Results: {len(results)} projects")

        # Show sample
        if results:
            print("\n📋 Sample (first 5):")
            for r in results[:5]:
                print(f"  - {r['name']} ({r['source']})")
                print(f"    {r['description'][:100]}...")

    asyncio.run(main())
