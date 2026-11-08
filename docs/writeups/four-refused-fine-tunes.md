# Four fine-tunes the held-out gate refused

**4 of 4 LoRA adapters were refused.** On a CRM follow-up exam (20 train, 18 held-out cases), each adapter
lost held-out cases the base model passed: 2, 2, 3 and 4. The last three counts are cases stable across 3
samples on both arms; the first adapter ran once, so its 2 are one-pass losses. The gate does not average:
a held-out case that passed on the base and fails on the adapter is a regression, whatever the train score
did. The script below recounts every verdict from committed files.

## The setup

A 2B open-weight model (Gemma 4 E2B, 4-bit MLX build), served locally with a LoRA adapter. The exam is
tool-calling: a question about a client, mocked `crm_lookup` / `deals_list` tools, an answer graded by
deterministic checks, no LLM judge. Training rows are passing trajectories on **train** cases only; a leak
guard was seen failing on a planted held-out row before every build.

Caveat for all four: the MLX base scores 12/18 held-out; the shipped champion (same family, different
quantisation and runtime) scores 15/18. Nothing here is a statement about the champion.

## The four runs

| run | what changed | train | held-out | held-out lost (base pass → adapter fail) |
|---|---|---|---|---|
| v1 | 11 rows of passing single-turn trajectories, 100 iters | 16 → 13 | 12 → 12 | 2 (one pass) |
| v2 | 16 rows, multi-turn traces added, 150 iters | 16 → 17 | 12 → 12 | 2 stable |
| v3 | 30 rows, 57% with two or more tool calls in one turn, 250 iters | 16 → 16 | 12 → 11 | 3 stable |
| v4 | the same 30 rows cut into 96 per-step examples, prompt masked, 400 iters | 16 → 13 | 12 → 9 | 4 stable |

**v1.** Nine of 11 rows were one call then an answer, and the adapter learned that: cases needing a second
call failed with `never called tool 'deals_list'`. Held-out stayed 12/18 only because two other cases went
up. *Lesson: a flat held-out score can hide two regressions; count per case.*

**v2.** Multi-turn rows added; first stability-controlled snapshots on this runtime (0 of 38 unstable).
Not repeating identical calls transferred; `two-tool-combo` still stopped after one call. *Lesson:
multi-turn rows put one call per turn; they do not teach two calls inside one turn.*

**v3.** We augmented exactly that shape: 20 train-only variant inputs (screened for any 40-character
overlap with held-out), 14 of which gave passing rows. The adapter got worse, and two of its own training
rows failed: on a prompt byte-identical to its row up to the first tool result, where the row calls again,
it answered. Cause: no prompt mask, so the loss covered every token, mostly 4–5 KB JSON tool payloads.
Train loss 0.005 meant payloads memorised, not decisions. *Lesson: what the rows contain is not what the
loss sees.*

**v4.** One example per assistant step, earlier context masked out of the loss. The target moved: for the
first time `two-tool-combo` passed 3/3, both tools called. Four other held-out cases broke. After a tool
result the target was "call again" in 40 of 96 examples, "answer" in 56; the adapter learned the reflex
without the stop condition and repeated the identical call or looped to the step limit. *Lesson: a per-step
cut changes the call/answer base rate; count targets by kind before training.* The iteration-200
checkpoint (v4b, picked for its lower validation loss) was worse: 5/18, 7 stable held-out lost, every
failure `no final answer emitted`.

## What did not hold, and what did

- **No adapter gained held-out score.** The registered v2–v4 prediction, "0 stable held-out down", failed
  every time. On synthetic cases a fine-tune could only ever show "holds".
- **Train scores are not evidence**: the rows are the train cases.
- **The token effect is real**: v1 completion tokens 13,807 → 3,465 (−75%), reasoning characters 35,590 → 0.
- **Each refusal named the next defect** (under-calling v1–v3, over-calling v4); an average would have hidden it.
- The next fix (up-weight answer steps, or mask only tool payloads in whole rows) is **unrun**.

⚠️ Not re-derived (taken from the probe write-ups): the 4–5 KB payload size, train/validation losses, the
40/56 target split, and token effects for v2–v4 (MLX snapshots carry no metrics). Correction from the
recount: v1's probe write-up says "3 held-out down"; its committed results files show 2 down, 2 up.

*Not included:* E6 (prompt-injected lessons), E30 (a two-call strategy), E31 (a quantisation swap), E38
(encoder extractors) were also refuted, but none trains weights.

## Re-derive

```sh
python3 scripts/writeups/four-refused-fine-tunes.py
```

Output (run 2026-11-06):

```
v1   [one pass, not rule-A] train 16/20 -> 13/20 | held-out 12/18 -> 12/18 | up 3 down 6 | unstable 0 | held-out down 2 (one pass) -> REFUSED by its registered prediction
v2   [rule-A, 3 samples] train 16/20 -> 17/20 | held-out 12/18 -> 12/18 | up 3 down 2 | unstable 0 | stable held-out down 2 -> REFUSED
v3   [rule-A, 3 samples] train 16/20 -> 16/20 | held-out 12/18 -> 11/18 | up 4 down 5 | unstable 0 | stable held-out down 3 -> REFUSED
v4   [rule-A, 3 samples] train 16/20 -> 13/20 | held-out 12/18 -> 9/18 | up 1 down 7 | unstable 0 | stable held-out down 4 -> REFUSED
v4b  [rule-A, 3 samples] train 16/20 -> 4/20 | held-out 12/18 -> 5/18 | up 0 down 19 | unstable 0 | stable held-out down 7 -> REFUSED
base snapshots v2 == v3 == v4 case for case: True
v1 completion tokens 13807 -> 3465 (-75%), reasoning chars 35590 -> 0
adapters refused by the held-out gate: 4 of 4
```

## Sources

- `docs/probes/i2-crm-lora-2026-09-20/RESULTS.md`, `results-base.json`, `results-adapter.json`
- `docs/probes/i2v2-crm-lora-2026-09-21/RESULTS.md`, `snapshot-base.json`, `snapshot-adapter.json`
- `docs/probes/i2v3-crm-lora-2026-09-21/RESULTS.md`, `snapshot-base.json`, `snapshot-adapter.json`
- `docs/probes/i2v4-crm-lora-2026-09-21/RESULTS.md`, `snapshot-base.json`, `snapshot-adapter.json`,
  `snapshot-adapter-iter200.json`, `compare.py` (the per-case gate rule this script reuses)
