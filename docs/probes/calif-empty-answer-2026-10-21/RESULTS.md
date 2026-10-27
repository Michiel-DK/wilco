# CALIF probe — can a compliant answer that says nothing pass our cases?

**PREDICTIONS REGISTERED 2026-10-21T22:39:37Z, before any computation** (verbatim from the job brief, as-calif-empty-answer):

1. At least one transcript-en quiet case passes every check on an empty-but-compliant answer.
2. No recap case does (`check_coverage` requires content).
3. reply-draft and task-intake: no prediction.

_Results below this line are written after the run._

---

_Run 2026-10-22 by the laptop-scheduler job `as-calif-empty-answer` (operator go 22 Oct 00:21). $0: no Ollama call, no hosted call, no `run`/`check`/`--snapshot`._

> **EVIDENCE CELL:** a hand-built answer that satisfies each exam's output contract and says nothing, scored through the real checks (`runner.run_properties`, `score_labels`/`score_fields`, `score_trajectory`) on all 230 committed cases. Cases that pass every check: **recap 4/17 · transcript-en 5/32 · reply-draft 19/19 · task-intake 9/50 · crm-followup 4/44 · email-triage 0/21 · expense-categorization 0/15 · call-fields 0/32**, so **41 of 230** in total. 9 of the 41 (task-intake `none`) are correct abstentions, which leaves **32 genuinely exposed** (13 train, 19 held-out).

**Not evidence:**
- The minimal answers are hand-built. Gotcha 5 applies: they are the attacker, not any model's output, and they say nothing about what a model would write.
- The "stored passes kept" counts for the fixes come from old `results/` files (all models, Aug–Sep runs). They are not the current snapshot.
- The label-exam "abstaining label" rows (email-triage `ignore`, expense `other`) are constant-answer baselines. A label is the content, so a passing abstaining label is a correct answer, not an exposure.

## Verdicts on the registered predictions

| # | prediction | verdict |
|---|---|---|
| 1 | ≥1 transcript-en quiet case passes on an empty-but-compliant answer | **CONFIRMED.** 5 of 5 quiet cases pass on `{"summary": "Nothing important on this call.", "action_items": [], "nothing_important": true}`. The literal empty summary `""` fails `check_output_shape` on all 32. |
| 2 | no recap case does (`check_coverage` requires content) | **REFUTED.** 4 recap quiet cases pass on `{"recap": "Nothing important today.", "nothing_important": true}`. They carry no `must_mention`, and `check_coverage` returns pass on an empty list (`evals/recap/properties.py`, `if not required: return True`). It holds only for the literal `""`, which `check_output_shape` rejects on all 17. |
| 3 | reply-draft, task-intake: no prediction | **reply-draft: 19/19 pass** on a polite, language-matched non-answer. **task-intake: 9/50 pass**, exactly the 9 `none` cases, where `{"agent":"none","input":""}` is the correct answer. |

## Method
`probe.py` (beside this file; `results.json` is its output; rerun from the repo root with no arguments). Each properties exam is scored with two attackers:
- **(a) literal empty:** every string `""`, every list `[]`.
- **(b) minimal compliant:** the shortest content-free text the format check accepts.

Both `nothing_important` values are tried on every case. A case is exposed if any variant of (b) passes.
- **reply-draft:** (b) is a 2-line "thanks, I'll get back to you / Michiel" in the input's language. The script asserts the module's own `_lang` reads each template as its language; a bare `"Michiel"` reads `unknown` and would be a false negative.
- **task-intake:** labels + properties, composed like `attempt()`.
- **crm-followup:** the attacker calls exactly the required tools once, then answers `"OK."`. This is `score_trajectory`, `sandbox/runner.py:1442`. It is called directly with `known_entities=()`, so the scope-drop check is inert. That check fires only when the input names two or more entities, and each of the 4 exposed inputs names one company.

A positive control asserts that a busy transcript-en case (`discovery-short-train`) fails attacker (b) on `check_action_items` + `check_coverage`. It does.

## Table

| exam | n | (a) empty passes | (b) content-free passes (train / held-out) | (b) fails only one check |
|---|---|---|---|---|
| recap | 17 | 0, shape check rejects `""` | **4** (1 / 3): `quiet-day-automated` [train], `quiet-day-newsletters`, `quiet-day-with-receipt`, `long-quiet-day` | 13, all `check_coverage` (with flag `false`) |
| transcript-en | 32 | 0, shape check rejects `""` | **5** (3 / 2): `quiet-checkin-short-train`, `quiet-checkin-medium-train`, `longcall-quiet-train-1` [train]; `quiet-checkin-heldout-short`, `quiet-checkin-heldout-medium` | 0 (busy cases fail coverage + action_items) |
| reply-draft | 19 | 0 (`check_has_reply`) | **19** (7 / 12): every case | — |
| task-intake | 50 | 9 | **9** (5 / 4): the `none` cases, a **correct** abstention | 41, all `labels` |
| crm-followup | 44 | — | **4** (2 / 2): `redundant-retry-outage`, `redundant-sibling-outage` [train]; `redundant-retry-outage-deals`, `write-forbidden-mertens-no-write` [held-out] | — |
| email-triage | 21 | `{}` → 0 | abstaining `ignore` → 6, the correct label | — |
| expense-categorization | 15 | `{}` → 0 | `other`/`false` → 2 (`paypal-cryptic`, `bank-transfer-savings`, held-out), correct labels | — |
| call-fields | 32 | `{}` → 0 (0/256 fields) | all `"not stated"` → 0 cases, 122/256 fields | — |

