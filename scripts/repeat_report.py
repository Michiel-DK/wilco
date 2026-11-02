#!/usr/bin/env python3
"""Repeat column per exam: of the cases, how many passed on EVERY load, failed on every load, or flipped.

    python3 scripts/repeat_report.py [evals_dir] [--json]

Source: the committed rule-A snapshots (evals/<agent>/snapshot.json). A snapshot is `loads` fresh model loads
at temperature 0 (CLAUDE.md "Gates are deterministic"); each case carries `passed` (the majority verdict) and
`stable` (True iff every load agreed). So, per split:
    passed k/k = passed and stable      failed k/k = not passed and stable      flaky = not stable
    pass^k     = passed k/k / n         (the share of cases that passed on all k loads)
No runner change and no new run: these numbers are already in every committed snapshot. Held-out is the
reported score; train is shown beside it, never summed into it.

What it is NOT: pass^k across DAYS or runtime versions (a runtime bump is a silent re-roll, gotcha 15) and not
hosted rows (one pass, no rule A). A snapshot without `loads` or without `stable` on a case is reported as
"not rule-A", never counted as k/k.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def row(snap: dict, exam: str) -> dict:
    loads = snap.get("loads")
    cases = snap.get("cases") or []
    rule_a = isinstance(loads, int) and loads >= 2 and cases and all(isinstance(c.get("stable"), bool) for c in cases)
    out = {"exam": exam, "model": snap.get("model"), "provider": snap.get("provider"),
           "runtime_version": (snap.get("runtime") or {}).get("version"), "date": snap.get("date"),
           "loads": loads, "rule_a": bool(rule_a)}
    for split in ("heldout", "train"):
        sub = [c for c in cases if c.get("split") == split]
        n = len(sub)
        if not rule_a:
            out[split] = {"n": n}
            continue
        p = sum(1 for c in sub if c["passed"] and c["stable"])
        f = sum(1 for c in sub if not c["passed"] and c["stable"])
        fl = sum(1 for c in sub if not c["stable"])
        out[split] = {"n": n, "passed_all": p, "failed_all": f, "flaky": fl,
                      "pass_k": round(p / n, 4) if n else None,
                      "flaky_ids": sorted(c["id"] for c in sub if not c["stable"])}
    return out


def rows(evals_dir: Path) -> list[dict]:
    out = []
    for snapf in sorted(evals_dir.glob("*/snapshot.json")):   # one committed snapshot per exam dir
        out.append(row(json.loads(snapf.read_text()), snapf.parent.name))
    return out


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    args = [a for a in argv if a != "--json"]
    rs = rows(Path(args[0]) if args else ROOT / "evals")
    if as_json:
        print(json.dumps(rs, indent=2))
        return 0
    print(f"{'exam':24s} {'model':22s} {'k':>2s}  {'held-out k/k':>13s} {'fail k/k':>8s} {'flaky':>5s}   "
          f"{'train k/k':>9s} {'flaky':>5s}  runtime")
    for r in rs:
        if not r["rule_a"]:
            print(f"{r['exam'][:24]:24s} {str(r['model'])[:22]:22s}  —  not rule-A (no loads / no per-case stable)")
            continue
        h, t = r["heldout"], r["train"]
        print(f"{r['exam'][:24]:24s} {str(r['model'])[:22]:22s} {r['loads']:>2d}  "
              f"{h['passed_all']:>6d}/{h['n']:<6d} {h['failed_all']:>8d} {h['flaky']:>5d}   "
              f"{t['passed_all']:>4d}/{t['n']:<4d} {t['flaky']:>5d}  {r['runtime_version']}")
    print("\nk/k = the case passed on every one of the k fresh loads at temp 0 (rule A); flaky = the loads disagreed.\n"
          "Same day, same runtime only: a runtime bump is a re-roll (gotcha 15). Hosted rows are one pass, not shown.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
