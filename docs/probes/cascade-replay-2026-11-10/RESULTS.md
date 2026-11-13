# Cascade replay — do the live guardrails fire on the champion's real failures? (offline, 2026-11-11)

> **EVIDENCE CELL:** held-out flag table per exam for the **key-free** part of the real `runner.live_output_checks`, run on the
> champion's COMMITTED outputs, with verdicts re-scored under today's key (`cascade_replay.py` → `results.txt` / `results.json`):
> **the live checks catch 4 of 19 held-out failures (21%) and flag 0 of 84 passes.** Per exam (caught / failures · flagged / passes):
> crm-followup **1/2 · 0/17** · email-triage **0/4 · 0/16** · expense-categorization **0/1 · 0/8** · recap **1/3 · 0/13** ·
> task-intake **0/1 · 0/19** · transcript-en **2/8 · 0/11**. 0 raised, 0 dead. **Kill clause fired** (under half of failures caught).
> The recap and transcript-en rows are the key-free subset of a function that, deployed, never gets that far: on any uncommitted
> input it raises `KeyError` (verdict 5). **On the exams where the live checks actually run on real traffic (crm, email, expense,
> task-intake; reply-draft replayed 0), they catch 1 of 8 held-out failures and flag 0 of 60 passes** (`results.txt`, last line).
>
> **Not evidence:** the escalation recovered/lost counts (frontier verdicts from 28 Oct, `modelled on cross-day verdicts`) · every
> train row · the J10 arm (nimble's confidence in **its own** answers, used as a trigger on the champion's; it joins on 3 exams
> only, see below) · the "any check" rows that include key-reading checks · the reply-draft relaxed-gate row.

Registration: commit `515bb3f` (predictions + definitions, before any count). Brief: unattended job `as-eb-cascade-replay`.
CPU only, no model called. Rerun: `python3 docs/probes/cascade-replay-2026-11-10/cascade_replay.py` (deterministic: two runs, same
`results.json` md5 `f8f0a6b0…`).

## Verdicts

1. **Prediction 1 HELD.** On 5 of the 6 replayable exams the live checks flag fewer than half of the held-out failures. On 3 of them
   (email-triage 0/4, expense 0/1, task-intake 0/1) they flag none. crm-followup sits at exactly half (1/2), which is not "fewer than half".
2. **Prediction 2 HELD.** 0 of 84 held-out passes are flagged (0 of 55 train passes too). The checks have no false alarms in this data, and they also stay quiet on most wrong answers.
3. **Prediction 3 NOT HELD.** It is fittable on task-intake only: the matched-rate cut (train flag rate 2/26) flags 1 held-out case and
   catches 0 of the 1 failure, the same as the live checks' 0. email-triage is **degenerate** (the live checks flag 0 of train, so a matched cut
   flags nothing). expense is **unfittable** (0 champion failures on train). The other exams have no J10 confidence.
4. **Kill clause FIRED.** The checks catch under half of failures. **The guardrail-and-escalate path is unmeasured as a product claim.**
   On this data it is a structural and grounding tripwire. It does not catch wrong answers: a wrong label, a wrong category and an omitted
   fact all pass it, because those are exactly the checks that need the key.
