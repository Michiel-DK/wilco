# Labeller certification vs PUBLIC HUMAN labels — RAGTruth summarization (2026-11-10/11) — BRANCH: **NOT CERTIFIED** (TNR 0.67 < 0.8); `as-eb-labeller-vs-checks` results are Claude-vs-key only and must say so

> **EVIDENCE CELL:** the Claude labeller (`claude-fable-5-1`, provider `anthropic`) vs RAGTruth's HUMAN span labels on
> "does this summary contain unsupported content", 300 RAGTruth summarization responses (test split, seeded 150 human-positive
> + 150 human-negative): Cohen's κ, TPR, TNR with Wilson 95% bounds, and the labeller's own flip rate on a seeded 60 re-asked.
>
> **Not evidence:** raw agreement (printed, not read — κ is the agreement figure) · the digit-rule rows (`check_grounded`,
> `check_no_invented_numbers` on the same pairs — diagnostic for OUR checks, a different question) · anything about meeting or
> call text (RAGTruth summaries are news, CNN/DM + Recent News) · any property other than unsupported content · the
> per-label-type and span-overlap rows (diagnostic).

## Pre-registration — written 2026-11-11 before the first labeller call and before the digit rule was computed

### Data (verified this session)

- RAGTruth, `github.com/ParticleMedia/RAGTruth` HEAD `c103204b9ce28d6bbad859304bf30de72b8ed8fe` (`git ls-remote`, 2026-11-11),
  raw files from `main`, downloaded to a git-ignored dir (`.cache/ragtruth-dl/` in the job worktree, removed after). sha256:
  `LICENSE b7fd7d6b…f5b244` · `README.md 3686178d…ee06628d` · `dataset/response.jsonl e4c2e4ac…18073` ·
  `dataset/source_info.jsonl 0dffc26e…d12d578b`. **Committed here: response ids, human labels/offsets, verdicts. Never the
  source or response texts.**
- Licence, quoted in full from the downloaded `LICENSE`:

  > MIT License
  >
  > Copyright (c) 2023 Particle Media
  >
  > Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
  > documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
  > rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
  > persons to whom the Software is furnished to do so, subject to the following conditions:
  >
  > The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
  > Software.
  >
  > THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
  > WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
  > COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
  > OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

- Pool: `task_type == "Summary"`, `split == "test"`, `quality == "good"` → **900 responses, 204 with ≥ 1 human span, 696 with
  none** (6 generator models × 150 sources). Sample (`label_probe.py sample`, seed `20261110`, ids sorted by int):
  **150 positive + 150 negative = 300**; **35** of the 150 positives have a human span containing a digit. Pass 2: a seeded
  60 of the 300 (`random.Random(20261111)`), listed in `sample.json` `pass2_ids`.
- Human label = "contains unsupported content" iff the response has ≥ 1 RAGTruth span of any type (Evident/Subtle Conflict,
  Evident/Subtle Baseless Info). RAGTruth's `implicit_true` spans (baseless but true in the world) count as unsupported, as in
  the dataset; the question tells the labeller to judge against the source only, which matches that definition.
  TofuEval / MeetingBank / FaithBench / UniSumEval were NOT downloaded (operator decides separately).

### Labeller and request

- Model **`claude-fable-5-1`**: the strongest Claude id that ran through `--provider anthropic` in
  `docs/probes/frontier-direct-2026-10-28/` (top tier there, highest Claude pooled score 129/155). `claude-fable-5-2` exists
  but was not in that probe, so the brief does not make it eligible. One model for the whole job.
- Request through `sandbox/router.py` `get_adapter("anthropic")` → `ChatCompletionsAdapter.generate`: body = `model`,
  `messages` = ONE user message (no system message), `max_tokens: 8192`, `stream: false`. The adapter sets `temperature: 0.0`
  and `drop_body_keys` **removes it before sending: no temperature is sent** (the endpoint 400s on it). Thinking is on and
  counted in `completion_tokens` (frontier-direct finding 7).
- Prompt: `PROMPT` in `label_probe.py`, source + response only, no RAGTruth label, label type, span or generator model shown.
  Answer = JSON `{"verdict": "pass"|"fail", "unsupported_span": "..."}`. "fail" = labeller says unsupported content.
