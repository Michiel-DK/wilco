#!/usr/bin/env python3
"""Grader hash in snapshots: recorded, never a refusal, and named when `check` drifts (2026-10-31).

    python3 sandbox/test_grader_hash.py

No model, no server (stub provider; network patched to raise). Pins:
  1. ONE list: scripts/loop_gate.py's GRADER_FILES IS sandbox/grader_files.GRADER_FILES (same object)
  2. snapshot_payload without grader_files keeps its exact old key set; with it, adds exactly `grader_files`
  3. snapshot_files covers GRADER_FILES + prompt.md, "absent" for missing files, and changes when any edits
  4. snapshot_preflight NEVER refuses on grader_files: a snapshot whose every hash differs from the tree
     passes preflight identically to one without the key
  5. grader_attribution: unrecorded -> says so; all equal -> "unchanged ... model, runtime or server";
     one edited file -> names exactly that file
  6. cmd_check wiring: on a drifting stub run the attribution line is printed; on a clean one it is not
Each pin seen RED under a hand mutation (PR body).
"""
from __future__ import annotations
import contextlib, hashlib, importlib.util, io, json, sys, tempfile, types, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
import grader_files  # noqa: E402
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
    spec = importlib.util.spec_from_file_location("loop_gate", ROOT / "scripts" / "loop_gate.py")
    lg = importlib.util.module_from_spec(spec); spec.loader.exec_module(lg)
    check("1. loop_gate.GRADER_FILES is the shared list (the same object, not a copy)",
          lg.GRADER_FILES is grader_files.GRADER_FILES and "sandbox/retry.py" in lg.GRADER_FILES)
    src = (ROOT / "scripts" / "loop_gate.py").read_text()
    check("1b. loop_gate.py does not re-type the list", "GRADER_FILES = (" not in src)

    agent, exam = runner.load_agent("email-triage"), runner.load_exam("email-triage")
    with contextlib.redirect_stdout(io.StringIO()):
        res = runner.run_exam(agent, exam, "stub", agent["model"])
    p0 = runner.snapshot_payload(agent, exam, "stub", "m", res)
    gf = grader_files.snapshot_files("email-triage")
    p1 = runner.snapshot_payload(agent, exam, "stub", "m", res, grader_files=gf)
    check("2a. without grader_files: no new key", "grader_files" not in p0)
    check("2b. with it: exactly one new key, the hashes", set(p1) - set(p0) == {"grader_files"} and p1["grader_files"] == gf)

    want = {t.format(agent="email-triage") for t in grader_files.GRADER_FILES} | {"agents/email-triage/prompt.md"}
    check("3a. snapshot_files covers GRADER_FILES + prompt.md", set(gf) == want, str(sorted(set(gf) ^ want)))
    check("3b. a missing file is recorded 'absent' (email-triage has no tools_mock.py)",
          gf["evals/email-triage/tools_mock.py"] == "absent" and len(gf["evals/email-triage/cases.json"]) == 64)
    with tempfile.TemporaryDirectory() as td:
        for rel in want:
            if (ROOT / rel).is_file():
                (Path(td) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(td) / rel).write_bytes((ROOT / rel).read_bytes())
        base = grader_files.snapshot_files("email-triage", Path(td))
        moved = []
        for rel in sorted(want):
            f = Path(td) / rel
            old = f.read_bytes() if f.exists() else None
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes((old or b"") + b"\n#x\n")
            if grader_files.changed(base, grader_files.snapshot_files("email-triage", Path(td))) != [rel]:
                moved.append(rel)
            if old is None:
                f.unlink()
            else:
                f.write_bytes(old)
    check("3c. editing (or creating) each file changes exactly that one entry", moved == [], str(moved))

    snap = json.loads((ROOT / "evals" / "email-triage" / "snapshot.json").read_text())
    ver = lambda: snap["runtime"]["version"]  # noqa: E731
    srv = lambda: {k: snap["runtime"][k] for k in runner.OLLAMA_STAMP_FIELDS}  # noqa: E731
    c_plain = runner.snapshot_preflight(snap, exam, version_fn=ver, server_settings_fn=srv)
    bogus = {**snap, "grader_files": {k: "0" * 64 for k in gf}}
    c_bogus = runner.snapshot_preflight(bogus, exam, version_fn=ver, server_settings_fn=srv)
    check("4. preflight never refuses on grader_files (every hash wrong -> same answer as no key)",
          c_bogus == c_plain and c_plain is None, f"{c_plain!r} vs {c_bogus!r}")

    unrec = {k: v for k, v in snap.items() if k != "grader_files"}   # independent of what the committed file carries
    check("5a. unrecorded -> says so", "not recorded" in runner.grader_attribution(unrec, "email-triage"))
    rec = {**snap, "grader_files": dict(gf)}
    a_same = runner.grader_attribution(rec, "email-triage", current=dict(gf))
    check("5b. all equal -> 'unchanged' and names model/runtime/server", "unchanged" in a_same and "runtime" in a_same, a_same)
    cur = {**gf, "sandbox/retry.py": "f" * 64}
    a_one = runner.grader_attribution(rec, "email-triage", current=cur)
    check("5c. one edited file -> names exactly it", a_one.endswith(": sandbox/retry.py"), a_one)
    check("5d. a file the snapshot never recorded (list grew) is named as changed",
          grader_files.changed({"a": "1"}, {"a": "1", "b": "2"}) == ["b"]
          and grader_files.changed({"a": "1", "b": "2"}, {"a": "1"}) == ["b"])

    # 5e. the PRODUCTION path (current=None hashes the live tree): edit one file in a temp copy -> named
    import shutil
    with tempfile.TemporaryDirectory() as td:
        for rel in want:
            if (ROOT / rel).is_file():
                (Path(td) / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / rel, Path(td) / rel)
        saved_root = grader_files.ROOT
        grader_files.ROOT = Path(td)
        try:
            rec_t = {**snap, "grader_files": grader_files.snapshot_files("email-triage")}
            same_line = runner.grader_attribution(rec_t, "email-triage")
            (Path(td) / "evals/email-triage/cases.json").write_bytes(
                (Path(td) / "evals/email-triage/cases.json").read_bytes() + b" ")
            edited_line = runner.grader_attribution(rec_t, "email-triage")
        finally:
            grader_files.ROOT = saved_root
    check("5e. live-tree attribution (no `current`): unchanged, then names the edited cases.json",
          "all unchanged" in same_line and edited_line.endswith(": evals/email-triage/cases.json"), f"{same_line} | {edited_line}")

    # 6c/6d. the two SNAPSHOT WRITERS put grader_files in what they write — run against a temp ROOT so the
    # committed evals/*/snapshot.json is never touched; take_snapshot_loads is faked (no run)
    committed_before = hashlib.sha256((ROOT / "evals/email-triage/snapshot.json").read_bytes()).hexdigest()
    fake_agg = {**res, "cases": [dict(c, stable=True) for c in res["cases"]]}
    with tempfile.TemporaryDirectory() as td:
        for sub in ("agents/email-triage", "evals/email-triage"):
            shutil.copytree(ROOT / sub, Path(td) / sub, ignore=shutil.ignore_patterns("snapshot*.json", "__pycache__"))
        saved = (runner.ROOT, runner.RESULTS_DIR, runner.take_snapshot_loads, runner._all_agents, grader_files.ROOT)
        runner.ROOT, runner.RESULTS_DIR = Path(td), Path(td) / "results"
        grader_files.ROOT = Path(td)
        runner.take_snapshot_loads = lambda *a, **k: (json.loads(json.dumps(fake_agg)), {"name": "stub", "version": None})
        runner._all_agents = lambda: ["email-triage"]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                runner.cmd_run(types.SimpleNamespace(agent="email-triage", provider="stub", model=None, snapshot=True,
                                                     loads=3, timeout=None, dedupe_tools=False, assembly="full",
                                                     scoped_rule="off", split="all"))
            w1 = json.loads((Path(td) / "evals/email-triage/snapshot.json").read_text())
            (Path(td) / "evals/email-triage/snapshot.json").unlink()
            with contextlib.redirect_stdout(io.StringIO()):
                runner.cmd_run_all(types.SimpleNamespace(snapshot=True, loads=3))
            w2 = json.loads((Path(td) / "evals/email-triage/snapshot.json").read_text())
        finally:
            runner.ROOT, runner.RESULTS_DIR, runner.take_snapshot_loads, runner._all_agents, grader_files.ROOT = saved
    check("6c. `run --snapshot` writes grader_files into the snapshot", isinstance(w1.get("grader_files"), dict)
          and "evals/email-triage/cases.json" in w1["grader_files"], str(sorted(w1)))
    check("6d. `run-all --snapshot` writes grader_files into the snapshot", isinstance(w2.get("grader_files"), dict)
          and "evals/email-triage/cases.json" in w2["grader_files"], str(sorted(w2)))
    committed_after = hashlib.sha256((ROOT / "evals/email-triage/snapshot.json").read_bytes()).hexdigest()
    check("6e. the committed snapshot was never touched (byte-identical before/after the writer runs)",
          committed_before == committed_after)

    # 6. cmd_check wiring on the stub: drift vs no drift
    stub_snap = runner.snapshot_payload(agent, exam, "stub", agent["model"],
                                        {**res, "cases": [dict(c, stable=True) for c in res["cases"]]},
                                        loads=3, runtime={"name": "stub", "version": None}, grader_files=dict(gf))
    flipped = json.loads(json.dumps(stub_snap))
    flipped["cases"][0]["passed"] = not flipped["cases"][0]["passed"]
    out = {}
    saved = (runner._load_snapshot, runner.ollama_unload)
    runner.ollama_unload = lambda m: None
    try:
        for label, sd in (("clean", stub_snap), ("drift", flipped)):
            runner._load_snapshot = lambda name, sd=sd: sd
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = runner.cmd_check(types.SimpleNamespace(agent="email-triage", tolerance=1.0, dedupe_tools=False))
            out[label] = (rc, buf.getvalue())
    finally:
        runner._load_snapshot, runner.ollama_unload = saved
    check("6a. clean stub check: rc 0, no attribution line", out["clean"][0] == 0 and "grader files" not in out["clean"][1],
          out["clean"][1][-300:])
    check("6b. drifting stub check: rc 1 and the attribution line ('all unchanged') is printed",
          out["drift"][0] == 1 and "grader files: all unchanged" in out["drift"][1], out["drift"][1][-300:])
    # 6f. check-all wiring: one drifting agent (stub) -> its attribution line printed
    import shutil
    with tempfile.TemporaryDirectory() as td:
        for sub in ("agents/email-triage", "evals/email-triage"):
            shutil.copytree(ROOT / sub, Path(td) / sub, ignore=shutil.ignore_patterns("snapshot*.json", "__pycache__"))
        (Path(td) / "evals/email-triage/snapshot.json").write_text(json.dumps(flipped))
        saved = (runner.ROOT, runner.RESULTS_DIR, runner.ollama_unload, runner._all_agents)
        runner.ROOT, runner.RESULTS_DIR = Path(td), Path(td) / "results"
        runner.ollama_unload = lambda m: None
        runner._all_agents = lambda: ["email-triage"]
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc_all = runner.cmd_check_all(types.SimpleNamespace(tolerance=1.0))
        finally:
            runner.ROOT, runner.RESULTS_DIR, runner.ollama_unload, runner._all_agents = saved
    check("6f. drifting `check-all`: rc 1 and the attribution line printed", rc_all == 1
          and "grader files: all unchanged" in buf.getvalue(), buf.getvalue()[-300:])

    print(f"\n{len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
