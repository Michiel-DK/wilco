#!/usr/bin/env python3
"""Adversarial register + sub-score report (item 6, 2026-10-31).

    python3 sandbox/test_adversarial_report.py

Pins (no model, no server):
  1. the register EQUALS the rule's output over every evals/**/cases.json (class injection|decoy, or an id
     containing bait|decoy|injection): nothing missing, nothing extra — a new bait case cannot ship unregistered
  2. every entry resolves to a real case, carries kind + split matching cases.json, and a non-empty `why`
  3. no cases.json was edited for this (no `adversarial` key in any case)
  4. report: adversarial and rest are disjoint, together = the split's n, and passed counts use passed AND
     stable; the exam's own heldout_score is untouched by the report (reads only)
  5. an exam with register entries but no snapshot is listed as "no snapshot", never as 0/n
  6. the text output prints the crm-followup held-out adversarial fraction
Each pin seen RED under a hand mutation (PR body).
"""
from __future__ import annotations
import importlib.util, io, json, os, re, sys, tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("adversarial_report", ROOT / "scripts" / "adversarial_report.py")
ar = importlib.util.module_from_spec(spec); spec.loader.exec_module(ar)
FAILED: list[str] = []
RULE = re.compile(r"(bait|decoy|injection)")


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def all_cases() -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(ROOT / "evals"):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__pycache__"]
        if "cases.json" in filenames:
            exam = Path(dirpath).relative_to(ROOT / "evals").as_posix()
            for c in json.loads((Path(dirpath) / "cases.json").read_text())["cases"]:
                out[f"{exam}/{c['id']}"] = c
    return out


def main() -> int:
    reg = json.loads((ROOT / "evals" / "adversarial_cases.json").read_text())["cases"]
    cases = all_cases()
    by_rule = {k for k, c in cases.items() if c.get("class") in ("injection", "decoy") or RULE.search(c["id"])}
    check("1a. every case the rule finds is registered", sorted(by_rule - set(reg)) == [], str(sorted(by_rule - set(reg))))
    check("1b. nothing registered that the rule does not find", sorted(set(reg) - by_rule) == [], str(sorted(set(reg) - by_rule)))
    bad = [k for k, e in reg.items() if k not in cases or e.get("split") != cases[k].get("split")
           or e.get("kind") not in ("injection", "decoy", "bait") or not str(e.get("why", "")).strip()]
    check("2. every entry resolves, split matches cases.json, kind valid, why non-empty", bad == [], str(bad))
    regd = json.loads((ROOT / "evals" / "adversarial_cases.json").read_text())
    cand = regd.get("candidates_from_notes", {})
    check("2b. candidates_from_notes resolve, are NOT in `cases` (lower bound stated, not silently merged)",
          all(k in cases for k in cand) and not (set(cand) & set(reg)) and len(cand) >= 8, str(sorted(set(cand) - set(cases))))
    check("2c. the register note says it is a lower bound", "LOWER BOUND" in regd["note"])
    inline = [k for k, c in cases.items() if "adversarial" in c]
    check("3. no case carries an inline `adversarial` key", inline == [], str(inline))

    rows = ar.report(ROOT)
    probs = []
    for r in rows:
        if not r["snapshot"]:
            continue
        snap = json.loads((ROOT / "evals" / r["exam"] / "snapshot.json").read_text())
        for split in ("heldout", "train"):
            n = sum(1 for c in snap["cases"] if c["split"] == split)
            if r[split]["adv_n"] + r[split]["rest_n"] != n:
                probs.append((r["exam"], split, "n"))
            want_adv = sum(1 for c in snap["cases"] if c["split"] == split and f"{r['exam']}/{c['id']}" in reg
                           and c["passed"] and c["stable"])
            if r[split]["adv_passed"] != want_adv:
                probs.append((r["exam"], split, "passed"))
    check("4a. adversarial + rest = n per split; passed = passed AND stable", probs == [], str(probs))
    adv_total = sum(r["heldout"]["adv_n"] + r["train"]["adv_n"] for r in rows if r["snapshot"])
    check("4b. the report covers every registered case that has a snapshot",
          adv_total == sum(1 for k in reg if (ROOT / "evals" / k.split('/')[0] / "snapshot.json").exists()), str(adv_total))

    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "evals" / "x"; d.mkdir(parents=True)
        (Path(td) / "evals" / "adversarial_cases.json").write_text(json.dumps(
            {"cases": {"x/a-bait": {"kind": "bait", "split": "heldout", "why": "w"},
                       "y/b-bait": {"kind": "bait", "split": "heldout", "why": "w"}}}))
        (d / "snapshot.json").write_text(json.dumps({"model": "m", "cases": [
            {"id": "a-bait", "split": "heldout", "passed": True, "stable": False},
            {"id": "c", "split": "heldout", "passed": True, "stable": True}]}))
        rr = {r["exam"]: r for r in ar.report(Path(td))}
    check("4c. a flaky adversarial pass is NOT counted as passed", rr["x"]["heldout"]["adv_passed"] == 0
          and rr["x"]["heldout"]["adv_failed_ids"] == ["a-bait"], str(rr["x"]))
    check("5. an exam without a snapshot -> 'no snapshot', not 0/n", rr["y"]["snapshot"] is False and "heldout" not in rr["y"], str(rr["y"]))

    buf = io.StringIO()
    with redirect_stdout(buf):
        ar.main([str(ROOT)])
    crm = next(r for r in rows if r["exam"] == "crm-followup")
    line = next((l for l in buf.getvalue().splitlines() if l.startswith("crm-followup")), "")
    check("6. text row prints crm's held-out adversarial and rest fractions",
          f"{crm['heldout']['adv_passed']}/{crm['heldout']['adv_n']}" in line
          and f"{crm['heldout']['rest_passed']}/{crm['heldout']['rest_n']}" in line, line)
    check("6b. failed TRAIN adversarial ids are printed too (marked '(train)')",
          all(f"{i} (train)" in line for i in crm["train"]["adv_failed_ids"]) and crm["train"]["adv_failed_ids"], line)
    check("6c. the footer says LOWER BOUND", "LOWER BOUND" in buf.getvalue())
    print(f"\n{len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
