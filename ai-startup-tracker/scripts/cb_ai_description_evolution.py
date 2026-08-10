"""
How AI companies' DESCRIPTIONS changed, 2023 -> 2025 (Crunchbase full-text).

Complements the identity/category panel (cb_ai_identity_panel.py): instead of
"did the AI category get added", this asks "how did the description TEXT change"
for the AI cohort — did they refresh their pitch with generative-AI-era
vocabulary (LLM, generative AI, agents, copilots, RAG...)?

Join cb2023 & cb2025 organization_descriptions on org uuid, restrict to AI-2025
companies present in 2023, and detect vocabulary that APPEARED in the 2025
description but was absent in 2023. Split by identity origin (already-AI-2023 vs
repackaged-from-non-AI). Aggregates only.

Outputs:
  37_cb_ai_desc_change_summary.csv     % adding AI / gen-AI language, by origin
  38_cb_ai_genai_terms_surge.csv       which gen-AI terms were newly added most

    python3 scripts/cb_ai_description_evolution.py
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "pb_longitudinal"
OUT = ROOT / "output"

AICAT = ("(lower(category_list) LIKE '%artificial intelligence%' "
         "OR lower(category_list) LIKE '%machine learning%' "
         "OR lower(category_list) LIKE '%generative%' "
         "OR lower(category_list) LIKE '%natural language%' "
         "OR lower(category_list) LIKE '%computer vision%' "
         "OR lower(category_list) LIKE '%deep learning%' "
         "OR lower(category_list) LIKE '%neural network%' "
         "OR lower(category_groups_list) LIKE '%artificial intelligence%')")

# any-AI vocabulary (broad) and the generative-AI-era vocabulary (post-2022)
ANY_AI = re.compile(r"artificial intelligence|machine learning|deep learning|"
                    r"neural network|\bai[- ]|ai-powered|ai-driven|\bml\b", re.I)
GENAI = {
    "generative ai": r"generative ai|gen-?ai\b",
    "llm": r"\bllm\b|large language model",
    "gpt / chatgpt": r"\bgpt\b|chatgpt",
    "agents": r"\bai agent|agentic|autonomous agent",
    "copilot": r"co-?pilot",
    "transformer/diffusion": r"transformer model|diffusion model|stable diffusion",
    "foundation model": r"foundation model",
    "RAG/prompt": r"retrieval[- ]augmented|\brag\b|prompt engineering",
    "multimodal": r"multi-?modal",
    "openai/anthropic": r"openai|anthropic|hugging ?face",
}
GENAI_ANY = re.compile("|".join(v for v in GENAI.values()), re.I)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", default="2026", choices=["2025", "2026"],
                    help="end year of the comparison (default 2026, falls back to 2025)")
    a = ap.parse_args()
    to = a.to
    dto = D / f"cb{to}_organization_descriptions.parquet"
    org_to = D / f"cb{to}_organizations.parquet"
    if not dto.exists() or not org_to.exists():
        if to == "2026":
            print(f"cb2026 files missing — falling back to 2025."); to = "2025"
            dto = D / "cb2025_organization_descriptions.parquet"
            org_to = D / "cb2025_organizations.parquet"
        if not dto.exists():
            print(f"MISSING {dto} — extract organization_descriptions first."); return

    con = duckdb.connect(); con.execute("SET enable_progress_bar=false")
    print(f"building AI-{to} cohort with 2023 & {to} descriptions...")
    df = con.execute(f"""
        SELECT a.uuid, o23.is_ai23,
               d23.description AS t23, dN.description AS t25
        FROM (SELECT uuid, {AICAT} AS is_ai FROM read_parquet('{org_to}')) a
        JOIN (SELECT uuid, {AICAT} AS is_ai23 FROM read_parquet('{D}/cb2023_organizations.parquet')) o23
             ON a.uuid=o23.uuid
        JOIN read_parquet('{D}/cb2023_organization_descriptions.parquet') d23 ON a.uuid=d23.uuid
        JOIN read_parquet('{dto}') dN ON a.uuid=dN.uuid
        WHERE a.is_ai AND d23.description IS NOT NULL AND dN.description IS NOT NULL
          AND length(d23.description) > 20 AND length(dN.description) > 20
    """).fetchdf()
    print(f"  {len(df):,} AI-{to} companies with both 2023 & {to} descriptions")

    t23 = df["t23"].fillna("").str.lower()
    t25 = df["t25"].fillna("").str.lower()
    df["ai23_txt"] = t23.apply(lambda s: bool(ANY_AI.search(s)))
    df["ai25_txt"] = t25.apply(lambda s: bool(ANY_AI.search(s)))
    df["genai23"] = t23.apply(lambda s: bool(GENAI_ANY.search(s)))
    df["genai25"] = t25.apply(lambda s: bool(GENAI_ANY.search(s)))
    df["added_ai_lang"] = (~df["ai23_txt"]) & df["ai25_txt"]
    df["added_genai_lang"] = (~df["genai23"]) & df["genai25"]
    # did the text change at all (token Jaccard < 0.9 = meaningful rewrite)
    def jac(a, b):
        A, B = set(a.split()), set(b.split())
        return len(A & B) / len(A | B) if (A | B) else 1.0
    df["rewrote"] = [jac(a, b) < 0.9 for a, b in zip(t23, t25)]

    df["origin"] = df["is_ai23"].map({True: "already AI 2023", False: "repackaged (non-AI 2023)"})
    rows = []
    for label in ["already AI 2023", "repackaged (non-AI 2023)", "ALL"]:
        sub = df if label == "ALL" else df[df.origin == label]
        n = len(sub)
        rows.append({
            "cohort": label, "companies": n,
            "added_AI_language_pct": round(100*sub.added_ai_lang.mean(), 1),
            "added_genAI_language_pct": round(100*sub.added_genai_lang.mean(), 1),
            f"mentions_genAI_{to}_pct": round(100*sub.genai25.mean(), 1),
            "rewrote_desc_pct": round(100*sub.rewrote.mean(), 1),
        })
    summ = pd.DataFrame(rows)
    print(f"\n=== AI companies: description change 2023 -> {to} ===")
    print(summ.to_string(index=False))
    summ.to_csv(OUT / f"37_cb_ai_desc_change_summary_{to}.csv", index=False)

    # which gen-AI terms were newly ADDED (absent 2023, present 2025) ------
    rows = []
    for term, pat in GENAI.items():
        rx = re.compile(pat, re.I)
        newly = sum((not rx.search(a)) and bool(rx.search(b)) for a, b in zip(t23, t25))
        in25 = int(t25.apply(lambda s: bool(rx.search(s))).sum())
        rows.append({"genai_term": term, f"companies_mentioning_{to}": in25,
                     "newly_added_since_2023": newly})
    terms = pd.DataFrame(rows).sort_values("newly_added_since_2023", ascending=False)
    print("\n=== Gen-AI vocabulary newly added to AI-company descriptions ===")
    print(terms.to_string(index=False))
    terms.to_csv(OUT / f"38_cb_ai_genai_terms_surge_{to}.csv", index=False)

    print(f"\nsaved -> output/37_cb_ai_desc_change_summary_{to}.csv, 38_cb_ai_genai_terms_surge_{to}.csv")


if __name__ == "__main__":
    main()
