# The trace record (2026-11-11, ST1 slice 1)

One record per model turn, whatever produced it: an exam run, a live run, a user's correction, or a client's export.
Error analysis, a label sheet and a new exam case are all cut from this one shape. Written by `scripts/trace_store.py`
(importers for the three shapes this repo already wrote); pinned by `sandbox/test_trace_store.py`. The store is
`clients/<name>/traces/traces.jsonl`: JSONL, append-only, git-ignored, wipeable like `clients/<name>/retrieval`.

| field | type | meaning |
|---|---|---|
| `record_id` | sha256 hex | of the JSON list `[source, session_id, turn, input]`; recomputed on every read, a duplicate refuses the whole import |
| `session_id` | str | one conversation. exam: `exam:<task>:<provider>/<model>:<case_id>@<ts>` · live: `live:<file>:<line>` · correction: `correction:<client>:<id>` |
| `turn` | int ≥ 0 | 0 for a single-turn input; a multi-turn case gives one record per turn |
| `ts` | ISO 8601 **with offset** | a naive time is refused, never guessed. Results files store none: `import-results --ts`. Live lines: `--tz`, applied only to naive lines |
| `source` | `exam` \| `live` \| `correction` \| `client:<name>` \| `external:<producer>` | where the record came from. `client:<name>` is a client's export; `external:<producer>` is an agent run elsewhere whose trace is graded by `wilco grade --traces` |
| `task` | str | the agent / exam name (`recap`, `crm-followup`, …); a correction takes its client's `base_agent` |
| `case_id`, `split` | str \| null | exam records only: the join key back to `evals/<task>/cases.json`, and the split, so a held-out record never feeds training |
| `input` | str | the text the model was given for THIS turn (a multi-turn record holds its own turn, not the joined `a \| b` string) |
| `output_raw` | str \| list \| null | what the model emitted, as stored: a trajectory turn's raw steps, a correction's string draft; null when the source kept none |
| `output_parsed` | object \| null | the parsed answer (`got`, a live `output`, a correction's object draft) |
| `tool_calls`, `tool_results` | list | this turn's calls and what the tools returned; `[]` when none |
| `model`, `provider` | str | `unknown` spelled out when the source did not record them |
| `runtime` | object \| `unknown` | the snapshot stamp's keys (`name`, `version`, `kv_cache_type`, `flash_attention`) when the source carries them, else `unknown` |
| `grader_hash` | str \| null | set only when the record carries a verdict. `unknown` for an imported, stored verdict: today's grader files did not produce it. A verdict re-scored now would carry `label_sheet.grader_hash` (sha256 of `grader_files.snapshot_files`) |
| `verdict` | `pass` \| `fail` \| null | the exam's verdict for this turn. Live records: always null (a live guard failing is kept in `meta.checks_failed`; its absence is not a pass) |
| `verdict_source` | `stored` \| `rescored` \| null | `stored` = copied from the results file |
| `failed_checks` | list | `{bucket, check[, turn]}` as the runner writes them; per turn for a multi-turn case |
| `labels` | list | empty by default. A correction carries one `{kind: correction, action, final, user, changed_fields}` |
| `meta` | object | source-specific leftovers needed to rebuild the original shape (metrics, failures, live `via`/`request`, raw ts). Never the answer key: `expected` is re-joined from `cases.json` by `case_id` |
| `steps` | int ≥ 1, optional | model calls in THIS turn (tool rounds plus the final answer): what `max_steps` compares against. The importer lifts it from the results' `steps`; a record without it cannot be graded by `wilco grade --traces` |
| `termination` | `{"cause": str}`, optional | the loop stopped without answering (cap hit, `max_tokens`, crash). The grade forces a fail and files it under the `termination` bucket |
| `final_state` | object, optional | the state the session's write tools left behind (`{"shortlist": ["A-17", "B-02"]}`), on the **last** turn's record only; graded once per session by `state_match`. wilco sees what the producer writes down |
| `repeat` | int ≥ 0, optional | which of the k runs of this case the session is (default 0). `(case_id, model, repeat)` is unique; the grade refuses gaps and unequal k |
| `protocol_break` | object, optional | the turn's output could not be parsed (wilco's own loop writes it; filed under the `format` bucket) |

## Grading a trace made elsewhere

`wilco grade <task> --traces FILE [--exam-dir DIR]` scores a JSONL file of these records without a model: `scripts/trace_grade.py`
reads and validates it itself (it does not import the store), rebuilds each turn and calls the runner's own scorer. The producer
writes no verdict: `verdict`, `verdict_source`, `grader_hash`, `failed_checks` and `labels` must be empty (the one exception is
`verdict_source: stored`, which the importer writes). `output_parsed` is `{"answer": <final text of the turn>}`; `tool_calls` is
`[{"tool", "args"}]` and `tool_results` is index-aligned with it, a failed call being an object with an `error` key (a result with
`is_error` and no `error` key is refused). Worked example: `integrations/agent-traces/`.

## Glossary

- **trace**: everything one model run did for one input: what it was given, what it called, what came back, what it answered.
- **record**: one line of a trace store; one turn of one trace (the table above).
- **session**: the records that belong to one conversation; a single-turn input is a session of one turn.
- **case**: one input in `evals/<exam>/cases.json`, with an id, a split and an expected block.
- **check**: one deterministic test of an answer (`check_grounded`, `tools_called`, …), in `properties.py` or the runner.
- **key**: a case's expected block, the answer the checks compare against. It never enters a trace record.
- **label**: a judgement attached to a record by a person, or by a labeller that is never the verdict (pass/fail/unsure, a failure mode, a correction).
- **correction**: a user's accept / edit / reject of a draft (`scripts/corrections.py`); becomes a label.
- **failure mode**: a named, recurring way an answer goes wrong, found by reading traces; a candidate for a new check or case.
- **verdict**: pass or fail for one case (or turn), from the checks; the exam score counts verdicts.
- **snapshot**: `evals/<exam>/snapshot.json`: per-case verdicts over 3 fresh loads plus the runtime stamp; `check` compares a run to it.
- **champion**: the model an agent ships with, named in `agents/<name>/agent.yaml`; changing it is operator-signed.

## Not built here

A real client export arrives in their field names. Mapping them onto these fields (a mapping file per client, plus the
`client:<name>` source) is the next slice. So is a re-score path that would write `verdict_source: rescored` with
today's `grader_hash`.
