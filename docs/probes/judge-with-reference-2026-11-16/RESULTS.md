# Judge with reference: results (recap only, nimble `13ae0a506102`, 16–17 Nov 2026)

> **EVIDENCE CELL:** recap `check_coverage`, both splits pooled (n = 91, 10 key fails): A0 (no reference) vs A1 (the key's
> `must_mention` list in the state), same judge build, same day, 3 fresh loads per arm. Raw agreement with the key **67.0% → 92.3%,
> +25.3 pp**. The flip rule (≥ 10 pp) **fires**.
>
> **Not evidence:** the heldout/train sub-splits (small n: train has 2 key fails); the n-a7 pass 1 columns (a different judge
> build, see below); the A0-run-1-vs-n-a7 flip counts; `partial_A0_run3_interrupted.jsonl` (19 decisions from a run that
> died at 00:02, kept only as a cross-load determinism check: 0 of 19 verdicts and 0.0 max |Δp| against the fresh run 3).

**κ here is against our key, not against humans.** n-a7b found wrong keys in 4 of 8 audited failing cells. A judge shown the
key's own spec can inherit those errors, so a higher κ in A1 means "agrees more with our key", not "more correct".

**Not one-to-one comparable with the 30 Sep / 18 Oct nimble numbers.** Ollama 0.40.16 refused the n-a7 build (`24e550a16a70`,
Q8_0 GGUF, `BLOCKED.md`). Both arms here ran on today's registry `nimble:latest` **`13ae0a506102`** (mxfp8 safetensors, num_ctx 8192,
`runtime.json` entry 3). A0 was re-measured on it. The decision is A1 − A0 within this one judge. The old build is backed up at
`~/ollama-backup/nimble-bbf1d6fc-2026-11-16/` (lane report).

## What moved (read this before the headline)

- **Coverage.** The key passes 81 of 91, so always-pass scores 89.0%. Without the reference, nimble sits **22 pp below
  always-pass** (TPR 0.716: it fails 23 recaps the key passes). With the list it rises to **3.3 pp above** always-pass. Almost
  all of the +25.3 pp is the judge *no longer failing good recaps* (TPR 0.716 → 0.988). It catches **4 of 10** key fails, up
  from 3 of 10. κ goes from 0.009 to 0.496, inside the predicted 0.4–0.7. On train (2 key fails) κ stays negative in both arms.
- **Compression.** With the ratio given, nimble passes **every one of 119** decisions. A1 equals always-pass exactly (κ 0.000,
  TNR 0/37). Without it, nimble caught 4 of 37. The reference made compression slightly worse (−3.4 pp).
- **Stability.** All 3 runs of each arm are identical, decision by decision (0 flips across runs in every cell). pass^3 therefore
  equals single-run agreement, and its delta matches the raw delta. Run 3's A0 load took about 2× the wall time of runs 1–2 (another
  job held the GPU, ⚠️ inferred from timing only). The verdicts did not move.

## Prediction vs result (prediction 64b4113, before any run; dated note be95473)

| cell | predicted A1 − A0 | result | predicted κ A1 | result κ A1 | verdict |
|---|---|---|---|---|---|
| recap coverage | +10 to +25 pp | **+25.3 pp** | 0.4–0.7 | 0.496 | direction held, the flip rule fires; **size 0.3 pp above the predicted upper bound** (one decision: 25 pp of 91 = 22.75, observed 23) |
| recap compression | −5 to +5 pp | −3.4 pp | < 0.2 | 0.000 | held |

Headline refutation conditions: "no cell moves ≥ 10 pp" did not happen. "Compression moves ≥ 10 pp" did not happen. **The headline
holds on recap.** The transcript-en rows (including abstention, the cell predicted to fire by construction) were not run (operator cut,
21:10), so they stay untested.

**Kill clause.** A0 run 1 vs n-a7 pass 1: coverage 10/91 flips, compression 4/119, so 14/210 = 6.7% > 2%. As the dated note says,
this cannot separate a runtime move from the judge move (both changed). The A0 rerun is the baseline and n-a7 is context only.

## For the decider (C5)

Recap was decisive for the flip condition: one cell moved ≥ 10 points, so the claim narrows to **"without the reference, a local
judge cannot replace the answer key"**. The detail matters for the client sentence. On the presence check, the reference turns the
judge into a near-lookup over the key's own list, mostly by stopping false fails, and it still misses 6 of 10 real failures. On the
length check, the reference makes the judge a rubber stamp. So "with the reference" is not "can replace the key" either: the gain
comes from the key, and it does not reach length checks.

What recap cannot answer: whether the gain survives long, paraphrase-heavy inputs (transcript-en coverage), whether a list overcomes
omission blindness (transcript-en action_items), and the abstention row. transcript-en ≈ 5.5 h GPU at n-a7's timings (⚠️ not
re-measured on this build).

## Tables (re-derived by `python3 -u judge_ref.py check`)

