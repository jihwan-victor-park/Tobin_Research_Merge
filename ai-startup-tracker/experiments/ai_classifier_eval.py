"""Validation of the AI label.

Every result in the paper depends on y^AI. The pipeline builds it from a union
of four signals of very different quality, so this measures each one against a
common reference on a stratified sample that spans all three coverage buckets.

Reference labels are produced by an LLM adjudicator reading only the company's
own description under a strict rubric, then a random subset is exported for
author adjudication. The LLM reference is a REFERENCE, not ground truth; the
paper reports it as model-adjudicated and treats the human-labelled subset as
the gold set. Agreement between the two is what licenses the former.

    railway run -s Postgres -- .venv/bin/python experiments/ai_classifier_eval.py --n 600
"""
from __future__ import annotations
import argparse, json, math, os, random, re, sys, time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "analysis"))
from _db import q, save, RESULTS  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))
import anthropic  # noqa: E402

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
BATCH = 8

RUBRIC = """You are labelling companies for an economics research dataset.

Label 1 if artificial intelligence, machine learning, or statistical learning is
CENTRAL to what the company builds or sells -- its product IS an AI/ML system, or
its core capability depends on one.

Label 0 otherwise. In particular label 0 when:
  - AI is only an internal tool or a marketing adjective
  - the description is generic software/SaaS with no learning component
  - the description mentions "data", "analytics" or "automation" with no model
  - there is not enough information to tell (also set "unsure": true)

Return ONLY a JSON array, same order as the input:
[{"i":0,"label":1,"unsure":false}]"""


def ask(batch):
    payload = "\n\n".join(f'{i}. NAME: {b["name"]}\nDESCRIPTION: {b["description"][:600]}'
                          for i, b in enumerate(batch))
    for attempt in range(4):
        try:
            r = CLIENT.messages.create(model=MODEL, max_tokens=1200, system=RUBRIC,
                                       messages=[{"role": "user", "content": payload}])
            m = re.search(r"\[.*\]", r.content[0].text, re.S)
            return json.loads(m.group(0)) if m else []
        except Exception:  # noqa: BLE001
            if attempt == 3:
                return []
            time.sleep(2 * (attempt + 1))
    return []


def prf(pred, truth):
    tp = int(((pred == 1) & (truth == 1)).sum())
    fp = int(((pred == 1) & (truth == 0)).sum())
    fn = int(((pred == 0) & (truth == 1)).sum())
    tn = int(((pred == 0) & (truth == 0)).sum())
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f = 2 * p * r / (p + r) if p == p and r == r and (p + r) else float("nan")
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=p, recall=r, f1=f,
                accuracy=(tp + tn) / max(len(pred), 1))


