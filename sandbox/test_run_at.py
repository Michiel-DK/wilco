#!/usr/bin/env python3
"""run_at: every exam result says when its run started — and nothing that scores or gates reads it.

    python3 sandbox/test_run_at.py

Through the real entry points, on the stub provider (no model, no server, no Ollama call):
  1. run_exam's result carries `run_at`, ISO-8601 with a UTC offset, between the wall-clock
     instants taken just before and just after the call
  2. save_result writes it to the results file (the thing a results page reads)
  3. snapshot_payload does NOT carry it (snapshots keep their own `date`; their key set is
     unchanged, so no committed snapshot moves and `check` compares exactly what it did)
  4. aggregate_loads keeps load 1's run_at (when the multi-load run began), never a later one
  5. verdicts are unchanged by it: the same exam on the same stub gives the same per-case
     passed list with run_at present
  6. it is the START of the run: stamped before the first model call (a 1.5 s first call separates the two)
Seen RED by hand on the pre-change runner.py (1a-1d, 2, 4a, 4b fail; 3 and 5 pass on both — they
are the no-regression half; 2 and 4b require run_at non-null so they cannot pass on None == None).
"""
from __future__ import annotations
import json, sys, tempfile, time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
import runner  # noqa: E402

FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def main() -> int:
    agent, exam = runner.load_agent("email-triage"), runner.load_exam("email-triage")
    before = datetime.now().astimezone().replace(microsecond=0)
    res = runner.run_exam(agent, exam, "stub", agent["model"])
    after = datetime.now().astimezone()

    ra = res.get("run_at")
    check("1a. run_exam result carries run_at", isinstance(ra, str), repr(ra))
    parsed = None
    try:
        parsed = datetime.fromisoformat(ra) if isinstance(ra, str) else None
    except ValueError:
        pass
    check("1b. run_at is ISO-8601", parsed is not None, repr(ra))
    check("1c. run_at carries a UTC offset (a page in another timezone reads it right)",
          parsed is not None and parsed.utcoffset() is not None, repr(ra))
    check("1d. run_at falls between just-before and just-after the call",
          parsed is not None and before <= parsed <= after, f"{before} <= {ra} <= {after}")

    with tempfile.TemporaryDirectory() as td:
        saved_dir = runner.RESULTS_DIR
        runner.RESULTS_DIR = Path(td)
        try:
            path = runner.save_result(res)
            on_disk = json.loads(path.read_text())
        finally:
            runner.RESULTS_DIR = saved_dir
    check("2. save_result writes run_at to the results file", ra is not None and on_disk.get("run_at") == ra, str(on_disk.get("run_at")))

    snap = runner.snapshot_payload(agent, exam, "stub", agent["model"], res)
    check("3a. snapshot_payload does not carry run_at", "run_at" not in snap, str(sorted(snap)))
    check("3b. snapshot_payload keeps its own date", "date" in snap, str(sorted(snap)))

    time.sleep(1.1)
    res2 = runner.run_exam(agent, exam, "stub", agent["model"])
    res3 = runner.run_exam(agent, exam, "stub", agent["model"])
    agg = runner.aggregate_loads([res, res2, res3])
    check("4a. later loads really have a later run_at (else 4b proves nothing)",
          res2.get("run_at") is not None and res2.get("run_at") != ra, f"{ra} vs {res2.get('run_at')}")
    check("4b. aggregate_loads keeps load 1's run_at", ra is not None and agg.get("run_at") == ra, f"{agg.get('run_at')} vs {ra}")

    # 6. run_at is the START: the first model call sleeps 1.5 s, so a stamp taken at the end would land
    #    at least one whole second after that call began (test-honesty refuter, survivor 1).
    first_call = []
    real_adapter_for = runner.adapter_for

    def slow_adapter_for(*a, **k):
        ad = real_adapter_for(*a, **k)
        real_gen = ad.generate

        def gen(*ga, **gk):
            if not first_call:
                first_call.append(datetime.now().astimezone())
                time.sleep(1.5)
            return real_gen(*ga, **gk)
        ad.generate = gen
        return ad
    runner.adapter_for = slow_adapter_for
    try:
        res_slow = runner.run_exam(agent, exam, "stub", agent["model"])
    finally:
        runner.adapter_for = real_adapter_for
    rs = datetime.fromisoformat(res_slow["run_at"]) if res_slow.get("run_at") else None
    check("6. run_at is stamped before the first model call (not at the end of the run)",
          rs is not None and bool(first_call) and rs <= first_call[0], f"run_at={rs} first_call={first_call[:1]}")

    v1 = [(c["id"], c["passed"]) for c in res["cases"]]
    v2 = [(c["id"], c["passed"]) for c in res2["cases"]]
    check("5. per-case verdicts identical across stub runs with run_at present", v1 == v2 and len(v1) > 0)

    print(f"\n{len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