| cell | split | n (key fail) | arm | κ run 1 · 2 · 3 | raw agree run 1 · 2 · 3 | raw pooled | pass^3 | flips across runs |
|---|---|---|---|---|---|---|---|---|
| recap coverage | both | 91 (10) | A0 | 0.009 · 0.009 · 0.009 | 61/91 · 61/91 · 61/91 | 67.0% | 61/91 (67.0%) | 0 |
| recap coverage | both | 91 (10) | A1 | 0.496 · 0.496 · 0.496 | 84/91 · 84/91 · 84/91 | 92.3% | 84/91 (92.3%) | 0 |
| recap coverage | heldout | 49 (8) | A0 | 0.006 · 0.006 · 0.006 | 29/49 · 29/49 · 29/49 | 59.2% | 29/49 (59.2%) | 0 |
| recap coverage | heldout | 49 (8) | A1 | 0.626 · 0.626 · 0.626 | 45/49 · 45/49 · 45/49 | 91.8% | 45/49 (91.8%) | 0 |
| recap coverage | train | 42 (2) | A0 | -0.082 · -0.082 · -0.082 | 32/42 · 32/42 · 32/42 | 76.2% | 32/42 (76.2%) | 0 |
| recap coverage | train | 42 (2) | A1 | -0.033 · -0.033 · -0.033 | 39/42 · 39/42 · 39/42 | 92.9% | 39/42 (92.9%) | 0 |
| recap compression | both | 119 (37) | A0 | 0.143 · 0.143 · 0.143 | 86/119 · 86/119 · 86/119 | 72.3% | 86/119 (72.3%) | 0 |
| recap compression | both | 119 (37) | A1 | 0.000 · 0.000 · 0.000 | 82/119 · 82/119 · 82/119 | 68.9% | 82/119 (68.9%) | 0 |
| recap compression | heldout | 70 (13) | A0 | 0.228 · 0.228 · 0.228 | 59/70 · 59/70 · 59/70 | 84.3% | 59/70 (84.3%) | 0 |
| recap compression | heldout | 70 (13) | A1 | 0.000 · 0.000 · 0.000 | 57/70 · 57/70 · 57/70 | 81.4% | 57/70 (81.4%) | 0 |
| recap compression | train | 49 (24) | A0 | 0.085 · 0.085 · 0.085 | 27/49 · 27/49 · 27/49 | 55.1% | 27/49 (55.1%) | 0 |
| recap compression | train | 49 (24) | A1 | 0.000 · 0.000 · 0.000 | 25/49 · 25/49 · 25/49 | 51.0% | 25/49 (51.0%) | 0 |

| cell | split | A1 − A0 raw (pp) | A1 − A0 pass^3 (pp) | flip rule (≥ 10 pp) | A0 run 1 vs n-a7 pass 1 flips | n-a7 pass 1 κ · raw (its 18 Oct key) | n-a7 pass 1 κ · raw (today's key) |
|---|---|---|---|---|---|---|---|
| recap coverage | both | +25.3 | +25.3 | FIRES | 10/91 | 0.226 · 64/91 | 0.095 · 65/91 |
| recap coverage | heldout | +32.7 | +32.7 | FIRES | 7/49 | 0.481 · 38/49 | 0.171 · 34/49 |
| recap coverage | train | +16.7 | +16.7 | FIRES | 3/42 | -0.231 · 26/42 | -0.085 · 31/42 |
| recap compression | both | -3.4 | -3.4 | does not fire | 4/119 | 0.000 · 82/119 | 0.000 · 82/119 |
| recap compression | heldout | -2.9 | -2.9 | does not fire | 2/70 | 0.000 · 57/70 | 0.000 · 57/70 |
| recap compression | train | -4.1 | -4.1 | does not fire | 2/49 | 0.000 · 25/49 | 0.000 · 25/49 |

| cell | split | always-pass raw (key pass rate) | arm | raw run 1 | raw − always-pass (pp) | TPR | TNR (key fails caught) | AUROC |
|---|---|---|---|---|---|---|---|---|
| recap coverage | both | 89.0% (81/91) | A0 | 67.0% | -22.0 | 0.716 | 0.300 (3/10) | 0.602 |
| recap coverage | both | 89.0% (81/91) | A1 | 92.3% | +3.3 | 0.988 | 0.400 (4/10) | 0.747 |
| recap coverage | heldout | 83.7% (41/49) | A0 | 59.2% | -24.5 | 0.634 | 0.375 (3/8) | 0.555 |
| recap coverage | heldout | 83.7% (41/49) | A1 | 91.8% | +8.2 | 1.000 | 0.500 (4/8) | 0.799 |
| recap coverage | train | 95.2% (40/42) | A0 | 76.2% | -19.0 | 0.800 | 0.000 (0/2) | 0.700 |
| recap coverage | train | 95.2% (40/42) | A1 | 92.9% | -2.4 | 0.975 | 0.000 (0/2) | 0.762 |
| recap compression | both | 68.9% (82/119) | A0 | 72.3% | +3.4 | 1.000 | 0.108 (4/37) | 0.876 |
| recap compression | both | 68.9% (82/119) | A1 | 68.9% | +0.0 | 1.000 | 0.000 (0/37) | 0.735 |
| recap compression | heldout | 81.4% (57/70) | A0 | 84.3% | +2.9 | 1.000 | 0.154 (2/13) | 0.837 |
| recap compression | heldout | 81.4% (57/70) | A1 | 81.4% | +0.0 | 1.000 | 0.000 (0/13) | 0.706 |
| recap compression | train | 51.0% (25/49) | A0 | 55.1% | +4.1 | 1.000 | 0.083 (2/24) | 0.913 |
| recap compression | train | 51.0% (25/49) | A1 | 51.0% | +0.0 | 1.000 | 0.000 (0/24) | 0.775 |
