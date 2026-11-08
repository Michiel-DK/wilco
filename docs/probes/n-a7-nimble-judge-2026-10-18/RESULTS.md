# N-A7 / J7 — nimble as a yes/no judge over the stored 27 Sep outputs, vs our deterministic key

> **EVIDENCE CELL:** nimble:latest (`24e550a16a70`, Ollama 0.40.2, KV/flash `unset`/`unset`) `noul` verdicts at p ≥ 0.5 vs
> the deterministic key (`evals/<exam>/properties.py` re-run on the stored `got`), per check, **applicable** decisions, held-out and
> train stated separately, on the 27 Sep matrix outputs of **recap, reply-draft and transcript-en** (call-fields is not in the matrix).
> Pass 1 = all 4,244 decisions (88 refused by the window, kept out); **pass 2 = recap only (595 decisions)**, see the amendment.
>
> **Not evidence:** the 0.5 threshold (AUROC is printed beside every κ so the cut is not the finding; the in-sample "best threshold"
> below is illustrative only) · the models that produced the outputs (they are not under test here; their scores are not re-read) ·
> call-fields (absent from the matrix, not judged) · any cell with < 10 key failures (printed, marked *underpowered*, not read) ·
> stability on reply-draft and transcript-en (one pass only).

## Pre-registration — written 2026-10-18T11:12Z (13:12 CEST), BEFORE the first judged decision

Committed locally in the worktree before `judge_probe.py run 1` started; the commit time precedes `raw_pass1.jsonl`.

### Setup (verified this session, before inference)

- Judge: `nimble:latest`, id `24e550a16a70` (`ollama list`), Ollama `0.40.2` (`/api/version`), server
  `OLLAMA_KV_CACHE_TYPE` / `OLLAMA_FLASH_ATTENTION` = `unset` / `unset` (read with `runner.ollama_server_settings()`,
  the `lsof` → `ps -E` path of gotcha 21). Window: `num_ctx 8194` (`ollama show`, `ollama ps`). The endpoint
  REFUSES an over-window prompt with HTTP 400 "input is never truncated" (seen on `longcall-support-heldout-2`,
  8,562 tokens), so no decision is silently truncated; refused decisions are counted and kept out of every κ.
- Data: `docs/probes/matrix-2026-09-27/results/` — recap (7 models × 17 cases), reply-draft (7 × 17),
  transcript-en (11 × 32) = 590 stored outputs. **call-fields is not in the 27 Sep matrix; it is not judged.**
- Key: each check's verdict re-derived by running `evals/<exam>/properties.py` (master `d5da44d`) on the stored
  `got`. All-checks-pass reproduces the stored `passed` on **590 / 590** outputs (0 disagreements).
- Decisions: one `noul` question per (exam, output, check), 20 checks, **4,244 decisions per pass**, two passes
  (pass 2 after `ollama stop nimble`). `state = {input: <case input>, output: <the stored got, JSON-serialised>}`.
  "yes" (p ≥ 0.5) = the check passes. The question text is the check's definition in plain words
  (`judge_probe.py` `Q`); **no `expected` value is ever shown to the judge** (no `must_mention`, `must_commit`,
  `max_ratio`, owner map, withdrawn list) — the judge answers the judgement the key approximates, from input +
  output alone.
- One question per request: batching all 8 transcript-en questions in one request moved p by up to 0.108
  (`withdrawn_excluded`, longcall-pricing-heldout-1, Sol) against single-question calls, so batching is not used.
- Latency measured: 1.3 s (short input, cold state) · ~2 s per further question on a cached 4.5k-token state ·
  17–33 s for a 4.5k–6.9k-token state cold. The brief's "~90 ms a decision" does not hold; expect ~2 h a pass.
- **Applicable vs vacuous.** A check whose expected field is absent on a case (e.g. `check_coverage` with no
  `must_mention`, `check_action_owner` outside the longcall band) passes VACUOUSLY in the key; the judge cannot
  know that. Headline numbers are on **applicable** decisions; the all-decisions number is reported beside it.
  `check_ignores_planted_instructions` has 0 applicable decisions (the 27 Sep outputs predate the M1 injection cases).

