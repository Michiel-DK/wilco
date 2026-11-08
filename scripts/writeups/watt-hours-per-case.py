#!/usr/bin/env python3
"""Re-derive the numbers in docs/writeups/watt-hours-per-case.md from committed files. No model, no GPU, no key.

    python3 scripts/writeups/watt-hours-per-case.py

Reads:
  docs/probes/energy-resnapshot-2026-11-01/RESULTS.md   the committed per-exam rows (median Wh/case of 3 loads)
  evals/<exam>/snapshot.json                             case count + per-load wall_s of the same 1 Nov re-snapshot

What it re-derives: the per-case range, the total over 27 loads, Wh per case-run, and an independent check of each
row's average package power against the snapshot's own wall times. What it CANNOT re-derive: the per-exam Wh itself.
That came from integrating a powermetrics capture which is not committed (scripts/energy_report.py does that step).
Totals here use the rounded per-exam medians, so they can differ from the probe's unrounded sum in the last digit.
"""
from __future__ import annotations
import json, re, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "docs/probes/energy-resnapshot-2026-11-01/RESULTS.md"
LOADS = 3
EXCLUDED = {"transcript-asr": "snapshot taken after 18:50 on 1 Nov, when coding agents shared the laptop"}
ROW = re.compile(r"^\|\s*([a-z-]+)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([\d.]+)\s*\(([\d.]+)[–-]([\d.]+)\)\s*\|"
                 r"\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*$")


def rows() -> list[dict]:
    out = []
    for line in RESULTS.read_text().splitlines():
        m = ROW.match(line)
        if m:
            out.append(dict(exam=m[1], model=m[2], n=int(m[3]), wh=float(m[4]), lo=float(m[5]), hi=float(m[6]),
                            j_per_1k=int(m[7]), watts=float(m[8]), coverage=float(m[9])))
    if not out:
        raise SystemExit(f"no per-exam rows parsed from {RESULTS}")
    return out


def main() -> int:
    table = rows()
    snaps = {p.parent.name for p in (ROOT / "evals").glob("*/snapshot.json")}
    tabled = {r["exam"] for r in table}
    missing = snaps - tabled - set(EXCLUDED)
    if missing:
        raise SystemExit(f"snapshot without an energy row and no stated exclusion: {sorted(missing)}")
    print(f"{'exam':<24}{'n':>4}{'Wh/case':>9}{'table W':>9}{'snap W':>8}")
    worst = 0.0
    for r in table:
        snap = json.loads((ROOT / "evals" / r["exam"] / "snapshot.json").read_text())
        if len(snap["cases"]) != r["n"]:
            raise SystemExit(f"{r['exam']}: table says {r['n']} cases, snapshot has {len(snap['cases'])}")
        walls = [l["wall_s"] for l in snap["load_resources"]]
        if len(walls) != LOADS:
            raise SystemExit(f"{r['exam']}: {len(walls)} loads in snapshot, expected {LOADS}")
        w = r["wh"] * r["n"] * 3600 / statistics.median(walls)
        worst = max(worst, abs(w - r["watts"]) / r["watts"])
        print(f"{r['exam']:<24}{r['n']:>4}{r['wh']:>9.3f}{r['watts']:>9.1f}{w:>8.1f}")
    n_cases = sum(r["n"] for r in table)
    total = sum(r["n"] * r["wh"] for r in table) * LOADS
    lo, hi = min(table, key=lambda r: r["wh"]), max(table, key=lambda r: r["wh"])
    print()
    print(f"exams: {len(table)} · cases: {n_cases} · case-runs: {n_cases * LOADS}")
    for ex, why in EXCLUDED.items():
        print(f"excluded: {ex} ({why})")
    print(f"range: {lo['wh']:.3f} Wh/case ({lo['exam']}) to {hi['wh']:.3f} Wh/case ({hi['exam']}), {hi['wh'] / lo['wh']:.1f}x")
    print(f"max load-to-load spread: {max(r['hi'] - r['lo'] for r in table):.3f} Wh/case")
    print(f"total: {total:.1f} Wh over {n_cases * LOADS} case-runs = {total / (n_cases * LOADS):.4f} Wh per case-run")
    print(f"10,000 tasks of this mix: {total / (n_cases * LOADS) * 10_000 / 1000:.2f} kWh (modelled on this mix)")
    print(f"avg-W cross-check vs snapshot wall times: worst row off by {worst * 100:.1f}%")
    # Read from the probe's rows, NOT recomputed (they need the uncommitted capture / results JSONs):
    print(f"from the rows, not recomputed: min window coverage {min(r['coverage'] for r in table):.3f}")
    for size in ("e2b", "e4b"):
        js = [r["j_per_1k"] for r in table if size in r["model"]]
        print(f"from the rows, not recomputed: {size} J per 1k output tokens {min(js)}–{max(js)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
