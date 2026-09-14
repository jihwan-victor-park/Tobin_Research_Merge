"""RQ7: what happens when a language model is allowed to fill in attributes
its input text does not state?

The project's enrichment pass once permitted this and the model returned its
prior over "startup" (San Francisco / 2020 / 11-50 employees) rather than
declining. Those values were removed, so the incident is not reproducible from
the live database. This script reruns it as a controlled experiment with known
ground truth, so the distortion can be measured rather than recalled.

Design
------
Sample firms that HAVE a verified country, city and founding year from a
commercial register. Strip every explicit year and place name out of their
description, so the answer is genuinely absent from the input. Then ask the
same model, on the same inputs, under two instructions:

  ESTIMATE  "give your best estimate for every field"        (the failed rule)
  GROUNDED  "report only what the text states, else null"    (the adopted rule)

and compare both to the truth, and to each other.

    railway run -s Postgres -- .venv/bin/python experiments/imputation_experiment.py --n 400
"""
from __future__ import annotations
import argparse, json, math, os, re, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "analysis"))
from _db import q, save, RESULTS  # noqa: E402
import pandas as pd  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
import anthropic  # noqa: E402

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
BATCH = 10

ESTIMATE_PROMPT = """You are enriching a startup database. For each company below, return
your best estimate of these fields. Always provide a value for every field.

Return ONLY a JSON array, one object per company, in the same order:
[{"i":0,"country":"...","city":"...","founded_year":2020,"team_size_bucket":"11-50"}]

team_size_bucket must be one of: "1-10","11-50","51-200","201-500","500+".
"""

GROUNDED_PROMPT = """You are extracting facts from company descriptions. For each company below,
report ONLY what the text explicitly states. If the text does not state a field,
return null for that field. Do not guess, infer, or use outside knowledge.

Return ONLY a JSON array, one object per company, in the same order:
[{"i":0,"country":null,"city":null,"founded_year":null,"team_size_bucket":null}]

team_size_bucket must be one of: "1-10","11-50","51-200","201-500","500+", or null.
"""


def scrub(text: str, city: str | None, country: str | None) -> str:
    """Remove the answer from the input: years and the true place names."""
    t = re.sub(r"\b(1[89]\d{2}|20[0-2]\d)\b", "[YEAR]", text or "")
    for place in filter(None, [city, country]):
        t = re.sub(re.escape(place), "[PLACE]", t, flags=re.IGNORECASE)
    # Common country adjectives / demonyms that leak the answer.
    for w in ["american", "british", "chinese", "indian", "german", "french", "israeli",
              "japanese", "korean", "canadian", "australian", "dutch", "swedish", "spanish",
              "italian", "brazilian", "swiss", "singaporean", "u.s.", "us-based", "uk-based",
              "silicon valley", "bay area"]:
        t = re.sub(rf"\b{re.escape(w)}\b", "[PLACE]", t, flags=re.IGNORECASE)
    return t


def ask(system: str, batch: list[dict]) -> list[dict]:
    payload = "\n\n".join(
        f'{i}. NAME: {b["name"]}\nDESCRIPTION: {b["desc"][:700]}' for i, b in enumerate(batch))
    for attempt in range(4):
        try:
            r = CLIENT.messages.create(
                model=MODEL, max_tokens=2000, system=system,
                messages=[{"role": "user", "content": payload}])
            txt = r.content[0].text.strip()
            m = re.search(r"\[.*\]", txt, re.S)
            return json.loads(m.group(0)) if m else []
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                print(f"    ! batch failed: {type(e).__name__}", file=sys.stderr)
                return []
            time.sleep(2 * (attempt + 1))
    return []


def run_mode(system: str, rows: list[dict], workers: int = 8) -> list[dict]:
    batches = [rows[i:i + BATCH] for i in range(0, len(rows), BATCH)]
    out: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for batch, res in zip(batches, ex.map(lambda b: ask(system, b), batches)):
            by_i = {int(o.get("i", -1)): o for o in res if isinstance(o, dict)}
            for i, src in enumerate(batch):
                o = by_i.get(i, {})
                out.append({**src, "p_country": o.get("country"), "p_city": o.get("city"),
                            "p_year": o.get("founded_year"), "p_team": o.get("team_size_bucket")})
    return out


