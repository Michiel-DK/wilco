#!/usr/bin/env python3
"""Scaffold a new exam + agent: `python3 scripts/exam_new.py <task> --mode labels|fields|properties|trajectory`.

Writes, and refuses to overwrite any of them (exit 2 if evals/<task>/ or agents/<task>/ exists):
  evals/<task>/cases.json      two example cases (one train, one heldout) in the mode's expected shape;
                               every case carries a `_comment` explaining its fields. `_comment` sits at
                               the CASE level on purpose: labels/fields mode compares every key inside
                               `expected`, so a comment there would be scored as a field.
  agents/<task>/agent.yaml     provider ollama, tier local, model left as a placeholder to pick with `diff`
  agents/<task>/prompt.md      a skeleton whose answer format matches the mode
  evals/<task>/properties.py   (properties mode) one example check carrying the contract
  evals/<task>/tools_mock.py   (trajectory mode) one tool + the _BACKEND_DOWN idea

Then: replace the example cases with real ones, and run `python3 scripts/exam_validate.py <task>`.
The guide is docs/write-an-exam.md. No inference, no network.

  exit 0  written      exit 2  refused (exists, bad name)
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODES = ("labels", "fields", "properties", "trajectory")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")

AGENT_YAML = """\
name: {task}
description: "<one line: what this agent does, for whom>"
provider: ollama
# Quoted on purpose: the placeholder carries ': ' and must stay a string. Pick the model by
# measurement: `wilco diff {task} --models ollama/m1,openrouter/m2`, then `wilco pick {task}`;
# `wilco adopt {task} <provider/model>` writes the winner here. Never by hand.
model: "<pick one with: wilco diff>"
tier: local               # local | eu | frontier — data may not leave this tier
temperature: 0.0
max_tokens: 2048
"""

_C_ID = "unique, stable id; `check` and snapshots key on it"
_C_SPLIT = ("train = you may iterate on it; heldout = the reported score, never tuned on. "
            "Keep about a third heldout. Moving a case between splits is an operator-signed decision")
_C_INPUT = "the exact text the agent receives (the user message)"


def _case(cid, split, inp, expected, expected_comment):
    return {"id": cid, "split": split, "input": inp, "expected": expected,
            "_comment": {"id": _C_ID, "split": _C_SPLIT, "input": _C_INPUT, "expected": expected_comment}}


def cases_for(task, mode):
    if mode == "labels":
        c = "exact match (case-insensitive) on every key; each label must be in prompt.md's declared list"
        cases = [_case("example-train-1", "train", "Example input that should get label_a.",
                       {"label": "label_a"}, c),
                 _case("example-heldout-1", "heldout", "Example input that should get label_b.",
                       {"label": "label_b"}, c)]
    elif mode == "fields":
        c = ("one entry per field the agent must extract; the case passes only if EVERY field matches "
             "(strings case-insensitive, everything else exact); the report also gives fields_matched/fields_total")
        cases = [_case("example-train-1", "train", "Call with Ann Peeters of Acme about a 4200 EUR order.",
                       {"contact_name": "Ann Peeters", "company": "Acme", "amount": 4200}, c),
                 _case("example-heldout-1", "heldout", "Bob Smit from Globex wants a quote for 900 EUR.",
                       {"contact_name": "Bob Smit", "company": "Globex", "amount": 900}, c)]
    elif mode == "properties":
        c = ("no golden answer: properties.py's checks pass or fail the output. Each check finds THIS "
             "block by the exact input text (_exp); must_mention = terms the answer must contain")
        cases = [_case("example-train-1", "train", "Acme called: the delivery slips to Friday.",
                       {"must_mention": ["Acme", "Friday"]}, c),
                 _case("example-heldout-1", "heldout", "Globex paid invoice 17 this morning.",
                       {"must_mention": ["Globex"]}, c)]
    else:
        c = {"tools_called": "tools the run must call (each at least once)",
             "answer_contains": "substrings the final answer must contain (numbers match on a token boundary)",
             "max_steps": "tool calls + the answer turn may not exceed this",
             "error_recovery": "the named tool errors for this input (tools_mock._BACKEND_DOWN); `fact` = words "
                               "naming what that tool was to supply. The answer must say, in one sentence, that "
                               "the lookup failed AND name that fact, must not repeat the failing call, and must "
                               "not invent a name"}
        cases = [_case("example-train-1", "train", "What is the status of Acme?",
                       {"tools_called": ["lookup"], "answer_contains": ["active"], "max_steps": 3}, c),
                 _case("example-heldout-1", "heldout", "What is the status of Globex? Guess if the system is down.",
                       {"tools_called": ["lookup"],
                        "error_recovery": {"tool": "lookup", "fact": ["status"]},
                        "max_steps": 3}, c)]
    exam = {"agent": task}
    if mode != "labels":
        exam["mode"] = mode
    exam["note"] = f"Scaffolded by scripts/exam_new.py --mode {mode}. Replace both example cases."
    exam["not_verified"] = ["<what this exam CANNOT catch; printed on every run>"]
    exam["cases"] = cases
    return exam


PROMPTS = {
    "labels": """\
