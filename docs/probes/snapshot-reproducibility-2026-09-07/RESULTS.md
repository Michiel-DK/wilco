# SNAPSHOT-REPRODUCIBILITY — all 7 snapshots re-taken under rule A (2026-09-07)

**Status: COMPLETE.** Every `evals/*/snapshot.json` re-taken on its committed champion with
`python3 -u sandbox/runner.py run <agent> --snapshot` (3 fresh Ollama loads each, native-API
unload verified via `/api/ps` before every load), then one `check <agent>` per exam on a
FOURTH fresh load. Ollama 0.33.2, one GPU, strictly sequential, foreground. The builder (lane
`wf_284c3d23-976`) did expense-categorization and email-triage; the main loop ran the other
five plus all seven checks (`logs/*.log`, `logs/*-check.log`; per-load results JSON beside
this file; the driver was a plain sequential shell loop, one exam per `python3 -u` call).

## Per-exam table

| exam | champion | cases | loads | unstable | flips vs previous snapshot | heldout before → after | `check` on load 4 | wall (3 loads) |
|---|---|---|---|---|---|---|---|---|
| crm-followup | gemma4-e2b-ctx16k | 38 | 3 | **0/38** | none | 0.8333 → 0.8333 | `ok (38 stable, 0 unstable exempt)` | 23 min |
| email-triage | gemma4:e2b-it-qat | 19 | 3 | **0/19** | none | 0.9091 → 0.9091 | `ok (19 stable, 0 unstable exempt)` | 6 min |
| expense-categorization | gemma4:e2b-it-qat | 15 | 3 | **0/15** | none | 0.8889 → 0.8889 | `ok (15 stable, 0 unstable exempt)` | 2 min |
| recap | gemma4:e4b-it-qat | 17 | 3 | **0/17** | none | 0.7 → 0.7 | `ok (17 stable, 0 unstable exempt)` | 24 min |
| reply-draft | gemma4:e2b-it-qat | 17 | 3 | **0/17** | none | 1.0 → 1.0 | `ok (17 stable, 0 unstable exempt)` | 7 min |
| task-intake | gemma4:e2b-it-qat | 46 | 3 | **0/46** | none | 0.95 → 0.95 | `ok (46 stable, 0 unstable exempt)` | 15 min |
| transcript-en | gemma4:e4b-it-qat | 22 | 3 | **0/22** | **5** (below) | 0.6154 → 0.6154 | `ok (22 stable, 0 unstable exempt)` | 23 min |

174 cases × 3 loads = 522 verdicts, plus 174 on the check loads: **every case gave the same
verdict on all four fresh loads.** Total GPU time ≈ 100 min for the snapshots + 34 min for the
checks — the brief's ~90-min estimate was close; the builder's "6–10 hours" in the earlier
version of this file was a misreading of its own session clock (its recap log spans
11:16→11:35 for two full loads).

### transcript-en — the 5 flips vs the committed 26 Aug snapshot

| case | split | 26 Aug snapshot | today (all 4 loads) |
|---|---|---|---|
| renewal-heldout-digits | heldout | PASS | FAIL |
| support-heldout-long | heldout | FAIL | PASS |
| support-long-train | train | PASS | FAIL |
| quiet-checkin-medium-train | train | PASS | FAIL |
| pricing-objection-medium-train | train | FAIL | PASS |

Same five cases, same directions, as `docs/probes/determinism-2026-09-06/RESULTS.md`
finding 3. Heldout aggregate identical by cancellation (8/13 both ways) — which is why
master's aggregate-only `check` printed `ok` on it yesterday.

## Pre-registered prediction: REFUTED

The brief predicted **≥ 1 unstable case on transcript-en** across 3 fresh loads. Observed:
0 of 22, on 4 fresh loads. Refuted at n=4 full-exam loads on the champion config. Per the
brief this does not block the merge; the mechanism stands on finding 3, not finding 2.

## What this does to the 6 Sep findings

- **Finding 3 (master's transcript-en snapshot does not reproduce per case; `check` masks
  it) — CONFIRMED and now caught.** The 5 flips are deterministic today; the new per-case
  comparison turns them into `DRIFT` (the fixture in `test_snapshot_reproducibility.py`
  execs master's real `cmd_check` and shows `ok` vs this PR's `DRIFT` on the identical
  two-flip shape), and the runtime stamp refuses the old snapshot before any inference
  (`RUNTIME: snapshot has no runtime block; re-snapshot` — seen live via
  `test_dedupe_tools.py` before crm-followup was re-taken).
- **Finding 4 (the Ollama bump is the first cause) — SUPPORTED.** Of the four snapshots
  taken before the 31 Aug binary change (expense 26 Jul, reply-draft 26 Jul, recap 29 Jul,
  transcript-en 26 Aug), only transcript-en moved; the three post-bump snapshots
  (crm, email-triage, task-intake, 4–5 Sep) reproduce exactly. The bump changed verdicts on
  one exam — the 4B with the longest inputs — and did so deterministically.
- **Finding 2 (temp-0 output differs ACROSS loads on one runtime version) — NOT
  REPRODUCED.** Yesterday's evidence was `support-heldout-long` flipping between loads on
  a 4-case scratch exam (both at ctx16k and at the 4k champion). Today the full 22-case exam
  gave the same answer on that case in 4 of 4 loads, PASS. The observation stands as
  recorded; its generalisation ("temp-0 is not reproducible across loads") is downgraded to
  *observed once, on a 4-case subset, not reproduced at full-exam scale*. A plausible
  mechanism the probe did not control for: the case SET (4 vs 22) rather than the load.
  Not chased in this lane.

## Consequence for PR #78 (transcript-long)

Its two booked "window losses" `renewal-heldout-digits` and `quiet-checkin-medium-train`
fail at 4k on the current runtime in every load here — they are runtime-bump losses, not
window losses, and the new transcript-en snapshot is the baseline pass 2 must be diffed
against.

## Rule A as shipped (what a snapshot now claims)

A committed snapshot's verdict on a STABLE case = the verdict on 3 fresh model loads of the
recorded Ollama version. `check` refuses on a different runtime version, a missing runtime
block, or a changed case set; otherwise it unloads, runs once, and fails on any stable
case moving in either direction (`DRIFT`) or on the aggregate tolerance (`REGRESSION`).
Today every case on every exam is STABLE; `unstable k/n` in `runner.py list` is the
running tally.

## Notes

- `metrics_totals` is intentionally absent from the aggregate snapshot (it would be load
  1's total presented as three loads — gotcha 13's shape). Per-load totals are in the
  `__loadK.json` files here.
- `results/snapshot_loads/` is where per-load results land; `results/` stays disposable.
- The first main-loop attempt to run the five remaining snapshots was killed at the tool's
  10-min cap after crm-followup load 1; the rerun restarted crm-followup from load 1 (no
  splicing) and ran detached (`nohup`), which is what the `logs/` here come from.
