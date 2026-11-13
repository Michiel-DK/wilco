# Grade an agent trace made elsewhere

Your agent runs on your side (any framework, any model). wilco never imports it and calls no model: it scores the
trace you stored, with its own deterministic checks, per turn and per session, with a Wilson interval on cases.

**What you write.** An exam folder with one `cases.json` (`mode: "agent-trace"`, `write_tools`, `not_verified`, and per
case `id`, `split`, `input` or `turns`, `expected` with `max_steps`; see `exam/cases.json`), and a JSONL trace, one
record per turn (`docs/trace-record.md`): `session_id`, `turn`, `ts` with offset, `task`, `case_id`, `input` (the exam's
text, character for character), `output_parsed: {"answer": ...}`, `tool_calls` `[{tool, args}]`, `tool_results`
(index-aligned; a failed call is an object with an `error` key), `model`, `steps` (model calls this turn), `repeat`
(0..k-1), `final_state` (last turn only). You write no verdict: wilco refuses one.

```sh
wilco validate desk-assistant --exam-dir integrations/agent-traces/exam     # lint the exam, grade nothing
wilco grade desk-assistant --traces integrations/agent-traces/traces.jsonl \
      --exam-dir integrations/agent-traces/exam [--label NAME] [--strict]   # -> results/external/desk-assistant__trace__NAME.json
```

The example is fictional (3 sessions) and every new check fails once: `book-room-okafor` books room 21, not 12
(`args_match`, and `facts_not_contradicted` on "room 21"); `shortlist-cheapest` leaves one room of two
(`state_match`); `injected-refund` refunds after a note said to (`no_injected_write`). Exit 0 means the grade ran.

| check | what it does NOT verify |
|---|---|
| `args_match` (exact / subset / keys) | paraphrased values (`"Proposal"` is not `"proposal"`); the other calls to the tool; that the tool ran |
| `state_match` (equals / set / contains / absent) | how the state was reached; that you reported `final_state` truthfully |
| `facts_not_contradicted` | any contradiction you did not list (plain lowercase substring, so `16500` hits a listed `6500`, `6,500` does not) |
| `no_injected_write` | whether the injection CAUSED the write; an injection without the marker |
| `tools_called`, `tools_not_called`, `tools_allowed`, `max_steps`, `answer_contains(_any)`, grounded numbers, redundant call, `error_recovery` | the runner's own checks, unchanged: see the exam's `not_verified` and `docs/gotchas.md` |

Scores: `pass^k` is cases that passed all k sessions out of n cases, per split; `pass@1` is the mean session verdict times n,
as a case count; the per-turn rate counts a case when that turn passed in all k sessions. Intervals use n = cases (the k runs of
a case are not independent). Train and held-out are never summed. Runs are sampled, so wilco never says "stable"; sessions more
than 24 h apart print a WARNING. `--strict` refuses an exam folder that is not committed. Refusals exit 2 with one stderr line.
