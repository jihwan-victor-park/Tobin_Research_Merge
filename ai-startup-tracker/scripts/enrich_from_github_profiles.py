"""
Second GitHub pass: read the whole profile, not just the account type.

The first pass asked only whether a login was an Organization and discarded the
rest of the response. Sampling confirmed organisations shows what was thrown
away: created_at on 100% of them, location on 58%, a website on 58%, and a
proper company name on 67% — the exact fields we have been considering paying
an LLM to guess.

Everything here is inference with a stated basis, in the spirit the advisor
asked for: we do not need certainty, we need a signal, a rule, and a recorded
confidence.

  founding year   the GitHub account's creation year. This is an *upper bound*
                  on founding, not the founding date — a company cannot have
                  created its org before it existed, and most create one early.
                  Stored separately from any real founding year, never merged
                  into it, so the distinction survives.
  country         parsed from a free-text location field, which is why the raw
                  string is always kept alongside the parse. "Cologne" resolves
                  through a city gazetteer, "San Francisco, CA" through a US
                  state code, "United States of America" directly.
  domain          the profile's blog/website field.

    python scripts/enrich_from_github_profiles.py --limit 500 --dry-run
    python scripts/enrich_from_github_profiles.py
    python scripts/enrich_from_github_profiles.py --status
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import requests
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.db.connection import get_engine
from backend.utils.country import GLOBE_COUNTRIES, normalize_country
from scripts.import_gov_grants import _hostname

load_dotenv()
TOKEN = os.getenv("GITHUB_TOKEN", "")
API = "https://api.github.com/users/"
HIDDEN = "verification_status = 'emerging_github'"
LOGIN_SYNTAX = r"^[A-Za-z0-9](?:-?[A-Za-z0-9]){0,38}$"

MIN_INTERVAL = 0.72          # 5,000 requests/hour
_pace_lock = threading.Lock()
_next_slot = [0.0]
_sleep_lock = threading.Lock()
_resume_at = [0.0]

US_STATES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il",
    "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt",
    "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri",
    "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
}

# Cities that carry their country unambiguously in startup profiles. Kept small
# and explicit rather than pulling in a geocoding dependency: a wrong guess here
# becomes a country statistic, so only unambiguous entries belong.
CITY_COUNTRY = {
    "san francisco": "United States", "sf": "United States", "new york": "United States",
    "nyc": "United States", "boston": "United States", "seattle": "United States",
    "austin": "United States", "chicago": "United States", "los angeles": "United States",
    "palo alto": "United States", "mountain view": "United States", "menlo park": "United States",
    "cambridge, ma": "United States", "denver": "United States", "atlanta": "United States",
    "san diego": "United States", "miami": "United States", "silicon valley": "United States",
    "bay area": "United States", "brooklyn": "United States",
    "london": "United Kingdom", "manchester": "United Kingdom", "edinburgh": "United Kingdom",
    "oxford": "United Kingdom", "bristol": "United Kingdom",
    "berlin": "Germany", "munich": "Germany", "münchen": "Germany", "hamburg": "Germany",
    "cologne": "Germany", "köln": "Germany", "frankfurt": "Germany", "stuttgart": "Germany",
    "paris": "France", "lyon": "France", "toulouse": "France",
    "amsterdam": "Netherlands", "rotterdam": "Netherlands", "utrecht": "Netherlands",
    "eindhoven": "Netherlands", "delft": "Netherlands",
    "madrid": "Spain", "barcelona": "Spain", "valencia": "Spain",
    "milan": "Italy", "milano": "Italy", "rome": "Italy", "roma": "Italy", "turin": "Italy",
    "stockholm": "Sweden", "gothenburg": "Sweden", "oslo": "Norway",
    "copenhagen": "Denmark", "helsinki": "Finland", "reykjavik": "Iceland",
    "zurich": "Switzerland", "zürich": "Switzerland", "geneva": "Switzerland",
    "lausanne": "Switzerland", "vienna": "Austria", "wien": "Austria",
    "brussels": "Belgium", "ghent": "Belgium", "leuven": "Belgium",
    "lisbon": "Portugal", "porto": "Portugal", "dublin": "Ireland",
    "warsaw": "Poland", "krakow": "Poland", "kraków": "Poland", "wroclaw": "Poland",
    "prague": "Czech Republic", "budapest": "Hungary", "bucharest": "Romania",
    "athens": "Greece", "sofia": "Bulgaria", "zagreb": "Croatia", "ljubljana": "Slovenia",
    "tallinn": "Estonia", "riga": "Latvia", "vilnius": "Lithuania",
    "tel aviv": "Israel", "jerusalem": "Israel", "haifa": "Israel", "herzliya": "Israel",
    "bangalore": "India", "bengaluru": "India", "mumbai": "India", "delhi": "India",
    "new delhi": "India", "hyderabad": "India", "pune": "India", "chennai": "India",
    "gurgaon": "India", "noida": "India",
    "seoul": "South Korea", "busan": "South Korea", "pangyo": "South Korea",
    "tokyo": "Japan", "osaka": "Japan", "kyoto": "Japan", "fukuoka": "Japan",
    "beijing": "China", "shanghai": "China", "shenzhen": "China", "hangzhou": "China",
    "guangzhou": "China", "singapore": "Singapore", "hong kong": "Hong Kong",
    "taipei": "Taiwan", "jakarta": "Indonesia", "bangkok": "Thailand",
    "kuala lumpur": "Malaysia", "manila": "Philippines", "hanoi": "Vietnam",
    "ho chi minh": "Vietnam", "sydney": "Australia", "melbourne": "Australia",
    "brisbane": "Australia", "auckland": "New Zealand",
    "toronto": "Canada", "vancouver": "Canada", "montreal": "Canada", "ottawa": "Canada",
    "waterloo": "Canada", "calgary": "Canada",
    "são paulo": "Brazil", "sao paulo": "Brazil", "rio de janeiro": "Brazil",
    "buenos aires": "Argentina", "santiago": "Chile", "bogota": "Colombia",
    "bogotá": "Colombia", "mexico city": "Mexico", "lima": "Peru",
    "lagos": "Nigeria", "nairobi": "Kenya", "cape town": "South Africa",
    "johannesburg": "South Africa", "cairo": "Egypt", "dubai": "United Arab Emirates",
    "abu dhabi": "United Arab Emirates", "istanbul": "Turkey", "moscow": "Russia",
    "kyiv": "Ukraine", "kiev": "Ukraine", "minsk": "Belarus", "zurich, switzerland": "Switzerland",
}


def parse_country(loc: str) -> tuple[str | None, float]:
    """(country, confidence) from a free-text GitHub location string."""
    if not loc:
        return None, 0.0
    raw = " ".join(loc.split()).strip()
    low = raw.lower()

    # normalize_country echoes back anything it does not recognise, so "Earth"
    # and "remote" would otherwise pass as countries. Only accept a result that
    # is a real country name.
    def as_country(s: str) -> str | None:
        n = normalize_country(s)
        return n if n in GLOBE_COUNTRIES else None

    # An explicit country name for the whole string is the strongest form.
    direct = as_country(raw)
    if direct:
        return direct, 0.95

    parts = [p.strip() for p in re.split(r"[,/|·•]", low) if p.strip()]

    # The city is checked before any two-letter token, because those tokens are
    # genuinely ambiguous: "San Francisco, CA" is California and "Berlin, DE" is
    # Germany, yet CA and DE are also the codes for Canada and Delaware. The city
    # name settles both without guessing.
    for p in parts:
        if p in CITY_COUNTRY:
            return CITY_COUNTRY[p], 0.85
    for city, country in CITY_COUNTRY.items():
        if re.search(rf"\b{re.escape(city)}\b", low):
            return country, 0.75

    # Unknown city with a US state code in the tail — "Fresno, CA".
    if len(parts) > 1 and parts[-1] in US_STATES:
        return "United States", 0.8
    for p in reversed(parts):                       # country usually trails
        cc = as_country(p)
        if cc:
            return cc, 0.9
    return None, 0.0


def ensure_schema(engine) -> None:
    with engine.begin() as c:
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS github_profile (
                company_id    INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
                login         VARCHAR(200),
                display_name  VARCHAR(200),
                location_raw  VARCHAR(200),
                country_guess VARCHAR(96),
                country_conf  REAL,
                blog          VARCHAR(300),
                bio           TEXT,
                created_year  INTEGER,
                public_repos  INTEGER,
                followers     INTEGER,
                fetched_at    TIMESTAMPTZ DEFAULT now()
            )
        """))
        c.execute(text("ALTER TABLE company_enrichment "
                       "ADD COLUMN IF NOT EXISTS github_created_year INTEGER"))
        c.execute(text("ALTER TABLE github_profile ADD COLUMN IF NOT EXISTS bio TEXT"))


