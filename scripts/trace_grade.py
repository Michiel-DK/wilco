#!/usr/bin/env python3
"""wilco grade <task> --traces FILE [--exam-dir DIR] [--label NAME] [--compare-stored] [--model M] [--strict]
-- grade a STORED agent trace (made by an agent that ran elsewhere) with this repo's own checks. No model, no network.

The trace is scored, never replayed: each turn's (parsed, trace) is rebuilt from the file and handed to
runner._score_one_turn (the one call site of score_trajectory), with the scoring trace assembled by
runner._scoring_trace - the same helper runner._run_turns calls, so the two paths cannot drift. The checks the runner
lacks (args_match, state_match, facts_not_contradicted, no_injected_write) live in sandbox/trace_checks.py.

Input: JSONL, one record per turn (docs/trace-record.md), grouped into sessions by session_id; a session is one run of one
case, the k repeats of a case are k sessions. This script reads and validates the file ITSELF: it does not import
scripts/trace_store.py (the private store), so the public cut can ship it.

Exam: evals/<task>/ (in-repo; tools_mock gives known entities, end_state is graded from a write log DERIVED from
the crm_update calls whose result is {"ok": true, ...}) or, with --exam-dir DIR, a data-only DIR holding cases.json
(mode "agent-trace"). An exam dir may not hold properties.py / tools_mock.py / rubric.md, may not use end_state or
samples > 1, must name every check key from the known list, and every turn must carry max_steps.

Scores: pass^k = cases that passed all k sessions / n cases, per split; pass@1 successes = round(mean session verdict * n);
per-turn pass rate: a case passes turn t when turn t passed in all k sessions. Wilson intervals are on n CASES (the k runs of a
case are not independent draws), train and heldout are never summed. Runs are sampled, not rule-A loads: this never says "stable".

Exit 0 the grade ran; 2 refused (ONE stderr line, never a traceback); 1 with --compare-stored when a stored verdict or
failed_checks list differs. Writes results/external/<task>__trace__<label>.json."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
import runner  # noqa: E402
import stats  # noqa: E402
import grader_files  # noqa: E402
import trace_checks  # noqa: E402

PROG = os.environ.get("WILCO_PROG") or "trace_grade.py"
SPLITS = ("train", "heldout")
EXAM_DIR_FORBIDDEN = ("properties.py", "tools_mock.py", "rubric.md")
RECORD_FIELDS = {"record_id", "session_id", "turn", "ts", "source", "task", "case_id", "split", "input", "output_raw",
                 "output_parsed", "tool_calls", "tool_results", "model", "provider", "runtime", "grader_hash", "verdict",
                 "verdict_source", "failed_checks", "labels", "meta", "steps", "termination", "final_state", "repeat",
                 "protocol_break"}
REQUIRED = ("session_id", "turn", "ts", "task", "case_id", "input", "model", "tool_calls", "tool_results", "steps")
# tier of a failed check for root_check: lower = more fundamental (no answer / died < wrong facts or actions < content < cost)
TIER = {"termination": 0, "window": 0, "unparseable": 0, "answer_present": 0,
        "error_recovery": 1, "no_injected_write": 1, "tools_not_called": 1, "tools_allowed": 1, "grounded_answer": 1,
        "facts_not_contradicted": 1, "state_match": 1, "end_state": 1, "args_match": 1, "tools_called": 1,
        "answer_contains": 2, "answer_contains_any": 2, "answer_not_contains": 2, "scope_coverage": 2,
        "max_steps": 3, "redundancy": 3}

HELP = f"""usage: {PROG} grade <task> --traces FILE [--exam-dir DIR] [--label NAME] [--compare-stored] [--model M] [--strict]

