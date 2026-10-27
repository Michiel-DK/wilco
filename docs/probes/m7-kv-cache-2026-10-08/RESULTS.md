# M7 — KV-cache bake-off: does a quantised K/V cache move any verdict? (2026-10-08, laptop, $0)

> **EVIDENCE CELL:** the committed f16 snapshots of `transcript-en` (gemma4-e4b-ctx16k) and `crm-followup` (gemma4-e2b-ctx16k), both
> re-sat 2 Oct at Ollama 0.35.0, **vs** the same exams, same models, same runtime version, 3 loads each, on a second Ollama
> instance (127.0.0.1:11435) started with `OLLAMA_KV_CACHE_TYPE=q8_0` and then `q4_0` (`OLLAMA_FLASH_ATTENTION=true`, server log
> line in `logs/`). Verdict = per-case rule A (`compare.py`): any case stable on both arms that passes on f16 and fails on the arm.
> **Not evidence:** wall times (shared laptop, the M1 lane's tests run beside it); memory figures (`ollama ps`, one instance,
> sampled); the labels exams (not run — short inputs, the cache is not the lever there).

**Why:** the K/V cache, not the weights, bounds the window on a 16 GB machine. If q8_0 holds every stable case, the ctx16k champions
can take a 32k window at the same memory (gotcha 16: the window is a precondition). Pickup note §8.

**Registered before the run (15:10, 8 Oct):**
1. `q8_0`: **0 stable cases flip** on both exams (train + held-out).
2. `q4_0`: flips **only on transcript-en** (long inputs, numbers); 0 on crm-followup.
3. Memory at the exam's own context: q8_0 ≈ half the f16 cache, q4_0 ≈ a quarter (vendor figures; measured here only as `ollama ps` size).
4. **The runtime stamp cannot see this setting:** `runtime.version` is 0.35.0 on every arm, so `check` would accept a q4_0 server as the
   committed runtime. If prediction 2 shows any flip, that is a gotcha-15 class finding: a server-side env var is a silent re-roll.

**Kill / what would refute:** any stable flip on q8_0 refutes 1 and closes the 32k lead; 0 flips on q4_0 for transcript-en refutes 2
(then q4_0 is free memory and the question moves to the long band at 32k).

**Mechanics:** probe worktree from master `HEAD`, `sandbox/router.py` base_url pointed at :11435 (uncommitted, probe-only — the
real entry point `run --snapshot --loads 3` is unchanged); the worktree's `evals/<exam>/snapshot.json` is overwritten per arm and copied
to `snapshot-<arm>-<exam>.json` here, then restored. The app's own instance on :11434 stays untouched.

## What ran

_(filled by `m7.sh` + hand after the arms finish)_

### Arm 1 — `q8_0`, transcript-en (gemma4-e4b-ctx16k), 3 loads, 3,150 s wall, 0/32 unstable on both sides

| | train (13) | held-out (19) | flips | runtime stamp |
|---|---|---|---|---|
| f16 (committed 2 Oct) | 7 | 10 | — | ollama 0.35.0 |
| q8_0 cache | **5** | **11** | 1 up (`renewal-heldout-medium`, held-out) · 2 down (`longcall-support-train-1`: `check_coverage` omitted "38 minutes"; `pricing-objection-medium-train`: `check_action_items` missing "comparison"), both train, both 3/3 | **ollama 0.35.0 — identical** |

