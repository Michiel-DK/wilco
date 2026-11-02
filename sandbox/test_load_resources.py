#!/usr/bin/env python3
"""Per-load resources (item 4, 2026-10-31): wall time + peak memory recorded per snapshot load, never scored.

    python3 sandbox/test_load_resources.py

No model, no server: ps / lsof / api-ps are injected fakes; urllib patched to raise. Pins:
  1. tree_rss_kb sums the root AND every descendant (grandchildren too), ignores unrelated processes,
     None when the root is gone
  2. ResourceSampler keeps the PEAK across samples, counts failed samples instead of raising
  3. measure_load: the run's result is returned unchanged; resources carry wall_s, peak, samples, basis,
     and api_ps (ollama only); an unfindable listener -> {"wall_s", "unavailable": reason} and the run
     STILL happens exactly once
  4. take_snapshot_loads: every per-load result carries load_resources, the aggregate carries the list of
     all loads in order; nothing is added inside the run_exam record itself
  5. snapshot_payload: `load_resources` only when passed (legacy key set unchanged); never read by
     snapshot_preflight (bogus resources -> same preflight answer)
  6. _local_server_url: ollama / mlx / llamacpp (+ its env override) -> their URL; hosted + stub -> None
Each pin seen RED under a hand mutation (PR body).
"""
from __future__ import annotations
import contextlib, io, json, os, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
import runner  # noqa: E402

FAILED: list[str] = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def _no_net(*a, **k):
    raise AssertionError("network call attempted")


urllib.request.urlopen = _no_net
runner.urllib.request.urlopen = _no_net