def _throttle() -> None:
    while True:
        with _sleep_lock:
            wait = _resume_at[0] - time.time()
        if wait <= 0:
            break
        time.sleep(min(wait, 30))
    with _pace_lock:
        slot = max(time.time(), _next_slot[0])
        _next_slot[0] = slot + MIN_INTERVAL
    delay = slot - time.time()
    if delay > 0:
        time.sleep(delay)


def _park(resp) -> None:
    try:
        until = float(resp.headers.get("X-RateLimit-Reset")) + 5
    except (TypeError, ValueError):
        until = time.time() + 60
    with _sleep_lock:
        if until > _resume_at[0]:
            _resume_at[0] = until
            print(f"  · rate limit — sleeping {max(0,(until-time.time())/60):.1f} min", flush=True)


def fetch(session, login: str):
    for _ in range(2):
        _throttle()
        try:
            r = session.get(API + login, timeout=20)
        except requests.RequestException:
            return None
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return {}
        if r.status_code in (403, 429) and r.headers.get("X-RateLimit-Remaining") == "0":
            _park(r)
            continue
        return None
    return None


def candidates(engine, limit: int):
    """Hidden companies whose name could be a GitHub login and that we have not
    profiled yet. Accounts already known to belong to a person are skipped."""
    with engine.connect() as c:
        return c.execute(text(f"""
            SELECT co.id, co.name, co.domain, co.country
            FROM companies co
            LEFT JOIN github_profile p ON p.company_id = co.id
            LEFT JOIN github_entity_check g ON g.company_id = co.id
            WHERE co.{HIDDEN}
              AND co.source_domain IS NULL
              AND p.company_id IS NULL
              AND co.name ~ '{LOGIN_SYNTAX}'
              AND (g.entity_type IS NULL OR g.entity_type NOT IN ('User', 'missing'))
            LIMIT :lim
        """), {"lim": limit}).mappings().all()