grade a stored agent trace (JSONL, docs/trace-record.md) with this repo's own checks; no model is called

  --traces FILE      one record per turn; sessions grouped by session_id; k repeats = k sessions per case
  --exam-dir DIR     a data-only exam (cases.json, mode agent-trace); default: the in-repo exam evals/<task>/
  --label NAME       result file label (default: the trace file's stem) -> results/external/<task>__trace__<label>.json
  --compare-stored   compare verdict + failed_checks per case and per turn against records that carry verdict_source stored
  --model M          the model to grade when the file holds more than one
  --strict           refuse (instead of warning) an --exam-dir that is not committed in a git repository

Exit 0: the grade ran. Exit 2: refused, one line on stderr. Exit 1: --compare-stored found a difference."""


class Refuse(Exception):
    """One sentence for stderr, exit 2."""


def _names(items, n=4) -> str:
    items = sorted(items, key=str)
    return ", ".join(repr(i) for i in items[:n]) + (", ..." if len(items) > n else "")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(dir_: Path, *args) -> str | None:
    try:
        p = subprocess.run(["git", "-C", str(dir_), *args], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def parse_ts(v):
    """datetime with offset, or None (a naive time is refused, never guessed)."""
    if not isinstance(v, str):
        return None
    s = v[:-1] + "+00:00" if v.endswith(("Z", "z")) else v
    try:
        d = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo is not None and d.utcoffset() is not None else None


# ---- the exam -------------------------------------------------------------------------------------------------------
class Exam:
    def __init__(self, task, doc, mode, path, tools_mod=None):
        self.task, self.doc, self.mode, self.path = task, doc, mode, path   # mode: "exam-dir" | "in-repo"
        self.cases = {c["id"]: c for c in doc["cases"]}
        self.write_tools = tuple(doc.get("write_tools") or ())
        ents = doc.get("entities")
        self.known_entities = (runner._known_entities(tools_mod) if tools_mod is not None
                               else (dict(ents) if isinstance(ents, dict) else tuple(ents or ())))
        self.derive_writes = tools_mod is not None


def _walk_keys(v, key):
    if isinstance(v, dict):
        return key in v or any(_walk_keys(x, key) for x in v.values())
    if isinstance(v, list):
        return any(_walk_keys(x, key) for x in v)
    return False


def _read_cases(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise Refuse(f"cannot read {path.name} as JSON")
    if not isinstance(doc, dict) or not isinstance(doc.get("cases"), list) or not doc["cases"]:
        raise Refuse(f"{path.name} needs an object with a non-empty cases list")
    return doc


def _check_cases_shape(doc: dict) -> None:
    """Shape every case needs, both modes: string id, split, input (or turns + turns_expected)."""
    seen = set()
    for c in doc["cases"]:
        cid = c.get("id") if isinstance(c, dict) else None
        if not isinstance(cid, str) or cid in seen:
            raise Refuse(f"cases need unique string ids (offending: {cid!r})")
        seen.add(cid)
        if c.get("split") not in SPLITS:
            raise Refuse(f"case {cid!r}: split must be train or heldout")
        if "turns" in c:
            if not (isinstance(c["turns"], list) and c["turns"] and all(isinstance(t, str) for t in c["turns"])):
                raise Refuse(f"case {cid!r}: turns must be a non-empty list of strings")
            if not (isinstance(c.get("turns_expected"), list) and len(c["turns_expected"]) == len(c["turns"])):
                raise Refuse(f"case {cid!r}: turns_expected must be a list parallel to turns")
        elif not isinstance(c.get("input"), str):
            raise Refuse(f"case {cid!r}: needs an input string")


def _turn_blocks(c: dict):
    if "turns" in c:
        return [(f"turn {k}", e.get("expected") if isinstance(e, dict) else None) for k, e in enumerate(c["turns_expected"])]
    return [("expected", c.get("expected"))]


def validate_exam_dir(task: str, d: Path) -> Exam:
    if not d.is_dir() or not (d / "cases.json").is_file():
        raise Refuse(f"--exam-dir {str(d)!r} is not a folder holding cases.json")
    for name in EXAM_DIR_FORBIDDEN:
        if (d / name).exists():
            raise Refuse(f"the exam dir holds {name}: an outside exam is data only (cases.json); wilco runs only its own checks")
    if (ROOT / "evals" / task).exists():
        raise Refuse(f"task {task!r} is also a folder in evals/: an outside exam cannot take an in-repo exam's name")
    doc = _read_cases(d / "cases.json")
    if doc.get("agent") != task:
        raise Refuse(f"cases.json agent is {doc.get('agent')!r}, not the task {task!r}")
    if doc.get("mode") != "agent-trace":
        raise Refuse('cases.json needs "mode": "agent-trace"')
    wt = doc.get("write_tools")
    if not (isinstance(wt, list) and all(isinstance(x, str) for x in wt)):
        raise Refuse("cases.json needs write_tools: a list of the tool names that change state (may be empty)")
    nv = doc.get("not_verified")
    if not (isinstance(nv, str) and nv or isinstance(nv, list) and nv and all(isinstance(x, str) and x for x in nv)):
        raise Refuse("cases.json needs not_verified: what this exam cannot catch")
    ents = doc.get("entities")
    if ents is not None and not (isinstance(ents, (list, dict))):
        raise Refuse("entities must be a list of names or {name: [aliases]}")
    if doc.get("samples", 1) != 1:
        raise Refuse("samples > 1 is not supported: repeats are k sessions in the trace file")
    if _walk_keys(doc["cases"], "end_state"):
        raise Refuse("end_state is not supported in an outside exam (it needs the CRM mock); use session.state_match")
    _check_cases_shape(doc)
    for c in doc["cases"]:
        for where, ex in _turn_blocks(c):
            if not isinstance(ex, dict):
                raise Refuse(f"case {c['id']!r} {where}: needs an expected object")
            keys = [k for k in ex if not k.startswith("_")]
            bad = [k for k in keys if k not in trace_checks.TURN_KEYS]
            if bad:
                raise Refuse(f"case {c['id']!r} {where}: unknown check key {bad[0]!r} (known: {', '.join(trace_checks.TURN_KEYS)})")
            ms = ex.get("max_steps")
            if not isinstance(ms, int) or isinstance(ms, bool) or ms < 1:
                raise Refuse(f"case {c['id']!r} {where}: max_steps is required (an integer >= 1); the runner's default of 4 would cap your loop silently")
            msg = trace_checks.validate_turn_block(ex)
            if msg:
                raise Refuse(f"case {c['id']!r} {where}: {msg}")
        if "session" in c:
            msg = trace_checks.validate_session_block(c["session"])
            if msg:
                raise Refuse(f"case {c['id']!r}: {msg}")
    return Exam(task, doc, "exam-dir", d)


def load_in_repo(task: str) -> Exam:
    path = ROOT / "evals" / task / "cases.json"
    if not path.is_file() or not (ROOT / "agents" / task / "agent.yaml").is_file():
        raise Refuse(f"no exam named {task!r} (need evals/{task}/cases.json and agents/{task}/agent.yaml), or pass --exam-dir")
    doc = _read_cases(path)
    if doc.get("mode") not in ("trajectory", "agent-trace"):
        raise Refuse(f"{task!r} is not a tool-using exam (mode {doc.get('mode', 'labels')!r}); traces are graded for trajectory exams only")
    _check_cases_shape(doc)
    tools = runner.load_tools(task) if (ROOT / "evals" / task / "tools_mock.py").exists() else None
    for c in doc["cases"]:
        for where, ex in _turn_blocks(c):
            msg = trace_checks.validate_turn_block(ex) if isinstance(ex, dict) else None
            if msg:
                raise Refuse(f"case {c['id']!r} {where}: {msg}")
        if "session" in c:
            msg = trace_checks.validate_session_block(c["session"])
            if msg:
                raise Refuse(f"case {c['id']!r}: {msg}")
    return Exam(task, doc, "in-repo", path.parent, tools)


# ---- the trace file -------------------------------------------------------------------------------------------------
def read_records(path: Path, task: str) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Refuse(f"cannot read the trace file {str(path)!r}: {exc.__class__.__name__}")
    recs = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            raise Refuse(f"trace file line {n} is not JSON")
        recs.append((n, rec))
    if not recs:
        raise Refuse("the trace file holds no records")
    out = []
    for n, r in recs:
        out.append(_validate_record(n, r, task))
    return out


def _validate_record(n: int, r, task: str) -> dict:
    where = f"trace file line {n}"
    if not isinstance(r, dict):
        raise Refuse(f"{where} is not an object")
    extra = sorted(set(r) - RECORD_FIELDS)
    if extra:
        raise Refuse(f"{where}: unknown field {extra[0]!r} (producer data belongs in meta)")
    for f in REQUIRED:
        if f not in r:
            raise Refuse(f"{where}: missing field {f!r}")
    for f in ("session_id", "task", "case_id", "input", "model"):
        if not isinstance(r[f], str) or (f != "input" and not r[f]):
            raise Refuse(f"{where}: bad {f}")
    if r["task"] != task:
        raise Refuse(f"{where}: task {r['task']!r} is not {task!r}")
    for f, lo in (("turn", 0), ("steps", 1), ("repeat", 0)):
        if f in r and (not isinstance(r[f], int) or isinstance(r[f], bool) or r[f] < lo):
            raise Refuse(f"{where}: {f} must be an integer >= {lo}")
    if parse_ts(r["ts"]) is None:
        raise Refuse(f"{where}: ts needs an ISO 8601 time WITH a UTC offset (a naive time is refused, not guessed)")
    # wilco writes verdicts. A producer's verdict is refused, never averaged in; the importer's stored one (verdict_source
    # "stored", with its verdict and failed_checks) is the one exception.
    stored = r.get("verdict_source") == "stored"
    if r.get("labels"):
        raise Refuse(f"{where}: labels must be empty (wilco writes labels and verdicts, not the producer)")
    if not stored:
        if any(r.get(f) not in (None, [], "") for f in ("verdict", "verdict_source", "failed_checks", "grader_hash")):
            raise Refuse(f"{where}: the producer may not supply verdict, verdict_source, failed_checks or grader_hash (wilco grades)")
    else:
        if r.get("verdict") not in ("pass", "fail") or not isinstance(r.get("failed_checks"), list):
            raise Refuse(f"{where}: verdict_source stored needs a verdict (pass|fail) and a failed_checks list")
    calls, results = r["tool_calls"], r["tool_results"]
    if not isinstance(calls, list) or not isinstance(results, list) or len(calls) != len(results):
        raise Refuse(f"{where}: tool_calls and tool_results must be lists of the same length")
    for c in calls:
        if not (isinstance(c, dict) and isinstance(c.get("tool"), str) and isinstance(c.get("args"), dict)):
            raise Refuse(f"{where}: a tool_calls entry is not {{tool: str, args: object}}")
    for res in results:
        if isinstance(res, dict) and res.get("is_error") and "error" not in res:
            raise Refuse(f"{where}: a tool result carries is_error without an error key (a failed call must be an object with an error key)")
    op = r.get("output_parsed")
    if op is not None and not isinstance(op, dict):
        raise Refuse(f"{where}: output_parsed must be an object like {{\"answer\": text}}")
    for f in ("termination", "protocol_break"):
        v = r.get(f)
        if v is not None and not isinstance(v, dict):
            raise Refuse(f"{where}: {f} must be null or an object")
    if r.get("termination") is not None and not isinstance(r["termination"].get("cause"), str):
        raise Refuse(f"{where}: termination needs a cause string")
    if r.get("final_state") is not None and not isinstance(r["final_state"], dict):
        raise Refuse(f"{where}: final_state must be null or an object")
    return r


def group_sessions(recs: list, exam: Exam, model: str | None) -> tuple[list[dict], str]:
    models = sorted({r["model"] for r in recs})
    if model is None:
        if len(models) > 1:
            raise Refuse(f"the trace file holds {len(models)} models ({_names(models)}); pass --model (one grade is one model)")
        model = models[0]
    elif model not in models:
        raise Refuse(f"--model {model!r} is not in the trace file (models: {_names(models)})")
    recs = [r for r in recs if r["model"] == model]
    by_session: dict = {}
    for r in recs:
        by_session.setdefault(r["session_id"], []).append(r)
    sessions, seen_triple = [], {}
    for sid, rs in by_session.items():
        rs = sorted(rs, key=lambda r: r["turn"])
        turns = [r["turn"] for r in rs]
        if turns != list(range(len(rs))):
            raise Refuse(f"session {sid!r}: turns must be 0..n-1 with no gap or duplicate (got {turns})")
        cid = rs[0]["case_id"]
        if len({r["case_id"] for r in rs}) > 1 or len({r.get("repeat", 0) for r in rs}) > 1:
            raise Refuse(f"session {sid!r}: case_id and repeat must be the same on every turn")
        case = exam.cases.get(cid)
        if case is None:
            raise Refuse(f"session {sid!r}: case_id {cid!r} is not in the exam")
        want = case["turns"] if "turns" in case else [case["input"]]
        if len(rs) != len(want):
            raise Refuse(f"session {sid!r}: case {cid!r} has {len(want)} turn(s), the trace has {len(rs)}")
        for r, text in zip(rs, want):
            if r["input"] != text:
                raise Refuse(f"session {sid!r}: turn {r['turn']} input differs from the exam's text for case {cid!r}")
            if r.get("split") not in (None, case["split"]):
                raise Refuse(f"session {sid!r}: split {r['split']!r} differs from the exam's {case['split']!r} for case {cid!r}")
        for r in rs[:-1]:
            if r.get("final_state") is not None:
                raise Refuse(f"session {sid!r}: final_state belongs on the last turn's record only")
        triple = (cid, rs[0]["model"], rs[0].get("repeat", 0))
        if triple in seen_triple:
            raise Refuse(f"case {cid!r} repeat {triple[2]} appears in two sessions ({seen_triple[triple]!r}, {sid!r})")
        seen_triple[triple] = sid
        sessions.append({"session_id": sid, "case": case, "repeat": triple[2], "records": rs})
    per_case: dict = {}
    for s in sessions:
        per_case.setdefault(s["case"]["id"], []).append(s["repeat"])
    for cid, reps in sorted(per_case.items()):
        have = set(reps)
        if max(reps) + 1 != len(have):   # no range(max) allocation: a record with repeat=10**9 must refuse, not OOM
            first = next(i for i in range(len(have) + 1) if i not in have)
            raise Refuse(f"case {cid!r} is missing repeat index {first} (repeats must be 0..k-1)")
    ks = {cid: len(reps) for cid, reps in per_case.items()}
    if len(set(ks.values())) > 1:
        cid, n = min(ks.items(), key=lambda kv: kv[1])
        raise Refuse(f"unequal k: case {cid!r} has {n} run(s), others have {max(ks.values())}")
    return sorted(sessions, key=lambda s: (list(exam.cases).index(s["case"]["id"]), s["repeat"])), model


# ---- scoring --------------------------------------------------------------------------------------------------------
def derived_write_log(calls: list, results: list) -> list:
    """The crm mock's write log, rebuilt: crm_update appends {company, field, value} to _STATE exactly when it returns
    {"ok": true, ...} carrying those same three values (evals/crm-followup/tools_mock.py). A declared derivation, pinned
    against the mock's state() in sandbox/test_trace_grade_crm_identity.py."""
    out = []
    for c, res in zip(calls, results):
        if c["tool"] == "crm_update" and isinstance(res, dict) and res.get("ok") is True:
            out.append({"company": res.get("company"), "field": res.get("field"), "value": res.get("value")})
    return out


def grade_session(exam: Exam, s: dict) -> dict:
    case, recs = s["case"], s["records"]
    multi = "turns" in case
    turn_traces, texts, turns, all_checks = [], [], [], []
    session_passed = True
    for k, r in enumerate(recs):
        calls = [{"tool": c["tool"], "args": c["args"]} for c in r["tool_calls"]]
        trace_k = {"tools_called": [c["tool"] for c in calls], "tool_calls": calls, "tool_results": list(r["tool_results"]),
                   "steps": r["steps"]}
        if r.get("termination") is not None:
            trace_k["termination"] = r["termination"]
        if r.get("protocol_break") is not None:
            trace_k["protocol_break"] = r["protocol_break"]
        turn_traces.append(trace_k)
        texts.append(r["input"])
        scoring, input_text, scope = runner._scoring_trace(turn_traces, k, texts)
        try:
            expected = runner._turn_expected(case, k, r["input"]) if multi else case["expected"]
        except ValueError as exc:
            raise Refuse(str(exc))
        ws = None
        if not multi and "end_state" in expected:
            ws = derived_write_log(calls, trace_k["tool_results"]) if exam.derive_writes else []
        ti = k if multi else None
        parsed = r.get("output_parsed") or {}
        passed, failures, fcs = runner._score_one_turn(parsed, scoring, expected, input_text, turn_index=ti,
                                                       known_entities=exam.known_entities, scope_text=scope,
                                                       write_state=ws)
        extra = trace_checks.turn_checks(expected, str(parsed.get("answer", "")), calls)
        if extra:
            passed = False
            failures = failures + [f"{cid}: {msg}" for cid, msg in extra]
            fcs = fcs + trace_checks.failed_check_entries(extra, ti)
        turns.append({"turn": k, "tools_called": trace_k["tools_called"], "tool_calls": calls,
                      "tool_results": trace_k["tool_results"], "got": parsed, "steps": r["steps"], "passed": passed,
                      "failures": failures, "failed_checks": fcs})
        all_checks.extend(fcs)
        session_passed = session_passed and passed
    final_state = recs[-1].get("final_state")
    sess = trace_checks.session_checks(case.get("session") or {}, turn_traces, final_state, exam.write_tools)
    sfcs = trace_checks.failed_check_entries(sess, "session")
    all_checks.extend(sfcs)
    if sess:
        session_passed = False
    failed_turn = next((t["turn"] for t in turns if not t["passed"]), "session" if sess else None)
    return {"session_id": s["session_id"], "case_id": case["id"], "split": case["split"], "repeat": s["repeat"],
            "passed": session_passed, "turns": turns, "session_failed_checks": sfcs, "failed_checks": all_checks,
            "session_failures": [f"{cid}: {msg}" for cid, msg in sess], "first_failed_turn": failed_turn,
            "root_check": _root_check(turns, sfcs)}


def _root_check(turns: list, sfcs: list):
    """The earliest failing turn's highest-tier (lowest TIER, then check id) failed check; a session-only failure
    names its own. None when nothing failed. (The first_fail / root_category method of first-failure-2026-11-10,
    read from per-turn failed_checks; taxonomy.case_findings is not used: it counts a multi-turn failure twice.)"""
    for t in turns:
        if t["failed_checks"]:
            return min((TIER.get(c["check"], 4), c["check"]) for c in t["failed_checks"])[1]
    return min((TIER.get(c["check"], 4), c["check"]) for c in sfcs)[1] if sfcs else None


def _count(ok: int, n: int) -> dict:
    lo, hi = stats.wilson(ok, n)
    return {"passed": ok, "total": n, "score": round(ok / n, 3) if n else None, "ci95": [round(lo, 3), round(hi, 3)]}


def aggregate(sessions: list, exam: Exam) -> dict:
    """Per split, counts of CASES (never sessions): pass^k, pass@1 successes, flaky, per-turn pass."""
    by_case: dict = {}
    for s in sessions:
        by_case.setdefault(s["case_id"], []).append(s)
    k = len(next(iter(by_case.values())))   # equal across cases (group_sessions refuses otherwise)
    out = {"k": k, "pass_k": {}, "pass_at_1": {}, "flaky": {}, "per_turn": {}}
    for sp in SPLITS:
        cases = [cid for cid in exam.cases if exam.cases[cid]["split"] == sp and cid in by_case]   # graded cases only
        n = len(cases)
        allp = sum(all(s["passed"] for s in by_case[c]) for c in cases)
        sessions_n = [s["passed"] for c in cases for s in by_case[c]]
        mean = (sum(sessions_n) / len(sessions_n)) if sessions_n else 0.0
        out["pass_k"][sp] = _count(allp, n)
        out["pass_at_1"][sp] = _count(round(mean * n), n)
        out["flaky"][sp] = sum(len({s["passed"] for s in by_case[c]}) > 1 for c in cases)
        pt = {}
        for t in range(max((len(by_case[c][0]["turns"]) for c in cases), default=0)):
            have = [c for c in cases if len(by_case[c][0]["turns"]) > t]
            pt[str(t)] = _count(sum(all(s["turns"][t]["passed"] for s in by_case[c]) for c in have), len(have))
        out["per_turn"][sp] = pt
    return out


def provenance(exam: Exam, trace_path: Path, strict: bool, warnings: list, tmin, tmax) -> dict:
    d = exam.path
    cases_path = d / "cases.json"
    rev = _git(d, "rev-parse", "HEAD") or "unknown"
    dirty = None
    if exam.mode == "exam-dir":
        if rev == "unknown":
            if strict:
                raise Refuse("--strict needs --exam-dir inside a git repository (its revision is unknown)")
        else:
            dirty = bool(_git(d, "status", "--porcelain", "--untracked-files=all", "--", ".") or "")
            if dirty and strict:
                raise Refuse("--strict: the exam dir has uncommitted changes; commit it so the score names a revision")
            if dirty:
                warnings.append("WARNING: the exam dir has uncommitted changes; this score does not name a committed exam")
    extra = {"sandbox/trace_checks.py": _sha(ROOT / "sandbox" / "trace_checks.py")}
    if exam.mode == "exam-dir":
        extra["exam-dir/cases.json"] = _sha(cases_path)
    span = round((tmax - tmin).total_seconds() / 3600, 3)
    if span > 24:
        warnings.append(f"WARNING: the sessions span {span} h (> 24 h): a score across days is provider drift until shown otherwise")
    return {"exam": {"mode": exam.mode, "path": str(d.resolve()), "git_rev": rev, "uncommitted": dirty,
                     "cases_sha256": _sha(cases_path)},
            "traces": {"path": str(trace_path.resolve()), "sha256": _sha(trace_path)},
            "grader_hash": grader_files.digest({**grader_files.snapshot_files(exam.task), **extra}),
            "span_hours": span}


def compare_stored(sessions: list) -> list[str]:
    """Per case and per turn: the new verdict and failed_checks vs the stored ones (verdict_source stored)."""
    diffs = []
    for s in sessions:
        for t, r in zip(s["turns"], s["_records"]):
            if r.get("verdict_source") != "stored":
                raise Refuse(f"--compare-stored: session {s['session_id']!r} turn {t['turn']} carries no stored verdict")
            new_v = "pass" if t["passed"] else "fail"
            tag = f"{s['case_id']} turn {t['turn']}"
            if new_v != r["verdict"]:
                diffs.append(f"{tag}: verdict stored {r['verdict']} now {new_v}")
            if t["failed_checks"] != r["failed_checks"]:
                diffs.append(f"{tag}: failed_checks stored {r['failed_checks']} now {t['failed_checks']}")
    return diffs


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refuse(f"usage: {PROG} grade <task> --traces FILE [--exam-dir DIR] [--label NAME] [--compare-stored] "
                     f"[--model M] [--strict] ({message})")


def run(argv: list) -> tuple[int, dict | None]:
    p = _Parser(prog=f"{PROG} grade", add_help=False)
    p.add_argument("task")
    p.add_argument("--traces", required=True)
    p.add_argument("--exam-dir", default=None)
    p.add_argument("--label", default=None)
    p.add_argument("--compare-stored", action="store_true")
    p.add_argument("--model", default=None)
    p.add_argument("--strict", action="store_true")
    a = p.parse_args(argv)
    exam = validate_exam_dir(a.task, Path(a.exam_dir)) if a.exam_dir else load_in_repo(a.task)
    trace_path = Path(a.traces)
    recs = read_records(trace_path, a.task)
    sess_in, model = group_sessions(recs, exam, a.model)
    stamps = [parse_ts(r["ts"]) for s in sess_in for r in s["records"]]
    warnings: list = []
    prov = provenance(exam, trace_path, a.strict, warnings, min(stamps), max(stamps))
    skipped = sorted(set(exam.cases) - {s["case"]["id"] for s in sess_in})
    if skipped:
        warnings.append(f"WARNING: {len(skipped)} of {len(exam.cases)} exam cases have no session in the trace file and are not "
                        f"graded (n counts graded cases only): {_names(skipped)}")
    graded = []
    for s in sess_in:
        g = grade_session(exam, s)
        g["_records"] = s["records"]
        graded.append(g)
    diffs = compare_stored(graded) if a.compare_stored else []
    agg = aggregate(graded, exam)
    label = re.sub(r"[^A-Za-z0-9._-]", "_", a.label if a.label is not None else trace_path.stem).lstrip(".") or "trace"
    first = [g for g in graded if g["repeat"] == 0]
    cases_out = []
    for g in first:
        last = g["turns"][-1]
        det = {"turns": [{k: v for k, v in t.items() if k != "failed_checks"} for t in g["turns"]]}
        if "turns" not in exam.cases[g["case_id"]]:
            det.update({k: last[k] for k in ("tools_called", "tool_calls", "tool_results", "steps")})
        cases_out.append({"id": g["case_id"], "split": g["split"], "passed": g["passed"], "got": last["got"],
                          "failed_checks": g["failed_checks"], "first_failed_turn": g["first_failed_turn"],
                          "root_check": g["root_check"], "detail": det})
    result = {"agent": a.task, "provider": "external", "model": model, "mode": "agent-trace", "label": label,
              "k": agg["k"], "train": agg["pass_k"]["train"], "heldout": agg["pass_k"]["heldout"],
              "pass_k": agg["pass_k"], "pass_at_1": agg["pass_at_1"], "flaky": agg["flaky"], "per_turn": agg["per_turn"],
              "span_hours": prov["span_hours"], "provenance": prov, "cases": cases_out,
              "sessions": [{k: v for k, v in g.items() if not k.startswith("_")} for g in graded],
              "cases_in_exam": len(exam.cases), "cases_not_graded": skipped,
              "not_verified": exam.doc.get("not_verified")}
    for w in warnings:
        print(w, file=sys.stderr)
    d = runner.RESULTS_DIR / "external"
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{a.task}__trace__{label}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(_summary(a.task, agg))
    for g in graded:
        if not g["passed"]:
            print(f"  FAIL {g['case_id']} (repeat {g['repeat']}): first_failed_turn={g['first_failed_turn']} root_check={g['root_check']}")
    runner.print_not_verified(exam.doc)
    print(f"saved {out}")
    for line in diffs:
        print(f"DIFF {line}")
    if a.compare_stored:
        print(f"compare-stored: {len(diffs)} difference(s) over {sum(len(g['turns']) for g in graded)} turn(s)")
    return (1 if diffs else 0), result


def _summary(task: str, agg: dict) -> str:
    def part(sp, blk):
        c = blk[sp]
        return f"{sp} {c['passed']}/{c['total']} ({stats.fmt_ci(c['passed'], c['total'])})"
    h = agg["pass_k"]["heldout"]
    return (f"{task}: {part('train', agg['pass_at_1'])} · {part('heldout', agg['pass_at_1'])} · "
            f"pass^k heldout {h['passed']}/{h['total']} ({stats.fmt_ci(h['passed'], h['total'])}), "
            f"k={agg['k']} sampled runs (pass@1 as a case count; CI n = cases)")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] in ("-h", "--help"):
        print(HELP)
        return 0
    try:
        rc, _ = run(argv)
        return rc
    except Refuse as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