- Up to 5 attempts per response (HTTP error, empty answer, unparseable). **A response with no usable verdict after 5 is
  scored as the WRONG label** (against the labeller). Workers: 6.
- Estimate (`label_probe.py estimate`, before any call): **360 calls, 1,798,494 prompt chars → 449,623 estimated input
  tokens**, cap 1,500,000 → under cap (`estimate.json`).

### Rules fixed now

- Positive class = "contains unsupported content" (human: ≥ 1 span; labeller: `fail`). TPR = labeller fail | human
  positive; TNR = labeller pass | human negative; Cohen's κ (`scripts/label_sheet.py` `cohen_kappa`) on the 300; Wilson 95%
  (`sandbox/stats.py` `wilson`) on TPR, TNR and the flip rate; κ gets a seeded 2,000-rep paired bootstrap 95% interval.
- **The branch reads POINT estimates** of κ, TPR, TNR. Wilson lower bounds are printed beside them and read in the text, but
  do not decide the branch.
- Flip rate = share of the 60 where pass 2's verdict ≠ pass 1's (pass 2 runs only after pass 1 is complete).
- Note: the 50/50 sample is not RAGTruth's prevalence (204/900 = 23%); κ on a balanced sample is not κ at 23% prevalence.
  TPR and TNR are prevalence-free; they are the rates to carry.

### Predictions

1. Labeller vs human on "contains unsupported content": **κ ≥ 0.6, TPR ≥ 0.8, TNR ≥ 0.8**.
2. Our digit rule catches **under half** of the 150 human-marked hallucinations (catch = the check returns False), because
   most are not numbers — stated separately for `evals/recap` `check_grounded` (input = source, output `{"recap": response}`)
   and `evals/reply-draft` `check_no_invented_numbers` (input = source, output `{"reply": response}`), the real functions.
3. On the 35 positives whose human span contains a digit, each function's **false-pass rate is under 20%** (false pass = the
   check returns True on a human-positive). Its false-fail rate on the 150 human-negatives is printed beside it.

### Verdict branches (written before the run)

- κ ≥ 0.6 **and** TPR ≥ 0.8 **and** TNR ≥ 0.8 → **"certified for unsupported-content on news summaries;
  `as-eb-labeller-vs-checks` may run"**.
- anything below → **"not certified; that job's results are Claude-vs-key only and must say so"**.

**Not certified by this probe under either branch:** coverage; action items and owner; reply-addresses-the-ask; field
extraction. No public human labels exist for the last three; coverage labels exist elsewhere (licences not cleared here).
Nor meeting/call text, nor any language other than English.

## Results — run 2026-11-11 (pass 1 300 calls, pass 2 60 calls; `label_probe.py analyse` → `analysis.json`)

**Branch taken: "not certified; that job's results are Claude-vs-key only and must say so."** TPR clears 0.8, κ lands
exactly on 0.6, and TNR misses: the labeller calls 49 of 150 human-clean summaries unsupported.

### Evidence cell — `claude-fable-5-1` vs RAGTruth human labels, n = 300 (150 + / 150 −)

| metric | value | 95% interval | bar | met |
|---|---|---|---|---|
| Cohen's κ | **0.600** (float `0.6000000000000001`) | bootstrap 0.511–0.686 | ≥ 0.6 | at the bar exactly; lower bound well under |
| TPR (fail on human-positive) | **139/150 = 0.927** | Wilson 0.874–0.959 | ≥ 0.8 | yes, lower bound too |
| TNR (pass on human-negative) | **101/150 = 0.673** | Wilson 0.595–0.743 | ≥ 0.8 | **no**, upper bound under the bar too |
| flip rate, pass 2 vs pass 1 | **3/60 = 0.05** (ids 725, 886, 2374) | Wilson 0.017–0.137 | (none set) | — |

Confusion: TP 139 · FN 11 · TN 101 · FP 49. Null verdicts: 0 (all 360 calls answered and parsed on the first attempt).
κ = 0.600 exactly comes from the balanced design: chance agreement is 0.5 when one side is 150/150, so κ = (0.80 − 0.5)/0.5.
The branch reads point estimates (registered), so κ alone would have passed, but TNR decides it.

