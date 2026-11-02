#!/usr/bin/env python3
"""The improvement loop's driver: propose a prompt edit from TRAIN failures, sit it, keep it only through loop_gate.

    python3 scripts/improve_loop.py <agent> --proposer <module:function> [--iterations 5] [--loads 3]
                                    [--provider P --model M] [--confirm-gpu] [--run-dir DIR]

Design: docs/research/improvement-loop-design-2026-10-31.md (the gate is TRAIN; held-out is read ONCE at the
end via loop_gate --final, never to select). What this script guarantees, each pinned by sandbox/test_improve_loop.py:
  * it never writes agents/<agent>/prompt.md, evals/<agent>/snapshot.json or a top-level results/ file — every
    sit runs with runner.RESULTS_DIR pointed at the run dir, candidate prompts live in memory and in the run dir;
  * the proposer sees TRAIN failures only: {id, input, failed_checks, got} — never a held-out id, never `expected`
    (gotcha 18 shape: a proposer that reads the key would "improve" by copying it);
  * every iteration sits the TRAIN split only (rule-A, `loads` loads); keep/refuse is loop_gate.train_gate over two
    loop-stamped records; the final step sits the FULL exam twice (original prompt, final prompt) and asks
    loop_gate --final once — `refuse-run` discards everything;
  * a real provider is GPU (or spend): refused without --confirm-gpu; the stub provider runs without it;
  * budget: --iterations, and a stop after 2 refusals in a row; every attempt logged to <run-dir>/loop_log.jsonl.
The PROPOSER is not chosen here (decision D17): it is a `module:function` taking (agent_name, prompt, failures)
and returning {"prompt": new_prompt, "targets": [train ids], "why": str}. `stub:append_line` exists for dry runs.
"""
from __future__ import annotations
import argparse, contextlib, importlib, io, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
sys.path.insert(0, str(ROOT / "scripts"))
import runner  # noqa: E402
import loop_gate  # noqa: E402

MAX_REFUSALS_IN_A_ROW = 2


def proposer_input(snapshot: dict, result: dict) -> list[dict]:
    """TRAIN failures only, from the candidate-or-baseline TRAIN sit. `result` is the aggregate run_exam record;
    `expected` and every held-out case are dropped here, before the proposer can see them."""
    failing = {c["id"] for c in snapshot["cases"] if c["split"] == "train" and not (c["passed"] and c.get("stable"))}
    out = []
    for c in result["cases"]:
        if c.get("split") != "train" or c["id"] not in failing:
            continue
        out.append({"id": c["id"], "input": c.get("input"), "failed_checks": c.get("failed_checks", []),
                    "got": c.get("got")})
    return out


def _train_only(exam: dict) -> dict:
    return {**exam, "cases": [c for c in exam["cases"] if c.get("split") == "train"]}


def default_sit(agent: dict, exam: dict, provider: str, model: str, loads: int, run_dir: Path, label: str) -> dict:
    """One rule-A sit through the runner, results confined to run_dir/label. Returns a loop-stamped snapshot record
    with the run_exam aggregate attached under `_result` (popped before it is written)."""
    d = run_dir / label
    d.mkdir(parents=True, exist_ok=True)
    saved = runner.RESULTS_DIR
    runner.RESULTS_DIR = d
    try:
        aggregate, runtime = runner.take_snapshot_loads(agent, exam, provider, model, loads)
    finally:
        runner.RESULTS_DIR = saved
    snap = runner.snapshot_payload(agent, exam, provider, model, aggregate, loads=loads, runtime=runtime)
    snap["loop_stamp"] = loop_gate.compute_loop_stamp(agent["name"])
    (d / "record.json").write_text(json.dumps(snap, indent=2))
    # inputs for the proposer (the snapshot payload carries no case text)
    exam_by_id = {c["id"]: c for c in exam["cases"]}
    for c in aggregate["cases"]:
        c["input"] = exam_by_id.get(c["id"], {}).get("input")
    snap["_result"] = aggregate
    return snap


