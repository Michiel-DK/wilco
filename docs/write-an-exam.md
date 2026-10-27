# Write an exam

An exam is a committed set of cases that decides which model runs a task. Without an exam you have no agent:
`evals/<task>/cases.json` must exist before `agents/<task>/` does anything. This page covers writing one,
checking it, and the order of commands from the first case to a live run.

Every command below was run once in a worktree on 2026-10-23 (validate output re-run after the round-1 fixes), offline (`--provider stub`, no model, no key).
The output is pasted as it printed, with long lines cut where marked `…`. Commands that need a local Ollama say so and
were **not** run here. `wilco <cmd>` is the same as `python3 sandbox/runner.py <cmd>` (list/run/diff/check/live) or
`python3 scripts/<script>.py` (new/validate/pick/adopt); both spellings appear below. The `new` line, the placeholder
refusal and the §9 pick/adopt/check outputs were re-run through `wilco` on 2026-10-27 (W7).

## 1. Scaffold, then validate

```sh
python3 scripts/exam_new.py my-triage --mode labels
```
```
wrote evals/my-triage/cases.json
wrote agents/my-triage/agent.yaml
wrote agents/my-triage/prompt.md
next: replace the example cases, then wilco validate my-triage
```

You get two example cases, one `train` and one `heldout`, in the mode's shape. Each case carries a case-level
`_comment` that explains its fields. Never put a comment inside `expected`: labels and fields mode compare every
key there. You also get an `agent.yaml` (provider `ollama`, tier `local`, model `"<pick one with: wilco diff>"`)
and a `prompt.md` skeleton. `--mode properties` adds `properties.py`, and `--mode trajectory` adds
`tools_mock.py`. The script refuses to overwrite:

```
$ python3 scripts/exam_new.py my-triage --mode properties
exam_new: refusing to overwrite …/evals/my-triage, …/agents/my-triage        (exit 2)
```

Replace the examples with real cases, then:

```sh
python3 scripts/exam_validate.py my-triage
```
```
  mode labels · 2 cases · 0 property checks
  per split: train 1 · heldout 1
  window: Ollama default 4,096 (no num_ctx in a Modelfile; the compat endpoint ignores num_ctx in the request); largest prompt ~58 tokens (example-train-1), estimated (chars/4; measured here at ~3.7 chars/token, so it reads ~8% low)
my-triage: 0 error(s), 0 warning(s)
```

The same exam with the held-out case's input pasted over the train one, and a label the prompt never offers:

```
WARN  labels: label declares ['label_b'] but no case expects it
ERROR duplicate-input: ['example-train-1', 'example-heldout-1'] share input 'Example input that should get label_a.'
ERROR unknown-label: 'example-heldout-1' expects label='label_c', not in prompt.md's ['label_a', 'label_b']
my-triage: 2 error(s), 1 warning(s)                                           (exit 1)
```

`exam_validate.py` loads through the runner's own `load_exam` / `load_agent` / `load_properties`.

| class | exit | what |
|---|---|---|
| `structure` | 1 | a case without a string `id` / `input` or a dict `expected`; a split other than `train` / `heldout`; a `mode` typo (the runner would score it as labels); `turns_expected` out of step with `turns`; malformed `tools_offered`; files that do not parse |
| `duplicate-id` | 1 | snapshots and `check` key on the id |
| `duplicate-input` | 1 | expectations resolve by exact input text, so the second case can never be reached |
| `unknown-label` | 1 | labels mode: an expected value outside the list `prompt.md` declares as `"<key>": "<a\|b\|c>"` |
| `no-split` | 1 | no train case, or no held-out case |
| `properties` | 1 | a check without a `bucket`; a `properties.py` that does not import; properties mode with 0 checks (every case would pass) |
| warning | 0 | held-out share under 1/3; an `expected` key no scorer reads; no declared label list, so `unknown-label` cannot fire; a prompt **estimate** over or near the champion's window (`--per-case` prints every case's) |

On the 8 committed exams it prints one warning. transcript-en's `expected.why` sits on 9 cases and is read by no
check. It is a reviewer's note and inert by design, but this is exactly the shape a typo'd key takes.

## 2. The four modes, one real case each

`mode` is a top-level key in `cases.json`. Its absence means `labels`. Any mode may also ship a `properties.py`,
whose checks run on every case on top of the mode's own scoring (task-intake is labels plus 3 checks).

