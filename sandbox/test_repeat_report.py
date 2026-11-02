#!/usr/bin/env python3
"""scripts/repeat_report.py: k/k counts read honestly from rule-A snapshots.

    python3 sandbox/test_repeat_report.py

Pins (hand-built snapshots + every committed one; no model, no server):
  1. passed k/k = passed AND stable; failed k/k = not passed AND stable; flaky = not stable; the three sum to n
  2. a majority-pass flaky case is flaky, never passed k/k
  3. held-out and train are counted separately (a train flake never touches the held-out row)
  4. a snapshot without `loads`, with loads < 2, or with a case lacking boolean `stable` is "not rule-A",
     never reported as k/k
  5. every committed evals/*/snapshot.json is rule-A and its held-out passed k/k + flaky-and-passed equals the
     snapshot's own heldout_score x n (the report agrees with the number the snapshot already states)
  6. the text row is exactly the row() values in header order (distinct-valued fixture, so no column can print a
     neighbour's number)
  7. a snapshot.scoped.json (an arm artifact) is never read
Each pin seen RED under a hand mutation (PR body).
"""
from __future__ import annotations
import importlib.util, io, json, sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("repeat_report", ROOT / "scripts" / "repeat_report.py")
rr = importlib.util.module_from_spec(spec); spec.loader.exec_module(rr)
FAILED: list[str] = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def snap(cases, loads=3):
    return {"model": "m", "provider": "ollama", "loads": loads, "runtime": {"version": "0.40.11"}, "cases": cases}


def c(cid, split, passed, stable=True):
    return {"id": cid, "split": split, "passed": passed, "stable": stable}


def main() -> int:
    s = snap([c("a", "heldout", True), c("b", "heldout", True), c("x", "heldout", False),
              c("f", "heldout", True, stable=False), c("g", "heldout", False, stable=False),
              c("t1", "train", True), c("t2", "train", True, stable=False)])
    r = rr.row(s, "e")
    h, t = r["heldout"], r["train"]
    check("1a. held-out passed k/k = passed AND stable = 2", h["passed_all"] == 2, str(h))
    check("1b. held-out failed k/k = 1", h["failed_all"] == 1, str(h))
    check("1c. held-out flaky = 2, ids listed", h["flaky"] == 2 and h["flaky_ids"] == ["f", "g"], str(h))
    check("1d. the three sum to n", h["passed_all"] + h["failed_all"] + h["flaky"] == h["n"] == 5, str(h))
    check("1e. pass^k = 2/5", h["pass_k"] == 0.4, str(h["pass_k"]))
    check("2. a majority-pass flaky case is flaky, not passed k/k", "f" in h["flaky_ids"])
    check("3. train counted separately (1 passed k/k, 1 flaky) and does not leak into held-out",
          t["passed_all"] == 1 and t["flaky"] == 1 and t["n"] == 2 and h["n"] == 5, str(t))

    check("4a. no `loads` -> not rule-A", rr.row({**s, "loads": None}, "e")["rule_a"] is False)
    check("4b. loads = 1 -> not rule-A", rr.row({**s, "loads": 1}, "e")["rule_a"] is False)
    bad = snap([c("a", "heldout", True), {"id": "b", "split": "heldout", "passed": True}])
    check("4c. a case without boolean `stable` -> not rule-A, no k/k reported",
          rr.row(bad, "e")["rule_a"] is False and "passed_all" not in rr.row(bad, "e")["heldout"])

    rows = rr.rows(ROOT / "evals")
    mism = []
    for r in rows:
        sd = json.loads((ROOT / "evals" / r["exam"] / "snapshot.json").read_text())
        hs = [x for x in sd["cases"] if x["split"] == "heldout"]
        majority_pass = sum(1 for x in hs if x["passed"])
        if not r["rule_a"] or round(majority_pass / len(hs), 4) != round(sd["heldout_score"], 4):
            mism.append((r["exam"], r["rule_a"], majority_pass, len(hs), sd["heldout_score"]))
        elif r["heldout"]["passed_all"] + sum(1 for x in hs if x["passed"] and not x["stable"]) != majority_pass:
            mism.append((r["exam"], "k/k mismatch"))
    check(f"5. every committed snapshot ({len(rows)}) is rule-A and agrees with its own heldout_score",
          mism == [] and len(rows) >= 8, str(mism))

    buf = io.StringIO()
    with redirect_stdout(buf):
        rr.main([str(ROOT / "evals")])
    out = buf.getvalue()
    line = next((l for l in out.splitlines() if l.startswith("crm-followup")), "")
    crm = next(r for r in rows if r["exam"] == "crm-followup")
    h, t = crm["heldout"], crm["train"]
    want = [crm["exam"], crm["model"], str(crm["loads"]), f"{h['passed_all']}/{h['n']}", str(h["failed_all"]),
            str(h["flaky"]), f"{t['passed_all']}/{t['n']}", str(t["flaky"]), str(crm["runtime_version"])]
    check("6a. the crm-followup text row is EXACTLY its row() values, every column in header order", line.split() == want,
          f"{line.split()} vs {want}")
    # 6b. distinct values per column, so a column printing a neighbour's value cannot pass
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "zz-exam"; d.mkdir()
        sx = {"model": "mm", "provider": "ollama", "loads": 3, "runtime": {"version": "9.9.9"}, "cases":
              [c("h1", "heldout", True), c("h2", "heldout", True), c("h3", "heldout", False),
               c("h4", "heldout", True, stable=False), c("h5", "heldout", True, stable=False),
               c("h6", "heldout", True, stable=False),
               c("t1", "train", True), c("t2", "train", True), c("t3", "train", True), c("t4", "train", True),
               c("t5", "train", False, stable=False), c("t6", "train", False), c("t7", "train", False)]}
        (d / "snapshot.json").write_text(json.dumps(sx))
        (d / "snapshot.scoped.json").write_text(json.dumps({**sx, "scoped_rule": "scoped"}))
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rr.main([td])
        got = next((l for l in buf2.getvalue().splitlines() if l.startswith("zz-exam")), "").split()
        n_rows = len(rr.rows(Path(td)))
    check("6b. distinct-valued fixture: zz-exam mm 3 | held-out 2/6 fail 1 flaky 3 | train 4/7 flaky 1 | 9.9.9",
          got == ["zz-exam", "mm", "3", "2/6", "1", "3", "4/7", "1", "9.9.9"], str(got))
    check("7. only snapshot.json is read: a snapshot.scoped.json beside it adds no row", n_rows == 1, str(n_rows))

    print(f"\n{len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
