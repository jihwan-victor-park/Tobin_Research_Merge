"""
Wayback AI-repackaging for the HIDDEN companies (not in CB/PB, so no snapshot
panel exists for them). Uses the Internet Archive to reconstruct each hidden
company's homepage text at ~2021 and ~2025, then runs the same diff-classifier
(scripts/ai_repackaging.py) to detect who repackaged around AI.

archive.org rate-limits hard, so: low concurrency, per-company timeouts, and
INCREMENTAL checkpointing to output/28_wayback_repackaging.csv (resumable — a
re-run skips domains already in the CSV). Many hidden companies are recent and
have no 2021 snapshot; those are recorded as 'no_2021_snapshot' and skipped.

    python scripts/wayback_repackaging.py --limit 300 --workers 5
"""
from __future__ import annotations
import argparse, csv, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); load_dotenv(ROOT / ".env")
from scripts.ai_repackaging import classify_change, CLASSES

OUT = ROOT / "output" / "28_wayback_repackaging.csv"
CDX = "http://web.archive.org/cdx/search/cdx"
UA = {"User-Agent": "Mozilla/5.0 (research)"}


def snap(domain, year):
    for _ in range(2):
        try:
            r = requests.get(CDX, params={"url": domain, "output": "json", "fl": "timestamp",
                "from": f"{year}0101", "to": f"{year}1231", "limit": 1,
                "filter": "statuscode:200"}, timeout=25)
            d = r.json()
            return d[1][0] if len(d) > 1 else None
        except Exception:
            time.sleep(3)
    return None


def fetch_text(domain, ts):
    try:
        r = requests.get(f"http://web.archive.org/web/{ts}id_/http://{domain}",
                         timeout=30, headers=UA)
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "nav", "footer", "svg"]):
            t.decompose()
        return " ".join(soup.get_text(" ").split())[:1500] or None
    except Exception:
        return None


def process(name, domain):
    ts21, ts25 = snap(domain, "2021"), snap(domain, "2025")
    if not ts21:
        return {"company": name, "domain": domain, "change": "no_2021_snapshot", "why": ""}
    if not ts25:
        return {"company": name, "domain": domain, "change": "no_2025_snapshot", "why": ""}
    t21, t25 = fetch_text(domain, ts21), fetch_text(domain, ts25)
    if not t21 or not t25 or len(t21) < 40 or len(t25) < 40:
        return {"company": name, "domain": domain, "change": "text_unavailable", "why": ""}
    res = classify_change(name, t21, t25)
    return {"company": name, "domain": domain,
            "change": res["change"] if res else "PARSE_FAIL",
            "why": (res or {}).get("why", "")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--workers", type=int, default=5)
    a = ap.parse_args()

    done = set()
    if OUT.exists():
        with open(OUT) as f:
            done = {r["domain"] for r in csv.DictReader(f)}
    print(f"already processed: {len(done)}")

    eng = create_engine(os.getenv("RAILWAY_DATABASE_URL"))
    with eng.connect() as c:
        rows = c.execute(text("""
            SELECT name, lower(domain) domain FROM companies
            WHERE verification_status = 'emerging_github' AND domain IS NOT NULL
              AND (cb_ai_tagged OR ai_score>=0.5 OR ai_mentioned OR llm_ai_verified)
            ORDER BY random() LIMIT :lim
        """), {"lim": a.limit * 3}).fetchall()
    todo = [(n, d) for n, d in rows if d not in done][:a.limit]
    print(f"processing {len(todo)} hidden AI domains via Wayback ({a.workers} workers)...")

    OUT.parent.mkdir(exist_ok=True)
    write_header = not OUT.exists()
    from collections import Counter
    c = Counter(); n = 0
    with open(OUT, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["company", "domain", "change", "why"])
        if write_header:
            w.writeheader()
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            futs = [ex.submit(process, name, dom) for name, dom in todo]
            for f in as_completed(futs):
                r = f.result(); w.writerow(r); fh.flush()
                c[r["change"]] += 1; n += 1
                if n % 25 == 0:
                    print(f"  {n}/{len(todo)}  {dict(c)}", flush=True)

    print("\nHidden-company Wayback repackaging (this run):")
    usable = sum(c[k] for k in CLASSES)
    for k in CLASSES + ["no_2021_snapshot", "no_2025_snapshot", "text_unavailable", "PARSE_FAIL"]:
        if c.get(k):
            print(f"  {k:18s}: {c[k]}")
    if usable:
        rep = c.get("repackaged_to_ai", 0)
        print(f"\n  of {usable} companies with both snapshots: "
              f"{rep} repackaged_to_ai ({100*rep/usable:.0f}%)")


if __name__ == "__main__":
    main()