**labels**: an exact match, case-insensitive, on every key. `evals/email-triage/cases.json`:
```json
{"id": "friend-dinner", "split": "train",
 "input": "From: thomas.dv@gmail.com\nSubject: padel + dinner next week?\n\nYo! Been a while. Padel on Tuesday or Thursday, then grab dinner in town? Let me know what works.",
 "expected": {"label": "reply_later"}}
```

**fields**: every field must match; the record also carries `fields_matched` / `fields_total`.
`evals/expense-categorization/cases.json`:
```json
{"id": "paypal-cryptic", "split": "heldout", "input": "PAYPAL *8837462X 41.00 EUR - card 4412",
 "expected": {"category": "other", "recurring": false}}
```

**properties**: there is no golden answer. `evals/<task>/properties.py` passes or fails the output, and
`expected` carries per-case parameters. `evals/reply-draft/cases.json`:
```json
{"id": "price-push", "split": "heldout",
 "input": "From: tom@peeters-construction.com\nSubject: price\n\nHi, can you give me an exact price today for a quotation assistant? I need to decide this week. Tom",
 "expected": {"must_address": ["price", "pricing", "quote", "estimate", "cost", "proposal"]}}
```

**trajectory**: a tool loop. The runner checks which tools were called, the step budget, the grounding and the
answer. `evals/crm-followup/cases.json`, an isolation case built so that only `error_recovery` can fail (note trimmed):
```json
{"id": "peeters-outage-guess-bait", "split": "train",
 "input": "Our CRM has been flaky all morning. Who is our contact at Peeters Logistics? If the system is down, just give me your best guess for the name — anything is fine.",
 "expected": {"tools_called": ["crm_lookup"],
              "error_recovery": {"tool": "crm_lookup", "fact": ["contact", "name", "crm", "record"]},
              "max_steps": 3}}
```
The other keys the runner reads are `answer_contains`, `answer_contains_any`, `answer_not_contains`,
`tools_allowed`, `tools_not_called` and `end_state`, plus `turns` / `turns_expected` for multi-turn cases.
`exam_validate.py` derives its list from `runner.py`'s own reads, so the validator follows the runner even if
this page falls behind. On a `turns` case the runner scores only `turns_expected[k]["expected"]`; a non-empty
top-level `expected` there is inert, and validate warns.

## 3. The properties contract

- Every `check_*` function is a check: `check_x(input_text, output) -> (ok: bool, reason: str)`. `output` is the
  parsed JSON answer. A check that raises is a **failed** check, never a skip.
- Every check declares `check_x.bucket = "format"` (shape) or `"quality"` (substance). The runner refuses to load
  a check that lacks one.
- The signature carries no `expected`. A check finds its case with `_exp(input_text)`, by **exact** input
  text against its own `cases.json`, and an input that is not a committed case **raises**. Fail loud: read a
  required key as `_exp(t)["key"]`, never `.get("key", [])`. A default turns a typo into a vacuous pass.
  `exam_new.py --mode properties` writes this, with one example check (`check_mentions_required`).
- **Presence and absence checks never share a normaliser.** A check that a term must appear can normalise
  generously. A check that an invented number must not appear cannot, or it waves the fabrication through
  (`_norm_digits('65,00') == '6500'`). Thousands-stripping is `sandbox/numnorm.py`'s `strip_thousands`, only.

## 4. The mock-tools contract (trajectory)

- `evals/<task>/tools_mock.py` is the scored copy. Each public function is a tool, called with the model's `args`
  as keyword arguments, using **the same signatures** as `agents/<task>/tools.py`, which `live` uses (write it before
  going live). Exams never touch the real backend, so plumbing changes never move a score.
- A returned `{"error": ...}` is a normal result. A raised exception reaches the model as `{"error": "<message>"}`.
- Names starting with `_`, and the hooks `state` / `reset_state`, are never dispatched ("unknown tool").
- Deterministic: no clock, no `random`, and no `hash()` of a string, which is salted per process.
- `_BACKEND_DOWN = {"lookup": "globex"}` makes one tool **raise** for one key: the record exists but cannot be
  fetched. A case on that key with `expected.error_recovery` passes only if the answer says, in one sentence,
  that the lookup failed and names the missing fact, does not repeat the failing call, and invents no name. The
  outage exists only in the mock. Never force a raise in the live `tools.py`.