def boot_ci(pred, truth, stat, B=2000, seed=0):
    rng = np.random.default_rng(seed)
    n = len(pred)
    vals = []
    for _ in range(B):
        idx = rng.integers(0, n, n)
        v = prf(pred.iloc[idx].reset_index(drop=True), truth.iloc[idx].reset_index(drop=True))[stat]
        if v == v:
            vals.append(v)
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))) if vals else (float("nan"),) * 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--from-cache", action="store_true")
    a = ap.parse_args()

    cache = os.path.join(RESULTS, "60_ai_label_sample.csv")
    if a.from_cache and os.path.exists(cache):
        df = pd.read_csv(cache)
        print(f"cached sample: {len(df)} rows")
    else:
        per = a.n // 3
        print(f"Sampling {per} firms from each coverage bucket...")
        frames = []
        for vs, lab in [("verified_cb", "Commercial A"), ("verified_pb", "Commercial B"),
                        ("emerging_github", "Unlisted")]:
            d = q(f"""select id, name, description, verification_status::text as vs,
                        coalesce(cb_ai_tagged,false) as cb_tag,
                        coalesce(ai_score,0) as ai_score,
                        coalesce(ai_mentioned,false) as ai_mentioned,
                        llm_ai_verified
                      from companies
                      where verification_status::text = '{vs}'
                        and description is not null and length(description) >= 80
                      order by md5(id::text) limit {per}""")
            d["bucket"] = lab
            frames.append(d)
        df = pd.concat(frames, ignore_index=True)
        print(f"  {len(df)} firms sampled")

        recs = df.to_dict("records")
        batches = [recs[i:i + BATCH] for i in range(0, len(recs), BATCH)]
        print("Adjudicating with the reference rubric...")
        labels, unsure = {}, {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            for batch, res in zip(batches, ex.map(ask, batches)):
                by_i = {int(o.get("i", -1)): o for o in res if isinstance(o, dict)}
                for i, src in enumerate(batch):
                    o = by_i.get(i, {})
                    labels[src["id"]] = o.get("label")
                    unsure[src["id"]] = bool(o.get("unsure", False))
        df["ref_label"] = df.id.map(labels)
        df["ref_unsure"] = df.id.map(unsure)
        save(df, "60_ai_label_sample.csv")

    ok = df[df.ref_label.isin([0, 1])].copy()
    print(f"\nadjudicated: {len(ok)}/{len(df)}   "
          f"unsure flagged: {int(ok.ref_unsure.sum())} ({100*ok.ref_unsure.mean():.1f}%)")
    print(f"reference AI rate: {100*ok.ref_label.mean():.1f}%")
    truth = ok.ref_label.astype(int).reset_index(drop=True)

    preds = {
        "ai_mentioned (keyword)": (ok.ai_mentioned.astype(bool)).astype(int),
        "ai_score >= 0.5": (ok.ai_score >= 0.5).astype(int),
        "vendor tag": (ok.cb_tag.astype(bool)).astype(int),
        "llm verdict (where run)": (ok.llm_ai_verified.fillna(False).astype(bool)).astype(int),
        "PIPELINE UNION": (ok.cb_tag.astype(bool) | (ok.ai_score >= 0.5)
                           | ok.ai_mentioned.astype(bool)
                           | ok.llm_ai_verified.fillna(False).astype(bool)).astype(int),
    }

    print("\n" + "=" * 74)
    print("Classifier performance against the reference label (all buckets)")
    print("=" * 74)
    rows = []
    for name, p in preds.items():
        p = p.reset_index(drop=True)
        m = prf(p, truth)
        f_lo, f_hi = boot_ci(p, truth, "f1")
        p_lo, p_hi = boot_ci(p, truth, "precision")
        r_lo, r_hi = boot_ci(p, truth, "recall")
        rows.append(dict(classifier=name, tp=m["tp"], fp=m["fp"], fn=m["fn"], tn=m["tn"],
                         precision=round(m["precision"], 3), prec_lo=round(p_lo, 3), prec_hi=round(p_hi, 3),
                         recall=round(m["recall"], 3), rec_lo=round(r_lo, 3), rec_hi=round(r_hi, 3),
                         f1=round(m["f1"], 3), f1_lo=round(f_lo, 3), f1_hi=round(f_hi, 3)))
    res = pd.DataFrame(rows)
    print(res[["classifier", "precision", "prec_lo", "prec_hi", "recall", "rec_lo", "rec_hi",
               "f1", "f1_lo", "f1_hi"]].to_string(index=False))
    save(res, "61_ai_classifier_performance.csv")

    print("\n" + "=" * 74)
    print("Per bucket — does the label behave the same way in each population?")
    print("=" * 74)
    rows = []
    for b, grp in ok.groupby("bucket"):
        t = grp.ref_label.astype(int).reset_index(drop=True)
        for name in ("ai_mentioned (keyword)", "PIPELINE UNION"):
            p = preds[name].reset_index(drop=True)[grp.index.map(
                {v: i for i, v in enumerate(ok.index)}).to_numpy()]
            p = pd.Series(p).reset_index(drop=True)
            m = prf(p, t)
            rows.append(dict(bucket=b, classifier=name, n=len(grp),
                             ref_ai_rate=round(100 * t.mean(), 1),
                             precision=round(m["precision"], 3), recall=round(m["recall"], 3),
                             f1=round(m["f1"], 3)))
    bd = pd.DataFrame(rows)
    print(bd.to_string(index=False))
    save(bd, "62_ai_classifier_by_bucket.csv")

    print("\n" + "=" * 74)
    print("Reference AI rate by bucket — the headline, measured independently")
    print("=" * 74)
    ref = ok.groupby("bucket").agg(n=("ref_label", "size"), ai=("ref_label", "sum"))
    ref["ref_ai_pct"] = (100 * ref.ai / ref.n).round(1)
    # Wilson interval on each bucket
    z = 1.959963984540054
    def wil(x, n):
        p = x / n; d = 1 + z**2/n
        c = (p + z**2/(2*n))/d; h = z*math.sqrt(p*(1-p)/n + z**2/(4*n**2))/d
        return round(100*(c-h), 1), round(100*(c+h), 1)
    ref[["lo", "hi"]] = [wil(int(r.ai), int(r.n)) for _, r in ref.iterrows()]
    print(ref.to_string())
    save(ref.reset_index(), "63_reference_ai_rate_by_bucket.csv")

    samp = ok.sample(min(150, len(ok)), random_state=7)[
        ["id", "name", "description", "bucket", "ref_label", "ref_unsure"]].copy()
    samp["human_label"] = ""
    samp["labeller"] = ""
    save(samp, "64_ai_gold_set_for_authors.csv")
    print(f"\nwrote {len(samp)} rows for author labelling (results/64_ai_gold_set_for_authors.csv).")


if __name__ == "__main__":
    main()
