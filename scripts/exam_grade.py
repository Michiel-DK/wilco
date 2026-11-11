#!/usr/bin/env python3
"""wilco grade <task> <answers-file> [--label NAME] [--node NAME] — score answers made OUTSIDE our runner.

The answers come from another tool (n8n first); the grading is ours. They go through the real entry point,
`runner.run_exam(load_agent(task), load_exam(task), 'external', label)`, with `runner.adapter_for` replaced
FOR THE DURATION OF THE CALL ONLY (restored in `finally`) by a replay adapter. Nothing here re-implements a
grader (gotcha 5), calls a model, or touches the network.

Replay rules, stated rather than hidden:
  * the adapter answers by the case INPUT (the user message), never by order, and records any input it has no
    answer for; a recorded miss aborts the grade (exit 2) before anything is written.
  * when an answer does not parse, the runner re-asks, and the replay returns the SAME text again. A case whose
    answer does not parse therefore fails, exactly as with any model that repeats itself. Retry backoff sleeps
    are skipped (they would only wait on the same recorded text) and restored afterwards.

Answer formats, detected from the file (never asked):
  (a) JSON object {case_id: text} or {case_id: {"text": text}}; keys starting with `_` (e.g. `_meta`) are ignored.
  (b) JSON list of {"case_id": ..., "text": ...}.
  (c) an n8n execution: `n8n execute --rawOutput` stdout (log lines before the first `{` are skipped) or an
      execution object from the n8n API / MCP. The items of the node named by --node (default `Result`) are read
      at data.resultData.runData[<node>][0].data.main[0]; each item's json carries `case_id` and `text`.
  (d) CSV with the header columns `case_id,text`.

Refused with exit 2 and ONE stderr line (never a traceback): an unknown task, an exam that is not single-turn
(trajectory mode, or any case with turns/tools), an exam that needs a judge model (rubric.md), an unrecognised
format, a missing n8n node, a case id the exam does not have, a case with no answer.

Writes results/external/<task>__external__<label>.json (a subfolder on purpose: `wilco pick` and taxonomy read
the top level of results/ as candidate model runs, and graded outside answers are not one) (label defaults to the answers file's stem, sanitized to
[A-Za-z0-9._-]) and prints the runner's own per-case lines plus `<task>: train p/t · heldout p/t (95% CI lo–hi)`.
Exit 0 means the grade ran, not that every case passed."""
from __future__ import annotations

import argparse
import csv
import io
import json

import yaml
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
import runner  # noqa: E402
import retry  # noqa: E402
import stats  # noqa: E402  (the single interval implementation)

PROG = os.environ.get("WILCO_PROG") or "exam_grade.py"
EXTERNAL = "external"


HELP = f"""usage: {PROG} grade <task> <answers-file> [--label NAME] [--node NAME]

score answers made in another tool (n8n first) with this repo's own grader; no model is called

  <task>            a single-turn exam under evals/ (multi-turn, tool-using and judge-graded exams are refused)
  <answers-file>    JSON {{case_id: text}}, JSON list of {{case_id, text}}, an n8n execution
                    (`n8n execute --rawOutput` output, or an API/MCP execution object), or CSV case_id,text
  --label NAME      result file label (default: the file's stem) -> results/external/<task>__external__<label>.json
  --node NAME       the n8n node whose items hold case_id + text (default: Result)

Exit 0: the grade ran (it does not mean every case passed). Exit 2: refused, one line on stderr."""


class Refuse(Exception):
    """One sentence for stderr, exit 2."""


def _names(items, n=5) -> str:
    items = sorted(items)
    return ", ".join(repr(i) for i in items[:n]) + (", ..." if len(items) > n else "")


# ---- parsing ---------------------------------------------------------------------------------

def _answer_text(v):
    if isinstance(v, str):
        return v
    if isinstance(v, dict) and isinstance(v.get("text"), str):
        return v["text"]
    return None


def _rows_to_map(rows, what: str) -> dict:
    out: dict = {}
    for cid, text in rows:
        if not isinstance(cid, str) or not isinstance(text, str):
            raise Refuse(f"unrecognised answers format: {what} needs a string case_id and a string text on every row")
        if cid in out:
            raise Refuse(f"case {cid!r} appears more than once in the answers file; give one answer per case")
        out[cid] = text
    return out