### Key prevalence (applicable decisions; key failures in brackets) — computed before inference

| exam | check | heldout n (fail) | train n (fail) |
|---|---|---|---|
| recap | grounded | 70 (1) | 49 (0) |
| recap | coverage | 49 (16) | 42 (7) |
| recap | compression | 70 (13) | 49 (24) |
| recap | abstention | 70 (7) | 49 (0) |
| recap | output_shape | 70 (0) | 49 (0) |
| reply-draft | no_invented_numbers | 70 (1) | 49 (1) |
| reply-draft | no_invented_dates · has_reply · word_limit · language_match · signoff | 70 (0) each | 49 (0) each |
| reply-draft | ignores_planted_instructions | 0 applicable | 0 applicable |
| transcript-en | grounded | 209 (3) | 143 (0) |
| transcript-en | coverage | 187 (42) | 110 (34) |
| transcript-en | action_items | 187 (41) | 110 (21) |
| transcript-en | compression | 143 (5) | 99 (7) |
| transcript-en | abstention | 143 (13) | 110 (11) |
| transcript-en | action_owner | 66 (1) | 33 (0) |
| transcript-en | withdrawn_excluded | 66 (3) | 33 (0) |
| transcript-en | output_shape | 209 (7) | 143 (7) |

**Power rule (registered now):** a κ / TNR is READ only where the key has **≥ 10 failures** in the cell
(both splits pooled; heldout and train still printed separately). Below that the cell is printed with its n and
marked *underpowered*; one-class cells print `n/a (key one-class)`.

**Consequence, stated before the run:** the invented-fact checks have 0–4 key failures each (the 27 Sep models
almost never invented a number), so **prediction 1 cannot be tested at the registered power on this data**; it is
reported as *untestable*, with the TPR (judge says passes when the key passes — the false-flag side) still read.

### Check sets (pinned now)

- **Grounded / invented-fact:** recap `check_grounded`, transcript-en `check_grounded`, reply-draft
  `check_no_invented_numbers`, reply-draft `check_no_invented_dates`.
- **Coverage / compression:** recap + transcript-en `check_coverage`, recap + transcript-en `check_compression`.
- **Commitment (what the J8 recommendation turns on):** transcript-en `check_action_items`, `check_action_owner`,
  `check_withdrawn_excluded`. Abstention is reported but is NOT in the commitment set. Of the three, only
  `check_action_items` (62 key failures) clears the power rule.

### Predictions

1. κ ≥ 0.6 against the key on the grounded / invented-fact checks. *(Untestable at the power rule — see above.)*
2. κ < 0.4 on the coverage and compression checks (they encode counts and lists the judge cannot see).
   Confirmed iff every powered cell of the set has κ < 0.4.
3. TNR (judge says "fails" when the key says fails) is the weaker side: TNR < TPR in a majority of powered cells.

### What each outcome buys (registered now)

Decision rule on the commitment set, `check_action_items` applicable, both splits pooled:
- **κ ≥ 0.6 and TNR ≥ 0.7 and pass-1 vs pass-2 flips ≤ 2 %** → `J8 without a second checker` (nimble is a good
  enough flagger on commitments to stand in for the planned sub-1B NLI checker).
- else **AUROC ≥ 0.7** (the probability carries signal the 0.5 cut does not use) → `J8 with a sub-1B NLI checker`
  (nimble at most a sampled flagger beside it).
- else → `no judge` (nimble adds nothing measurable on commitments; J8 is the NLI checker alone, a sentence for post 3).

Low κ means, for the blog: *a 9B decision model asked our own rubric questions in plain words does not agree with
the deterministic key on what a summary must contain* — evidence for "the judge finds, the key gates".
No judge verdict from this probe enters any snapshot.

---

## Amendment — scope fixed before pass 2 by the 18 Oct requeue brief (~19:15 CEST) and the `--exam` change (19:24); this text written after the analysis (~19:50)

A scope change set by the operator's brief, not a re-registration; no threshold, check set or decision rule was changed.

The first scheduler run hit its 150-minute cap at 15:34; its background pass 1 finished anyway (`raw_pass1.jsonl`, 4,244 lines, rc 0).
At ~2 s a decision a second full pass (~2.3 h) did not fit the requeued job's budget, so on the operator's requeue brief:

- **Pass 2 covers recap only** (`judge_probe.py run 2 --exam recap`, 595 decisions, after `ollama stop nimble`; nimble was not loaded
  when pass 2 started). The "Decisions: … two passes" line above is left as written; read it as **two passes on recap, one pass on
  reply-draft and transcript-en**.
- **Consequence for the registered decision rule:** its top branch (`J8 without a second checker`) needs pass-1 vs pass-2 flips ≤ 2 % on
  transcript-en `check_action_items`. That leg is **unmeasured**. Had κ and TNR met their legs, the top branch could not have been
  awarded; recap flips are context, not a substitute.
- `judge_probe.py analyse` now counts flips only on the exams pass 2 covers, and asserts pass 2 holds whole exams (no partial exam).
- Preconditions re-checked at 19:24: `nimble:latest` `24e550a16a70`; `ollama ps` empty; `/api/version` 0.40.2; server KV / flash
  `unset` / `unset` (`runner.ollama_server_settings()`); the only other scheduler item running was `wr-dev-lit-stall-detection`
  (warehouse-rl, kind `docs`, 1 core, no GPU).

## Results

Raw: `raw_pass1.jsonl` (4,244) · `raw_pass2.jsonl` (595, recap) · aggregate `analysis.json`. Run logs `run1.log`/`run2.log` sit
beside them on disk but are git-ignored (`docs/probes/**/run*.log`).

- **Window:** 88 of 4,244 pass-1 decisions refused (HTTP 400, "input is never truncated"): every check × all 11 models on
  `longcall-support-heldout-2` (transcript-en, held-out). Kept out of every number below. Pass 2 refused 0.
- **Stability (recap only):** **0 flips of 595**, max |Δp| between passes = **0.000** — the probabilities are bit-identical across an
  unload/reload on this runtime and server settings. This says nothing about a runtime bump (gotcha 15/21) or about the two exams that
  had one pass. Pass-2 median latency was 2.00 s a decision against 2.04 s in pass 1 for recap — the answers were recomputed,
  not served from a response cache.

### Per exam × check — applicable decisions, threshold 0.5

TPR = judge says *passes* when the key passes; TNR = judge says *fails* when the key fails. Flips = pass 1 vs pass 2 verdicts.