def load_proposer(spec: str):
    if spec == "stub:append_line":
        return lambda agent_name, prompt, failures: {"prompt": prompt + "\n- Read the question twice before answering.",
                                                     "targets": [f["id"] for f in failures][:2], "why": "stub dry run"}
    mod, _, fn = spec.partition(":")
    if not mod or not fn:
        raise SystemExit(f"error: --proposer must be module:function, got {spec!r}")
    return getattr(importlib.import_module(mod), fn)


def run_loop(agent_name: str, *, proposer, provider: str, model: str, iterations: int, loads: int,
             run_dir: Path, sit_fn=None, confirm_gpu: bool = False) -> dict:
    if provider != "stub" and not confirm_gpu:
        raise SystemExit(f"error: provider {provider!r} runs real inference ({iterations} iterations x {loads} loads on "
                         f"the train split + 2 full sits); pass --confirm-gpu only on the operator's word")
    sit = sit_fn or default_sit
    agent = runner.load_agent(agent_name)
    exam = runner.load_exam(agent_name)
    train_exam = _train_only(exam)
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_dir / "loop_log.jsonl"

    def write_log(entry):
        with log.open("a") as fh:
            fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}) + "\n")

    original_prompt = agent["system_prompt"]
    best_prompt = original_prompt
    best = sit(agent, train_exam, provider, model, loads, run_dir, "train-baseline")
    best_result = best.pop("_result")
    write_log({"step": "baseline", "train_score": best.get("train_score")})
    refusals = kept = 0
    for i in range(1, iterations + 1):
        failures = proposer_input(best, best_result)
        if not failures:
            write_log({"step": i, "stop": "no train failures left"})
            break
        prop = proposer(agent_name, best_prompt, failures)
        cand_agent = {**agent, "system_prompt": prop["prompt"]}
        (run_dir / f"prompt-{i}.md").write_text(prop["prompt"])
        cand = sit(cand_agent, train_exam, provider, model, loads, run_dir, f"train-cand-{i}")
        cand_result = cand.pop("_result")
        try:
            verdict = loop_gate.gate(best, cand)
        except loop_gate.InputRefused as e:
            verdict = {"verdict": "input-refused", "reason": str(e)}
        write_log({"step": i, "targets": prop.get("targets"), "why": prop.get("why"), **verdict})
        if verdict["verdict"] == "keep":
            best, best_result, best_prompt = cand, cand_result, prop["prompt"]
            kept += 1
            refusals = 0
        else:
            refusals += 1
            if refusals >= MAX_REFUSALS_IN_A_ROW:
                write_log({"step": i, "stop": f"{MAX_REFUSALS_IN_A_ROW} refusals in a row"})
                break
    final = {"verdict": "nothing kept", "kept": kept}
    if kept:
        base_full = sit(agent, exam, provider, model, loads, run_dir, "full-original")
        base_full.pop("_result")
        cand_full = sit({**agent, "system_prompt": best_prompt}, exam, provider, model, loads, run_dir, "full-final")
        cand_full.pop("_result")
        final = {**loop_gate.gate(base_full, cand_full, final=True), "kept": kept}
        (run_dir / "final-prompt.md").write_text(best_prompt)
    write_log({"step": "final", **final})
    return final


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="improve_loop.py")
    ap.add_argument("agent")
    ap.add_argument("--proposer", required=True)
    ap.add_argument("--iterations", type=int, default=5)
    ap.add_argument("--loads", type=int, default=3)
    ap.add_argument("--provider")
    ap.add_argument("--model")
    ap.add_argument("--confirm-gpu", action="store_true")
    ap.add_argument("--run-dir")
    a = ap.parse_args(argv)
    agent = runner.load_agent(a.agent)
    provider, model = a.provider or agent["provider"], a.model or agent["model"]
    run_dir = Path(a.run_dir) if a.run_dir else ROOT / "results" / f"loop-{a.agent}-{time.strftime('%Y%m%dT%H%M%S')}"
    final = run_loop(a.agent, proposer=load_proposer(a.proposer), provider=provider, model=model,
                     iterations=a.iterations, loads=a.loads, run_dir=run_dir, confirm_gpu=a.confirm_gpu)
    print(json.dumps(final))
    print(f"run dir: {run_dir}  (nothing outside it was written; prompt.md unchanged — adopting a kept prompt is a PR)")
    return 0 if final.get("verdict") == "confirm" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
