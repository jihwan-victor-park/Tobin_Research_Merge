# Analysis outputs

Every CSV here is produced by a script in `../analysis/` or `../experiments/`.
`../../paper/CLAIM_EVIDENCE.md` maps each number in the paper to the file it
came from.

## Six files are deliberately NOT committed

They contain row-level records — company names, descriptions, verified
locations — drawn from the two licensed commercial databases, and licensing
does not permit redistributing those rows:

| File | Produced by | Why it is local-only |
|---|---|---|
| `40_imputation_estimate_mode.csv` | `experiments/imputation_experiment.py` | names + verified country/city/year |
| `41_imputation_grounded_mode.csv` | same | same |
| `52_name_variant_pairs.csv` | `experiments/entity_resolution_eval.py` | names + domains |
| `54_er_adjudication_sample.csv` | same | the 215 pairs awaiting author labels |
| `60_ai_label_sample.csv` | `experiments/ai_classifier_eval.py` | names + full descriptions |
| `64_ai_gold_set_for_authors.csv` | same | the 150 firms awaiting author labels |

Regenerate them locally with:

```bash
railway run -s Postgres -- .venv/bin/python experiments/imputation_experiment.py --n 400
railway run -s Postgres -- .venv/bin/python experiments/ai_classifier_eval.py --n 600
railway run -s Postgres -- .venv/bin/python experiments/entity_resolution_eval.py
```

Both experiment scripts accept `--from-cache` to re-analyse without new API
calls. The two labelling files (`54_`, `64_`) should be shared between the
authors directly, not through this repository.

All *aggregate* outputs derived from these files — fill rates, divergences,
accuracy, precision/recall, threshold sweeps — are committed.
