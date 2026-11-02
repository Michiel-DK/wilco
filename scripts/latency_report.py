#!/usr/bin/env python3
"""Per-case latency, per result file, from what the runner already records. No model, no server.

    python3 scripts/latency_report.py [results_dir] [--json]

Source: `cases[i].detail.metrics` in each top-level `results/*.json` (the same per-case dict
`metrics_totals` is summed from — gotcha 13: this script reads ONLY that per-case dict, never the
per-turn entries under `detail.turns` and never `metrics_totals` as a second addend; the totals are
used only as a cross-check and a mismatch is printed, not hidden).

What the numbers ARE, stated on every row (`basis`):
  wall_ms   client-side wall clock for the WHOLE case: prefill + decode + every retry + every tool
            step + (hosted) the network. Measured on whatever machine ran the exam, serial; one load,
            except on a multi-load aggregate row (see below).
  e2e tok/s completion_tokens / wall seconds over the file's metered cases — END-TO-END, prefill
            included, so it UNDERSTATES decode speed. It is not decode tok/s and not TTFT.
What is NOT here (declared gap): time-to-first-token and decode-only tok/s. The router calls Ollama's
/v1 chat endpoint with stream=false; on Ollama 0.40.11 its `timings` block is sent only on streaming
responses with include_usage (middleware/openai.go, v0.40.11), so no per-call server timing reaches
the result files. Getting it is a router change (`full` tier) plus a re-sit.

Cases with no metrics, or with a `termination` record, are counted in `unmetered` and left out of the
percentiles (their wall time is incomplete), never filled with zero. A metered case whose completion
token count is None (backend did not report it) stays in the wall percentiles but leaves e2e tok/s
entirely (numerator and denominator). A top-level file written by `run --snapshot` is a multi-load
AGGREGATE (cases carry `stable`): its per-case walls come from different loads and the row says so.
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = {"ollama", "mlx", "systemone", "stub"}   # sandbox/router.py's local providers


def percentile(xs: list[float], q: float) -> float | None:
    """Nearest-rank percentile (no interpolation: every reported value is a real case's)."""
    if not xs:
        return None
    s = sorted(xs)
    return s[max(0, math.ceil(q / 100 * len(s)) - 1)]


def row_for(path: Path) -> dict | None:
    try:
        d = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get("cases"), list) or "agent" not in d:
        return None
    walls, comp, comp_wall, untokened, unmetered = [], 0, 0.0, 0, 0
    for c in d["cases"]:
        det = c.get("detail") if isinstance(c.get("detail"), dict) else {}
        m = det.get("metrics") if isinstance(det.get("metrics"), dict) else None
        if m is None or m.get("wall_ms") is None or "termination" in det:
            unmetered += 1
            continue
        walls.append(float(m["wall_ms"]))
        # None = "the backend did not report it" (router._empty_usage), never 0: such a case leaves BOTH
        # the token numerator and the wall denominator of e2e tok/s, so the rate is over known cases only.
        if m.get("completion_tokens") is None:
            untokened += 1
        else:
            comp += m["completion_tokens"]
            comp_wall += float(m["wall_ms"])
    tot = (d.get("metrics_totals") or {}).get("wall_ms")
    s = sum(walls)
    provider = d.get("provider", "?")
    # A `run --snapshot` writes the AGGREGATE of N loads at the top level (aggregate_loads): each case
    # record — wall included — is copied from the first load that voted with the majority, so walls on one
    # row can come from different loads, and metrics_totals is dropped. Say so on the row.
    aggregate = any("stable" in c for c in d["cases"])
    where = "local machine" if provider in LOCAL else "hosted (network included)"
    basis = (f"measured, client wall clock, serial, {where}; MULTI-LOAD AGGREGATE: each case's wall is from "
             f"the first load that voted with the majority, so a row mixes loads" if aggregate
             else f"measured, client wall clock, serial, one load, {where}")
    return {
        "file": path.name, "agent": d["agent"], "provider": provider, "model": d.get("model"),
        "run_at": d.get("run_at") or "unknown (file predates run_at)",
        "cases": len(d["cases"]), "metered": len(walls), "unmetered": unmetered,
        "p50_ms": percentile(walls, 50), "p95_ms": percentile(walls, 95), "max_ms": max(walls) if walls else None,
        "e2e_tok_s": round(comp / (comp_wall / 1000), 1) if comp_wall > 0 and comp else None,
        "untokened": untokened, "aggregate": aggregate,
        "basis": basis,
        # cross-check only: per-case wall over metrics_totals should be 1.0 when every case is metered
        "totals_check": (round(s / tot, 3) if tot else None),
    }


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    args = [a for a in argv if a != "--json"]
    rdir = Path(args[0]) if args else ROOT / "results"
    # top-level files only: per-load and arm results live in subdirs (runner.save_result convention)
    rows = [r for r in (row_for(p) for p in sorted(rdir.glob("*.json"))) if r]
    if as_json:
        print(json.dumps(rows, indent=2))
        return 0
    print(f"{'agent':22s} {'provider':10s} {'model':34s} {'n':>4s} {'p50 ms':>9s} {'p95 ms':>9s} {'e2e tok/s':>9s}  run_at")
    for r in rows:
        def cell(v, fmt):
            return format(v, fmt) if isinstance(v, (int, float)) else f"{'—':>9s}"
        print(f"{r['agent'][:22]:22s} {r['provider'][:10]:10s} {str(r['model'])[:34]:34s} {r['metered']:4d} "
              f"{cell(r['p50_ms'], '9.0f')} {cell(r['p95_ms'], '9.0f')} {cell(r['e2e_tok_s'], '9.1f')}  {r['run_at']}")
        if r["unmetered"]:
            print(f"{'':22s}   {r['unmetered']} case(s) unmetered, left out")
        if r["untokened"]:
            print(f"{'':22s}   {r['untokened']} case(s) with no token count: left out of e2e tok/s")
        if r["aggregate"]:
            print(f"{'':22s}   multi-load aggregate: walls mixed across loads (first majority-voting load per case)")
        if r["totals_check"] is not None and r["unmetered"] == 0 and abs(r["totals_check"] - 1) > 0.001:
            print(f"{'':22s}   ⚠ per-case wall / metrics_totals = {r['totals_check']} (expected 1.0)")
    print("\nwall = whole case (prefill+decode+retries+tool steps), serial; one load unless the row says aggregate. e2e tok/s includes prefill: "
          "NOT decode speed, NOT TTFT (not recorded: /v1 stream=false carries no timings on Ollama 0.40.11).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