def _run_data(obj):
    """The runData dict of an n8n execution (raw CLI output or API/MCP object), or None."""
    if not isinstance(obj, dict):
        return None
    rd = ((obj.get("data") or {}).get("resultData") or {}).get("runData") if isinstance(obj.get("data"), dict) else None
    if isinstance(rd, dict):
        return rd
    rd = (obj.get("resultData") or {}).get("runData") if isinstance(obj.get("resultData"), dict) else None
    if isinstance(rd, dict):
        return rd
    return _run_data(obj.get("execution")) if isinstance(obj.get("execution"), dict) else None


def _from_n8n(run_data: dict, node: str) -> dict:
    if node not in run_data:
        raise Refuse(f"the n8n execution has no node named {node!r} (nodes present: "
                     f"{', '.join(sorted(run_data)) or 'none'}); pass --node NAME")
    try:
        items = run_data[node][0]["data"]["main"][0]
        rows = [(i["json"]["case_id"], i["json"]["text"]) for i in items]
    except (KeyError, IndexError, TypeError):
        raise Refuse(f"node {node!r} in the n8n execution has no items with json.case_id and json.text")
    return _rows_to_map(rows, f"node {node!r}")


def _no_dup_keys(pairs):
    """json.loads keeps the LAST value of a repeated key, which would grade a wrong-then-right file as right."""
    seen = set()
    for k, _ in pairs:
        if k in seen:
            raise Refuse(f"case {k!r} appears twice in the JSON object; give one answer per case")
        seen.add(k)
    return dict(pairs)


def parse_answers(text: str, node: str) -> dict:
    """{case_id: answer text} from any of the four formats."""
    text = text.lstrip("﻿")
    body = text.lstrip()
    if not body:
        raise Refuse("the answers file is empty")
    if body[:1] in "{[":
        try:
            obj = json.loads(body, object_pairs_hook=_no_dup_keys)
        except ValueError:
            raise Refuse("unrecognised answers format: the file starts like JSON but does not parse")
        return _from_json(obj, node)
    first = body.split("\n", 1)[0]
    try:
        header = next(csv.reader([first]))
    except (StopIteration, csv.Error):
        header = []
    if "case_id" in header and "text" in header:
        rd = csv.DictReader(io.StringIO(body))
        return _rows_to_map([(r.get("case_id"), r.get("text")) for r in rd], "the CSV")
    # n8n execute --rawOutput: log lines, then one JSON object that starts a line
    m = re.search(r"(?m)^\{", text)
    if m:
        try:
            obj = json.loads(text[m.start():], object_pairs_hook=_no_dup_keys)
        except ValueError:
            raise Refuse("unrecognised answers format: no parseable JSON after the log lines")
        return _from_json(obj, node)
    raise Refuse("unrecognised answers format: expected a JSON object or list, an n8n execution, "
                 "or a CSV with the header case_id,text")


def _from_json(obj, node: str) -> dict:
    if isinstance(obj, list):
        return _rows_to_map([(r.get("case_id"), r.get("text")) if isinstance(r, dict) else (None, None)
                             for r in obj], "the JSON list")
    if isinstance(obj, dict):
        rd = _run_data(obj)
        if rd is not None:
            return _from_n8n(rd, node)
        rows = []
        for k, v in obj.items():
            if k.startswith("_"):
                continue
            t = _answer_text(v)
            if t is None:
                raise Refuse(f"unrecognised answers format: the value for {k!r} is neither text nor "
                             '{"text": ...}')
            rows.append((k, t))
        if not rows:
            raise Refuse("unrecognised answers format: the JSON object holds no answers")
        return _rows_to_map(rows, "the JSON object")
    raise Refuse("unrecognised answers format: expected a JSON object or list")


# ---- the exam ---------------------------------------------------------------------------------

