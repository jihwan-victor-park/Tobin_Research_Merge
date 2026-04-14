"""
Domain extraction, canonicalization, and classification utilities.
"""
import re
from typing import Optional, List
from urllib.parse import urlparse

try:
    import tldextract
except ImportError:
    tldextract = None


# Domains that are NOT product/company sites
NON_PRODUCT_DOMAINS = frozenset({
    "github.com", "github.io", "gitlab.com", "bitbucket.org",
    "readthedocs.io", "readthedocs.org", "rtfd.io",
    "docs.rs", "pkg.go.dev", "pypi.org", "npmjs.com",
    "medium.com", "dev.to", "substack.com", "hashnode.dev",
    "twitter.com", "x.com", "linkedin.com", "facebook.com",
    "youtube.com", "reddit.com", "discord.gg", "discord.com",
    "t.me", "telegram.org", "slack.com",
    "arxiv.org", "papers.ssrn.com", "scholar.google.com",
    "huggingface.co", "kaggle.com",
    "notion.so", "notion.site",
    "google.com", "amazonaws.com", "azure.com",
    "wikipedia.org", "stackoverflow.com",
})

# Patterns in URL paths that indicate docs, not product sites
NON_PRODUCT_PATH_PATTERNS = re.compile(
    r"/(docs|wiki|blog|issues|pull|releases|tree|blob|raw|commit)/", re.IGNORECASE
)


def canonicalize_domain(url_or_domain: str) -> Optional[str]:
    """
    Canonicalize a URL or domain string into a clean registrable domain.

    - Lowercases
    - Strips protocol, www., trailing slashes, tracking params
    - Returns registrable domain (e.g., 'example.com')

    Returns None if input is empty or unparseable.
    """
    if not url_or_domain or not isinstance(url_or_domain, str):
        return None

    raw = url_or_domain.strip()
    if not raw:
        return None

    # Add scheme if missing so urlparse works
    if not re.match(r"^https?://", raw, re.IGNORECASE):
        raw = "https://" + raw

    try:
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower().strip(".")
    except Exception:
        return None

    if not host:
        return None

    # Strip www.
    if host.startswith("www."):
        host = host[4:]

    # Use tldextract for registrable domain if available
    if tldextract is not None:
        ext = tldextract.extract(host)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}".lower()
        # Fallback if tldextract can't parse (e.g., IP addresses)
        return host if host else None

    # Fallback without tldextract: just return the cleaned host
    return host if host else None


def extract_domains_from_text(text: str) -> List[str]:
    """
    Extract URLs from text and return their canonical domains.
    Useful for parsing README content for website links.
    """
    if not text:
        return []

    # Match http/https URLs
    url_pattern = re.compile(
        r'https?://[^\s\)\]\}\>"\'`,;]+', re.IGNORECASE
    )
    urls = url_pattern.findall(text)

    domains = []
    seen = set()
    for url in urls:
        # Clean trailing punctuation
        url = url.rstrip(".)],;:!?'\"")
        domain = canonicalize_domain(url)
        if domain and domain not in seen:
            seen.add(domain)
            domains.append(domain)

    return domains


def extract_homepage_domain(
    repo_homepage: Optional[str],
    readme_text: Optional[str],
    org_blog_url: Optional[str],
) -> Optional[str]:
    """
    Try to extract a product domain from multiple sources, in priority order:
    1. repo.homepage
    2. org profile blog/website
    3. README URLs (prefer 'website', 'demo', 'app', 'waitlist' context)

    Returns the first valid product domain found, or None.
    """
    # Priority 1: repo homepage
    if repo_homepage:
        domain = canonicalize_domain(repo_homepage)
        if domain and is_product_domain(domain):
            return domain

    # Priority 2: org blog URL
    if org_blog_url:
        domain = canonicalize_domain(org_blog_url)
        if domain and is_product_domain(domain):
            return domain

    # Priority 3: README URLs near product-related keywords
    if readme_text:
        product_keywords = re.compile(
            r"(website|homepage|app|demo|waitlist|pricing|product|try it|get started|sign up|launch)",
            re.IGNORECASE,
        )
        lines = readme_text.split("\n")
        for line in lines:
            if product_keywords.search(line):
                urls = re.findall(r'https?://[^\s\)\]\}\>"\'`,;]+', line)
                for url in urls:
                    url = url.rstrip(".)],;:!?'\"")
                    domain = canonicalize_domain(url)
                    if domain and is_product_domain(domain):
                        return domain

        # Fallback: any non-excluded domain in README
        all_domains = extract_domains_from_text(readme_text)
        for domain in all_domains:
            if is_product_domain(domain):
                return domain

    return None


def is_product_domain(domain: str) -> bool:
    """
    Check if a domain looks like a real product/company site
    (not a code host, docs site, social media, etc.).
    """
    if not domain:
        return False

    domain_lower = domain.lower()

    # Check against known non-product domains
    if domain_lower in NON_PRODUCT_DOMAINS:
        return False

    # Check if it's a subdomain of a non-product domain
    for npd in NON_PRODUCT_DOMAINS:
        if domain_lower.endswith("." + npd):
            return False

    # IP addresses are not product domains
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", domain_lower):
        return False

    # Localhost
    if domain_lower.startswith("localhost") or domain_lower.startswith("127."):
        return False

    return True