def tv(p: Counter, qc: Counter) -> float:
    keys = set(p) | set(qc)
    np_, nq = sum(p.values()) or 1, sum(qc.values()) or 1
    return 0.5 * sum(abs(p[k] / np_ - qc[k] / nq) for k in keys)


def jsd(p: Counter, qc: Counter) -> float:
    keys = set(p) | set(qc)
    np_, nq = sum(p.values()) or 1, sum(qc.values()) or 1

    def kl(a, b):
        return sum(a[k] * math.log(a[k] / b[k]) for k in a if a[k] > 0 and b[k] > 0)
    P = {k: p[k] / np_ for k in keys}
    Q = {k: qc[k] / nq for k in keys}
    M = {k: 0.5 * (P[k] + Q[k]) for k in keys}
    return 0.5 * kl(P, M) + 0.5 * kl(Q, M)


# Tokens the model uses to decline. Treating these as answers is what made the
# first pass of this experiment report a 100% fill rate in GROUNDED mode.
DECLINE = {"", "null", "none", "unknown", "n/a", "na", "not stated", "not specified",
           "not mentioned", "unspecified", "not provided", "nan", "unknown city",
           "unknown country", "-", "?"}


def norm(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    s = str(x).strip().lower()
    if s in DECLINE:
        return None
    # Years arrive as 2010, "2010" or 2010.0 depending on the JSON round-trip.
    m = re.fullmatch(r"(1[89]\d{2}|20[0-3]\d)(\.0)?", s)
    return m.group(1) if m else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--from-cache", action="store_true",
                    help="re-analyse the saved model outputs without new API calls")
    a = ap.parse_args()

    if a.from_cache:
        edf = pd.read_csv(os.path.join(RESULTS, "40_imputation_estimate_mode.csv"))
        gdf = pd.read_csv(os.path.join(RESULTS, "41_imputation_grounded_mode.csv"))
        print(f"Re-analysing cached outputs: {len(edf)} estimate rows, {len(gdf)} grounded rows")
        report(edf, gdf)
        return

    print(f"Sampling {a.n} firms with verified country, city, founding year and a description...")
    df = q(f"""
      select id, name, country, city, founded_year, description,
             verification_status::text as bucket
      from companies
      where verification_status::text in ('verified_cb','verified_pb')
        and country is not null and city is not null
        and founded_year between 1990 and 2025
        and description is not null and length(description) >= 120
      order by md5(id::text) limit {a.n}""")
    print(f"  got {len(df)} firms; {df.country.nunique()} countries, "
          f"{df.city.nunique()} cities, years {df.founded_year.min()}-{df.founded_year.max()}")

    rows = [dict(id=int(r.id), name=r["name"], desc=scrub(r.description, r.city, r.country),
                 t_country=r.country, t_city=r.city, t_year=int(r.founded_year), bucket=r.bucket)
            for _, r in df.iterrows()]

    print("\nRunning ESTIMATE mode (model told to always answer)...")
    est = run_mode(ESTIMATE_PROMPT, rows)
    print("Running GROUNDED mode (model told to return null when unstated)...")
    gro = run_mode(GROUNDED_PROMPT, rows)

    edf, gdf = pd.DataFrame(est), pd.DataFrame(gro)
    save(edf.drop(columns=["desc"]), "40_imputation_estimate_mode.csv")
    save(gdf.drop(columns=["desc"]), "41_imputation_grounded_mode.csv")
    report(edf, gdf)


