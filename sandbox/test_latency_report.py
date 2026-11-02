#!/usr/bin/env python3
"""scripts/latency_report.py reads per-case wall time once, honestly, and never double-counts.

    python3 sandbox/test_latency_report.py

Hand-built results files in a temp dir (no model, no server). Pins:
  1. per-case wall comes ONLY from cases[i].detail.metrics: a multi-turn case's per-turn wall_ms
     (detail.turns[*].wall_ms) is NOT added on top (gotcha 13), and metrics_totals is not an addend
  2. a case with no metrics, a null wall_ms, or a termination record is `unmetered`, left out of the
     percentiles, never counted as 0 ms
  3. percentiles are nearest-rank: every reported p50/p95 is a real case's value
  4. e2e tok/s = completion tokens / wall seconds over metered cases only
  5. run_at is passed through; a file without it says so, never a guessed date
  6. basis says local vs hosted from the provider
  7. subdirectory files (per-load, arms) are not read
  8. a real stub run, saved by the runner, round-trips through the report (real entry points)
  9. a multi-load aggregate (cases carry `stable`) is labelled as mixing loads, never "one load"
 10. a None completion-token count leaves e2e tok/s entirely (never counted as 0)
 11. local basis covers mlx/stub; a totals mismatch is computed and PRINTED
 12. the text table's columns are in their header order
Each pin was seen RED under a hand mutation of the script (PR body lists them).
"""
from __future__ import annotations
import importlib.util, io, json, sys, tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
spec = importlib.util.spec_from_file_location("latency_report", ROOT / "scripts" / "latency_report.py")
lr = importlib.util.module_from_spec(spec); spec.loader.exec_module(lr)

FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def case(cid, wall, comp=10, **extra):
    det = {"metrics": {"wall_ms": wall, "completion_tokens": comp, "prompt_tokens": 100}}
    det.update(extra)
    return {"id": cid, "split": "heldout", "passed": True, "detail": det}


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        local = {"agent": "crm-followup", "provider": "ollama", "model": "m", "run_at": "2026-10-31T15:00:00+01:00",
                 "cases": [case("a", 1000.0), case("b", 2000.0), case("c", 3000.0),
                           # multi-turn: per-turn walls sum to the case wall; must not be added again
                           case("t", 4000.0, turns=[{"turn": 1, "wall_ms": 1500.0}, {"turn": 2, "wall_ms": 2500.0}]),
                           {"id": "nometrics", "split": "heldout", "passed": False, "detail": {}},
                           case("nullwall", None),
                           case("died", 9999.0, termination={"cause": "timeout"})],
                 "metrics_totals": {"wall_ms": 10000.0 + 9999.0}}
        (d / "crm-followup__ollama__m.json").write_text(json.dumps(local))
        hosted = {"agent": "email-triage", "provider": "openrouter", "model": "h",
                  "cases": [case("x", 500.0, comp=50)], "metrics_totals": {"wall_ms": 500.0}}
        (d / "email-triage__openrouter__h.json").write_text(json.dumps(hosted))
        # 9. a multi-load aggregate (cases carry `stable`, no metrics_totals) — as `run --snapshot` writes it
        agg = {"agent": "transcript-en", "provider": "ollama", "model": "g",
               "cases": [dict(case("s1", 100.0), stable=True), dict(case("s2", 200.0), stable=False)]}
        (d / "transcript-en__ollama__g.json").write_text(json.dumps(agg))
        # 10. None completion tokens = unknown: out of both numerator and denominator
        unk = {"agent": "reply-draft", "provider": "ollama", "model": "u",
               "cases": [case("k", 1000.0, comp=10), case("n1", 1000.0, comp=None),
                         case("n2", 1000.0, comp=None), case("n3", 1000.0, comp=None)],
               "metrics_totals": {"wall_ms": 4000.0}}
        (d / "reply-draft__ollama__u.json").write_text(json.dumps(unk))
        # 11. per-case walls disagree with metrics_totals (every case metered) -> printed warning
        bad = {"agent": "task-intake", "provider": "mlx", "model": "w",
               "cases": [case("w1", 1000.0), case("w2", 3000.0)], "metrics_totals": {"wall_ms": 8000.0}}
        (d / "task-intake__mlx__w.json").write_text(json.dumps(bad))
        (d / "snapshot_loads").mkdir()
        (d / "snapshot_loads" / "crm-followup__ollama__m__load1.json").write_text(json.dumps(local))
        (d / "notaresult.json").write_text(json.dumps({"hello": 1}))

        rows = {r["file"]: r for r in (lr.row_for(p) for p in sorted(d.glob("*.json"))) if r}
        buf = io.StringIO()
        with redirect_stdout(buf):
            lr.main([str(d), "--json"])
        via_main = json.loads(buf.getvalue())
        tbuf = io.StringIO()
        with redirect_stdout(tbuf):
            lr.main([str(d)])
        text = tbuf.getvalue()

    r = rows.get("crm-followup__ollama__m.json") or {}
    check("1a. metered = the 4 cases with a complete wall", r.get("metered") == 4, str(r))
    check("1b. max is the multi-turn case's own wall (4000), turns not added (else 8000)", r.get("max_ms") == 4000.0, str(r.get("max_ms")))
    check("2. no-metrics, null-wall and terminated cases are unmetered (3), not 0 ms", r.get("unmetered") == 3, str(r.get("unmetered")))
    check("3a. p50 nearest-rank over [1000,2000,3000,4000] = 2000", r.get("p50_ms") == 2000.0, str(r.get("p50_ms")))
    check("3b. p95 nearest-rank = 4000", r.get("p95_ms") == 4000.0, str(r.get("p95_ms")))
    check("4. e2e tok/s = 40 tokens / 10 s = 4.0", r.get("e2e_tok_s") == 4.0, str(r.get("e2e_tok_s")))
    check("5a. run_at passed through", r.get("run_at") == "2026-10-31T15:00:00+01:00", str(r.get("run_at")))
    h = rows.get("email-triage__openrouter__h.json") or {}
    check("5b. a file without run_at says so", "predates run_at" in str(h.get("run_at")), str(h.get("run_at")))
    check("6a. local basis on ollama", "local machine" in r.get("basis", ""), r.get("basis", ""))
    check("6b. hosted basis on openrouter", "hosted" in h.get("basis", ""), h.get("basis", ""))
    check("7a. main() reads top-level files only (no per-load copy, no non-result)",
          sorted(x["file"] for x in via_main) == sorted(["crm-followup__ollama__m.json", "email-triage__openrouter__h.json",
              "transcript-en__ollama__g.json", "reply-draft__ollama__u.json", "task-intake__mlx__w.json"]),
          str([x["file"] for x in via_main]))
    a = rows.get("transcript-en__ollama__g.json") or {}
    check("9a. a multi-load aggregate is flagged", a.get("aggregate") is True, str(a))
    check("9b. its basis says the walls mix loads (not 'one load')",
          "MULTI-LOAD AGGREGATE" in a.get("basis", "") and "one load" not in a.get("basis", ""), a.get("basis", ""))
    check("9c. a plain single-load file is not flagged", r.get("aggregate") is False and "one load" in r.get("basis", ""))
    u = rows.get("reply-draft__ollama__u.json") or {}
    check("10a. None tokens leave tok/s entirely: 10 tok / 1 s = 10.0 (not 2.5)", u.get("e2e_tok_s") == 10.0, str(u.get("e2e_tok_s")))
    check("10b. the 3 untokened cases are counted and still in the wall percentiles",
          u.get("untokened") == 3 and u.get("metered") == 4, str(u))
    w = rows.get("task-intake__mlx__w.json") or {}
    check("11a. mlx is a LOCAL provider", "local machine" in w.get("basis", ""), w.get("basis", ""))
    check("11b. totals_check = per-case wall / metrics_totals = 0.5", w.get("totals_check") == 0.5, str(w.get("totals_check")))
    check("11c. the text report prints the mismatch warning on that row",
          "per-case wall / metrics_totals = 0.5" in text, text[-600:])
    line = next((l for l in text.splitlines() if l.startswith("crm-followup")), "")
    cols = line.split()
    check("12. text table columns: n, p50, p95, tok/s in that order (4 2000 4000 4.0)",
          cols[3:7] == ["4", "2000", "4000", "4.0"], line)

    # 8. real entry points: a stub run saved by the runner
    import runner
    agent, exam = runner.load_agent("email-triage"), runner.load_exam("email-triage")
    with redirect_stdout(io.StringIO()):
        res = runner.run_exam(agent, exam, "stub", agent["model"])
    with tempfile.TemporaryDirectory() as td:
        saved = runner.RESULTS_DIR
        runner.RESULTS_DIR = Path(td)
        try:
            p = runner.save_result(res)
        finally:
            runner.RESULTS_DIR = saved
        row = lr.row_for(p)
    check("8a. a runner-saved stub result is read", row is not None and row["cases"] == len(exam["cases"]), str(row and row["cases"]))
    check("8c. the stub provider is LOCAL", row is not None and "local machine" in row["basis"], str(row and row["basis"]))
    check("8b. its run_at comes from the runner, not the fallback", row is not None and row["run_at"] == res.get("run_at")
          and "predates" not in str(row["run_at"]), str(row and row["run_at"]))

    print(f"\n{len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
