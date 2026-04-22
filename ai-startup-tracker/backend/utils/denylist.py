"""
Big-tech / non-startup denylist.

Used across scrapers and the dashboard to exclude companies that are clearly
not emerging startups (incumbents, public companies, mega-caps, major research
labs, and generic GitHub org handles that slip in via bulk imports).
"""
from __future__ import annotations


# Lowercase names / handles. Match is case-insensitive on name OR domain root.
BIG_TECH_DENYLIST: frozenset[str] = frozenset({
    # US mega-caps / big tech
    "google", "alphabet", "microsoft", "msft", "apple", "amazon", "aws",
    "meta", "facebook", "netflix", "nvidia", "intel", "amd", "qualcomm",
    "oracle", "ibm", "cisco", "salesforce", "adobe", "sap", "dell", "hp",
    "hpe", "vmware", "servicenow", "workday", "snowflake", "palantir",
    # Established AI labs / "AI incumbents" (not emerging)
    "openai", "anthropic", "anthropics", "deepmind", "google-deepmind",
    "cohere", "cohere-ai", "mistralai", "mistral-ai", "xai", "x-ai",
    "huggingface", "stability-ai", "stabilityai", "eleutherai",
    "allenai", "allen-ai", "ai2",
    # Chinese tech giants
    "alibaba", "tencent", "baidu", "bytedance", "jd", "pinduoduo",
    "meituan", "huawei", "xiaomi", "didi", "netease", "sensetime",
    "megvii", "iflytek", "yitu",
    # Korean / Japanese / Other Asian giants
    "samsung", "lg", "sk", "naver", "kakao", "line", "rakuten", "sony",
    "softbank", "toyota", "honda", "nissan", "hitachi", "fujitsu", "nec",
    # European incumbents
    "siemens", "bosch", "philips", "nokia", "ericsson", "asml", "sap",
    # Ride / consumer tech that keeps showing up in HN hiring
    "uber", "lyft", "doordash", "instacart", "airbnb", "stripe", "square",
    "block", "paypal", "ebay", "twitter", "x", "snap", "pinterest",
    "reddit", "spotify", "shopify", "cloudflare", "datadog", "mongodb",
    "elastic", "gitlab", "atlassian", "dropbox", "zoom", "slack",
    "twilio", "okta", "crowdstrike",
    # Cloud / infra giants
    "redhat", "red-hat", "canonical", "ubuntu", "docker", "hashicorp",
    # Telcos / hardware
    "verizon", "att", "t-mobile", "comcast", "jpmorgan", "goldmansachs",
    # GitHub-org generic handles that aren't companies
    "microsoft-archive", "azure", "googlecloudplatform", "google-research",
    "googleapis", "microsoft-research", "facebookresearch", "meta-llama",
    "pytorch", "tensorflow", "kubernetes", "istio", "envoyproxy",
    "apache", "grpc", "linkedin", "aws-samples", "aws-amplify",
    "microsoftdocs", "dotnet", "nodejs", "python", "rust-lang",
    "containers", "coreos", "fedora", "linuxfoundation",
})


def is_denylisted(name: str | None, domain: str | None = None) -> bool:
    """Return True if the company name or its domain root matches the denylist."""
    if name:
        n = name.strip().lower()
        if n in BIG_TECH_DENYLIST:
            return True
    if domain:
        d = domain.strip().lower()
        # strip www. and take root label (e.g. 'openai.com' -> 'openai')
        if d.startswith("www."):
            d = d[4:]
        root = d.split(".")[0] if d else ""
        if root and root in BIG_TECH_DENYLIST:
            return True
    return False
