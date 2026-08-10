"""
Wayback AI event-study dater — recover the EXACT month a company added AI to its
homepage, for the PitchBook companies that ADDED AI language 2021->2025.

This upgrades the endpoint diff (2021-vs-2025) into a dated treatment event, so
the AI pivot can be placed on a timeline and related to the ChatGPT inflection
(Nov 2022) and, later, to hiring/funding deltas (difference-in-differences).

Method (per domain):
  1. CDX (ONE call) -> the full list of homepage captures 2019..2025, collapsed
     to one per month (collapse=timestamp:6). This is the cheap half of Wayback.
  2. Binary search the monthly snapshot list for the transition: fetch the page
     text at the midpoint, keyword-test for AI, narrow the interval. ~log2(N)
     page fetches (~6) instead of scanning all ~48 monthly snapshots.
  3. Emit the first month AI language appears = the treatment month.

The AI keyword set is IDENTICAL to the panel predicate in
scripts/pb_longitudinal_repackaging.py (no definitional drift — important for the
paper). Dating uses keyword presence only (free, no LLM); the pivot-vs-washing
call is the separate, already-built classifier.

archive.org rate-limits hard -> low concurrency, per-request timeout+backoff,
and INCREMENTAL checkpointing to output/29_wayback_event_study.csv (resumable: a
re-run skips domains already in the CSV).

Boundary/edge codes (not a dated pivot, but informative):
  ai_before_window  earliest snapshot already shows AI  (left-censored: pivot pre-2019)
  no_ai_on_web      latest snapshot has no AI            (desc says AI, homepage doesn't)
  no_snapshots      no usable captures in the window
  text_unavailable  captures exist but pages wouldn't fetch

    python3 scripts/wayback_ai_event_study.py --limit 300 --workers 4
    python3 scripts/wayback_ai_event_study.py --aggregate   # summarize the CSV so far
"""
from __future__ import annotations
import argparse, csv, os, re, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import duckdb
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); load_dotenv(ROOT / ".env")

DATA = ROOT / "data" / "pb_longitudinal"
PB2021 = str(DATA / "pb2021_company.dat")
PB2025 = [str(DATA / f"pitchbook_{seg}_glob_company.parquet") for seg in ("vc", "pe", "other")]
OUT = ROOT / "output" / "29_wayback_event_study.csv"
CDX = "http://web.archive.org/cdx/search/cdx"
UA = {"User-Agent": "Mozilla/5.0 (academic research; company web-history)"}

# Same AI predicate as the panel, in Python regex form (no definitional drift).
_AI_RE = re.compile(
    r"artificial intelligence|machine learning|\bai[- ]|\bai\b|deep learning|"
    r"neural network|generative ai|large language model|\bllm\b", re.I)


def _domain(url: str) -> str | None:
    if not url:
        return None
    u = url.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    u = u.split("/")[0].split("?")[0].strip()
    return u or None


def added_ai_domains(limit: int) -> list[tuple[str, str]]:
    """(name, domain) for PB companies that were NOT AI in 2021 but ARE in 2025
    and have a Website. Mirrors the panel's 'added' cell exactly."""
    con = duckdb.connect(); con.execute("SET enable_progress_bar=false")
    def ai(col: str) -> str:
        return (f"regexp_matches({col}, 'artificial intelligence|machine learning|"
                " ai |ai-|deep learning|neural network|generative ai|large language model|llm')")
    con.execute(f"""CREATE VIEW y21 AS SELECT CAST(CompanyID AS VARCHAR) id, CompanyName cname,
        lower(coalesce(Description,'')||' '||coalesce(Keywords,'')) x, Website site
        FROM read_csv('{PB2021}', delim='|', header=true, quote=chr(7), ignore_errors=true, all_varchar=true)""")
    con.execute(f"""CREATE VIEW y25 AS SELECT CAST(CompanyID AS VARCHAR) id,
        lower(coalesce(Description,'')||' '||coalesce(Keywords,'')) x, Website site
        FROM read_parquet({PB2025})""")
    rows = con.execute(f"""
        SELECT a.cname, coalesce(b.site, a.site) site
        FROM y21 a JOIN y25 b USING(id)
        WHERE NOT {ai('a.x')} AND {ai('b.x')}
          AND coalesce(b.site, a.site) IS NOT NULL
        ORDER BY random() LIMIT {limit * 4}
    """).fetchall()
    out = []
    for name, site in rows:
        d = _domain(site)
        if d:
            out.append((name, d))
    return out


def cdx_months(domain: str) -> list[str]:
    """One CDX call -> sorted monthly-collapsed 200-capture timestamps, 2019..2025."""
    for _ in range(3):
        try:
            r = requests.get(CDX, params={
                "url": domain, "output": "json", "fl": "timestamp",
                "from": "20190101", "to": "20251231",
                "filter": "statuscode:200", "collapse": "timestamp:6",
            }, timeout=30, headers=UA)
            d = r.json()
            return sorted(row[0] for row in d[1:]) if len(d) > 1 else []
        except Exception:
            time.sleep(3)
    return []


