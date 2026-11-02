#!/usr/bin/env python3
"""Adversarial sub-score per exam: how the champion does on the cases built to trick it, beside — never inside —
the score.

    python3 scripts/adversarial_report.py [repo_root] [--json]

Inputs: evals/adversarial_cases.json (which cases are adversarial; the rule is in its `note`) and each exam's
committed rule-A snapshot (evals/<exam>/snapshot.json). Per exam and split:
    adversarial passed k/k / n_adv     (passed on every load, the repeat_report definition)
    rest        passed k/k / n_rest
The two never add up into a new score: the exam's own score is unchanged and stays the headline.
An exam whose register entries have no snapshot (e.g. recap-en before its baseline) is listed as "no snapshot".
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def report(root: Path = ROOT) -> list[dict]:
    reg = json.loads((root / "evals" / "adversarial_cases.json").read_text())["cases"]
    by_exam: dict[str, set] = {}
    for key in reg:
        exam, cid = key.split("/", 1)
        by_exam.setdefault(exam, set()).add(cid)
    rows = []
    for exam in sorted(by_exam):
        snapf = root / "evals" / exam / "snapshot.json"
        if not snapf.exists():
            rows.append({"exam": exam, "snapshot": False, "n_registered": len(by_exam[exam])})
            continue
        snap = json.loads(snapf.read_text())
        ids = {c["id"] for c in snap["cases"]}
        missing = sorted(by_exam[exam] - ids)
        row = {"exam": exam, "snapshot": True, "model": snap.get("model"), "missing_from_snapshot": missing}
        for split in ("heldout", "train"):
            sub = [c for c in snap["cases"] if c["split"] == split]
            adv = [c for c in sub if c["id"] in by_exam[exam]]
            rest = [c for c in sub if c["id"] not in by_exam[exam]]
            ok = lambda cs: sum(1 for c in cs if c["passed"] and c.get("stable") is True)  # noqa: E731
            row[split] = {"adv_passed": ok(adv), "adv_n": len(adv), "rest_passed": ok(rest), "rest_n": len(rest),
                          "adv_failed_ids": sorted(c["id"] for c in adv if not (c["passed"] and c.get("stable") is True))}
        rows.append(row)
    return rows


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    args = [a for a in argv if a != "--json"]
    rows = report(Path(args[0]) if args else ROOT)
    if as_json:
        print(json.dumps(rows, indent=2))
        return 0
    print(f"{'exam':24s} {'held-out adversarial':>21s} {'held-out rest':>14s}   {'train adv':>9s}   failed adversarial")
    for r in rows:
        if not r["snapshot"]:
            print(f"{r['exam']:24s}  no snapshot yet ({r['n_registered']} registered case(s))")
            continue
        h, t = r["heldout"], r["train"]
        print(f"{r['exam']:24s} {h['adv_passed']:>10d}/{h['adv_n']:<10d} {h['rest_passed']:>6d}/{h['rest_n']:<7d}   "
              f"{t['adv_passed']:>4d}/{t['adv_n']:<4d}   "
              f"{', '.join(h['adv_failed_ids'] + [i + ' (train)' for i in t['adv_failed_ids']]) or '-'}")
        if r["missing_from_snapshot"]:
            print(f"{'':24s}  ⚠ registered but not in the snapshot: {', '.join(r['missing_from_snapshot'])}")
    print("\nadversarial = marked as a trap by the exam's author in the case id or class (rule in evals/adversarial_cases.json).\n"
          "A LOWER BOUND: notes name more traps (`candidates_from_notes`, operator to accept or reject).\n"
          "passed = on every one of the snapshot's loads. Reported BESIDE the exam score, never summed into it.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
