# pricing/

`prices.json` is the one price table `scripts/pick.py` reads. These are **list prices**, not metered spend:
a `$/10k` figure from `pick` is *modelled on* the run's own `metrics_totals` tokens × this list price
(CLAUDE.md gotcha 20 — every outward number says which it is).

```json
{"as_of": "2026-09-27", "source": "<url or file>", "unit": "USD per 1M tokens",
 "models": {"<provider>/<model>": {"input": 0.09, "output": 0.34, "as_of": "2026-09-27"}}}
```

- **Key = `<provider>/<model>` exactly as the result file spells them** (`provider` + `model` fields, e.g.
  `openrouter/google/gemma-4-31b-it`, `ollama/gemma4:e2b-it-qat`). No fuzzy matching: a model missing
  here is printed as "cost unknown" and excluded from the cheapest pick, never priced at 0.
- **Hosted rows** were seeded from `docs/probes/matrix-2026-09-27/list_rates.json` (OpenRouter
  `/api/v1/models` list price, fetched 2026-09-27) by a script, not typed. Every row carries its own `as_of`.
- **Local rows** (Ollama / MLX) are `{"input": 0, "output": 0, "note": "runs on the user's machine;
  electricity not metered"}` — `pick` tags them `≈0 local`. Seeded for the committed champions only; add a
  line for any other local model you run.
- These are **not** the repo-radar ledger rates the results page uses (`docs/probes/matrix-2026-09-27/tables.md`
  says `(ledger)`), so a `pick` dollar figure can differ from the page's on the same tokens.

## Updating

1. Fetch the provider's current list price (for OpenRouter: `GET https://openrouter.ai/api/v1/models`;
   ⚠️ the field names and per-token unit were not re-checked when this file was written — confirm them
   against the response before converting to USD per 1M tokens).
2. Write the new numbers with a script from the fetched file, set the row's `as_of` to the fetch date, and
   update the top-level `as_of` / `source`. Never type a price from memory.
3. Re-run `python3 scripts/pick.py <task> ...`; the table prints the `as_of` it used.
