# A model judge against our answer key: κ ≈ 0 on 5 of 7 measurable checks

**Headline.** We asked a 9B local decision model (nimble, served by Ollama) to grade 590 stored outputs from three office-task
exams (e-mail recap, reply drafting, call summary), one yes/no question per output per check: 4,244
decisions. Against our deterministic answer key, Cohen's κ was **0.00–0.01 on 5 of the 7 checks** with enough key failures to
measure; 0.23 on recap coverage; 0.96 on one format check. Raw agreement on "are all the call's commitments listed?" was 79 %,
exactly the key's pass rate: a judge that always says "yes" gets it for free, at κ 0.00.

Derivation: κ at p ≥ 0.5 per check, on the 3,195 *applicable* decisions (4,244 minus 88 refused by the judge's context
window and 961 vacuous passes), both splits pooled. 579 of the 590
outputs got verdicts. A check counts as measurable only with ≥ 10 key
failures, a rule committed before inference.

## Method, in plain words

- The outputs came from 7 models (recap, reply-draft) and 11 (transcripts), produced earlier; only the judge is under test.
- The **key is not a human rater.** It is each exam's hand-written deterministic check code (`evals/<exam>/properties.py`) re-run
  on the stored outputs; per the probe's notes it reproduced the exams' stored pass/fail on all 590 outputs.
- Each question is the check's definition in plain words. The judge never sees the case's expected values and returns p(yes).
- Predictions, thresholds and the decision rule were committed before inference; a later scope cut is recorded as an amendment.

## What we found

Recap coverage aside, on the coverage, compression and commitment checks the judge **says "yes" to almost everything** (TPR ≈ 1,
TNR ≈ 0). Its probability carries some signal
(AUROC 0.70–0.81): bad outputs get slightly lower p, inside a narrow band near the top.

So we picked a cut per check on the train split and read it once on held-out. κ rose to **0.41** (recap compression), **0.44**
(commitments) and **0.29** (transcript coverage); on commitments that is TNR 0.38 on 39 held-out failures. The cuts differ per
check (0.68 to 0.99), and **one global cut sends those three back to κ 0.00–0.28**.

The one high κ (0.96, transcript output shape) is a format question; its one miss is a `null` where a true/false flag belonged,
a type check, which is code's job.

## What did not hold, or could not be tested

- **Invented facts: untestable.** We predicted κ ≥ 0.6 on the invented-number checks. The stored outputs had 0–3 key failures per
  check. On the false-flag side, the judge called **half the clean e-mail replies** inventors of
  numbers (TPR 0.50).
- **Abstention is inverted.** On "is the nothing-important flag correct?" AUROC is **below 0.5** (0.36 on transcripts; 0.21 on
  recap, on only 7 failures): the judge appears to answer "is the flag true?" instead.
- **Six of 20 checks have a one-class key** (every output passed), so κ is undefined; one more had no applicable case.
- **Stability on one exam only.** A second pass after unloading the model covered recap: 0 of 595 verdicts flipped, max |Δp| 0.000.
  The other exams had one pass.
- **The key was wrong once, and the judge was right.** A hand-read disagreement showed a recap key requiring a surname spelled
  as in the sender's e-mail address, not as the message was signed (6 of 7 models failed on it, per the probe's notes). That key was corrected in a later commit. Every κ here is against the key **as stored in the decision files when
  the probe ran**. ⚠️ not re-derived: κ against today's corrected key.

**So:** the deterministic key stays the gate; a judge is at most a calibrated flagger feeding human review.

## Re-derive

No API key, no GPU, standard library. Recomputes every figure not marked otherwise; exits 1 on any drift from the probe's
`analysis.json` / `calibration.json` (both guards seen red).

```sh
python3 scripts/writeups/judge-vs-key.py
```

```
decisions pass 1: 4244 | window-refused: 88 | vacuous (not applicable): 961 | applicable, judged: 3195
checks: 20 | outputs in the decision file: 590, judged (not refused): 579 | models per exam: {'recap': 7, 'reply-draft': 7, 'transcript-en': 11}
pass 2: 595 decisions, exams ['recap'], flips 0/595, max |dp| 0.000
cross-check vs analysis.json: 57 applicable cells, 0 mismatches

powered checks (>= 10 key failures), applicable, both splits pooled, threshold 0.5:
  recap/compression              n 119  fails 37  kappa 0.00  TPR 1.00  TNR 0.00  AUROC 0.81
  recap/coverage                 n  91  fails 23  kappa 0.23  TPR 0.79  TNR 0.43  AUROC 0.71
  transcript-en/abstention       n 253  fails 24  kappa 0.01  TPR 0.21  TNR 0.83  AUROC 0.36
  transcript-en/action_items     n 286  fails 60  kappa 0.00  TPR 1.00  TNR 0.00  AUROC 0.79
  transcript-en/compression      n 231  fails 12  kappa 0.00  TPR 1.00  TNR 0.00  AUROC 0.70
  transcript-en/coverage         n 286  fails 73  kappa 0.01  TPR 0.99  TNR 0.01  AUROC 0.75
  transcript-en/output_shape     n 341  fails 12  kappa 0.96  TPR 1.00  TNR 0.92  AUROC 1.00
one-class key (6): recap/output_shape, reply-draft/has_reply, reply-draft/language_match, reply-draft/no_invented_dates, reply-draft/signoff, reply-draft/word_limit
underpowered (6, key failures): recap/abstention (7), recap/grounded (1), reply-draft/no_invented_numbers (2), transcript-en/action_owner (1), transcript-en/grounded (3), transcript-en/withdrawn_excluded (3)
reply-draft no_invented_numbers TPR 0.50 | abstention AUROC recap 0.21, transcript-en 0.36

transcript-en action_items raw agreement: 226/286 = 79% at kappa 0.00; key pass rate 79%

train-chosen cut, read on held-out (cells with >= 10 train key failures):
  recap/compression: cut 0.6762 -> held-out kappa 0.41 (TPR 0.81, TNR 0.69, 13 key failures)
  transcript-en/abstention: cut 0.9862 -> held-out kappa 0.01 (TPR 0.07, TNR 1.00, 13 key failures)
  transcript-en/action_items: cut 0.9487 -> held-out kappa 0.44 (TPR 0.97, TNR 0.38, 39 key failures)
  transcript-en/coverage: cut 0.8289 -> held-out kappa 0.29 (TPR 0.61, TNR 0.79, 39 key failures)
  one global cut 0.842 (pooled train kappa 0.20) -> held-out kappa per cell: 0.07, 0.02, 0.00, 0.28
cross-check vs calibration.json: 0 mismatches
```

## Sources

- `docs/probes/n-a7-nimble-judge-2026-10-18/` — `RESULTS.md`, `raw_pass1.jsonl`, `raw_pass2.jsonl`, `analysis.json`, `calibration.json`, `judge_probe.py`, `calibrate_threshold.py`
- `docs/probes/matrix-2026-09-27/results/` (the outputs that were judged)
- `docs/research/deterministic-vs-judge-2026-09-30.md` (why the probe was run)
- `scripts/writeups/judge-vs-key.py`