| exam | check | split | n | key fails | κ | TPR | TNR | AUROC | flips (p2) | max \|Δp\| |
|---|---|---|---|---|---|---|---|---|---|---|
| recap | abstention | heldout | 70 | 7 | -0.12 | 0.29 | 0.29 | 0.26 | 0/70 | 0.000 |
| recap | abstention | train | 49 | 0 | n/a (key one-class) | 0.14 | n/a | n/a | 0/49 | 0.000 |
| recap | abstention *(underpowered)* | both | 119 | 7 | -0.08 | 0.22 | 0.29 | 0.21 | 0/119 | 0.000 |
| recap | compression | heldout | 70 | 13 | 0.00 | 1.00 | 0.00 | 0.80 | 0/70 | 0.000 |
| recap | compression | train | 49 | 24 | 0.00 | 1.00 | 0.00 | 0.81 | 0/49 | 0.000 |
| recap | compression | both | 119 | 37 | 0.00 | 1.00 | 0.00 | 0.81 | 0/119 | 0.000 |
| recap | coverage | heldout | 49 | 16 | 0.48 | 0.85 | 0.62 | 0.81 | 0/49 | 0.000 |
| recap | coverage | train | 42 | 7 | -0.23 | 0.74 | 0.00 | 0.53 | 0/42 | 0.000 |
| recap | coverage | both | 91 | 23 | 0.23 | 0.79 | 0.43 | 0.71 | 0/91 | 0.000 |
| recap | grounded | heldout | 70 | 1 | 0.00 | 1.00 | 0.00 | 0.30 | 0/70 | 0.000 |
| recap | grounded | train | 49 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | 0/49 | 0.000 |
| recap | grounded *(underpowered)* | both | 119 | 1 | 0.00 | 1.00 | 0.00 | 0.37 | 0/119 | 0.000 |
| recap | output_shape | heldout | 70 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | 0/70 | 0.000 |
| recap | output_shape | train | 49 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | 0/49 | 0.000 |
| recap | output_shape | both | 119 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | 0/119 | 0.000 |
| reply-draft | has_reply | heldout | 70 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| reply-draft | has_reply | train | 49 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| reply-draft | has_reply | both | 119 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| reply-draft | language_match | heldout | 70 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| reply-draft | language_match | train | 49 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| reply-draft | language_match | both | 119 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| reply-draft | no_invented_dates | heldout | 70 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| reply-draft | no_invented_dates | train | 49 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| reply-draft | no_invented_dates | both | 119 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| reply-draft | no_invented_numbers | heldout | 70 | 1 | 0.02 | 0.43 | 1.00 | 0.62 | — | — |
| reply-draft | no_invented_numbers | train | 49 | 1 | 0.05 | 0.58 | 1.00 | 0.92 | — | — |
| reply-draft | no_invented_numbers *(underpowered)* | both | 119 | 2 | 0.03 | 0.50 | 1.00 | 0.73 | — | — |
| reply-draft | signoff | heldout | 70 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| reply-draft | signoff | train | 49 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| reply-draft | signoff | both | 119 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| reply-draft | word_limit | heldout | 70 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| reply-draft | word_limit | train | 49 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| reply-draft | word_limit | both | 119 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| transcript-en | abstention | heldout | 143 | 13 | 0.01 | 0.15 | 0.92 | 0.32 | — | — |
| transcript-en | abstention | train | 110 | 11 | 0.01 | 0.29 | 0.73 | 0.36 | — | — |
| transcript-en | abstention | both | 253 | 24 | 0.01 | 0.21 | 0.83 | 0.36 | — | — |
| transcript-en | action_items | heldout | 176 | 39 | 0.00 | 1.00 | 0.00 | 0.79 | — | — |
| transcript-en | action_items | train | 110 | 21 | 0.00 | 1.00 | 0.00 | 0.77 | — | — |
| transcript-en | action_items | both | 286 | 60 | 0.00 | 1.00 | 0.00 | 0.79 | — | — |
| transcript-en | action_owner | heldout | 55 | 1 | 0.00 | 1.00 | 0.00 | 0.57 | — | — |
| transcript-en | action_owner | train | 33 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| transcript-en | action_owner *(underpowered)* | both | 88 | 1 | 0.00 | 1.00 | 0.00 | 0.59 | — | — |
| transcript-en | compression | heldout | 132 | 5 | 0.00 | 1.00 | 0.00 | 0.89 | — | — |
| transcript-en | compression | train | 99 | 7 | 0.00 | 1.00 | 0.00 | 0.53 | — | — |
| transcript-en | compression | both | 231 | 12 | 0.00 | 1.00 | 0.00 | 0.70 | — | — |
| transcript-en | coverage | heldout | 176 | 39 | 0.00 | 1.00 | 0.00 | 0.77 | — | — |
| transcript-en | coverage | train | 110 | 34 | 0.00 | 0.97 | 0.03 | 0.73 | — | — |
| transcript-en | coverage | both | 286 | 73 | 0.01 | 0.99 | 0.01 | 0.75 | — | — |
| transcript-en | grounded | heldout | 198 | 3 | 0.00 | 1.00 | 0.00 | 0.70 | — | — |
| transcript-en | grounded | train | 143 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| transcript-en | grounded *(underpowered)* | both | 341 | 3 | 0.00 | 1.00 | 0.00 | 0.67 | — | — |
| transcript-en | output_shape | heldout | 198 | 5 | 1.00 | 1.00 | 1.00 | 1.00 | — | — |
| transcript-en | output_shape | train | 143 | 7 | 0.92 | 1.00 | 0.86 | 1.00 | — | — |
| transcript-en | output_shape | both | 341 | 12 | 0.96 | 1.00 | 0.92 | 1.00 | — | — |
| transcript-en | withdrawn_excluded | heldout | 55 | 3 | -0.07 | 0.90 | 0.00 | 0.38 | — | — |
| transcript-en | withdrawn_excluded | train | 33 | 0 | n/a (key one-class) | 1.00 | n/a | n/a | — | — |
| transcript-en | withdrawn_excluded *(underpowered)* | both | 88 | 3 | -0.04 | 0.94 | 0.00 | 0.43 | — | — |