def show_status(engine) -> None:
    with engine.connect() as c:
        done = c.execute(text("SELECT COUNT(*) FROM github_profile")).scalar()
        loc = c.execute(text("SELECT COUNT(*) FROM github_profile WHERE country_guess IS NOT NULL")).scalar()
        yr = c.execute(text("SELECT COUNT(*) FROM github_profile WHERE created_year IS NOT NULL")).scalar()
        web = c.execute(text("SELECT COUNT(*) FROM github_profile WHERE blog IS NOT NULL")).scalar()
    print(f"profiled     : {done:,}")
    for lbl, n in (("country", loc), ("created year", yr), ("website", web)):
        print(f"   {lbl:14} {n:6,} ({n/max(done,1)*100:5.1f}%)")


def run(engine, limit: int, workers: int, dry_run: bool) -> None:
    rows = candidates(engine, limit)
    print(f"to profile: {len(rows):,}", flush=True)
    if not rows:
        return
    session = requests.Session()
    session.headers.update({"Accept": "application/vnd.github+json"})
    if TOKEN:
        session.headers["Authorization"] = f"Bearer {TOKEN}"

    def work(row):
        j = fetch(session, str(row["name"]).strip())
        return row, j

    buf, done, stats = [], 0, {"country": 0, "year": 0, "domain": 0, "bio": 0}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(work, r) for r in rows]):
            row, j = f.result()
            done += 1
            if not j:
                buf.append({"cid": row["id"], "login": str(row["name"])[:200], "name": None,
                            "loc": None, "cc": None, "conf": None, "blog": None,
                            "year": None, "repos": None, "followers": None, "bio": None})
            else:
                cc, conf = parse_country(j.get("location") or "")
                created = (j.get("created_at") or "")[:4]
                buf.append({
                    "cid": row["id"], "login": str(row["name"])[:200],
                    "name": (j.get("name") or None) and j["name"][:200],
                    "loc": (j.get("location") or None) and j["location"][:200],
                    "cc": cc, "conf": conf or None,
                    "blog": (j.get("blog") or None) and j["blog"][:300],
                    "year": int(created) if created.isdigit() else None,
                    "repos": j.get("public_repos"), "followers": j.get("followers"),
                    "bio": (j.get("bio") or None) and " ".join(j["bio"].split())[:500],
                })
                if cc:
                    stats["country"] += 1
                if created.isdigit():
                    stats["year"] += 1
                if j.get("blog"):
                    stats["domain"] += 1
                if j.get("bio"):
                    stats["bio"] = stats.get("bio", 0) + 1
            if len(buf) >= 200 or done == len(rows):
                if not dry_run:
                    flush(engine, buf)
                buf = []
                print(f"  {done}/{len(rows)} — country {stats['country']:,} "
                      f"year {stats['year']:,} web {stats['domain']:,} "
                      f"bio {stats['bio']:,}", flush=True)
    print(f"✓ done ({done:,}) {stats}", flush=True)


