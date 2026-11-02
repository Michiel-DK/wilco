#!/usr/bin/env python3
"""scripts/improve_loop.py: the loop driver keeps its promises (item 2, 2026-10-31).

    python3 sandbox/test_improve_loop.py

No model, no server: the stub provider (offline) and injected sit functions; urllib patched to raise. Pins:
  1. a real stub dry run (default_sit -> take_snapshot_loads -> run_exam on the stub) writes ONLY inside its run dir:
     agents/<agent>/prompt.md and evals/<agent>/snapshot.json byte-identical after, results/ top level unchanged
  2. a non-stub provider without --confirm-gpu is refused BEFORE any sit
  3. the proposer sees TRAIN failures only and never an `expected` key (sentinel through run_loop, not only the helper)
  4. every iteration sits the TRAIN split only; only the two final sits carry held-out cases
  5. keep goes through loop_gate (+2 stable train gain -> keep); the final step uses --final (confirm / refuse-run)
  6. refuse-run when a stable held-out case goes down at the end; 2 refusals in a row stop the loop
Each pin seen RED under a hand mutation (PR body).
"""
from __future__ import annotations
import contextlib, copy, hashlib, importlib.util, io, json, sys, tempfile, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
spec = importlib.util.spec_from_file_location("improve_loop", ROOT / "scripts" / "improve_loop.py")
il = importlib.util.module_from_spec(spec); spec.loader.exec_module(il)
runner, loop_gate = il.runner, il.loop_gate
FAILED: list[str] = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def _no_net(*a, **k):
    raise AssertionError("network call attempted")


urllib.request.urlopen = _no_net
runner.urllib.request.urlopen = _no_net
AGENT = "email-triage"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "absent"


def make_sit(script):
    """A fake sit: `script(label, exam, agent)` -> {case id: (passed, stable)}; returns a loop-gate-ready record."""
    calls = []

    def sit(agent, exam, provider, model, loads, run_dir, label):
        calls.append({"label": label, "splits": sorted({c["split"] for c in exam["cases"]}), "prompt": agent["system_prompt"]})
        verdicts = script(label, exam, agent)
        cases = [{"id": c["id"], "split": c["split"], "passed": verdicts.get(c["id"], (True, True))[0],
                  "stable": verdicts.get(c["id"], (True, True))[1]} for c in exam["cases"]]
        rec = {"provider": provider, "model": model, "loads": loads, "temperature": 0.0, "max_tokens": 2048, "judge": None,
               "runtime": {"version": "x"}, "train_score": None, "cases": cases,
               "loop_stamp": loop_gate.compute_loop_stamp(AGENT)}
        rec["_result"] = {"cases": [dict(c, input=f"input of {c['id']}", expected={"label": "SECRET-KEY"},
                                         got={"label": "x"}, failed_checks=[{"check": "label"}]) for c in cases]}
        return rec
    return sit, calls


