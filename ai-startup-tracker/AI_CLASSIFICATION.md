# AI Startup Classification Strategy

How we determine whether a scraped company is an **AI startup**.

---

## Decision Flow

```
┌─────────────────────────────────────────────────────────────┐
│                  Scraped Company                            │
│          (name + description + website_url)                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │  STEP 1: Keyword Match            │
        │                                   │
        │  name/description contains:       │
        │  "AI", "ML", "LLM", "GPT",       │
        │  "neural", "generative",          │
        │  "machine learning", "NLP"        │
        └───────────────────────────────────┘
                  │               │
               HIT ✓           NO HIT
                  │               │
                  ▼               ▼
          ┌──────────┐    ┌───────────────────────────────┐
          │  AI = C?  │    │  STEP 2: Website Scrape       │
          │  score=1  │    │                               │
          │  (fast,   │    │  Fetch homepage text          │
          │   free)   │    │  → run same keyword check     │
          └──────────┘    └───────────────────────────────┘
                                    │               │
                                 HIT ✓           NO HIT
                                    │               │
                                    ▼               ▼
                            ┌──────────┐   ┌────────────────────────┐
                            │  AI = C?  │   │  STEP 3: LLM Judge     │
                            │  score=1  │   │                        │
                            └──────────┘   │  Send to Claude:       │
                                           │  "Is this an AI        │
                                           │   startup? yes/no +    │
                                           │   confidence"          │
                                           │                        │
                                           │  (only ~20% of total   │
                                           │   reach this step)     │
                                           └────────────────────────┘
                                                     │
                                        ┌────────────┴────────────┐
                                     YES (≥0.7)              NO (<0.7)
                                        │                         │
                                        ▼                         ▼
                                 ┌──────────┐             ┌──────────────┐
                                 │  AI = C?  │             │  AI = N?     │
                                 │  score=   │             │  score=      │
                                 │confidence │             │ confidence   │
                                 └──────────┘             └──────────────┘
```

---

## Why This Order?

| Step              | Coverage            | Speed        | Cost         |
| ----------------- | ------------------- | ------------ | ------------ |
| 1. Keyword match  | ~40% of AI startups | Instant      | Free         |
| 2. Website scrape | +~40% more          | 2–5s/company | Free         |
| 3. LLM judge      | Remaining ~20%      | 1–3s/company | ~$0.001/call |

**Total LLM calls ≈ 20% of dataset** → fast + cheap.

---

## What Gets Stored

```
companies table
├── ai_score        (0.0 – 1.0)   ← confidence that it's an AI startup
├── ai_tags         (text[])       ← ["LLM", "computer vision", ...]
└── classification  step used      ← "keyword" | "website" | "llm"
```

---

## AI Keywords Used

```python
STRONG = ["artificial intelligence", "machine learning", "large language model",
          "generative AI", "deep learning", "neural network", "LLM", "GPT",
          "NLP", "computer vision", "reinforcement learning"]

MEDIUM = ["AI-powered", "AI-driven", "ML model", "predictive", "automation",
          "intelligent", "smart", "recommendation engine", "chatbot"]
```

`STRONG` hit → `ai_score = 1.0`
`MEDIUM` hit only → `ai_score = 0.7` → goes to LLM for confirmation

---

## Run It

```bash
# Step 1+2 only (fast, no API cost)
python scripts/classify_ai_startups.py --method keyword

# Full pipeline (keyword → website → LLM)
python scripts/classify_ai_startups.py --method full

# LLM only on unclassified companies
python scripts/classify_ai_startups.py --method llm-only
```