You classify <what> for <whom>.

Classify the input into exactly one label:

- "label_a": <when>
- "label_b": <when>

Respond with ONLY a JSON object, no other text:
{"label": "<label_a|label_b>"}
""",
    "fields": """\
You extract CRM fields from <what>.

Respond with ONLY a JSON object, no other text:
{"contact_name": "<full name>", "company": "<company>", "amount": <number>}
""",
    "properties": """\
You <do what> for <whom>. Name every company the input mentions.

Respond with ONLY a JSON object, no other text:
{"answer": "<your answer>"}
""",
    "trajectory": """\
You answer questions about accounts using tools. You must look facts up, never answer from memory.

Available tools:
- lookup(key: str) — returns the record for one account: status, owner.

Protocol — respond with ONLY one JSON object per turn, no other text:
- To call a tool:        {"tool": "lookup", "args": {"key": "<account name>"}}
- To answer (when you have the facts): {"answer": "<your answer>"}

After you call a tool, its result arrives as {"tool_result": ...}. Base your answer only on tool
results. If a tool returns an error, say so in your answer; never guess.
""",
}

PROPERTIES_PY = '''\
"""Property checks for {task}. The contract, which sandbox/runner.py enforces:

  * Every function named check_* is a check. Signature: check_x(input_text, output) -> (ok: bool, reason: str).
    `output` is the parsed JSON answer (a dict). A check that raises is a FAILED check, never a skip.
  * Every check declares `check_x.bucket = "format"` (output shape) or `"quality"` (substance). The runner
    refuses to load a check without one.
  * The signature carries no `expected`. A check that needs per-case data looks it up with _exp(input_text):
    by EXACT input text against this exam's own cases.json. An input that is not a committed case RAISES.
    Fail loud: a missing key raises too, so a typo in cases.json can never pass every case silently.
  * A check earns its place only if one case isolates it: some output must fail THIS check and no other
    (`failed_checks == [{{"bucket": ..., "check": "check_x"}}]`). See docs/write-an-exam.md.
"""
import json
from functools import lru_cache
from pathlib import Path

_HERE = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _expectations_by_input() -> dict:
    data = json.loads((_HERE / "cases.json").read_text())   # missing file -> raises, never {{}}
    return {{c["input"]: c["expected"] for c in data["cases"]}}


def _exp(input_text: str) -> dict:
    table = _expectations_by_input()
    if input_text not in table:
        raise KeyError(f"{task} properties: input is not a committed case in {{_HERE / 'cases.json'}} "
                       f"(first 60 chars: {{input_text[:60]!r}})")
    return table[input_text]


def check_mentions_required(input_text, output):
    """PRESENCE: every must_mention term appears in the answer (case-insensitive substring)."""
    required = _exp(input_text)["must_mention"]   # KeyError on a case without the key: fail loud
    answer = output.get("answer")
    if not isinstance(answer, str):
        return False, f"no string 'answer' in output (got {{type(answer).__name__}})"
    missing = [t for t in required if t.lower() not in answer.lower()]
    return (not missing), (f"missing: {{missing}}" if missing else "")


check_mentions_required.bucket = "quality"
'''

TOOLS_MOCK_PY = '''\
"""Frozen exam fixture for {task}: the tools every EXAM run sees. Deterministic and free.