def report(edf, gdf):
    print("\n" + "=" * 74)
    print("1. FILL RATE — does the instruction change whether the model answers?")
    print("=" * 74)
    fill = []
    for label, d in (("ESTIMATE", edf), ("GROUNDED", gdf)):
        for f, col in (("country", "p_country"), ("city", "p_city"),
                       ("founded_year", "p_year"), ("team_size", "p_team")):
            filled = d[col].map(norm).notna().sum()
            fill.append(dict(mode=label, field=f, n=len(d), filled=int(filled),
                             fill_rate=round(100 * filled / len(d), 1)))
    fdf = pd.DataFrame(fill)
    print(fdf.pivot(index="field", columns="mode", values="fill_rate").to_string())
    save(fdf, "42_imputation_fill_rate.csv")

    print("\n" + "=" * 74)
    print("2. WHAT THE MODEL SAYS WHEN IT GUESSES (estimate mode)")
    print("=" * 74)
    conc = []
    for f, col, tcol in (("country", "p_country", "t_country"),
                         ("city", "p_city", "t_city"),
                         ("founded_year", "p_year", "t_year")):
        pred = Counter(edf[col].map(norm).dropna())
        true = Counter(v for v in (norm(x) for x in edf[tcol]) if v)
        if not pred:
            continue
        pm, pn = pred.most_common(1)[0]
        tm, tn = true.most_common(1)[0]
        conc.append(dict(field=f,
                         predicted_mode=pm, predicted_mode_share=round(100 * pn / sum(pred.values()), 1),
                         true_mode=tm, true_mode_share=round(100 * tn / sum(true.values()), 1),
                         distinct_predicted=len(pred), distinct_true=len(true),
                         total_variation=round(tv(pred, true), 3),
                         jensen_shannon=round(jsd(pred, true), 3)))
    cdf = pd.DataFrame(conc)
    print(cdf.to_string(index=False))
    save(cdf, "43_imputation_distribution_distortion.csv")

    print("\nTop-5 predicted vs true, per field:")
    for f, col, tcol in (("country", "p_country", "t_country"),
                         ("city", "p_city", "t_city"), ("founded_year", "p_year", "t_year")):
        pred = Counter(edf[col].map(norm).dropna())
        true = Counter(v for v in (norm(x) for x in edf[tcol]) if v)
        sp, st = sum(pred.values()) or 1, sum(true.values()) or 1
        print(f"\n  {f}:")
        print(f"    {'PREDICTED':<34} {'TRUE'}")
        for (a1, b1), (a2, b2) in zip(pred.most_common(5), true.most_common(5)):
            print(f"    {str(a1)[:22]:<24}{100*b1/sp:>6.1f}%   "
                  f"{str(a2)[:22]:<24}{100*b2/st:>6.1f}%")

    print("\n" + "=" * 74)
    print("3. ACCURACY — is the guess right?")
    print("=" * 74)
    acc = []
    for label, d in (("ESTIMATE", edf), ("GROUNDED", gdf)):
        for f, col, tcol in (("country", "p_country", "t_country"),
                             ("city", "p_city", "t_city")):
            m = d[col].map(norm).notna()
            if m.sum() == 0:
                acc.append(dict(mode=label, field=f, answered=0, correct=0,
                                acc_given_answered=float("nan"), acc_overall=0.0))
                continue
            ok = (d.loc[m, col].map(norm) == d.loc[m, tcol].map(norm)).sum()
            acc.append(dict(mode=label, field=f, answered=int(m.sum()), correct=int(ok),
                            acc_given_answered=round(100 * ok / m.sum(), 1),
                            acc_overall=round(100 * ok / len(d), 1)))
        m = d.p_year.map(norm).notna()
        if m.sum():
            yr = pd.to_numeric(d.loc[m, "p_year"].map(norm), errors="coerce")
            good = yr.notna()
            err = (yr[good] - d.loc[m, "t_year"][good]).abs()
            acc.append(dict(mode=label, field="founded_year(+-2y)", answered=int(m.sum()),
                            correct=int((err <= 2).sum()),
                            acc_given_answered=round(100 * (err <= 2).sum() / m.sum(), 1),
                            acc_overall=round(100 * (err <= 2).sum() / len(d), 1)))
            print(f"  [{label}] founding-year error: median {err.median():.0f}y, "
                  f"mean {err.mean():.1f}y, |err|>5y in {100*(err>5).mean():.0f}% of answers")
    adf = pd.DataFrame(acc)
    print()
    print(adf.to_string(index=False))
    save(adf, "44_imputation_accuracy.csv")

    print("\n" + "=" * 74)
    print("4. THE POINT")
    print("=" * 74)
    e_fill = fdf[(fdf["mode"] == "ESTIMATE")].fill_rate.mean()
    g_fill = fdf[(fdf["mode"] == "GROUNDED")].fill_rate.mean()
    print(f"Mean fill rate:   ESTIMATE {e_fill:.1f}%   GROUNDED {g_fill:.1f}%")
    print("A single line in the instruction moves the fill rate by "
          f"{e_fill - g_fill:.0f} percentage points on identical inputs.")
    print("Values produced under ESTIMATE are indistinguishable from measured")
    print("values once written to a column, which is why the source tag has to be")
    print("stored with the value rather than inferred later.")


if __name__ == "__main__":
    main()
