# M6 — a rule always-on vs the committed baseline on crm-followup (2026-10-08, laptop, $0)

> **EVIDENCE CELL:** the committed crm-followup snapshot (gemma4-e2b-ctx16k, Ollama 0.35.0, re-sat 2 Oct, 3 loads) **vs** the same
> model, same runtime, same cases, 3 loads, with ONE rule appended to `agents/crm-followup/prompt.md` for every case — the E6
> library's own fix text for `redundant-retry-outage`: *"never repeat a tool call with identical arguments after an error; state
> that the source is down and answer with what you have."* Verdict per case, rule A (`compare.py`).
> **Not evidence:** wall times; any reading of WHY a case flipped beyond its `failed_checks` (the mechanism section is a reading).

**Why:** pickup note §9 test 1. E6 (9 Sep) injected 21 lessons by retrieval and lost 4 held-out on crm; its mechanism section named
this rule as the big loss (the outage-protocol checks REQUIRE the retry/acknowledge behaviour the rule argues against). That was one
arm among 21 lessons. This isolates the one rule, always on, so the "always-on breaks the outage cases" half of the §9 hypothesis gets
its own number.

**Scope cut, declared:** the §9 design has three arms — always-on, *scoped* (the rule shown only right after a successful identical
call), and *sham scoped* (generic text at the same moments). Scoped and sham need a hook inside the agent loop (inject text at a
trace event); that is a `sandbox/runner.py` change (full tier, PR) and is NOT in this probe. Only the always-on arm runs here. If it
does not break the outage cases, the §9 premise for crm is already weakened and the hook is not worth a lane.

**Registered before the run (15:25, 8 Oct):**
1. Always-on: **≥ 1 stable held-out case DOWN** among the outage/retry family (`redundant-retry-outage-deals`, `crm-outage-mid-sweep`,
   `peeters-outage-fill-in`, `peeters-outage-honest-ack`, `peeters-partial-honest-control`) — the E6 mechanism reproduced in isolation.
2. **0 held-out UP**: a rule that is true for one train case generalises to nothing on held-out.
3. Train: `redundant-retry-outage` (the rule's own source case) passes on both arms or flips UP; its siblings (`redundant-sibling-outage`,
   `outage-mid-sweep-regression`) are the likely train DOWNs.
**Refuted if:** 0 stable held-out down (then "always-on breaks the protocol" was an E6 artefact of 21 lessons + format destabilisation,
not of this rule) — in that case the scoped hook has nothing to beat on crm and the lane is not opened.

**Mechanics:** detached probe worktree at master `HEAD`; `agents/crm-followup/prompt.md` + the two rule lines (uncommitted, probe-only);
`run crm-followup --snapshot --loads 3` through the real entry point on the app's own Ollama instance (:11434, f16 cache); runs ONLY
after M7's arms finish (one 16 GB machine); snapshot copied to `snapshot-always-on.json`, compared with `git show HEAD:` baseline.

## What ran (8 Oct 18:03–18:28, 1,463 s wall, 3 loads, 0/38 unstable on both arms)

| | train (20) | held-out (18) | flips | runtime |
|---|---|---|---|---|
| baseline (committed 2 Oct) | 12 | 15 | — | ollama 0.35.0, f16 |
| always-on rule | 13 | **13** | 2 up, both train (`redundant-retry-outage` — the rule's own source case — and `decoy-owner-after-deals-devos`) · 3 down: **2 stable held-out** (`crm-outage-mid-sweep`: no final answer emitted, 3/3; `peeters-hedge-suppresses-lookup`: never called `deals_list`, answer missing 4200, 3/3) + 1 train (`redundant-stale-refresh`: repeated identical `crm_lookup`, 3/3) | identical |

## Verdict

- **Prediction 1 CONFIRMED — kill fires:** two stable held-out cases down. `crm-outage-mid-sweep` is the outage family as predicted;
  `peeters-hedge-suppresses-lookup` is not an outage case — the rule's second clause ("state that the source is down and answer with
  what you have") read as a licence to skip the second lookup. The E6 mechanism reproduces in isolation: one true-for-one-case rule,
  always on, costs two held-out cases on this exam.
- **Prediction 2 CONFIRMED:** 0 held-out up. **Prediction 3 CONFIRMED:** the rule fixes exactly its own source case (train) and nothing
  the source case does not resemble; its sibling `redundant-stale-refresh` goes DOWN — the rule says "after an error", the sibling's
  repeat follows a success, and the model generalised the ban the wrong way.
- **The §9 hook is now worth a lane:** "scoped" (shown only after a successful identical call) is the arm that would have to beat
  13/18 → 15/18 on held-out while keeping the source case. Not run here; a `runner.py` change (full tier).
- **Cross-probe observation, not a prediction:** the SAME two held-out cases (`crm-outage-mid-sweep`, `peeters-hedge-suppresses-lookup`)
  went down under M7's 4-bit KV cache the same evening — an unrelated perturbation. Both are marked stable (3/3) in the committed snapshot
  and both flip under either nudge. They are the exam's margin: the held-out score's first two cases to go in any change. The gate catches
  them, which is the point; a report that names "the cases that always move first" would be a cheap addition to `check`.

**f16 memory samples (M7's baseline, `ollama ps` on :11434):** e4b-ctx16k 3.3 GB at 16,384 (q8_0/q4_0 instance showed 3.1 GB);
e2b-ctx16k 1.8 GB at 16,384 (the :11435 instance showed 3.6 GB under both quantised arms — a larger figure, not a smaller one).
`ollama ps` is not a cache-size instrument; left as recorded, not interpreted.