The contract, which sandbox/runner.py enforces:
  * Each public function is a tool, called by name with the model's `args` as keyword arguments.
    Same signatures as agents/{task}/tools.py, the real tools a `live` run uses (write that file before
    going live). The exam never touches the real backend, so plumbing changes can never move a score.
  * Return a dict (or list). A returned {{"error": ...}} is a normal tool result the model must handle.
    A RAISED exception becomes {{"error": "<message>"}} for the model; the run continues.
  * Names starting with "_" and the hooks `state` / `reset_state` are never dispatched as tools
    ("unknown tool"). `reset_state()` / `state()` are optional hooks for exams that grade writes.
  * Deterministic means: no clock, no random, no hash() of strings (salted per process).

_BACKEND_DOWN: a tool RAISES for exactly one key, simulating an outage where the record exists but
cannot be fetched this run. A case on that key with `expected.error_recovery` passes only if the answer
says the lookup failed instead of inventing the value. The mock is the only place this outage exists;
never put a forced raise in the live tools.py.
"""

_RECORDS = {{
    "acme": {{"status": "active", "owner": "Ann Peeters"}},
    "globex": {{"status": "churned", "owner": "Bob Smit"}},
}}

_BACKEND_DOWN = {{"lookup": "globex"}}


def _norm(key: str) -> str:
    return key.strip().lower()


def lookup(key: str = "") -> dict:
    if _norm(key) == _BACKEND_DOWN["lookup"]:
        raise RuntimeError(f"backend timeout fetching {{key!r}} (upstream 504): the record exists "
                           f"but could not be retrieved")
    rec = _RECORDS.get(_norm(key))
    if rec is None:
        return {{"error": f"no record for {{key!r}}"}}
    return dict(rec)


def known_entities() -> dict:
    """Scope-coverage registry (optional): canonical name -> the strings that count as a mention of it.
    An input naming two known accounts fails `scope_coverage` if the answer drops one. crm-followup's
    mock adds contact names as aliases."""
    return {{name: [name] for name in sorted(_RECORDS)}}
'''


def plan(task, mode):
    """{relative path: content} for every file `new` writes."""
    files = {
        f"evals/{task}/cases.json": json.dumps(cases_for(task, mode), indent=2, ensure_ascii=False) + "\n",
        f"agents/{task}/agent.yaml": AGENT_YAML.format(task=task),
        f"agents/{task}/prompt.md": PROMPTS[mode],
    }
    if mode == "properties":
        files[f"evals/{task}/properties.py"] = PROPERTIES_PY.format(task=task)
    if mode == "trajectory":
        files[f"evals/{task}/tools_mock.py"] = TOOLS_MOCK_PY.format(task=task)
    return files


def main(argv=None):
    # W7: `wilco new` in the usage line under the shim (WILCO_PROG); the script's name run directly
    ap = argparse.ArgumentParser(prog=f"{os.environ['WILCO_PROG']} new" if os.environ.get("WILCO_PROG") else None,
                                 description=__doc__.split("\n")[0])
    ap.add_argument("task")
    ap.add_argument("--mode", required=True, choices=MODES)
    ap.add_argument("--root", default=str(REPO), help="repo root to write under (tests use a temp dir)")
    a = ap.parse_args(argv)
    if not NAME_RE.fullmatch(a.task):
        print(f"exam_new: task name {a.task!r} must match {NAME_RE.pattern}", file=sys.stderr)
        return 2
    root = Path(a.root)
    taken = [d for d in (root / "evals" / a.task, root / "agents" / a.task) if d.exists()]
    if taken:
        print(f"exam_new: refusing to overwrite {', '.join(str(d) for d in taken)}", file=sys.stderr)
        return 2
    for rel, content in plan(a.task, a.mode).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        print(f"wrote {rel}")
    print(f"next: replace the example cases, then wilco validate {a.task}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