def flush(engine, buf: list, attempts: int = 4) -> None:
    """Write a batch, retrying a dropped connection.

    Railway closes idle proxy connections, and a run of this length will hit
    that eventually. Losing hours of remaining work to one transient socket
    error is not acceptable, and the write is safe to repeat: every statement
    is an upsert or a guarded update.
    """
    for attempt in range(attempts):
        try:
            _flush_once(engine, buf)
            return
        except OperationalError as e:
            if attempt == attempts - 1:
                raise
            wait = 5 * (2 ** attempt)
            print(f"  · database connection lost ({e.__class__.__name__}) — "
                  f"retrying in {wait}s", flush=True)
            time.sleep(wait)
            engine.dispose()      # drop the stale pool before reconnecting


def _flush_once(engine, buf: list) -> None:
    """Write the profile rows, then propagate only what the company still lacks."""
    with engine.begin() as c:
        for b in buf:
            c.execute(text("""
                INSERT INTO github_profile (company_id, login, display_name, location_raw,
                    country_guess, country_conf, blog, bio, created_year, public_repos, followers, fetched_at)
                VALUES (:cid, :login, :name, :loc, :cc, :conf, :blog, :bio, :year, :repos, :followers, now())
                ON CONFLICT (company_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name, location_raw = EXCLUDED.location_raw,
                    country_guess = EXCLUDED.country_guess, country_conf = EXCLUDED.country_conf,
                    blog = EXCLUDED.blog, bio = EXCLUDED.bio,
                    created_year = EXCLUDED.created_year,
                    public_repos = EXCLUDED.public_repos, followers = EXCLUDED.followers,
                    fetched_at = now()
            """), b)
            if b["cc"] and (b["conf"] or 0) >= 0.7:
                c.execute(text("UPDATE companies SET country = :cc, updated_at = now() "
                               "WHERE id = :cid AND country IS NULL"),
                          {"cc": b["cc"], "cid": b["cid"]})
            if b["year"]:
                c.execute(text("""
                    INSERT INTO company_enrichment (company_id, github_created_year, sources, enriched_at)
                    VALUES (:cid, :y, CAST(:s AS jsonb), now())
                    ON CONFLICT (company_id) DO UPDATE SET
                        github_created_year = COALESCE(company_enrichment.github_created_year, EXCLUDED.github_created_year),
                        sources = company_enrichment.sources || EXCLUDED.sources
                """), {"cid": b["cid"], "y": b["year"],
                       "s": '{"github_created_year": {"source": "github_profile", '
                            '"confidence": 0.5, "note": "account creation year, upper bound on founding"}}'})
            # The profile bio is often the only sentence anyone has written about
            # these companies, and a description is what every downstream
            # classifier needs. Only fills a genuinely empty description.
            if b.get("bio") and len(b["bio"]) >= 15:
                c.execute(text("""
                    UPDATE companies SET description = :bio, updated_at = now()
                    WHERE id = :cid AND (description IS NULL OR description = '')
                """), {"bio": b["bio"], "cid": b["cid"]})
            dom = _hostname(b["blog"] or "")
            if dom:
                # domain is UNIQUE; leave it alone if any company already holds it
                c.execute(text("""
                    UPDATE companies SET domain = :d, updated_at = now()
                    WHERE id = :cid AND domain IS NULL
                      AND NOT EXISTS (SELECT 1 FROM companies x WHERE x.domain = :d)
                """), {"d": dom, "cid": b["cid"]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    engine = get_engine()
    ensure_schema(engine)
    if a.status:
        show_status(engine)
        return
    run(engine, a.limit, a.workers, a.dry_run)
    print()
    show_status(engine)


if __name__ == "__main__":
    main()