**Prediction 1 (q8_0: 0 stable flips) is REFUTED on the first exam.** Three stable verdicts moved; the kill as registered (stable
held-out DOWN) does not fire, but the premise "q8_0 is verdict-neutral" is dead. Prediction 4 is therefore live, not hypothetical:
`check` compares `runtime.version` and would accept a q8_0 server as the committed f16 runtime, so **a server-side environment
variable is a silent re-roll of exactly the class gotcha 15 describes** (the 0.33.2 bump moved 5 of 22 the same way). Memory
during the arm: `ollama ps` 3.1 GB at the 16,384 context (f16 sample pending, M6's waiter records it).

### Arm 2 — `q8_0`, crm-followup (gemma4-e2b-ctx16k), 3 loads, 2,110 s wall, 0/38 unstable on both sides

| | train (20) | held-out (18) | flips | runtime stamp |
|---|---|---|---|---|
| f16 (committed 2 Oct) | 12 | 15 | — | ollama 0.35.0 |
| q8_0 cache | **11** | 15 | 1 down (`redundant-stale-refresh`, train, 3/3: `crm_lookup` called again with identical args — the redundancy monitor) | identical |

Held-out unchanged; one stable train verdict moved. Running count after two arms: **4 stable flips out of 70 cases on q8_0**,
0 held-out down, 1 held-out up. `ollama ps` 3.6 GB at 16,384 context for the 2B (its f16 figure: M6's waiter).

### Arm 3 — `q4_0`, transcript-en (gemma4-e4b-ctx16k), 3 loads, 3,194 s wall, 0/32 unstable on both sides — **KILL FIRES**

| | train (13) | held-out (19) | flips | runtime stamp |
|---|---|---|---|---|
| f16 (committed 2 Oct) | 7 | 10 | — | ollama 0.35.0 |
| q4_0 cache | 7 | **8** | 2 up (train) · 4 down: 2 train + **2 stable held-out** (`support-heldout-long`: `check_coverage` omitted "1284.50"; `support-heldout-short`: `check_action_items` missing "FD-1190"), every flip 3/3 | identical |

Prediction 2 (q4_0 flips on transcript-en) holds in direction; the registered kill (a stable held-out case down) fires: **a 4-bit
cache loses two held-out call summaries the committed f16 champion passes**, both on precise tokens (an amount, a ticket id). The
server log line for this arm reads `OLLAMA_KV_CACHE_TYPE:q4_0`; `ollama ps` reports the same 3.1 GB as q8_0 and so says nothing
about the cache size (not evidence, as registered).

### Arm 4 — `q4_0`, crm-followup (gemma4-e2b-ctx16k), 3 loads, 2,032 s wall, 0/38 unstable on f16, **2/38 unstable on q4_0** — **KILL FIRES**

| | train (20) | held-out (18) | flips | runtime stamp |
|---|---|---|---|---|
| f16 (committed 2 Oct) | 12 | 15 | — | ollama 0.35.0 |
| q4_0 cache | 14 | **12** | 2 up (train; one unstable) · 3 down: **2 stable held-out** (`crm-outage-mid-sweep`: no final answer emitted, 3/3; `peeters-hedge-suppresses-lookup`: never called `deals_list`, 3/3) + 1 unstable | identical |

## Verdict (all four arms, 8 Oct 15:07–18:02, $0)

| arm | exam | stable flips | stable held-out DOWN | kill |
|---|---|---|---|---|
| q8_0 | transcript-en | 3 of 32 (1 held-out up, 2 train down) | 0 | no |
| q8_0 | crm-followup | 1 of 38 (train down) | 0 | no |
| q4_0 | transcript-en | 6 of 32 | **2** | **fires** |
| q4_0 | crm-followup | 4 of 38 (+2 unstable) | **2** | **fires** |

- **Prediction 1 REFUTED:** q8_0 is not verdict-neutral — 4 stable verdicts moved across 70 cases, with 0 held-out down. By the gate's
  own rule (a challenger replaces the incumbent only if it passes every stable case the incumbent passes) q8_0 would still be accepted
  on these two exams, because every stable move was train or upward. That is a pass on the rule, not neutrality.
- **Prediction 2 REFUTED in half:** q4_0 flips on transcript-en as predicted AND on crm-followup, where it was predicted clean: two
  stable held-out cases down on each, and crm gains instability (2/38) the f16 champion does not have. The 32k-window lead is closed
  for q4_0 and open only for q8_0, under the rule above.
- **Prediction 4 CONFIRMED and now the finding that matters:** `runtime.version` reads `0.35.0` on every arm. A `check` run against a
  server started with `OLLAMA_KV_CACHE_TYPE=q4_0` would see the identical stamp, run, and report two held-out cases down as a model
  regression — or, on q8_0, report train cases moving and a held-out case up as if the champion had changed. **The KV-cache type is a
  server-side setting the stamp cannot see; it must be declared in the snapshot by hand until Ollama exposes it** (the `/api/version`
  endpoint carries only the version; the server config line exists only in the server's own log). Same class as gotcha 15.
- **Memory:** `ollama ps` reported the same size on q8_0 and q4_0 (3.1 GB e4b, 3.6 GB e2b), so it does not expose the cache saving at all;
  the f16 figure M6's waiter samples is only comparable to itself. Not evidence, as registered.

**What this changes:** (1) a new line for the snapshot: `kv_cache_type` recorded by hand from the server log (a runner field is a
full-tier change; until then the RESULTS of every snapshot run name it); (2) q8_0 as the route to a 32k window on 16 GB is a
*candidate*, to be sat as its own champion arm under rule A on the long transcripts — not assumed; (3) q4_0 is out.
**Not done here:** labels exams; a 32k Modelfile; the f16 memory baseline (M6 waiter); any champion change (operator-signed).
