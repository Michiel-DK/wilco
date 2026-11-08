# Re-snapshot of all 8 exams on the KV-cache-stamp lane (PR #105), 2026-10-10

> **EVIDENCE CELL:** per-case verdicts, committed snapshots at `origin/master` (Ollama 0.35.0, 3 loads) vs this
> re-snapshot on `lane/as-4-kv-cache-stamp` @ 27018af (Ollama 0.40.2, 3 loads, `kv_cache_type: unset`,
> `flash_attention: unset`): **0 of 230 stable verdicts moved, 0 cases unstable, 0 cases added or removed.**

**Not evidence:**
- Anything about the KV-cache type as a cause. This run used one cache setting (server default), so it cannot
  isolate it. The 8 Oct q8_0 / q4_0 arms (`docs/probes/m7-kv-cache-2026-10-08`) are the evidence for that.
- `wall_ms` changes in the crm-followup per-turn metrics. Timing is not a verdict.
- The aggregate train/heldout scores. They match too, but gotcha 15 says an aggregate can hide flips that cancel
  out, so the per-case diff is the evidence.

## Confound, stated first: this is also a runtime bump

Every snapshot at `origin/master` carries `runtime.version` 0.35.0. The live server, and therefore every new snapshot,
is 0.40.2 (`curl localhost:11434/api/version` → `{"version":"0.40.2"}`). So two things changed at once: the runtime
version and the new stamp fields. **A per-case diff cannot separate them.** In this run nothing moved, so there is no
move to attribute to either one. The result does not show that 0.40.2 is verdict-neutral in general. It shows only
that these 230 cases, on these champions, at the default cache type, gave the same verdicts as they did on 0.35.0.

## Run

- Command: `python3 -u sandbox/runner.py run-all --snapshot`, started by the laptop scheduler at
  2026-10-10T19:00:37 (log `laptop-scheduler/log/as-4-kv-cache-stamp-resnapshot.log`, 742 lines). All 8 exams
  printed their `(aggregate of 3 loads)` line.
- Ollama server: one process for the whole run. `~/.ollama/logs/server.log` has a single `server config` line
  (12:35:27, before the run), with `OLLAMA_KV_CACHE_TYPE:` empty (default) and `OLLAMA_FLASH_ATTENTION:false`. That
  agrees with the stamp's `"unset"` / `"unset"`. This is the hand-recorded cache type that gotcha 21 asks for.
- `harness_sha` in every snapshot: `40fec48…` (unchanged from master).

## Per-exam diff (new snapshot vs `git show origin/master:evals/<exam>/snapshot.json`)

| exam | champion | cases (old→new) | added | removed | stable verdicts moved | became unstable | unstable (new) | train | heldout | stamp |
|---|---|---|---|---|---|---|---|---|---|---|
| call-fields | gemma4-e4b-ctx16k | 32→32 | 0 | 0 | 0 | 0 | 0 | 0.7692 = | 0.7368 = | 0.40.2 · kv unset · fa unset |
| crm-followup | gemma4-e2b-ctx16k | 44→44 | 0 | 0 | 0 | 0 | 0 | 0.6 = | 0.875 = | 0.40.2 · kv unset · fa unset |
| email-triage | gemma4:e2b-it-qat | 21→21 | 0 | 0 | 0 | 0 | 0 | 0.875 = | 0.7692 = | 0.40.2 · kv unset · fa unset |
| expense-categorization | gemma4:e2b-it-qat | 15→15 | 0 | 0 | 0 | 0 | 0 | 1.0 = | 0.8889 = | 0.40.2 · kv unset · fa unset |
| recap | gemma4:e4b-it-qat | 17→17 | 0 | 0 | 0 | 0 | 0 | 0.4286 = | 0.7 = | 0.40.2 · kv unset · fa unset |
| reply-draft | gemma4:e2b-it-qat | 19→19 | 0 | 0 | 0 | 0 | 0 | 1.0 = | 0.9167 = | 0.40.2 · kv unset · fa unset |
| task-intake | gemma4:e2b-it-qat | 50→50 | 0 | 0 | 0 | 0 | 0 | 0.8929 = | 0.9545 = | 0.40.2 · kv unset · fa unset |
| transcript-en | gemma4-e4b-ctx16k | 32→32 | 0 | 0 | 0 | 0 | 0 | 0.5385 = | 0.5263 = | 0.40.2 · kv unset · fa unset |
| **total** | | **230→230** | 0 | 0 | **0** | 0 | **0** | | | 8/8 non-null |

Held-out: **no stable held-out case moved.** No champion or split changed.

Besides the stamp, the only changes in the snapshot files are `date` (all 8) and per-turn `wall_ms` (crm-followup).
I checked crm-followup line by line: every changed line is `wall_ms`, `date` or `runtime`.

## How the diff was checked (gotcha 2: a green diff proves nothing until it has been seen red)

- The differ matches cases by `id`, checks that ids are unique, and compares `passed` only where the case is
  `stable` on both sides. It also reports added/removed ids, split changes and stable→unstable cases.
- **Seen red:** I flipped `passed` on one held-out recap case (`buried-critical`) in the working copy and reran the
  differ. It reported exactly `recap: buried-critical heldout PASS→FAIL`. I then restored the file from the backup
  and confirmed the sha matches (`656fbc9…`).
- **Snapshot vs log:** for all 230 cases, the `passed` value in the snapshot equals the load-3 `[PASS]/[FAIL]` line
  in the run log. 0 mismatches.
