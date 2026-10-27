"""Q6(a) — "served by the local Ollama" is decided by base_url, not by the literal "ollama".

Why: PROVIDERS["systemone"] is served by the SAME Ollama as PROVIDERS["ollama"] (identical
base_url). Four sites gated Ollama behaviour on `provider == "ollama"` — take_snapshot_loads,
snapshot_preflight, cmd_check unload, cmd_check_all unload — so `run --snapshot --provider
systemone` took 3 samples with NO reload between them, stamped runtime.version None, and a
systemone snapshot was never version/KV-checked nor reloaded before `check`.

Everything is offline: every Ollama call is monkeypatched, no inference, no network.
check()-style (CLAUDE.md gotcha 17): run directly or via ./.cline/test.sh.

WITNESS vs CONTROL: checks tagged [W] are RED on the unfixed runner.py (the defect);
checks tagged [C] are green on both sides (negative controls / regression pins).
"""
import argparse
import contextlib
import io
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sandbox"))
import runner  # noqa: E402

FAILED = []


def check(label, ok, extra=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {extra}" if not ok and extra else ""))
    if not ok:
        FAILED.append(label)


@contextlib.contextmanager
def patched(mod, **attrs):
    saved = {k: getattr(mod, k) for k in attrs}
    try:
        for k, v in attrs.items():
            setattr(mod, k, v)
        yield
    finally:
        for k, v in saved.items():
            setattr(mod, k, v)


def _bomb(*a, **k):
    raise AssertionError("called when it must not be")


UNSET = {"kv_cache_type": "unset", "flash_attention": "unset"}
EXAM = {"cases": [{"id": "a"}]}
MLX = {"version": "0.1", "model_sha": "m", "adapter_sha": None}


def _fake_result(provider, model):
    cases = [{"id": "a", "split": "heldout", "passed": True, "expected": {}, "got": {}}]
    return {"agent": "fx", "provider": provider, "model": model, "mode": "labels",
            "train": {"passed": 0, "total": 0, "score": None},
            "heldout": {"passed": 1, "total": 1, "score": 1.0}, "cases": cases}


def _take(provider, loads=3):
    """Drive the REAL take_snapshot_loads; return (runtime, unload_models, exit)."""
    unloads = []
    over = dict(run_exam=lambda agent, exam, prov, model, **kw: _fake_result(prov, model),
                ollama_unload=lambda m: unloads.append(m),
                ollama_version=lambda: "0.40.2",
                save_result=lambda *a, **k: pathlib.Path("/dev/null"),
                mlx_runtime=lambda: {"name": "mlx", **MLX})
    rt, exited = None, None
    with patched(runner, **over), contextlib.redirect_stdout(io.StringIO()):
        try:
            _agg, rt = runner.take_snapshot_loads(
                {"name": "fx"}, {"cases": []}, provider, "m", loads,
                server_settings_fn=lambda: dict(UNSET))
        except SystemExit as e:
            exited = e
    return rt, unloads, exited


def _snap(provider, version="0.40.2", **runtime_extra):
    rt = {"name": provider, "version": version, **runtime_extra}
    return {"provider": provider, "model": "m", "heldout_score": 1.0, "train_score": None,
            "runtime": rt, "loads": 3,
            "cases": [{"id": "a", "split": "heldout", "passed": True, "expected": {},
                       "got": {}, "stable": True}]}


def _pf(snap, version="0.40.2", reader=None):
    return runner.snapshot_preflight(snap, EXAM, version_fn=lambda: version,
                                     server_settings_fn=reader or (lambda: dict(UNSET)))


# ---------------------------------------------------------------- the helper
print("\n(1) the predicate itself")
helper = getattr(runner, "_served_by_local_ollama", None)
check("[W] runner._served_by_local_ollama exists", callable(helper))
if callable(helper):
    check("[W] True for 'systemone' (same base_url as ollama)", helper("systemone") is True)
    check("[C] True for 'ollama'", helper("ollama") is True)
    for prov in ("mlx", "stub", "openrouter", "no-such-provider"):
        check(f"[C] False for {prov!r}", helper(prov) is False)

# ---------------------------------------------------------------- take_snapshot_loads
print("\n(2) take_snapshot_loads: unload before EVERY load, version + KV stamp")
rt_o, un_o, ex_o = _take("ollama")
rt_s, un_s, ex_s = _take("systemone")
check("[C] ollama: unloads exactly 3 times (the reference path)", len(un_o) == 3, str(un_o))
check("[W] systemone: unload count is 3 (0 on the unfixed runner)", len(un_s) == 3, str(un_s))
check("[W] systemone unload count equals the ollama count under the same harness",
      len(un_s) == len(un_o), f"{len(un_s)} vs {len(un_o)}")
check("[C] systemone: no SystemExit", ex_s is None, repr(ex_s))
rt_s = rt_s or {}
check("[W] systemone runtime.version == '0.40.2' (None on the unfixed runner)",
      rt_s.get("version") == "0.40.2", repr(rt_s))
check("[W] systemone runtime carries kv_cache_type and flash_attention",
      all(f in rt_s for f in runner.OLLAMA_STAMP_FIELDS), repr(rt_s))
check("[C] runtime name stays the provider name 'systemone'", rt_s.get("name") == "systemone")
check("[C] ollama runtime is version + stamp",
      (rt_o or {}).get("version") == "0.40.2"
      and all(f in (rt_o or {}) for f in runner.OLLAMA_STAMP_FIELDS), repr(rt_o))
for prov in ("openrouter", "stub"):
    rt, un, ex = _take(prov)
    check(f"[C] {prov}: 0 unloads, version None, no stamp fields",
          un == [] and (rt or {}).get("version") is None
          and not any(f in (rt or {}) for f in runner.OLLAMA_STAMP_FIELDS), f"{un} {rt}")
rt, un, ex = _take("mlx")
check("[C] mlx: 0 unloads and the mlx stamp (own branch untouched)",
      un == [] and rt == {"name": "mlx", **MLX}, f"{un} {rt}")

# ---------------------------------------------------------------- snapshot_preflight
print("\n(3) snapshot_preflight treats a systemone snapshot like an ollama one")
c = _pf(_snap("systemone"))
check("[W] systemone snapshot WITHOUT kv_cache_type -> RUNTIME: (None on the unfixed runner)",
      bool(c) and c.startswith("RUNTIME:"), repr(c))
c = _pf(_snap("systemone", version="0.35.0", **UNSET))
check("[W] systemone snapshot whose version differs -> VERSION:",
      bool(c) and c.startswith("VERSION:"), repr(c))
check("[C] systemone snapshot with the full matching stamp -> None",
      _pf(_snap("systemone", **UNSET)) is None)
c = _pf(_snap("systemone", **{**UNSET, "kv_cache_type": "q4_0"}))
check("[W] systemone snapshot, live KV type differs -> KV_CACHE_TYPE:",
      bool(c) and c.startswith("KV_CACHE_TYPE:"), repr(c))
check("[C] ollama snapshot without the stamp -> RUNTIME:",
      (_pf(_snap("ollama")) or "").startswith("RUNTIME:"))
check("[C] hosted (openrouter) snapshot never touches version_fn or the reader",
      runner.snapshot_preflight(_snap("openrouter", None), EXAM, version_fn=_bomb,
                                server_settings_fn=_bomb) is None)

# ---------------------------------------------------------------- cmd_check / cmd_check_all unload
print("\n(4) cmd_check and cmd_check_all unload before the exam run")


def _run_cmd(fn, args, snap, **over):
    unloads = []
    base = dict(load_agent=lambda n: {"name": n}, load_exam=lambda n: EXAM,
                snapshot_preflight=lambda *a, **k: None,
                moves_first_ids=lambda exam, model: set(),
                ollama_unload=lambda m: unloads.append(m),
                run_exam=lambda *a, **k: _fake_result(snap["provider"], snap["model"]),
                compare_to_snapshot=lambda *a, **k: {},
                _print_verdict=lambda *a, **k: True)
    base.update(over)
    with patched(runner, **base), contextlib.redirect_stdout(io.StringIO()):
        rc = fn(args)
    return rc, unloads


for prov in ("ollama", "systemone", "openrouter"):
    want = 0 if prov == "openrouter" else 1
    snap = _snap(prov)
    tag = "[C]" if prov != "systemone" else "[W]"
    rc, un = _run_cmd(runner.cmd_check,
                      argparse.Namespace(agent="fx", dedupe_tools=False, tolerance=0.0),
                      snap, _load_snapshot=lambda n, s=snap: s)
    check(f"{tag} cmd_check: {prov} snapshot -> {want} unload(s)", rc == 0 and len(un) == want, f"rc={rc} {un}")
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        (t / "agents" / "fx").mkdir(parents=True)
        (t / "agents" / "fx" / "agent.yaml").write_text("name: fx\n")
        (t / "evals" / "fx").mkdir(parents=True)
        (t / "evals" / "fx" / "snapshot.json").write_text(json.dumps(snap))
        rc, un = _run_cmd(runner.cmd_check_all, argparse.Namespace(tolerance=0.0), snap, ROOT=t)
    check(f"{tag} cmd_check_all: {prov} snapshot -> {want} unload(s)", rc == 0 and len(un) == want, f"rc={rc} {un}")


def main() -> int:
    print(f"\n{'FAILED: ' + ', '.join(FAILED) if FAILED else 'all green'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
