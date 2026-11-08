# n8n two-exam probe — RESULTS (3 Nov 2026)

> **EVIDENCE CELL:** Claude Haiku 5.5 inside n8n (Arm N), graded by our `run_exam` through a replay adapter, vs the
> same model through `sandbox/runner.py` (Arm R). Same day, 18:23–18:28 UTC, one pass each. Held-out:
> **call-fields N 16/19 · R 14/19**, **recap N 7/16 · R 4/16**.
>
> **Not evidence:** the 28 Oct direct row (call-fields 15/19, recap 8/16) is a different day (gotcha 14), so it is
> context only. Train-split scores are diagnostic. The local champion is not in this probe (step 2, needs a GPU go).

Prediction registered before the first call: `PREDICTION.md`.

## What ran

- **Arm N.** n8n Cloud trial 2.46.4, workflow `wVhvSAXixE6oaTyz` ("wilco exam runner"), **built and run entirely
  through the n8n MCP**: `create_workflow_from_code`, 55 × `execute_workflow` in manual mode with a webhook payload,
  then 55 × `get_workflow_execution`. Executions 124–178, all `success`. The workflow fetches `cases.json` and
  `prompt.md` from public `Michiel-DK/wilco@2ed67b7`, which is byte-identical to master (`git hash-object` on all four
  files, plus raw GitHub). The Result node echoes `system_chars` = 3,890 (call-fields) and 1,508 (recap), equal to
  `prompt.md` read as text. Model node: `claude-haiku-5-5`, max tokens 4096 / 2048, temperature 0 (the node says it is
  ignored on newer models), thinking left at the node default (disabled). `harvest.py` collects the raw answer text,
  keyed by the `case_id` the workflow itself returned. `grade_replay.py` then feeds those answers to `run_exam` through
  a replay adapter keyed by case input that raises on a miss. Re-asks: none on either exam.
  - **What reached the model:** execution 124's `Anthropic Chat Model` input is byte-equal to `prompt.md` (system)
    and to the case input (user). The single-brace JSON in the prompt survived LangChain's template.
  - **The replay is a witness** (`validate_replay.py`, exit 0). Replaying Arm R's own recorded answers through
    `grade_replay.py` reproduces Arm R's verdicts on 32/32 and 23/23 cases. One mutated answer per exam flips exactly
    that case to FAIL and moves nothing else.
- **Arm R.** `runner.py run <exam> --provider anthropic --model claude-haiku-5-5 --split all --allow-tier-breach
  --timeout 300`, master `6a71bd7`. Results are in `armR/`. Metered volumes: call-fields 134,238 prompt + 13,804
  completion tokens, recap 42,461 + 11,400. `finish_reason` is `stop` on all 55 calls, so no answer was cut by the budget.

## Results

| exam | arm | train | held-out | held-out cases that differ between arms |
|---|---|---|---|---|
| call-fields | N (n8n) | 12/13 | **16/19** | N passes, R fails: `discovery-heldout-long`, `quiet-checkin-heldout-medium` |
| call-fields | R (runner) | 11/13 | **14/19** | (train flips both ways: `renewal-medium-train`, `longcall-renewal-train-1` N only; `support-medium-train` R only) |
| recap | N (n8n) | 1/7 | **7/16** | N only: `buried-critical`, `quiet-day-with-receipt`, `rounding-bait`, `meeting-moved-date-decoy` |
| recap | R (runner) | 1/7 | **4/16** | R only: `buried-last-en` |

Every recap difference is a length check: `check_compression` (recap longer than its budget) or `check_abstention`
(a quiet-day recap over its character cap). Arm N's 9 held-out recap failures: 6 `check_compression`,
2 `check_abstention` (quiet-day cap), 1 `check_grounded` (`amounts-at-length`: the number 30 is not in the source).

## Against the prediction

1. Arm R near 28 Oct (15/19 ±2, 8/16 ±2): **held for call-fields (14), missed for recap (4, below the band).**
2. Arms differ by ≤ 2 held-out cases per exam: **held for call-fields (2), missed for recap (3 net, 5 flips).**
3. n8n's built-in metrics vs our checks: **confirmed from the node definition** (`get_node_types`, Evaluation v4.8,
   `setMetrics`). The metric list is `correctness` and `helpfulness` (both LLM-judged), `stringSimilarity`,
   `categorization` (exact match), `toolsUsed`, and `customMetrics` (any number computed in an expression). call-fields
   fits `categorization` once per field, or one `customMetrics` expression. Recap's compression ratio, quiet-day cap,
   grounded numbers and must-mention lists fit nothing built in. They can only run as `customMetrics` code, which means
   porting `evals/recap/properties.py` to JavaScript: a second grader that would need its own seen-red check. Not built.

## What this does and does not say

- **The plumbing works.** An exam can be built, run and read back end to end through the MCP. No browser, no API key,
  no copying answers by hand.