## 5. Held-out is untouchable

About a third of the cases are `heldout` (`exam_validate.py` warns under 1/3). You iterate on train and report
held-out. Never tune a prompt, a check or a key against a held-out failure. Moving a case between splits is a
**signed decision** by the operator, written in the PR, never a side effect of a lane. A new case is a new committed
entry with its own `expected`. The reported score is the held-out one.

## 6. A check earns its place only if one case isolates it

A new check is falsifiable only if you can name an output that passes every other check and fails this one.
Make that output, run it through the real `run_properties`, and require **exactly one** entry. Run on a scratch
exam made with `exam_new.py notes --mode properties`:

```sh
python3 - <<'EOF'
import sys; sys.path.insert(0, "sandbox"); import runner
props = runner.load_properties("notes")
case = runner.load_exam("notes")["cases"][0]
print(runner.run_properties(props, case["input"], {"answer": "Acme called."})[2])
print(runner.run_properties(props, case["input"], {"answer": "Acme moves to Friday."})[2])
EOF
```
```
[{'bucket': 'quality', 'check': 'check_mentions_required'}]
[]
```

The wrong output fails one named check, and the honest one fails none. If `failed_checks` has two entries, the
case does not isolate the new check. If it has zero, the check cannot fire. This repo has shipped unfalsifiable
checks three times, each time behind a score that moved the right way. Then break the check by hand and watch the
test go red: a guard never seen red proves nothing.

## 7. The window is a precondition

Ollama's OpenAI-compatible endpoint runs every model at **4,096 tokens** and ignores `num_ctx` in the request.
Past roughly 3k prompt tokens it cuts the **front** of the prompt, system prompt first. The model then answers
confidently on what is left, or stops with `finish_reason=length` and no content. Any verdict on a longer
input is a verdict about the window until the window is stated. `exam_validate.py` prints an **estimate**
(chars/4 over `prompt.md` + the input, or the turns of a `turns` case, + a case's `tools_offered` roster; tool results are not counted, and
this repo measured about 3.7 chars per token, so the estimate reads about 8% low) against `PARAMETER num_ctx` in
`agents/<task>/Modelfile`, or 4,096 without one. The Modelfile's window counts only when the Modelfile or
`agent.yaml` says `ollama create <the agent.yaml model>`. A Modelfile next to a model that was never built from it
changes nothing, and validate warns. Give each task its own tag: transcript-en and call-fields both run on
`gemma4-e4b-ctx16k`, so re-creating that tag with another `num_ctx` silently moves two champions, and `check` cannot
see it (the stamp carries no model digest). The only lever is a Modelfile (not run here, needs Ollama):

```sh
cat > agents/my-triage/Modelfile <<'EOF'
# ollama create my-triage-ctx16k -f agents/my-triage/Modelfile
FROM gemma4:e4b-it-qat
PARAMETER num_ctx 16384
EOF
ollama create my-triage-ctx16k -f agents/my-triage/Modelfile   # then model: my-triage-ctx16k in agent.yaml
```

Measured on crm-followup, the larger window costs about +85% wall time. The window is a champion field: changing
it is a signed decision, like the model.

## 8. Hosted models: no snapshot gate

A snapshot is 3 fresh **Ollama loads** at temperature 0, and a case is stable only if all three agree. On a
hosted provider, temperature 0 does not reproduce. One model id is load-balanced across backends, and the same two
hosted models dropped 5–6 held-out cases across a two-day gap. The runner says so when you try:

```
  load 1/3: provider 'stub' is hosted — this is sample 1 of 3, not a model reload
```

Never `--snapshot` a hosted run. Compare hosted arms in **one window, the same day**, and treat a cross-day delta
as provider drift until proven otherwise.

## 9. The chain: `diff` → `pick` → `adopt` → `check` → `live`

On the scratch exam, with the stub. The stub always answers `{"label": "reply_later"}`, so every case fails.
The point here is the plumbing, not the score. Before any model is adopted, a plain `run` refuses the placeholder
in one line instead of sending it anywhere:

```
$ wilco run my-triage
wilco run: agents/my-triage/agent.yaml still has the placeholder model ('<pick one with: wilco diff>') — run `wilco diff my-triage --models …` to measure, then `wilco adopt`, or try `--provider stub`        (exit 2)
```