def check_exam(task: str) -> None:
    if not (ROOT / "evals" / task / "cases.json").is_file() or not (ROOT / "agents" / task / "agent.yaml").is_file():
        raise Refuse(f"no exam named {task!r} (need evals/{task}/cases.json and agents/{task}/agent.yaml)")
    exam = json.loads((ROOT / "evals" / task / "cases.json").read_text())
    if exam.get("mode") == "trajectory" or any("turns" in c or "tools" in c for c in exam.get("cases", [])):
        raise Refuse(f"{task!r} is a tool-using or multi-turn exam; grading those from a transcript is out of "
                     "scope, only single-turn exams can be graded from answers")
    name = (yaml.safe_load((ROOT / "agents" / task / "agent.yaml").read_text()) or {}).get("name", task)
    # ^ judges.load_judge keys on the agent's name, not the folder: check both places a rubric can sit
    if (ROOT / "evals" / task / "rubric.md").exists() or (ROOT / "evals" / name / "rubric.md").exists():
        raise Refuse(f"{task!r} is graded by a judge model, which `grade` never calls; out of scope")
    if exam.get("samples", 1) > 1:
        raise Refuse(f"{task!r} scores {exam['samples']} samples per case (pass@k); one recorded answer per case "
                     "cannot be graded that way")


class Replay:
    """Answers by the user message (the case input). Misses are recorded, not swallowed by the case boundary."""

    def __init__(self, by_input: dict):
        self.by_input = by_input
        self.misses: list = []

    def generate(self, messages, model, temperature=0.0, max_tokens=512):
        user = [m for m in messages if m["role"] == "user"][0]["content"]
        if user not in self.by_input:
            self.misses.append(user[:60])
            raise KeyError(f"replay: no recorded answer for an input starting {user[:60]!r}")
        text = self.by_input[user]
        return text, {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None,
                      "content_chars": len(text), "reasoning_chars": 0, "finish_reason": "stop"}


def grade(task: str, answers: dict, label: str) -> dict:
    exam = runner.load_exam(task)
    ids = {c["id"] for c in exam["cases"]}
    unknown = set(answers) - ids
    if unknown:
        raise Refuse(f"the answers file has {len(unknown)} case id(s) the exam {task!r} does not have: {_names(unknown)}")
    missing = ids - set(answers)
    if missing:
        raise Refuse(f"{len(missing)} of {len(ids)} cases in {task!r} have no answer: {_names(missing)}")
    by_input: dict = {}
    for c in exam["cases"]:
        if c["input"] in by_input and by_input[c["input"]] != answers[c["id"]]:
            raise Refuse(f"two cases of {task!r} share one input but have different answers; "
                         "answers are matched by input, so this file cannot be graded")
        by_input[c["input"]] = answers[c["id"]]
    replay = Replay(by_input)
    agent = runner.load_agent(task)
    saved_adapter = runner.adapter_for
    saved_sleep = retry.call_with_retry.__kwdefaults__["sleep"]
    runner.adapter_for = lambda *a, **k: replay
    retry.call_with_retry.__kwdefaults__["sleep"] = lambda s: None
    try:
        result = runner.run_exam(agent, exam, EXTERNAL, label)
    except KeyError:
        if not replay.misses:
            raise
        result = None
    finally:
        runner.adapter_for = saved_adapter
        retry.call_with_retry.__kwdefaults__["sleep"] = saved_sleep
    if replay.misses:
        raise Refuse(f"internal: the grader asked for {len(replay.misses)} input(s) with no recorded answer; "
                     "nothing was written")
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refuse(f"usage: {PROG} grade <task> <answers-file> [--label NAME] [--node NAME] ({message})")


def main(argv=None) -> int:
    p = _Parser(prog=f"{PROG} grade", add_help=False)
    p.add_argument("task")
    p.add_argument("file")
    p.add_argument("--label", default=None)
    p.add_argument("--node", default="Result")
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] in ("-h", "--help"):
        print(HELP)
        return 0
    try:
        a = p.parse_args(argv)
        check_exam(a.task)
        path = Path(a.file)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise Refuse(f"cannot read the answers file {a.file!r}: {exc.__class__.__name__}")
        answers = parse_answers(text, a.node)
        label = re.sub(r"[^A-Za-z0-9._-]", "_", a.label if a.label is not None else path.stem).lstrip(".") or EXTERNAL
        result = grade(a.task, answers, label)
        saved = runner.save_result(result, subdir="external")
    except Refuse as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return 2
    print(f"{a.task}: train {result['train']['passed']}/{result['train']['total']} · "
          f"heldout {result['heldout']['passed']}/{result['heldout']['total']}"
          f" ({stats.fmt_ci(result['heldout']['passed'], result['heldout']['total'])})")
    print(f"saved {saved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