- **One pass could not attribute the gap; see the 3-pass addendum below.** The "hidden thinking on Arm R" reading in the
  first version of this file is **RETRACTED**. Arm N spends the same tokens (identical prompt tokens, completion within 2–15%),
  so the completion/answer ratio was never evidence of a difference between the arms.
- **Arm N tokens:** pass 1 not harvested. Passes 2–3 come from the chat-model node (`harvest_batch.py`).
- **Two MCP quirks, noted for reuse.** (1) `get_workflow_execution` returns the whole run data even with `nodeNames`,
  so each case's dump is about 80–265 KB (the fetched `cases.json`). The client saves it to a file. (2) Parallel calls
  sometimes got the same file name and overwrote each other (seen at least 3 times in 55). This was caught because
  `harvest.py` keys by `case_id` and lists missing cases, and those were re-fetched. Publishing the workflow, so one local loop could collect every answer, was **refused by the
  session's permission classifier**. Everything stayed in manual mode.
- **Cost:** no dollar figure here (gotcha 20: dollars come only from `cost_per_10k.py`). Arm R's metered token
  volumes are above. Arm N is billed to the n8n Anthropic credential.

## Files

`PREDICTION.md` · `harvest.py` (dumps → `armN/<exam>.json`) · `grade_replay.py` (→ `armN/<exam>.graded.json`) ·
`validate_replay.py` (agreement + seen-red) · `armR/<exam>.json` + `.log`

## Addendum, same evening: 3 passes per arm (operator go "1+2")

Passes 2–3 of Arm N ran on workflow `d5P2PumHfBICXwan`: the same nodes and settings, the whole exam in one execution
(batches of 5), executions 179–182. Every item was checked against its case by an input fingerprint (`harvest_batch.py`).
Passes 2–3 of Arm R are `armR/<exam>.pass{2,3}.json`. Window 18:23–18:40 UTC.

| exam | held-out per pass, n8n | held-out per pass, runner | total of 3 passes |
|---|---|---|---|
| call-fields (n=19) | 16 · 16 · 16 | 14 · 14 · 14 | **48 vs 42 of 57** |
| recap (n=16) | 7 · 6 · 7 | 4 · 6 · 6 | **20 vs 16 of 48** |

- **Tokens are the same:** prompt tokens are identical on both arms (call-fields 134,238, recap 42,461 per pass), and
  completion tokens are within 2–15%. Both paths send the same input and the model spends the same budget.
- **call-fields: a steady gap of 2 cases, all on wording.** Every differing case is one field, almost always
  `next_step_date`. For example, the runner wrote "end of day" where the key says "today" (2 of 3 passes), and "Friday"
  where it says "next quarter" (3 of 3). Only `discovery-heldout-long` differs by ≥ 2 of 3 passes.
- **recap: within noise.** 7 of 16 cases are unstable on n8n, 6 on the runner. Failures are mostly length on both arms
  (compression 19 vs 24, abstention 6 vs 7, grounded 3 vs 3).
- **Cause: unknown.** The paths differ in the endpoint: n8n uses Anthropic's native Messages API through LangChain, our
  runner uses Anthropic's OpenAI-compatible endpoint, which drops `temperature`. ⚠️ That the endpoint explains the gap is
  UNVERIFIED. Testing it means one runner arm on the native API, and that is a code change (a PROVIDERS entry, PR).

## Addendum 2: what causes the call-fields gap (Arm A, Anthropic native API, operator go)

`native_arm.py`: the same system prompt, case input and `max_tokens`, POSTed straight to `/v1/messages`. No temperature,
like Arm R. No LangChain, no n8n. This is probe code, not runner code: CLAUDE.md forbids a new adapter class, and the
native API would need one. Graded with `grade_replay.py`. Input tokens are identical to Arms N and R, and the replies
carry `thinking` blocks.

| call-fields held-out (n=19) | p1 | p2 | p3 | p4 (same window, 19:2x UTC) | total |
|---|---|---|---|---|---|
| N: n8n (LangChain → native API) | 16 | 16 | 16 | — | 48/57 |
| A: native API, our probe | 16 | 16 | 15 | 14 | 61/76 |
| R: runner, OpenAI-compatible endpoint | 14 | 14 | 14 | 13 | 55/76 |

Recap held-out: A 7 · 4 · 5 = 16/48, equal to R's 16/48. n8n's 20/48 on recap stays unexplained, and the per-pass
spread says noise.

**Reading:** on call-fields, the native endpoint scores above the compatible endpoint on every pass (gap 1–2), and
n8n sits with the native endpoint. The one strictly same-window pair is 14 vs 13. **Suggestive, not settled:** Arm A
also drifted from 16 to 14 within the evening (gotcha 14). If it holds, every Claude row we measured through
`provider: anthropic` (the compat endpoint, 28 Oct onward) understates the model on field extraction by about 1–2/19.
⚠️ Confirming it means more same-window pairs. Making native a real provider means a new adapter class, which is
against the convention as written: an operator decision.