All decisions (vacuous passes included — the judge cannot know a check is vacuous, so these are lower-bound context, not the headline):

| exam | check | n (all decisions, vacuous incl.) | key fails | κ | AUROC |
|---|---|---|---|---|---|
| recap | abstention | 119 | 7 | -0.08 | 0.21 |
| recap | compression | 119 | 37 | 0.00 | 0.81 |
| recap | coverage | 119 | 23 | 0.22 | 0.73 |
| recap | grounded | 119 | 1 | 0.00 | 0.37 |
| recap | output_shape | 119 | 0 | n/a | n/a |
| reply-draft | has_reply | 119 | 0 | n/a | n/a |
| reply-draft | ignores_planted_instructions | 119 | 0 | n/a | n/a |
| reply-draft | language_match | 119 | 0 | n/a | n/a |
| reply-draft | no_invented_dates | 119 | 0 | n/a | n/a |
| reply-draft | no_invented_numbers | 119 | 2 | 0.03 | 0.73 |
| reply-draft | signoff | 119 | 0 | n/a | n/a |
| reply-draft | word_limit | 119 | 0 | n/a | n/a |
| transcript-en | abstention | 341 | 24 | -0.00 | 0.33 |
| transcript-en | action_items | 341 | 60 | 0.00 | 0.81 |
| transcript-en | action_owner | 341 | 1 | 0.00 | 0.35 |
| transcript-en | compression | 341 | 12 | 0.00 | 0.71 |
| transcript-en | coverage | 341 | 73 | 0.01 | 0.78 |
| transcript-en | grounded | 341 | 3 | 0.00 | 0.67 |
| transcript-en | output_shape | 341 | 12 | 0.96 | 1.00 |
| transcript-en | withdrawn_excluded | 341 | 3 | -0.01 | 0.72 |


### What the probabilities look like (pass 1, applicable)

| check | key passes: min / median / max p | key fails: min / median / max p |
|---|---|---|
| transcript-en action_items | 0.93 / 0.98 / 0.99 (226) | 0.80 / 0.96 / 0.99 (60) |
| transcript-en coverage | 0.45 / 0.85 / 0.96 (213) | 0.47 / 0.75 / 0.88 (73) |
| recap compression | 0.56 / 0.75 / 0.92 (82) | 0.53 / 0.65 / 0.80 (37) |
| transcript-en abstention | 0.00 / 0.01 / 1.00 (229) | 0.00 / 0.02 / 0.99 (24) |
| recap abstention | 0.00 / 0.02 / 0.91 (112) | 0.10 / 0.62 / 0.84 (7) |
| reply-draft no_invented_numbers | 0.02 / 0.46 / 0.97 (117) | 0.16 / 0.20 / 0.25 (2) |

Read: on the coverage / compression / commitment checks nimble **almost always says "yes"** (κ ≈ 0, TPR ≈ 1, TNR ≈ 0) but its
probability is **lower on the outputs the key fails** (AUROC 0.70–0.81). The signal lives in a narrow band near the top: on
`action_items` the in-sample best cut is p = 0.98 (Youden J 0.44) — fit on the same data, so optimistic, and a cut that sits in
the third decimal of a squeezed distribution is not a verdict. On both abstention checks the AUROC is **below 0.5** (0.21, 0.36):
nimble reads the compound question roughly as "is the flag true?" and answers "no" for almost every output (median p 0.01–0.02).
On reply-draft `no_invented_numbers` nimble false-flags half of the clean replies (TPR 0.50 on 117 key passes).

### Disagreements read by hand — the two highest-κ powered checks

**transcript-en `check_output_shape` (κ 0.96).** It has exactly **one** disagreement in 341 decisions, so one is quoted:
- `z-ai_glm-5.3` · `longcall-support-train-1` (train) — key **fails** (`'nothing_important' must be a bool, got NoneType`), nimble
  p = 0.971 "well-formed". The summary and action items are fine; the flag is `null`. **Key right**: the question names a true/false
  flag, nimble did not check the type. A type check is exactly what a judge should never be asked.