def main() -> int:
    exam = runner.load_exam(AGENT)
    train_ids = [c["id"] for c in exam["cases"] if c["split"] == "train"]
    held_ids = [c["id"] for c in exam["cases"] if c["split"] == "heldout"]

    # 1. real stub dry run, writes confined to the run dir
    prompt_p, snap_p = ROOT / "agents" / AGENT / "prompt.md", ROOT / "evals" / AGENT / "snapshot.json"
    before = (sha(prompt_p), sha(snap_p), sorted(p.name for p in (ROOT / "results").glob("*")) if (ROOT / "results").exists() else [])
    with tempfile.TemporaryDirectory() as td:
        with contextlib.redirect_stdout(io.StringIO()):
            final = il.run_loop(AGENT, proposer=il.load_proposer("stub:append_line"), provider="stub", model="m",
                                iterations=3, loads=3, run_dir=Path(td) / "run")
        run_files = sorted(str(p.relative_to(td)) for p in Path(td).rglob("*") if p.is_file())
        log = [json.loads(l) for l in (Path(td) / "run" / "loop_log.jsonl").read_text().splitlines()]
    after = (sha(prompt_p), sha(snap_p), sorted(p.name for p in (ROOT / "results").glob("*")) if (ROOT / "results").exists() else [])
    check("1a. stub dry run: prompt.md, snapshot.json and the results/ top level untouched", before == after,
          f"{before[:2]} vs {after[:2]}; results diff {sorted(set(after[2]) ^ set(before[2]))}")
    check("1b. its sits landed in the run dir (records + per-load files) and a log was written",
          any(f.endswith("train-baseline/record.json") for f in run_files) and any("snapshot_loads" in f for f in run_files)
          and log[0]["step"] == "baseline", str(run_files[:6]))
    check("1c. the stub cannot improve, so 2 refusals stop it and nothing is kept",
          final.get("kept") == 0 and any(e.get("stop", "").startswith("2 refusals") for e in log), str(log[-2:]))

    # 2. GPU guard
    sit, calls = make_sit(lambda label, exam, agent: {})
    refused = False
    try:
        il.run_loop(AGENT, proposer=lambda *a: {"prompt": "p"}, provider="ollama", model="m", iterations=1, loads=3,
                    run_dir=Path(tempfile.mkdtemp()), sit_fn=sit)
    except SystemExit as e:
        refused = "--confirm-gpu" in str(e)
    check("2. a real provider without --confirm-gpu is refused before any sit", refused and calls == [], str(calls))

    # 3-5. keep path: baseline fails t0,t1; candidate fixes both; final confirm
    t0, t1 = train_ids[0], train_ids[1]
    seen_inputs = []

    def proposer(agent_name, prompt, failures):
        seen_inputs.append(copy.deepcopy(failures))
        return {"prompt": prompt + "\nEDIT", "targets": [f["id"] for f in failures], "why": "test"}

    def script(label, exam, agent):
        fixed = "EDIT" in agent["system_prompt"]
        v = {} if fixed else {t0: (False, True), t1: (False, True)}
        v[held_ids[0]] = (True, True)
        return v
    sit, calls = make_sit(script)
    with tempfile.TemporaryDirectory() as td:
        final = il.run_loop(AGENT, proposer=proposer, provider="ollama", model="m", iterations=3, loads=3,
                            run_dir=Path(td), sit_fn=sit, confirm_gpu=True)
        kept_prompt = (Path(td) / "final-prompt.md").read_text() if (Path(td) / "final-prompt.md").exists() else ""
    flat = json.dumps(seen_inputs)
    check("3a. the proposer saw exactly the two train failures", seen_inputs and sorted(f["id"] for f in seen_inputs[0]) == sorted([t0, t1]),
          str(seen_inputs[:1]))
    check("3b. no `expected` key and no held-out id ever reached the proposer", "expected" not in flat and "SECRET-KEY" not in flat
          and not any(h in flat for h in held_ids), flat[:200])
    iter_calls = [c for c in calls if c["label"].startswith("train-")]
    full_calls = [c for c in calls if c["label"].startswith("full-")]
    check("4a. every iteration sat the TRAIN split only", iter_calls and all(c["splits"] == ["train"] for c in iter_calls), str(iter_calls))
    check("4b. exactly two final sits carry held-out (original prompt, then the kept prompt)",
          [c["label"] for c in full_calls] == ["full-original", "full-final"] and all("heldout" in c["splits"] for c in full_calls)
          and "EDIT" not in full_calls[0]["prompt"] and "EDIT" in full_calls[1]["prompt"], str(full_calls))
    check("5a. +2 stable train gain kept; final verdict from --final is confirm", final.get("kept") == 1
          and final.get("verdict") == "confirm" and final.get("split") == "heldout" and "EDIT" in kept_prompt, str(final))

    # 3c. the helper alone: a record + result that DO carry held-out failures and `expected` -> filtered out
    snap = {"cases": [{"id": "tr", "split": "train", "passed": False, "stable": True},
                      {"id": "ho", "split": "heldout", "passed": False, "stable": True},
                      {"id": "ok", "split": "train", "passed": True, "stable": True}]}
    res = {"cases": [{"id": "tr", "split": "train", "input": "i", "expected": {"k": "KEY"}, "got": {}, "failed_checks": []},
                     {"id": "ho", "split": "heldout", "input": "i", "expected": {"k": "KEY"}, "got": {}, "failed_checks": []},
                     {"id": "ok", "split": "train", "input": "i", "expected": {"k": "KEY"}, "got": {}, "failed_checks": []}]}
    pi = il.proposer_input(snap, res)
    check("3c. proposer_input alone drops held-out failures, passing cases and `expected`",
          [x["id"] for x in pi] == ["tr"] and "expected" not in json.dumps(pi) and "KEY" not in json.dumps(pi), str(pi))

    # 6. refuse-run: the edit fixes train but breaks a stable held-out case
    def script_bad(label, exam, agent):
        fixed = "EDIT" in agent["system_prompt"]
        v = {} if fixed else {t0: (False, True), t1: (False, True)}
        v[held_ids[0]] = (False, True) if fixed else (True, True)
        return v
    sit, calls = make_sit(script_bad)
    with tempfile.TemporaryDirectory() as td:
        final = il.run_loop(AGENT, proposer=proposer, provider="ollama", model="m", iterations=3, loads=3,
                            run_dir=Path(td), sit_fn=sit, confirm_gpu=True)
    check("6a. a held-out case broken by the kept edit -> refuse-run", final.get("verdict") == "refuse-run"
          and final.get("downs") == [held_ids[0]], str(final))
    # the proposer never sees the held-out failure that caused it
    check("6b. ... and that held-out failure never reached the proposer", held_ids[0] not in json.dumps(seen_inputs))

    print(f"\n{len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