**Reading.** The labeller is a strict flagger. It finds the human-marked hallucinations: TPR 0.93, and on 119 of 139 true
positives its quoted span overlaps a human span. But it also flags a third of the summaries the human annotators passed.
Those 49 false positives spread over all six generator models (gpt-3.5 11, mistral-7B 10, llama-2-7b 9, llama-2-70b 9,
gpt-4 6, llama-2-13b 4). **They were NOT adjudicated.** Some may be real unsupported content that RAGTruth's annotators
missed, so a human-missed hallucination and a labeller over-call look identical in this cell. Re-reading them with a Claude
session would be the collusion the header bars. A human adjudication of the 49 is the only way to split them, and it is
not done here. No direction of the labeller's verdict is certified.

Diagnostic only, post-hoc and not registered: TPR is scored per response, and the labeller's quoted span overlaps a human
span on only 119 of the 150 positives. The response-level 0.93 includes 20 hits on a span no human marked. On this 50/50
sample, 11 of 112 labeller passes were human-positive. That share depends on prevalence (the pool's is 23%) and carries no
certification.

### Diagnostics (Not evidence for the cell)

- TPR by human label type (a response can carry several): Evident Conflict 60/63 · Evident Baseless Info 79/84 · Subtle
  Baseless Info 11/11 · Subtle Conflict 2/5 (n too small to read).
- Raw agreement 0.80 (printed, not read).
- Completion tokens per call: median 285, max 1,122. `max_tokens 8192` was never close.

### Digit rule on the same 300 pairs (diagnostic for OUR checks, a different question)

| | `recap` `check_grounded` | `reply-draft` `check_no_invented_numbers` |
|---|---|---|
| catch rate on the 150 human-positives | 45/150 = 0.30 (Wilson 0.23–0.38) | 46/150 = 0.31 (0.24–0.38) |
| false-pass on the 35 digit-span positives | **11/35 = 0.31** (0.19–0.48) | **11/35 = 0.31** (0.19–0.48) |
| false-fail on the 150 human-negatives | 28/150 = 0.19 (0.13–0.26) | 29/150 = 0.19 (0.14–0.26) |

- **Prediction 2 HELD**, for both functions: the digit rule catches under half (0.30 / 0.31). The real figure is lower
  still. The 19% false-fail rate on human-negatives shows that part of the "catch" fires on numbers no human marked (which
  numbers was NOT read per case; reformatting or world-knowledge figures are ⚠️ unverified guesses). The check never asks whether a flagged number sits
  inside the human span, so the catch rate is an upper bound on real detection.
- **Prediction 3 REFUTED**, for both functions: on positives whose human span contains a digit, the digit rule passes
  11 of 35 (0.31, against the predicted < 0.20). ⚠️ Unverified hypothesis, not broken down per case: a human span that contains a digit is not always an invented number.
  It may be a correct number in a wrong claim (a date attached to the wrong event), or a number the source also contains
  elsewhere, which the substring match counts as grounded.
- These rows are news text through checks written for recap and reply text. They say nothing about the checks' error rate
  on our own exams.

### Prediction 1: REFUTED (TNR 0.67 < 0.8); κ at the bar, TPR above it.

### Tokens (metered: the provider's `usage`, pooled ONLY from `analysis.json` `metrics_totals`)

- 360 calls answered, 0 failed attempts, 0 unmetered: **prompt 600,898 · completion 105,361** (completion includes
  thinking, frontier-direct finding 7).
- Not in `metrics_totals`: the 1 smoke call (`smoke.json`, a TRAIN-split row outside the sample): prompt 1,479 ·
  completion 271.
- Pre-run estimate: 449,623 (chars / 4). Metered prompt tokens ran 1.34× the estimate, still under the 1.5M cap.

### What this does NOT certify

Under this branch the labeller is certified for nothing. Even a pass would not have covered coverage, action items and
owner, reply-addresses-the-ask, field extraction (no public human labels exist for the last three), meeting or call text,
or non-English text. **What `as-eb-labeller-vs-checks` inherits:** every agreement figure it reports is Claude-vs-key,
not validity. Neither the labeller's "pass" nor its "fail" is certified. Against human labels on clean news summaries it
over-calls fail at 49/150.

### Files

`label_probe.py` (all steps) · `sample.json` (ids, human labels, offsets; no text) · `estimate.json` · `smoke.json` ·
`raw_pass1.jsonl` / `raw_pass2.jsonl` (verdict, span length + offset, per-attempt usage; no span text) · `digit_rule.json` ·
`analysis.json`.