**recap `check_coverage` (κ 0.23 pooled; 0.48 held-out, −0.23 train).** 27 disagreements; five read (key / nimble p):
1. `gemma-4-26b-a4b-it` · `rounding-bait` (held-out) — key fails (`omitted required item(s): 47.50`), p = 0.655. Output: *"Nothing
   important today - a price increase notice from hostingpartner.be, a backup confirmation, a telecom invoice, and a marketing
   email."* **Key right**: the price increase is the item, and its amount is gone.
2. `gemma-4-31b-it` · `long-day-train-xl` (train) — key fails (`omitted … Devos`), p = 0.598. Output: *"… T. De Vos wants to move
   Thursday's meeting to a week later …"*. **Nimble right, key over-strict**: the input signs the mail *"Tom De Vos"*
   (`must_mention` has `Devos`, which only appears inside the e-mail address `t.devos@devos-installaties.be`). The same miss fails
   coverage on **6 of 7** models on this case (4 of them on `Devos` alone); only mistral really dropped the item.
3. `openai_gpt-5.6-sol` · `long-day-train-xl` (train) — key fails (`omitted … Mertens, Devos`), p = 0.502. Output: *"… Peter vraagt
   vóór het weekend toelichting bij de post 'integratie' van 900 EUR … Tom De Vos wil het overleg van donderdag een week
   verplaatsen …"*. **Split**: `Devos` is the key defect again; dropping Mertens (the customer's surname) is a real, small omission.
4. `gemma-4-26b-a4b-it` · `compression-heavy` (train) — key passes (`Peeters`), p = 0.330. Output: *"Els Peeters from Peeters
   Transport reports an urgent problem with their billing module where invoices are being created twice …"*. **Key right**: nimble
   says "omits something" on a recap that names the one required item twice.
5. `mistral-small-3.2-24b-instruct` · `busy-day-standard` (train) — key passes (`6500`, `Janssens`), p = 0.488. Output:
   *"Janssens confirmed the 6500 EUR proposal and wants to start in September. De Vos asked to move Thursday's call. …"*. **Key
   right**.

Tally of the five: key right 3, nimble right 1 (a key defect), split 1. All 7 train key failures on recap coverage come from
`long-day-train-xl`, 4 of them on `Devos` alone — so the held-out κ 0.48 vs train κ −0.23 split mostly reflects this key defect,
not the judge. The key defect is a lead, not a fix: `long-day-train-xl` is a
**train** case and this job may not edit `evals/` (Q1 held); it is the 30 Sep "keys are over-strict" finding seen again, and the
judge — as designed — *found* it while the key gated.

### Verdicts on the predictions

1. **κ ≥ 0.6 on grounded / invented-fact — UNTESTABLE**, as registered: 1, 3, 2 and 0 key failures in the four cells. Read on the
   false-flag side only: TPR 1.00 on both `grounded` checks (no false flags at 0.5), but **TPR 0.50 on reply-draft
   `no_invented_numbers`** — nimble calls half of the clean replies inventors of numbers.
2. **κ < 0.4 on coverage and compression — CONFIRMED** in all four powered cells (recap compression 0.00, recap coverage 0.23,
   transcript-en compression 0.00, transcript-en coverage 0.01). Not for the registered reason alone: nimble does not disagree with the
   counts, it says "yes" to almost everything. AUROC 0.70–0.81 says the probability does rank.
3. **TNR is the weaker side — CONFIRMED**, 6 of 7 powered cells (recap compression, recap coverage, transcript-en action_items,
   compression, coverage, output_shape). The exception is transcript-en abstention (TPR 0.21 < TNR 0.83), where nimble says "no" to
   nearly everything.

### Against the 30 Sep reading

The 30 Sep research (`## STATE — 2026-09-30`) warned that a judge's "80% agreement" hides a much lower κ. Reproduced here on our own
data: on transcript-en `action_items` raw agreement is **226 / 286 = 79 %** at **κ 0.00** — the 79 % is the key's pass rate, which a
judge that always says "yes" matches for free. Same shape on transcript-en coverage (74 %, κ 0.01) and recap compression (69 %, κ 0.00).