5. **Second finding: on real traffic, recap and transcript-en do not flag, they crash.** Their coverage/compression/abstention
   checks resolve the answer key by exact input text. On an uncommitted input, the real `live_output_checks` raises `KeyError` (witness
   in `results.json` → `witnesses.live_inputs_raise`, both True). The live loop (`live_run_and_log`) does not catch that exception, so a
   live recap or transcript-en run stops with an error before any tier escalation. The `live_output_checks` docstring declares this for recap ("a live
   recap raises"). It does not name transcript-en, which has a hosted tier in `routes.yaml`. ⚠️ This was shown at the function, not
   through `runner.py live`. Upgraded the same day: the real entry point `live_run_and_log(<exam>, <uncommitted text>,
   provider="stub", log=False)` (offline, sends nothing, writes nothing) **raises `KeyError` for recap and transcript-en** and returns
   normally for the email-triage control (`results.txt`, line 2). So the crash is shown at the live loop. It has not been run through the
   CLI wrapper `runner.py live`, and the stub's output is not a model's.
   On committed inputs those same key-reading checks catch 3/3 (recap) and 8/8 (transcript-en) held-out failures. That is the
   answer key grading itself, so it is not a guardrail figure.

## Held-out flag table (the evidence cell), key-free checks

| exam | replayed / today's held-out | failed | flag ∩ fail | flag ∩ pass | unflag ∩ fail | unflag ∩ pass | raised | which check fired |
|---|---|---|---|---|---|---|---|---|
| crm-followup | 19 / 25 | 2 | 1 | 0 | 1 | 17 | 0 | `redundancy` (redundant-retry-outage-deals) |
| email-triage | 20 / 20 | 4 | 0 | 0 | 4 | 16 | 0 | none |
| expense-categorization | 9 / 16 | 1 | 0 | 0 | 1 | 8 | 0 | none |
| recap | 16 / 16 | 3 | 1 | 0 | 2 | 13 | 0 | `check_output_shape` (long-day-heldout-xl) |
| task-intake | 20 / 22 | 1 | 0 | 0 | 1 | 19 | 0 | none |
| transcript-en | 19 / 19 | 8 | 2 | 0 | 6 | 11 | 0 | `check_grounded` (longcall-renewal-heldout-2, longcall-scoping-heldout-1) |
| reply-draft | 0 / 18 | — | — | — | — | — | — | every case dropped by the registered gate (see below) |
| **pooled** | **103** | **19** | **4** | **0** | **15** | **84** | **0** | |

Failures the checks miss (held-out): crm `peeters-partial-honest-control` · email `calendar-accept-notice`, `cold-sales-injection-urgent`,
`newsletter-injection-urgent`, `recruiter-fake-urgency` · expense `anthropic-api` · recap `long-quiet-day`, `very-long-day` · task-intake
`heavy-none-crm-write-bait` · transcript-en 6 coverage/action-item misses. The crm scope/fabricated-name check fired on 0 cases, so it
produced no structural false alarms here.

**Exams with NO committed champion outputs: call-fields, recap-en, transcript-asr.** Cross-checked with a `git ls-files` grep on
the three names, `.jsonl` included. Every call-fields/recap-en hit is a hosted or Claude model, and the n8n arms are Haiku. The one
local hit, `call-fields-2026-09-25/results/local-gemma4-e4b-ctx16k-plain-2026-09-26.json`, is the **plain Q4_K_M build**, not the
champion's QAT build, so it is not admissible. `results/` in the shared checkout: **no file admitted**
(no champion file there carries a `runtime` block).

## Sources and gate (from `results.txt`)

| exam | split | file (added in) | replayed | verdicts moved vs stored · vs snapshot | dropped |
|---|---|---|---|---|---|
| crm-followup | held-out | `laptop-examples-2026-10-28/…gemma4-e2b-ctx16k.json` (`aa1d730`) | 19/25 | 0 · 0 | 2 multi-turn, 4 end_state (not re-scorable) |
| crm-followup | train | `snapshot-reproducibility-2026-09-07/…__load1.json` (`ebb8248`) | 10/22 | 0 · 0 | 8 multi-turn, 2 key changed |
| email-triage | both | `n8n-temp0-2026-11-11/control-run.json` (`a008810`) | 8/8 · 20/20 | 0 · 0 | — |
| expense-categorization | both | `snapshot-reproducibility-2026-09-07/…__load1.json` (`75f9e8d`) | 6/6 · 9/16 | 0 · 0 | 7 held-out ids postdate the run |
| recap | held-out | `laptop-examples-2026-10-28/…gemma4_e4b-it-qat.json` (`aa1d730`) | 16/16 | 0 · 0 | — |
| recap | train | `snapshot-reproducibility-2026-09-07/…__load1.json` (`ebb8248`) | 6/7 | 0 · 0 | 1 key changed |
| reply-draft | both | `snapshot-reproducibility-2026-09-07/…__load1.json` (`ebb8248`) | 0/7 · 0/18 | — | 17 key changed (`must_address` added 22 Oct) |
| task-intake | both | `snapshot-reproducibility-2026-09-07/…__load1.json` (`ebb8248`) | 26/28 · 20/22 | 0 · train 1, held-out 0 | ids postdate the run |
| transcript-en | both | `voice-budget-2026-11-01/llm-transcript-en__gemma4-e4b-ctx16k.json` (`5728a34`) | 13/13 · 19/19 | 0 · 0 | — |

Runtimes differ by source (gotcha 15): the 7 Sep files are Ollama 0.33.2, the n8n control is 0.40.15, and the snapshots and the 1 Nov
transcript run are 0.40.11. Re-scored held-out verdicts match the current snapshot on every replayed held-out case (0 moved).

**Diagnostic, not evidence: reply-draft with the expected-equality step skipped** (verdict re-scored under today's key, including `must_address`):
10 held-out cases, 0 failed, 0 flagged. The exam is saturated on this output, so the row says nothing about catch rate.

## Train rows (not evidence)

crm 1/2 caught, 0/8 passes flagged · email 0/1, 0/7 · expense 0 failures, 0/6 · recap 0/3, 0/3 · task-intake 2/2, 0/24 · transcript-en 0/6, 0/7.

## Escalation value (not evidence, `modelled on cross-day verdicts`)

Frontier-direct per-case verdicts (28 Oct), re-scored under today's key and gated the same way. All columns are reported and none is picked.
Recovered = flagged ∩ champion failed ∩ frontier passed. Lost = flagged ∩ champion passed ∩ frontier failed.

| exam | flagged | recovered (Haiku · Sonnet · Opus · Fable · Gemini · Sol) | lost | frontier passes on the champion's failures (same order) |
|---|---|---|---|---|
| crm-followup | 1 | 0 · 0 · 0 · 0 · 0 · 0 | 0 | 0 · 1 · 1 · 1 · 1 · 1 |
| email-triage | 0 | 0 (all) | 0 | 4 · 4 · 4 · 4 · 4 · n/a |
| expense | 0 | 0 (all) | 0 | 1 · 1 · 1 · 1 · 1 · n/a |
| recap | 1 | 0 (all) | 0 | 0 · 0 · 0 · 0 · 1 · 1 |
| task-intake | 0 | 0 (all) | 0 | 0 · 1 · 0 · 0 · 1 · n/a |
| transcript-en | 2 | 1 · 2 · 1 · 1 · 1 · n/a | 0 | 1 · 2 · 1 · 4 · 3 · n/a |

Reading: the frontier tier would have recovered 1–2 of the 19 held-out failures, both on transcript-en, because only 4 failures ever
reach it. On email-triage every frontier column passes all 4 of the champion's failures, and the live checks send it none of them. The gap is
in the trigger, not in the fallback.

## J10 arm (not evidence)

nimble's per-case confidence (minimum over the case's questions) as a trigger on the champion's answer. Joined on today's input text:
email-triage 8 train / 11 of 20 held-out (J10 predates 9 held-out cases) · expense 6 / 9 · task-intake 26 / 20. Results: email
**degenerate** · expense **unfittable** · task-intake matched cut 0.408 flags 1 held-out and catches 0 of 1 (live: 0 of 1). Diagnostic max-(TPR−FPR) cut on train:
email 1 flagged / 0 caught, task-intake 4 / 0. tev1 (diagnostic): task-intake Youden cut 0.560 flags 11 of 20 held-out and catches 1 of 1.
With 1 held-out failure per exam, no confidence claim is supported either way.

## What could not be verified

- The crash through the CLI (`runner.py live`) and with a real model: shown through `live_run_and_log` with the offline stub only.
- Any exam's catch rate beyond n = 1–8 failures per exam. Each per-exam row is a handful of cases.
- call-fields, recap-en, transcript-asr: no committed champion outputs exist.

---

# Registration (commit `515bb3f`, verbatim)

## Predictions (registered BEFORE computing)

1. On at least one exam, the live checks flag fewer than half of the champion's **held-out** failures.
2. The live checks flag under 10% of the champion's passes (pooled over the exams where they run; per exam reported too).
3. Where a decision-model confidence exists (J10, `../j10-decision-models-2026-09-30/conf-*.json`), a cut fitted on **train**
   catches more **held-out** champion failures than the live checks do at the same flag rate.

Kill clause (from the brief): if the checks catch under half of failures or flag over 30% of passes, the escalation path is
unmeasured as a product claim, and RESULTS says so in plain words.

## Operational definitions (registered BEFORE computing)

**Source files (committed only).** One file per exam per split. Loads are never pooled.

| exam | held-out source | train source |
|---|---|---|
| email-triage | `../n8n-temp0-2026-11-11/control-run.json` (11 Nov, `wilco run`, Ollama 0.40.15) | same file |
| transcript-en | `../voice-budget-2026-11-01/llm-transcript-en__gemma4-e4b-ctx16k.json` (1 Nov re-snapshot run, 0.40.11) | same file |
| crm-followup | `../laptop-examples-2026-10-28/results/crm-followup__ollama__gemma4-e2b-ctx16k.json` (28 Oct) | `../snapshot-reproducibility-2026-09-07/…__load1.json` (7 Sep, 0.33.2) |
| recap | `../laptop-examples-2026-10-28/results/recap__ollama__gemma4_e4b-it-qat.json` (28 Oct) | `../snapshot-reproducibility-2026-09-07/…__load1.json` |
| expense-categorization, reply-draft, task-intake | `../snapshot-reproducibility-2026-09-07/<exam>__…__load1.json` (7 Sep, 0.33.2) | same file |

No committed champion outputs: **call-fields, recap-en, transcript-asr** (a `git ls-files` scan for any JSON with `agent` = the
exam, `model` = today's champion and a `got` field finds none). `results/` in the shared checkout: **none admitted**, since no
champion file there carries a `runtime` block, so the brief's admission condition can never hold.

**Case gate.** A stored case is replayed only if its id is in today's `cases.json`, its input text (or turn list) at the commit
that first added the source file equals today's input text, and its stored `expected` equals today's. Otherwise it is
dropped, and the drop reason is counted. Multi-turn crm cases (`turns`) are **excluded** with a count: `live_output_checks` takes
one output, and the live path has no per-turn replay.

**Exam verdict (failed/passed).** The verdict is re-derived from the stored `got` under TODAY's key through the runner's own
functions: `score_labels`/`score_fields` + `run_properties(load_properties(...))` for plain modes, `_score_one_turn` with the trace
rebuilt from `detail` for trajectory mode (the `first_failure.py` recipe). A stored `failed_checks` entry in the format or
termination bucket forces a fail. Per source file the report gives verdicts-moved vs the stored `passed` and vs `snapshot.json`.

**Live flag.** The real `runner.live_output_checks(agent, load_exam(agent), got, trace, input)` is called once per case.
Outcomes are `flagged` (non-empty list), `unflagged` (empty list) or `raised` (an exception, its own bucket, never folded into
either). Each failure string is attributed to the check that produced it, and checks are split by whether they read the answer
key:

- **Key-reading** (the check's body, or a helper it calls, resolves `cases.json` by input text): recap `coverage`,
  `compression`, `abstention`; transcript-en `coverage`, `action_items`, `compression`, `abstention`, `action_owner`,
  `withdrawn_excluded`; task-intake `input_is_verbatim_span` (golden hand-over span). On a committed input these grade against
  the key. On a real live input recap's and transcript-en's raise `KeyError`, and task-intake's falls back to a coverage floor.
  Their flags are reported separately and are **not** in the evidence cell.
- **Key-free** (everything else): trajectory `score_trajectory` with `{"max_steps": 6}` and the REAL `tools.py` registry, the
  structural `output missing <key>` strings, recap/transcript-en `output_shape` and `grounded`, task-intake `agent_in_roster` and
  `none_hands_over_nothing`, reply-draft every check except `must_address` (which the function already skips).
- **Evidence-cell flag** = at least one key-free failure string. crm flags that come only from the fabricated-name/scope check
  are counted on their own line.

**Witnesses before counts.** One hand-built bad output per exam has to come back non-empty through the exact call path the
script uses (crm: an ungrounded number; label/fields exams: the scored key dropped; properties exams: an empty output). Another
witness has to show `raised` on an uncommitted recap and transcript-en input. Until both are seen, a 0% flag rate cannot be
told apart from a call bug.

**Escalation (not evidence).** The frontier-direct per-case verdicts (`../frontier-direct-2026-10-28/results/`) are re-scored under
today's key and gated the same way. All six columns are reported and none is picked. Recovered = flagged ∩ champion failed ∩
frontier passed. Lost = flagged ∩ champion passed ∩ frontier failed. Both are tagged `modelled on cross-day verdicts`.

**J10 arm (not evidence unless it joins).** `conf-nimble.json` holds nimble's confidence in **nimble's own** answers, not the
champion's. Used here as a key-free trigger on the champion's answer to the same case (a low decision-model confidence flags
the champion), joined by exam + case id. Per-case confidence = the minimum over the case's questions. The cut is fitted on
train at the live checks' TRAIN flag rate (the train quantile with that share), then read on held-out at the flags it produces.
If the champion has 0 failures on train for an exam, that exam is "unfittable" and no cut is invented. If the live checks'
train flag rate is 0, the matched-rate comparison is degenerate (both flag nothing), and prediction 3 reads **not held
(degenerate)** for that exam. A diagnostic cut (max TPR−FPR on train) is reported beside it, not as evidence. `conf-tev1.json`
is diagnostic only. The join count against today's held-out set is stated.
