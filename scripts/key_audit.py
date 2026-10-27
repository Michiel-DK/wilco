#!/usr/bin/env python3
"""Answer-key audit: the three mechanical parts of the N-A7b method, run after every matrix.

N-A7b (docs/probes/n-a7b-key-audit-2026-10-19/RESULTS.md) found 4 wrong keys in the 8 cells every
model failed, by hand. A wrong key had sat in a held-out split for three weeks. This prints the
leads; deciding whether a key is wrong (reading the input span) stays human.

  1. All-fail cells. Every (exam, case, check) failed by EVERY model that sat it.
       properties exams    -> each stored `got` re-scored through runner.run_properties, per check
       labels/fields exams -> per expected key, runner's own comparison (_fields_matched); check = the key;
                              PLUS every check of the exam's properties.py, if it has one: run_exam ANDs
                              run_properties into `passed` for every mode (task-intake is labels + properties)
       trajectory exams    -> stored `passed`; check = "<case>" (a trajectory exam WITH a properties.py
                              is refused: its `got` is not what run_exam handed run_properties)
     A record run_exam failed WITHOUT scoring (termination, timeout, parse error; see _died) counts
     as failing every check: the instrument gave it no pass, so the audit must not re-score its
     empty `got` into one. A dead model can therefore add a lead, never hide one.
     Also prints mismatches: (exam, model, case, rescored, stored) where the overall verdict
     differs (bools), or, with the same verdict, the failed checks differ from the record's stored
     `failed_checks` (sorted name lists: the property checks, plus the `labels`/`fields` gate
     entry). Non-empty means this script and the instrument disagree; do not trust the cell list.
  2. Required term found only inside an address. A required substring (`must_mention`, `must_commit`,
     `commit_owner` keys; enumerated from evals/{recap,transcript-en}/properties.py, and
     sandbox/test_key_audit.py fails when a properties file reads a key this script has not classified) whose
     case-insensitive occurrences in the case `input` ALL sit inside an email address, URL or domain
     token. The `Devos` class: the signature says "Tom De Vos", only the address says devos.
     A term with ZERO occurrences is not flagged (all() over nothing is True; that is a different lead).
  3. Phrasing-tight. Required substrings of >= 3 words (the `longcall-mixed-heldout-3` class).
     Listing only, no verdict.

Not scanned, on purpose: the NOT_REQUIRED_TERMS keys below (each with its reason); crm-followup
`answer_contains`/`answer_contains_any` (scored in runner.py, sourced from the tool mock, not `input`).

No inference. Standard library + sandbox/runner.py (read-only use). A report, not a gate:
  exit 0  report printed (whatever it lists)
  exit 1  a result file names a case id that is not in evals/<exam>/cases.json
  exit 2  bad arguments: unknown --exam, or no `<exam>__<model>-<date>.json` file in results_dir

    python3 scripts/key_audit.py docs/probes/matrix-2026-09-27/results/
    python3 scripts/key_audit.py <results_dir> --exam recap --json /tmp/ka.json
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
import runner  # noqa: E402

FILE_RE = re.compile(r"^(?P<exam>[^_]+)__(?P<model>.+)-(?P<date>\d{4}-\d{2}-\d{2})\.json$")
REQUIRED_KEYS = ("must_mention", "must_commit")   # lists of required substrings
REQUIRED_DICT_KEYS = ("commit_owner",)            # {required substring: owner}; the substrings are the keys
# Every other `expected` key a properties.py reads, and why it is not a required term.
# sandbox/test_key_audit.py greps evals/*/properties.py and fails on a key in neither table.
NOT_REQUIRED_TERMS = {
    "must_not_commit": "an ABSENCE key: the term must NOT appear in the output; flagging it as required inverts it",
    "speakers": "label -> name map used to resolve owners; not a substring the output must contain",
    "max_ratio": "a number (compression ceiling), not a term",
    "nothing_important": "a bool (abstention verdict), not a term",
    "abstain_max_chars": "a number (abstention length cap), not a term",
    "must_address": "an ANY-OF list (reply-draft check_must_address, PR #116): no single term is required, so the "
                    "all-of scans would flag every alternative as missing; the any-of key gets its own audit when one exists",
}
ADDRESS_RES = (
    re.compile(r"\S+@\S+"),
    re.compile(r"https?://\S+", re.I),
    re.compile(r"\S+\.[a-z]{2,6}\b", re.I),   # a bare domain, any 2-6 letter TLD (.org, .shop, ...)
)
TIGHT_WORDS = 3


# ---------------------------------------------------------------- scan 1

def all_fail_cells(results_dir, exam_filter=None):
    """Returns (cells, mismatches). cells: list of dicts for every (exam, case, check) with zero
    passes across the models that sat it. mismatches: (exam, model, case, rescored, stored)."""
    cells = defaultdict(lambda: {"n": 0, "passes": 0, "models": [], "split": None})
    mismatches = []
    exams = {}
    for f in sorted(Path(results_dir).glob("*.json")):
        m = FILE_RE.match(f.name)
        if not m:
            continue
        exam, model = m["exam"], m["model"]
        if exam_filter and exam != exam_filter:
            continue
        if exam not in exams:
            ex = runner.load_exam(exam)
            mode = ex.get("mode", "labels")
            props = runner.load_properties(exam)   # [] without a file; run_exam loads it for EVERY mode
            if props and mode not in ("properties", "labels", "fields"):
                raise SystemExit(f"key_audit: evals/{exam} is {mode!r} mode with a properties.py; "
                                 f"its property verdicts cannot be re-scored from `got` here")
            exams[exam] = (mode, {c["id"]: c for c in ex["cases"]}, props)
        mode, cases, props = exams[exam]
        for rec in json.loads(f.read_text())["cases"]:
            cid = rec["id"]
            case = cases.get(cid)
            if case is None:
                raise SystemExit(f"key_audit: {f.name} case {cid!r} is not in evals/{exam}/cases.json")
            split = case.get("split", rec.get("split"))
            got = rec.get("got")
            if mode in ("properties", "labels", "fields") and _died(rec):
                # run_exam scored nothing: the case failed before any check ran. Re-scoring the
                # empty `got` would credit passes (compression, absence) the instrument never gave.
                names = [] if mode == "properties" else list(case["expected"])
                verdicts = [(name, False) for name in names + [n for n, _fn in props]]
            elif mode in ("properties", "labels", "fields"):
                parsed = got if isinstance(got, dict) else {}
                verdicts = [] if mode == "properties" else [
                    (key, runner._fields_matched(parsed, {key: want}) == 1)
                    for key, want in case["expected"].items()]
                # The labels/fields gate as run_exam records it: one {"check": mode} entry when any
                # expected key misses. Compared per check below like the property checks.
                gate = set() if mode == "properties" or all(ok for _, ok in verdicts) else {mode}
                prop_fails = set()
                if props:
                    _, _, failed = runner.run_properties(props, case["input"], parsed)
                    prop_fails = {x["check"] for x in failed}
                    verdicts += [(name, name not in prop_fails) for name, _fn in props]
                ok_all = all(ok for _, ok in verdicts)
                if ok_all != rec["passed"]:
                    mismatches.append((exam, model, cid, ok_all, rec["passed"]))
                elif "failed_checks" in rec or rec["passed"]:
                    # Same verdict; now per check, against the record run_exam stored. A record
                    # predating failed_checks (failed, no key) cannot be compared per check.
                    names = {n for n, _fn in props} | ({mode} if mode != "properties" else set())
                    stored = {x["check"] for x in rec.get("failed_checks") or []} & names
                    if prop_fails | gate != stored:
                        mismatches.append((exam, model, cid, sorted(prop_fails | gate), sorted(stored)))
            else:
                verdicts = [("<case>", bool(rec["passed"]))]
            for check_name, ok in verdicts:
                cell = cells[(exam, cid, check_name)]
                cell["n"] += 1
                cell["passes"] += int(ok)
                cell["models"].append(model)
                cell["split"] = split
    out = [{"exam": k[0], "case": k[1], "check": k[2], "split": v["split"], "n": v["n"],
            "models": v["models"]}
           for k, v in sorted(cells.items()) if v["passes"] == 0]
    return out, mismatches


def _died(rec):
    """True for a record run_exam failed WITHOUT scoring: a termination (no answer, timeout) or a
    parse/type error. Read from the stored record, as run_exam writes it (runner.py, the
    TerminationError / Timeout / ValueError clauses of the case loop).

    `got == {"error": ...}` alone is NOT death: a model can ANSWER {"error": ...}, and run_exam scores
    that answer, storing the checks it failed. So the `got` shape decides only for a record with no
    `failed_checks` at all (one written before run_exam stored them); a dead record written since
    carries its own termination / error entry."""
    fc = rec.get("failed_checks") or []
    got = rec.get("got")
    return (not rec.get("passed")) and (
        any(x.get("bucket") == "termination" or x.get("check") == "error" for x in fc)
        or "termination" in (rec.get("detail") or {})
        or (not fc and isinstance(got, dict) and set(got) == {"error"}))


# ---------------------------------------------------------------- scans 2 + 3

def required_terms(expected):
    """The required substrings of one `expected` block, deduplicated, in key order."""
    terms = []
    for key in REQUIRED_KEYS:
        terms += [str(t) for t in (expected.get(key) or [])]
    for key in REQUIRED_DICT_KEYS:
        terms += [str(t) for t in (expected.get(key) or {})]
    return list(dict.fromkeys(terms))


def _address_spans(text):
    return [(m.start(), m.end(), m.group(0)) for r in ADDRESS_RES for m in r.finditer(text)]


def address_only_terms(cases_by_exam):
    """cases_by_exam: {exam: [case, ...]}. Flags a required term with >= 1 case-insensitive
    occurrence in `input`, every one of which lies inside an address/URL/domain token."""
    rows = []
    for exam, cases in sorted(cases_by_exam.items()):
        for c in cases:
            text = c.get("input")
            if not isinstance(text, str) or not isinstance(c.get("expected"), dict):
                continue
            spans = _address_spans(text)
            for term in required_terms(c["expected"]):
                hits = [(m.start(), m.end()) for m in re.finditer(re.escape(term), text, re.I)]
                if not hits:
                    continue
                tokens = []
                for hs, he in hits:
                    inside = [tok for s, e, tok in spans if s <= hs and he <= e]
                    if not inside:
                        break
                    tokens.append(inside[0])
                else:
                    rows.append({"exam": exam, "case": c["id"], "split": c.get("split"),
                                 "term": term, "token": tokens[0], "occurrences": len(hits)})
    return rows


def phrasing_tight_terms(cases_by_exam, min_words=TIGHT_WORDS):
    rows = []
    for exam, cases in sorted(cases_by_exam.items()):
        for c in cases:
            if not isinstance(c.get("expected"), dict):
                continue
            for term in required_terms(c["expected"]):
                if len(term.split()) >= min_words:
                    rows.append({"exam": exam, "case": c["id"], "split": c.get("split"),
                                 "term": term, "words": len(term.split())})
    return rows


def committed_cases(exam_filter=None):
    out = {}
    for path in sorted((ROOT / "evals").glob("*/cases.json")):
        exam = path.parent.name
        if exam_filter and exam != exam_filter:
            continue
        data = json.loads(path.read_text())
        out[exam] = data["cases"] if isinstance(data, dict) else data
    return out


# ---------------------------------------------------------------- report

def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(r[h]).replace("|", "\\|") for h in headers) + " |" for r in rows]
    return "\n".join(lines) if rows else "_none_"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results_dir")
    ap.add_argument("--exam")
    ap.add_argument("--json", dest="json_path")
    a = ap.parse_args(argv)
    if a.exam and not (ROOT / "evals" / a.exam / "cases.json").exists():
        ap.error(f"unknown --exam {a.exam!r}: no evals/{a.exam}/cases.json")
    rd = Path(a.results_dir)
    found = [f for f in sorted(rd.glob("*.json")) if (m := FILE_RE.match(f.name))
             and (not a.exam or m["exam"] == a.exam)] if rd.is_dir() else []
    if not found:
        ap.error(f"no <exam>__<model>-<date>.json result file in {a.results_dir!r}"
                 + (f" for --exam {a.exam!r}" if a.exam else "")
                 + " — an empty report here would read as 'no all-fail cells'")

    cells, mismatches = all_fail_cells(a.results_dir, a.exam)
    cases = committed_cases(a.exam)
    addr = address_only_terms(cases)
    tight = phrasing_tight_terms(cases)

    print(f"# key audit — {a.results_dir}\n")
    print(f"## 1. All-fail cells ({len(cells)})\n")
    print(f"re-score != stored passed: {mismatches}\n")
    print(_table(["exam", "case", "check", "split", "n"], cells))
    print(f"\n## 2. Required term only inside an address ({len(addr)})\n")
    print(_table(["exam", "case", "split", "term", "token"], addr))
    print(f"\n## 3. Phrasing-tight required substrings, >= {TIGHT_WORDS} words ({len(tight)})\n")
    print(_table(["exam", "case", "split", "term"], tight))

    if a.json_path:
        Path(a.json_path).write_text(json.dumps(
            {"results_dir": str(a.results_dir), "exam": a.exam, "all_fail_cells": cells,
             "rescore_mismatches": mismatches, "address_only_terms": addr,
             "phrasing_tight_terms": tight}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