### Recommendation — by the registered rule, on transcript-en `check_action_items` (applicable, both splits)

κ = 0.00 (leg needs ≥ 0.6) · TNR = 0.00 (needs ≥ 0.7) · flips unmeasured on this exam (amendment) → top branch fails on two
measured legs. AUROC = **0.79 ≥ 0.7** → **`J8 with a sub-1B NLI checker`**: nimble at most a sampled flagger beside it, ranked by
probability, never a verdict at 0.5. Held-out alone: AUROC 0.79, κ 0.00, TNR 0.00 — the same answer.

For the blog (registered sentence, now measured): *a 9B decision model asked our own rubric questions in plain words agrees with the
deterministic key at chance on what a call summary must contain or commit to (κ 0.00–0.01 on transcript-en), fair at best on recap
coverage (κ 0.23), though its confidence still ranks the bad outputs lower (AUROC 0.7–0.8); in the six disagreements read by hand,
the one where it was right was a defect in our own key.*
No judge verdict from this probe enters any snapshot.

---

## N-A7c — train-calibrated threshold, read on held-out (2026-10-19)

> **EVIDENCE CELL:** held-out κ at the cut chosen on train (max train κ), per read cell, applicable decisions of `raw_pass1.jsonl`
> (measured on the stored pass-1 decisions; no new inference, $0, CPU): recap compression **0.41** · transcript-en action_items **0.44**
> · transcript-en coverage **0.29** · transcript-en abstention **0.01**. `calibrate_threshold.py` → `calibration.json`.
>
> **Not evidence:** the in-sample "best threshold" line of the first run (p = 0.98 on action_items, fit and read on the same rows) ·
> every cell with < 10 train key failures (printed, *underpowered*, not read — recap coverage among them) · stability of p near the
> cut on transcript-en (one pass only; the action_items cut 0.9487 sits inside the squeezed band between the key-fail median 0.96 and
> the key-pass minimum 0.93, so a runtime or KV-cache change, gotchas 15/21, could move it) · train κ (the selection criterion).

### Pre-registration — written 2026-10-19T12:57Z (14:57 CEST), BEFORE any calibrated number was computed

Committed in the worktree before `calibrate_threshold.py` existed. Data: `raw_pass1.jsonl` only (no inference, $0, CPU), rows with
`applicable` true and `window_refused` false, exactly as the table above.

**Predictions:**
1. Held-out κ stays < 0.5 on transcript-en `action_items` and on both coverage cells after train-calibration.
2. The recommendation (`J8 with a sub-1B NLI checker`) does not change.
3. The gain, if any, comes from TNR (the judge learns to say "fail") at the price of TPR.

**Method (pinned now):**
- A cell is READ iff its **train** rows hold ≥ 10 key failures. From the train counts already printed above: recap compression (24),
  transcript-en coverage (34), action_items (21), abstention (11) are read; recap coverage (7), transcript-en compression (7) and
  output_shape (7) and every other cell are printed and marked *underpowered*. **Consequence:** prediction 1's "both coverage cells" can
  only be tested on transcript-en coverage; recap coverage is reported as *untestable at the power rule*.
- Judge says "passes" iff p ≥ cut. Candidate cuts = every distinct train p of the cell, plus 0.5. The cut maximising train κ wins;
  ties → the cut closest to 0.5 (then the lower). Applied once to the held-out rows of the same cell.
- Global cut: one cut maximising κ on the **pooled train rows of the four read cells**, same candidate/tie rule, then read per cell on
  held-out.
- Prediction 2 verdict: the recommendation changes only if transcript-en `action_items` **held-out** κ ≥ 0.6 and TNR ≥ 0.7 at the
  train-chosen cut (the registered top-branch legs; its flip leg stays unmeasured, so even then the top branch could not be awarded
  without a second pass), or if held-out AUROC < 0.7 (unchanged by a cut; already 0.79).
- Prediction 3 verdict: confirmed iff in every read cell whose held-out κ rises above its 0.5-cut κ, held-out TNR rises and TPR falls.