def has_ai(domain: str, ts: str) -> bool | None:
    """Fetch archived homepage text at ts and test the AI keyword set. None=fetch failed."""
    for _ in range(2):
        try:
            r = requests.get(f"http://web.archive.org/web/{ts}id_/http://{domain}",
                             timeout=30, headers=UA)
            if r.status_code != 200 or not r.text:
                time.sleep(2); continue
            soup = BeautifulSoup(r.text, "html.parser")
            for t in soup(["script", "style", "svg"]):
                t.decompose()
            txt = " ".join(soup.get_text(" ").split())[:4000]
            if len(txt) < 40:
                return None
            return bool(_AI_RE.search(txt))
        except Exception:
            time.sleep(3)
    return None


def ym(ts: str) -> str:
    return f"{ts[:4]}-{ts[4:6]}"


def process(name: str, domain: str) -> dict:
    snaps = cdx_months(domain)
    base = {"company": name, "domain": domain, "n_snaps": len(snaps), "n_fetches": 0}
    if len(snaps) < 2:
        return {**base, "treatment_ym": "", "code": "no_snapshots"}

    fetches = 0
    lo, hi = 0, len(snaps) - 1
    lo_ai = has_ai(domain, snaps[lo]); fetches += 1
    if lo_ai is None:
        # earliest unfetchable; walk inward for a usable lower anchor
        while lo < hi and lo_ai is None:
            lo += 1; lo_ai = has_ai(domain, snaps[lo]); fetches += 1
    if lo_ai:  # AI already present at the earliest usable capture
        return {**base, "n_fetches": fetches, "treatment_ym": ym(snaps[lo]), "code": "ai_before_window"}
    hi_ai = has_ai(domain, snaps[hi]); fetches += 1
    if hi_ai is None:
        while hi > lo and hi_ai is None:
            hi -= 1; hi_ai = has_ai(domain, snaps[hi]); fetches += 1
    if hi_ai is None:
        return {**base, "n_fetches": fetches, "treatment_ym": "", "code": "text_unavailable"}
    if not hi_ai:  # never shows AI on the homepage
        return {**base, "n_fetches": fetches, "treatment_ym": "", "code": "no_ai_on_web"}

    # invariant: snaps[lo] no-AI, snaps[hi] has-AI -> find first has-AI month
    while hi - lo > 1:
        mid = (lo + hi) // 2
        v = has_ai(domain, snaps[mid]); fetches += 1
        if v is None:  # unfetchable midpoint: nudge toward hi, keep interval valid
            mid2 = mid + 1
            while mid2 < hi and (v := has_ai(domain, snaps[mid2])) is None:
                mid2 += 1; fetches += 1
            fetches += 1
            if v is None or mid2 >= hi:
                hi = mid; continue
            mid = mid2
        if v:
            hi = mid
        else:
            lo = mid
    return {**base, "n_fetches": fetches, "treatment_ym": ym(snaps[hi]), "code": "dated"}


def aggregate() -> None:
    if not OUT.exists():
        print("no output yet"); return
    rows = list(csv.DictReader(open(OUT)))
    codes = Counter(r["code"] for r in rows)
    print(f"\nWayback AI event-study — {len(rows):,} domains processed")
    for k, v in codes.most_common():
        print(f"  {k:18s}: {v:>5}  ({100*v/len(rows):.0f}%)")
    dated = [r["treatment_ym"] for r in rows if r["code"] == "dated" and r["treatment_ym"]]
    if not dated:
        print("\n(no dated pivots yet)"); return
    by_month = Counter(dated)
    pre = sum(v for m, v in by_month.items() if m < "2022-11")
    post = sum(v for m, v in by_month.items() if m >= "2022-11")
    print(f"\ndated pivots: {len(dated):,}")
    print(f"  before ChatGPT (< 2022-11): {pre:,} ({100*pre/len(dated):.0f}%)")
    print(f"  after  ChatGPT (>=2022-11): {post:,} ({100*post/len(dated):.0f}%)")
    print("\nby half-year:")
    half = Counter()
    for m in dated:
        y, mo = m.split("-"); half[f"{y}-H{1 if int(mo)<=6 else 2}"] += 1
    for k in sorted(half):
        bar = "#" * round(40 * half[k] / max(half.values()))
        print(f"  {k}: {half[k]:>4} {bar}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--aggregate", action="store_true")
    a = ap.parse_args()
    if a.aggregate:
        aggregate(); return

    done = set()
    if OUT.exists():
        done = {r["domain"] for r in csv.DictReader(open(OUT))}
    print(f"already processed: {len(done)}")

    cand = added_ai_domains(a.limit)
    todo = [(n, d) for n, d in cand if d not in done][:a.limit]
    print(f"processing {len(todo)} added-AI domains via Wayback binary-search ({a.workers} workers)...")

    OUT.parent.mkdir(exist_ok=True)
    write_header = not OUT.exists()
    fields = ["company", "domain", "n_snaps", "n_fetches", "treatment_ym", "code"]
    c = Counter(); n = 0
    with open(OUT, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        if write_header:
            w.writeheader()
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            futs = [ex.submit(process, name, dom) for name, dom in todo]
            for f in as_completed(futs):
                r = f.result(); w.writerow(r); fh.flush()
                c[r["code"]] += 1; n += 1
                if n % 20 == 0:
                    print(f"  {n}/{len(todo)}  {dict(c)}", flush=True)

    print(f"\nthis run ({n} domains):")
    for k, v in c.most_common():
        print(f"  {k:18s}: {v}")
    print(f"\nsaved -> {OUT}   (run --aggregate for the timing distribution)")


if __name__ == "__main__":
    main()