def main() -> int:
    T = [(1, 0, 10), (100, 1, 500), (200, 100, 3000), (201, 200, 7000), (300, 1, 99999)]
    check("1a. root + child + grandchild + great-grandchild summed, sibling tree ignored",
          runner.tree_rss_kb(100, T) == 500 + 3000 + 7000, str(runner.tree_rss_kb(100, T)))
    check("1b. a root that is not running -> None (never 0)", runner.tree_rss_kb(999, T) is None)

    seq = iter([[(100, 1, 100)], [(100, 1, 900), (101, 100, 50)], RuntimeError("ps died"), [(100, 1, 300)]])

    def table():
        v = next(seq, [(100, 1, 300)])
        if isinstance(v, Exception):
            raise v
        return v
    smp = runner.ResourceSampler(100, table, interval_s=0.0)
    for _ in range(4):
        smp._sample()
    r = smp.result()
    check("2a. the peak is kept (950), not the last value", r["rss_tree_peak_kb"] == 950, str(r))
    check("2b. a failing sample is counted, never raised", r["failed_samples"] == 1 and r["samples"] == 3, str(r))

    runs = []
    sentinel = {"agent": "x", "cases": [], "marker": object()}

    def run_fn():
        runs.append(1)
        time.sleep(0.05)
        return sentinel
    res, rsc = runner.measure_load(run_fn, base_url="http://127.0.0.1:11434/v1", model="m", is_ollama=True,
                                   pid_fn=lambda u: 100, table_fn=lambda: [(100, 1, 1234)],
                                   api_ps_fn=lambda m: {"size": 5, "size_vram": 4}, interval_s=0.01)
    check("3a. the run's result is returned as-is (same object), run once", res is sentinel and len(runs) == 1)
    check("3b. resources: wall_s > 0, peak 1234, samples >= 1, basis stated, api_ps from Ollama",
          rsc.get("wall_s", 0) >= 0.0 and rsc.get("rss_tree_peak_kb") == 1234 and rsc.get("samples", 0) >= 1
          and "descendants" in rsc.get("basis", "") and rsc.get("api_ps") == {"size": 5, "size_vram": 4}, str(rsc))
    _, rsc_m = runner.measure_load(run_fn, base_url="http://127.0.0.1:8080/v1", model="m", is_ollama=False,
                                   pid_fn=lambda u: 100, table_fn=lambda: [(100, 1, 1)], interval_s=0.01)
    check("3c. non-ollama local server: no api_ps key", "api_ps" not in rsc_m and rsc_m.get("rss_tree_peak_kb") == 1, str(rsc_m))
    runs.clear()

    def no_listener(u):
        raise ValueError("expected 1 listener on port 11434, found []")
    res2, rsc2 = runner.measure_load(run_fn, base_url="http://127.0.0.1:11434/v1", model="m", is_ollama=True,
                                     pid_fn=no_listener)
    check("3d. unfindable listener -> unavailable + reason, wall still recorded, run still happened once",
          res2 is sentinel and len(runs) == 1 and "found []" in rsc2.get("unavailable", "") and "wall_s" in rsc2, str(rsc2))
    _, rsc3 = runner.measure_load(run_fn, base_url=None, model="m", is_ollama=False)
    check("3e. no local server (hosted/stub) -> unavailable, says why", "no local server" in rsc3.get("unavailable", ""), str(rsc3))

    # 3f-3j: the refuter's survivors
    smp2 = runner.ResourceSampler(100, lambda: [(100, 1, 77)], interval_s=3600)
    with smp2:
        pass   # a load far shorter than one interval
    check("3f. a sub-interval load still records a sample (the final one) and the thread is stopped",
          smp2.result()["samples"] >= 1 and smp2.result()["rss_tree_peak_kb"] == 77 and not smp2._thread.is_alive(),
          str(smp2.result()))
    import subprocess as _sp

    def timeout_pid(u):
        raise _sp.TimeoutExpired("lsof", 15)
    runs.clear()
    res4, rsc4 = runner.measure_load(run_fn, base_url="http://127.0.0.1:11434/v1", model="m", is_ollama=True,
                                     pid_fn=timeout_pid)
    check("3g. a lsof TimeoutExpired is recorded, the load still runs", res4 is sentinel and len(runs) == 1
          and "TimeoutExpired" in rsc4.get("unavailable", ""), str(rsc4))

    def exit_pid(u):
        raise SystemExit("tool 'lsof' not found")
    res5, rsc5 = runner.measure_load(run_fn, base_url="http://127.0.0.1:11434/v1", model="m", is_ollama=True,
                                     pid_fn=exit_pid)
    check("3h. even a SystemExit from the lookup is recorded, never escapes", res5 is sentinel
          and "SystemExit" in rsc5.get("unavailable", ""), str(rsc5))

    def bad_api(m):
        raise OSError("connection refused")
    _, rsc6 = runner.measure_load(run_fn, base_url="http://127.0.0.1:11434/v1", model="m", is_ollama=True,
                                  pid_fn=lambda u: 100, table_fn=lambda: [(100, 1, 5)], api_ps_fn=bad_api, interval_s=0.01)
    check("3i. an /api/ps failure is recorded as api_ps.unavailable with its cause", rsc6.get("api_ps", {}).get("unavailable", "")
          .startswith("OSError"), str(rsc6))

    def exit_table():
        raise SystemExit("ps not found")
    smp3 = runner.ResourceSampler(100, exit_table, interval_s=0.0)
    smp3._sample()
    check("3j. a SystemExit inside a sample is counted as a failed sample, never raised", smp3.failed == 1)
    saved_env = os.environ.get("SANDBOX_OFFLINE_PROBES")
    os.environ["SANDBOX_OFFLINE_PROBES"] = "1"
    probed = []
    real_pid = runner._listener_pid
    runner._listener_pid = lambda u: probed.append(u) or 1
    try:
        _, rsc7 = runner.measure_load(run_fn, base_url="http://127.0.0.1:11434/v1", model="m", is_ollama=True)
    finally:
        runner._listener_pid = real_pid
        if saved_env is None:
            os.environ.pop("SANDBOX_OFFLINE_PROBES", None)
        else:
            os.environ["SANDBOX_OFFLINE_PROBES"] = saved_env
    check("3k. SANDBOX_OFFLINE_PROBES=1 (the gate): no process probe at all, the reason recorded",
          probed == [] and "offline gate" in rsc7.get("unavailable", ""), str(rsc7))
    gate_sh = (ROOT / "scripts" / "test.sh").read_text()
    check("3l. the gate exports SANDBOX_OFFLINE_PROBES=1", "export SANDBOX_OFFLINE_PROBES=1" in gate_sh)

    # 4. take_snapshot_loads end to end with fakes
    agent, exam = runner.load_agent("email-triage"), runner.load_exam("email-triage")
    fixture = {"agent": "email-triage", "provider": "stub", "model": "m",
               "cases": [{"id": "a", "split": "heldout", "passed": True}],
               "train": {"passed": 0, "total": 0, "score": None}, "heldout": {"passed": 1, "total": 1, "score": 1.0}}
    saved_records = []

    def fake_run(*a, **k):
        r = json.loads(json.dumps(fixture))
        return r

    def fake_save(result, **k):
        saved_records.append(json.loads(json.dumps(result)))
        return Path("/dev/null")
    saved = (runner.run_exam, runner.save_result)
    runner.run_exam, runner.save_result = fake_run, fake_save
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            agg, _rt = runner.take_snapshot_loads(agent, exam, "stub", "m", 3)
    finally:
        runner.run_exam, runner.save_result = saved
    per_load = [r for r in saved_records if isinstance(r.get("load_resources"), dict)]
    check("4a. each of the 3 per-load results carries load_resources", len(per_load) == 3, str(len(per_load)))
    check("4b. the aggregate carries the list of all 3 loads, in order", isinstance(agg.get("load_resources"), list)
          and len(agg["load_resources"]) == 3 and agg["load_resources"] == [r["load_resources"] for r in per_load],
          str(agg.get("load_resources")))
    check("4c. nothing added inside the run_exam record's cases", all(set(c) == {"id", "split", "passed", "stable"}
          for c in agg["cases"]), str(agg["cases"]))

    # 5. snapshot payload + preflight
    p0 = runner.snapshot_payload(agent, exam, "stub", "m", agg)
    p1 = runner.snapshot_payload(agent, exam, "stub", "m", agg, load_resources=agg["load_resources"])
    check("5a. payload without load_resources: no new key; with: exactly that one key", "load_resources" not in p0
          and set(p1) - set(p0) == {"load_resources"})
    snap = json.loads((ROOT / "evals" / "email-triage" / "snapshot.json").read_text())
    ver = lambda: snap["runtime"]["version"]  # noqa: E731
    srv = lambda: {k: snap["runtime"][k] for k in runner.OLLAMA_STAMP_FIELDS}  # noqa: E731
    plain = runner.snapshot_preflight(snap, exam, version_fn=ver, server_settings_fn=srv)
    bogus = runner.snapshot_preflight({**snap, "load_resources": [{"rss_tree_peak_kb": -1}]}, exam, version_fn=ver,
                                      server_settings_fn=srv)
    check("5b. preflight ignores load_resources", plain == bogus and plain is None, f"{plain} vs {bogus}")

    # 6. which server is measured
    os.environ.pop("LLAMACPP_BASE_URL", None)
    U = runner._local_server_url
    check("6a. ollama -> its URL; mlx -> its URL; llamacpp -> its URL",
          U("ollama", True) == runner.PROVIDERS["ollama"]["base_url"] and U("mlx", False) == runner.PROVIDERS["mlx"]["base_url"]
          and U("llamacpp", False) == runner.PROVIDERS["llamacpp"]["base_url"])
    os.environ["LLAMACPP_BASE_URL"] = "http://127.0.0.1:9931/v1"
    check("6b. llamacpp honours LLAMACPP_BASE_URL", U("llamacpp", False) == "http://127.0.0.1:9931/v1")
    os.environ.pop("LLAMACPP_BASE_URL", None)
    check("6c. hosted + stub -> None", U("openrouter", False) is None and U("anthropic", False) is None and U("stub", False) is None)

    print(f"\n{len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