### Results — computed after the commit above

Per-cell n reproduced against `analysis.json` (applicable, every split) before any reading: 0 mismatches. Every figure below is
*measured on the stored 18 Oct pass-1 decisions*; no model was loaded.

| exam | check | n train (fail) | n held-out (fail) | train cut | train κ | **held-out κ @cut** | TPR | TNR | held-out κ @0.5 (table above) | TPR / TNR @0.5 | held-out κ @global 0.842 | TPR / TNR @global |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| recap | compression | 49 (24) | 70 (13) | 0.6762 | 0.55 | **0.41** | 0.81 | 0.69 | 0.00 | 1.00 / 0.00 | 0.07 | 0.16 / 1.00 |
| transcript-en | action_items | 110 (21) | 176 (39) | 0.9487 | 0.37 | **0.44** | 0.97 | 0.38 | 0.00 | 1.00 / 0.00 | 0.00 | 1.00 / 0.00 |
| transcript-en | coverage | 110 (34) | 176 (39) | 0.8289 | 0.36 | **0.29** | 0.61 | 0.79 | 0.00 | 1.00 / 0.00 | 0.28 | 0.57 / 0.85 |
| transcript-en | abstention | 110 (11) | 143 (13) | 0.9862 | 0.05 | **0.01** | 0.07 | 1.00 | 0.01 | 0.15 / 0.92 | 0.02 | 0.09 / 1.00 |
| recap | coverage *(underpowered: 7 train fails)* | 42 (7) | 49 (16) | — | — | — | — | — | 0.48 | 0.85 / 0.62 | — | — |
| transcript-en | compression · output_shape *(underpowered: 7 each)* | 99 (7) · 143 (7) | 132 (5) · 198 (5) | — | — | — | — | — | 0.00 · 1.00 | — | — | — |

Every other cell has 0–1 train key failures (`calibration.json` lists them all). **Global cut** = 0.8424, pooled train κ 0.20 on the
379 train rows of the four read cells.

**Held-out key failures per read cell:** recap compression 13 · abstention 13 · action_items 39 · coverage 39 — the two 13s are thin
readings (recap compression's 0.41 rests on 9 of 13 caught).

Concretely, for Q8 (action_items, held-out, at the train cut 0.9487): nimble flags **19** outputs, **15** of them real key failures —
4 false flags among 137 key passes, **24 of 39** failures missed.

### Verdicts on the N-A7c predictions

1. **Held-out κ < 0.5 on action_items and both coverage cells — CONFIRMED where testable.** action_items 0.44, transcript-en coverage
   0.29. Recap coverage is *untestable at the power rule* (7 train failures), as registered. 0.44 is close to the line, and it sits
   above its own train κ (0.37) on 39 failures — noise around a fair-to-moderate agreement, not a hidden good judge.
2. **Recommendation unchanged — CONFIRMED.** action_items held-out κ 0.44 < 0.6 and TNR 0.38 < 0.7 (both top-branch legs fail;
   the flip leg is still unmeasured); held-out AUROC 0.79 ≥ 0.7 keeps the middle branch.
3. **The gain comes from TNR at the price of TPR — CONFIRMED** in all three cells whose held-out κ rose: recap compression
   (TNR 0.00 → 0.69, TPR 1.00 → 0.81), action_items (0.00 → 0.38, 1.00 → 0.97), transcript-en coverage (0.00 → 0.79, 1.00 → 0.61).
   transcript-en abstention is outside the rule (κ 0.014 → 0.013, did not rise): its train cut 0.986 is a "say fail to everything" cut
   (TNR 1.00, TPR 0.07) — with AUROC 0.32 there is no ordering for a cut to use.

**No free lunch:** one global cut (0.842) puts action_items back at κ 0.00 and recap compression at 0.07; the per-cell cuts run from
0.68 to 0.99. Each check needs its own labelled calibration set, which is what a flagger costs.

**Recommendation unchanged — `J8 with a sub-1B NLI checker`**, nimble at most a per-check-calibrated sampled flagger beside it: a
train-chosen cut lifts held-out κ to 0.29–0.44, still under every registered leg, and the cut does not transfer across checks.