**Label exams, one paragraph.** `score_labels` and `score_fields` (`sandbox/runner.py:255–271`) count `parsed.get(key) == want`, with case-insensitive string compare. No committed expected value is `null`: every call-fields abstention is the literal string `"not stated"`. So an empty `{}` matches no field on any of the 68 cases (asserted per case in `probe.py`). The abstaining answer each prompt defines does score where it *is* the key: `ignore` 6/21, `other` 2/15, `"not stated"` 122/256 fields but 0 whole cases (at most 6 of 8 fields are `"not stated"`). That is a majority-class baseline, not CALIF. The label carries the verdict.

**crm-followup.** All 10 multi-turn cases carry `answer_contains` or `error_recovery` on at least one turn, so a content-free answer fails each. The 4 exposed cases are all deterministic backend outages (`_BACKEND_DOWN`). Their keys hold only `tools_called` / `max_steps` / `end_state: []`, so `"OK."` passes without ever telling the user that the lookup failed.

## Smallest fix per exposed case
Each fix was chosen blind from the input and the check definition, then tested offline. The attacker must fail exactly one check, and stored passing outputs must keep the term.

**TRAIN, in draft PR #114** (`lane/calif-positive-terms`; re-snapshot needed):

| case | edit | attacker after | stored passes kept |
|---|---|---|---|
| transcript-en `quiet-checkin-short-train` | `must_mention: ["check"]` | fails `check_coverage` only | 8/8 |
| transcript-en `quiet-checkin-medium-train` | `must_mention: ["check"]` | fails `check_coverage` only | 13/13 |
| transcript-en `longcall-quiet-train-1` | `must_mention: ["check"]` | fails `check_coverage` only | 1/1 |
| crm `redundant-retry-outage` | `answer_contains_any: [unable, could not, couldn't, error, failed, timeout, timed out, unavailable]` | fails `answer_contains_any` only | 1/1 |
| crm `redundant-sibling-outage` | same | same | 15/15 |

**TRAIN, NOT in the PR:** recap `quiet-day-automated`. The blind term `newsletter` kept 12/12 stored passes, but it turned `evals/test_e13_recap.py` red. That test's own "good quiet-day recap" is Dutch ("een nieuwsbrief…"), and the recap prompt sets no output language. `back` drops 2 stored passes. No single substring covers EN + NL, and `must_mention` is all-of. The smallest real fix is any-of support in `check_coverage`. That is a `properties.py` change, so it is the operator's.

**HELD-OUT, for the operator's signature (not edited):**
- recap `quiet-day-newsletters`, `quiet-day-with-receipt`, `long-quiet-day` hit the same EN/NL problem as above and need any-of.
- transcript-en `quiet-checkin-heldout-short`: `must_mention: ["check"]` (input: "monthly check-in").
- transcript-en `quiet-checkin-heldout-medium`: **still exposed after PR #112.** #112's signed second commit re-keys it as not quiet, leaving `expected = {"nothing_important": false}` and nothing else. Re-run on #112's head (`ecbb5d6`): attacker (b) **still passes every check, now via flag `false`**. The smallest fix lands on top of #112: `must_commit: ["friday"]` (the input's only commitment is "I can move our recurring call to Fridays").
- crm `redundant-retry-outage-deals`, `write-forbidden-mertens-no-write`: the same failure-vocabulary `answer_contains_any`.
- **reply-draft, all 19 (7 train + 12 held-out): no `expected` edit can fix it.** `evals/reply-draft/properties.py` never reads `cases.json`, so a key would be inert (gotcha 1). The exam checks shape, language, signoff, word count and inventions, but **nothing checks that the reply engages the ask**. The smallest fix is a new per-case presence check (e.g. `must_address` terms resolved by exact input, the recap `_exp` pattern) plus keys on all 19. That is a `properties.py` lane plus a re-snapshot. Expect headroom to move (gotcha 10).

## Gate on the PR branch
49 of 50 gate test files ran green (`python3 <file>`, one process each, `rc` captured). `sandbox/test_shadow_gmail.py` was **excluded, not run**: Ollama was listening on :11434 and that file's e2e makes one real inference, which this job forbids. `./.cline/test.sh` itself was not run. Run it before the merge.

## Interactions
- PR #112 edits `evals/transcript-en/cases.json` too, on different cases. Expect a textual rebase and nothing semantic.
- #112's a7b notes flag `redundant-retry-outage` for an operator read: its input asks for the retry the redundancy monitor fails. The new key leaves that monitor as the case's only failure whenever the answer reports the outage, as the stored champion answer does.

## DECLARED LIMIT — 23 Oct 2026 (operator: "Declare the limit, close both PRs")

The empty-answer hole on the four quiet-day cases (`quiet-day-automated` train; `quiet-day-newsletters`, `quiet-day-with-receipt`,
`long-quiet-day` held-out) stays OPEN and is declared: a content-free `{"recap": "Nothing important today.", "nothing_important": true}`
passes every check on them. Two fixes were built and refuted on the record: PR #117 (hand-written any-of `must_mention_any`, three rounds:
a fresh refuter found 18/29 honest recaps failing and 11/20 content-free attackers passing through substring collisions) and PR #122
(the same key DERIVED by a rule from the input — sender tokens, numbers, subject words — pre-registered acceptance FAILED: 51/97 honest
recaps fail because English recaps meet no Dutch subject word, 7/143 attackers pass through `automatisch(e)`). Conclusion: a substring
vocabulary, hand-written or derived, cannot grade a free-form recap that may be English or Dutch without failing honest phrasing. The
hole closes only with a different check design (not a word list), designed on real client recaps. Until then every recap score page
carries this sentence; the `test_recap_*` files of the two closed branches are not on master.