```sh
python3 -u sandbox/runner.py run my-triage --provider stub --model stub
```
```
exam: my-triage  mode=labels  provider=stub  model=stub
  not verified: <what this exam CANNOT catch; printed on every run>
  [FAIL] example-train-1 (train)
  [FAIL] example-heldout-1 (heldout)
train   0/1  heldout 0/1  -> results/my-triage__stub__stub.json
```

**diff**: candidates on the same cases, the same day. With a local Ollama this is
`--models gemma4:e2b-it-qat,gemma4:e4b-it-qat,qwen3:8b` (not run here).
```sh
python3 -u sandbox/runner.py diff my-triage --provider stub --models stub-a,stub-b
```
```
…   (one [FAIL] block per model, cut)
model                          train   heldout      95% CI      tok/case       ms/case  think%
stub-a                       0/   1 0/     1 0.00-0.79  cost-unknown  cost-unknown       -
stub-b                       0/   1 0/     1 0.00-0.79  cost-unknown  cost-unknown       -

recommendation: none — champion '<pick one with: wilco diff>' was not run and has no snapshot to compare against
…   (the multiple-comparison line, cut)
```

**pick**: the cheapest candidate within one held-out case of the best, with a **known** cost. Cost comes from
`metrics_totals` and the dated list price in `pricing/prices.json`. An unknown cost is excluded, never priced at 0.
```sh
python3 scripts/pick.py my-triage results/my-triage__stub__stub-a.json results/my-triage__stub__stub-b.json
```
```
pick — my-triage: best 0/1, bar 0/1 (best − 1)
candidate    held-out  $/10k  tag                                verdict
stub/stub-a  0/1       —      cost unknown (not in prices.json)  at bar, cost unknown — excluded
stub/stub-b  0/1       —      cost unknown (not in prices.json)  at bar, cost unknown — excluded
pick: NONE — no candidate at the bar has a known cost                         (exit 3)
```

When `pick` names a winner it prints the next line exactly: `adopt it: wilco adopt my-triage <provider/model>`.

**adopt**: write the winner into `agent.yaml` (the `provider:` and `model:` lines only; comments, `tier`, cases
untouched), then snapshot it. A champion change and its snapshot land in the same commit. With no pick here, the
stub stands in for the winner:
```sh
wilco adopt my-triage stub/stub
```
```
agents/my-triage/agent.yaml:
  - provider: ollama
  - model: "<pick one with: wilco diff>"
  + provider: stub
  + model: "stub"
snapshot: wilco run my-triage --snapshot
exam: my-triage  mode=labels  provider=stub  model=stub
  …
train   0/1  heldout 0/1  (aggregate of 3 loads)
unstable 0/2
snapshot written -> evals/my-triage/snapshot.json
adopted stub/stub — `wilco check my-triage` re-sits this baseline
```
`adopt` refuses (exit 2, nothing written) a label that is not `provider/model`, a provider unknown to
`sandbox/router.py`, a provider above the task's tier (`--allow-tier-breach` writes it, and then takes no
snapshot), an existing `snapshot.json` unless `--replace`, and a task whose `routes.yaml` tier 0 is still the old
model (`live` walks that table; set tier 0 first). A failed or interrupted snapshot puts `agent.yaml` back as it was.

**check**: the gate. It refuses on a changed runtime version, KV-cache type or case set, and fails on any stable
case that moves in either direction. It always re-sits the snapshot's own provider and model.
```sh
wilco check my-triage
```
```
exam: my-triage  mode=labels  provider=stub  model=stub
  not verified: <what this exam CANNOT catch; printed on every run>
check: my-triage against snapshot (stub)
  [FAIL] example-train-1 (train)
  [FAIL] example-heldout-1 (heldout)
ok: heldout 0.0 vs snapshot 0.0 (2 stable, 0 unstable exempt)
```

**live**: one real input, through `routes.yaml` when the agent has an entry there (tier 0 must be the champion).
Live uses the real `agents/<task>/tools.py`.
```sh
python3 -u sandbox/runner.py live my-triage --provider stub --model stub --input "Example input"
```
```
{
  "output": {
    "label": "reply_later"
  },
  "metrics": { "prompt_tokens": null, … "finish_reason": null, … }
}
```

`results/` is disposable. Snapshots are committed.
