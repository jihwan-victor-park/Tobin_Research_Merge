"""Tests for domain extraction and canonicalization."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.utils.domain import (
    canonicalize_domain,
    extract_domains_from_text,
    extract_homepage_domain,
    is_product_domain,
)


class TestCanonicalizeDomain:
    def test_full_url(self):
        assert canonicalize_domain("https://www.example.com/page?q=1") == "example.com"

    def test_http_url(self):
        assert canonicalize_domain("http://example.com") == "example.com"

    def test_bare_domain(self):
        assert canonicalize_domain("example.com") == "example.com"

    def test_www_stripped(self):
        assert canonicalize_domain("www.mysite.io") == "mysite.io"

    def test_trailing_slash(self):
        assert canonicalize_domain("https://mysite.io/") == "mysite.io"

    def test_subdomain(self):
        # tldextract should return registrable domain
        result = canonicalize_domain("https://app.mycompany.com/dashboard")
        assert result == "mycompany.com"

    def test_empty_input(self):
        assert canonicalize_domain("") is None
        assert canonicalize_domain(None) is None

    def test_uppercase(self):
        assert canonicalize_domain("HTTPS://WWW.EXAMPLE.COM") == "example.com"

    def test_co_uk_domain(self):
        result = canonicalize_domain("https://www.company.co.uk")
        assert result == "company.co.uk"


class TestIsProductDomain:
    def test_normal_domain(self):
        assert is_product_domain("mycompany.com") is True

    def test_github(self):
        assert is_product_domain("github.com") is False

    def test_github_io(self):
        assert is_product_domain("github.io") is False

    def test_readthedocs(self):
        assert is_product_domain("readthedocs.io") is False

    def test_medium(self):
        assert is_product_domain("medium.com") is False

    def test_huggingface(self):
        assert is_product_domain("huggingface.co") is False

    def test_localhost(self):
        assert is_product_domain("localhost") is False

    def test_ip_address(self):
        assert is_product_domain("192.168.1.1") is False

    def test_subdomain_of_excluded(self):
        assert is_product_domain("myproject.github.io") is False

    def test_empty(self):
        assert is_product_domain("") is False


class TestExtractDomainsFromText:
    def test_basic_urls(self):
        text = "Visit https://myai.com and https://docs.example.com for info."
        domains = extract_domains_from_text(text)
        assert "myai.com" in domains
        assert "example.com" in domains

    def test_no_urls(self):
        assert extract_domains_from_text("no urls here") == []

    def test_empty(self):
        assert extract_domains_from_text("") == []

    def test_dedup(self):
        text = "https://example.com https://example.com/page"
        domains = extract_domains_from_text(text)
        assert domains.count("example.com") == 1


class TestExtractHomepageDomain:
    def test_repo_homepage_priority(self):
        result = extract_homepage_domain(
            repo_homepage="https://myai-startup.com",
            readme_text="Check https://other.com",
            org_blog_url="https://blog.example.com",
        )
        assert result == "myai-startup.com"

    def test_org_blog_fallback(self):
        result = extract_homepage_domain(
            repo_homepage=None,
            readme_text=None,
            org_blog_url="https://mycompany.io",
        )
        assert result == "mycompany.io"

    def test_readme_with_keyword(self):
        readme = "## Website\nVisit https://cool-ai.com for a demo."
        result = extract_homepage_domain(
            repo_homepage=None,
            readme_text=readme,
            org_blog_url=None,
        )
        assert result == "cool-ai.com"

    def test_skips_github_homepage(self):
        result = extract_homepage_domain(
            repo_homepage="https://github.com/org/repo",
            readme_text=None,
            org_blog_url=None,
        )
        assert result is None

    def test_all_none(self):
        result = extract_homepage_domain(None, None, None)
        assert result is None
