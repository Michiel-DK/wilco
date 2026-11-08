# Per-case reproducibility of local temp-0 runs — a probe forced by PR #78's review (2026-09-06)

**Trigger:** python-reviewer (critical) and the correctness refuter on PR #78 both found the
lane's committed `snapshot.json` did not reproduce per case on independent `check` runs
(2 of 32 cases). Before deciding the lane, the main loop characterised the effect.

## What was run (all foreground, real entry point `runner.py run`/`check`, results in `results/`)

Scratch copy of PR #78's head with 4 cases only — `quiet-checkin-medium-train` (869 chars),
`renewal-heldout-digits` (3,278), `support-heldout-long` (5,615), `longcall-discovery-train-1`
(15,331); then master's full 22-case `check` at the old champion.

| run | config | load | `support-heldout-long` | note |
|---|---|---|---|---|
| det16k_1/2/3 | ctx16k, forward order | load A (already resident) | PASS ×3 (summary 367 chars, has `1284.50`) | identical across 3 runs |
| det16k_rev | ctx16k, reversed | load A | PASS | order does not matter within a load |
| det16k_rev_fresh | ctx16k, reversed | load B (`ollama stop`, reload) | **FAIL** (332 chars, no `1284.50`) | = the committed snapshot's verdict |
| det16k_rev_warm2 | ctx16k, reversed | load B, warm | FAIL | stable within load B |
| det16k_coresident | ctx16k, 2B loaded beside it | load B | FAIL | co-residency after load: no effect |
| det16k_2bfirst | ctx16k, 2B loaded FIRST, then 16k | load C | FAIL | |
| det4k_load1/2 | **4k (old champion)**, 4-case scratch | loads D, E | FAIL, FAIL | old snapshot: FAIL — but `renewal-heldout-digits` and `quiet-checkin-medium-train` FAIL here too; old snapshot has both PASS |
| master_check_4k_full22 | **4k, master, full `check`** | load F | PASS | `check` printed `ok: heldout 0.6154 vs snapshot 0.6154` |

## Findings

1. **Within a load, temp-0 output is deterministic** — 7 of 7 repeat runs agreed with their
   own load, in either order.
2. **Across loads it is not.** The same config, same case, same prompt produced two stable
   outputs (367 vs 332 chars) depending on the model load. Not order, not co-residency
   after load, not the window: the OLD 4k champion shows it too (`support-heldout-long`
   FAIL in two 4-case loads, PASS in the full-22 load, same day).
3. **Master's committed 26 Aug transcript-en snapshot does not reproduce per case today**
   (`master_check_4k_full22_2026-09-06.json`): heldout `renewal-heldout-digits` PASS→FAIL and
   `support-heldout-long` FAIL→PASS; train `support-long-train` PASS→FAIL,
   `quiet-checkin-medium-train` PASS→FAIL, `pricing-objection-medium-train` FAIL→PASS.
   5 verdicts of 22 differ; the heldout aggregate is unchanged by cancellation, so
   **`runner.py check` reported `ok`** — it compares the heldout SCORE, never the per-case
   verdicts. Gotcha 1 in its purest form: the gate is present and does not measure this.
4. **Likely first cause: the Ollama runtime moved.** `/Applications/Ollama.app/.../ollama`
   is dated 31 Aug (version 0.33.2 today); the 27 Aug results file for the same config
   matches the 26 Aug snapshot with 0 flips. The snapshot records `harness_sha` and not
   the runtime version. Finding 2 (across-load variance on one version) is separate and
   unexplained; both undermine "committed configs reproduce at samples=1, temp 0".
5. **Consequence for PR #78:** two of its three booked "losses from the window swap"
   (`renewal-heldout-digits`, `quiet-checkin-medium-train`) also fail at 4k today — they
   are not the window's cost. Its flip list and its clause-1 claim are both artefacts of
   findings 2–4, not of the lane's code.

## Scope of evidence

One machine (Apple Silicon, Metal), one exam, one day, 4+22 cases, ~12 runs. The
"0 flips across 3 runs" results elsewhere in this repo (crm ctx16k 4 Sep, email-triage ×5
4 Sep) were same-day and very likely same-load — they do not contradict finding 2.
Not measured: other exams across loads; whether `OLLAMA_NUM_PARALLEL` / batch settings /
free memory at load select the attractor; Ollama 0.33.x changelog.

## What this asks of the operator (instrument decisions, not lane decisions)

- `check` should compare per-case verdicts against the snapshot, not only the heldout
  aggregate (today's master `check` is green on a 5-of-22 divergence).
- Snapshots should record the runtime version (`ollama --version`) beside `harness_sha`,
  and a version bump should force a re-snapshot, reported as such.
- A cross-load protocol for "deterministic": e.g. a snapshot is the verdict set agreed by
  ≥2 of 3 fresh loads, with disagreeing cases listed as UNSTABLE rather than PASS/FAIL.
