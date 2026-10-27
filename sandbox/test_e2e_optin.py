#!/usr/bin/env python3
"""The gate is inference-free unless SANDBOX_E2E=1.

Why: `test_shadow_gmail.py::test_end_to_end_through_real_model` made ONE real
email-triage call whenever Ollama answered on localhost:11434 and skipped silently
otherwise, so `./.cline/test.sh` meant different things on different machines and a
"CPU-only" job running the gate loaded the champion into the GPU. The fix makes the
call opt-in: it runs only with SANDBOX_E2E exactly "1".

    python3 sandbox/test_e2e_optin.py                  # checks sandbox/test_shadow_gmail.py
    python3 sandbox/test_e2e_optin.py <path/to/copy>   # seen-red run against an old copy

How, without inference. `_ollama_up` hard-codes localhost:11434 (a live server on this
Mac), so a subprocess of the OLD file would make a real call. Instead, BEFORE the target
module is imported, this process (a) replaces `runner.live_run_and_log` with a recorder
that raises (the e2e test imports it from `runner` at call time; a copy that bound the
name at import is also patched on the module) and (b) refuses every outbound
`socket.connect` / `connect_ex` and every `subprocess.Popen` / `os.system` for the rest
of the run — import included. Per drive, `mod._ollama_up` is a recorder too. The env var
is cleared IN-PROCESS, so `SANDBOX_E2E=1 ./.cline/test.sh` cannot leak into this file.

What it checks. (1) Shape: the FIRST statement of the e2e function (after its docstring)
is exactly `if os.environ.get("SANDBOX_E2E") != "1":` ending in `return` — that pins the
exact-"1" contract for every value, which a sampled list cannot. (2) Effect (gotcha 1):
with the var unset or any of a list of near-miss values, the probe and the call are
reached 0 times, nothing connects, and the exact SKIP line prints; with "1" and the probe
down the old "not reachable" line prints; with "1" and the probe up the call is reached
once (the opt-in really opens). (3) No thread outlives a drive.

Limit, stated: this pins the gate, it is not a sandbox. Code written to evade it (a C
extension, ctypes, a fork) is out of scope; the backstops above catch the plausible paths.

The copy under test must sit in sandbox/ (it reads shadow_gmail.py from its own dir at
import time); name it so it does not match test_*.py or the gate will sweep it.
"""
import ast
import contextlib
import importlib.util
import io
import os
import pathlib
import socket
import subprocess
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
import runner  # noqa: E402

NEW_SKIP = "  [SKIP] end-to-end: set SANDBOX_E2E=1 to run the one real inference"
OLD_SKIP = "  [SKIP] end-to-end: Ollama not reachable at localhost:11434"
LABEL_LINE = "e2e: produced a valid triage label"
GATE_TEST = "os.environ.get('SANDBOX_E2E') != '1'"
NEAR_MISSES = ("0", "true", "", "yes", " 1", "1 ", "2", "01", "10", "on", "TRUE", "y")

FAILED = []
CALLS, ESCAPES = [], []  # live_run_and_log reached; connect/subprocess refused


def check(label, ok, extra=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {extra}" if not ok and extra else ""))
    if not ok:
        FAILED.append(label)


class _CallReached(Exception):
    """Raised by the live_run_and_log recorder: the model call was reached."""


class _Blocked(Exception):
    """Raised by a backstop: something tried to connect or spawn past the recorders."""


def _fake_call(*a, **k):
    CALLS.append(1)
    raise _CallReached


def _refuse(kind):
    def refuse(*a, **k):
        ESCAPES.append(kind)
        raise _Blocked(kind)
    return refuse


def _install_backstops():
    """Process-wide and never restored: the process exits when main() returns."""
    os.environ.pop("SANDBOX_E2E", None)
    runner.live_run_and_log = _fake_call
    socket.socket.connect = _refuse("socket.connect")
    socket.socket.connect_ex = _refuse("socket.connect_ex")
    subprocess.Popen = _refuse("subprocess.Popen")
    os.system = _refuse("os.system")


def _load(path):
    spec = importlib.util.spec_from_file_location("_e2e_target", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _gate_shape_ok(path):
    tree = ast.parse(pathlib.Path(path).read_text())
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
               and n.name == "test_end_to_end_through_real_model"), None)
    if fn is None:
        return False, "function not found"
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]
    first = body[0] if body else None
    if not isinstance(first, ast.If):
        return False, f"first statement is {type(first).__name__}"
    test = ast.unparse(first.test)
    ends_in_return = bool(first.body) and isinstance(first.body[-1], ast.Return)
    return (test == GATE_TEST and ends_in_return and not first.orelse,
            f"test={test!r} ends_in_return={ends_in_return} orelse={bool(first.orelse)}")


def _drive(mod, env_value, ollama_up):
    """Call the e2e test with SANDBOX_E2E=env_value (None = unset) and the probe
    stubbed to return `ollama_up`. Returns (stdout, probes, calls, escapes, new_threads)."""
    probes = []

    def fake_up():
        probes.append(1)
        return ollama_up

    del CALLS[:], ESCAPES[:]
    saved_up = mod._ollama_up
    had_mod_call = hasattr(mod, "live_run_and_log")
    if had_mod_call:
        mod.live_run_and_log = _fake_call
    os.environ.pop("SANDBOX_E2E", None)
    if env_value is not None:
        os.environ["SANDBOX_E2E"] = env_value
    mod._ollama_up = fake_up
    threads_before = set(threading.enumerate())
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            try:
                mod.test_end_to_end_through_real_model()
            except _CallReached:
                print("  <recorder: live_run_and_log reached>")
            except Exception as e:  # noqa: BLE001 — a blocked connect may be wrapped
                print(f"  <raised past the recorders: {type(e).__name__}: {e}>")
    finally:
        mod._ollama_up = saved_up
        os.environ.pop("SANDBOX_E2E", None)
    new_threads = [t for t in threading.enumerate() if t not in threads_before]
    return buf.getvalue(), len(probes), len(CALLS), list(ESCAPES), new_threads


def main():
    target = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                          else ROOT / "sandbox" / "test_shadow_gmail.py").resolve()
    print(f"target: {target}")
    _install_backstops()

    ok, detail = _gate_shape_ok(target)
    check("shape: first statement is the exact SANDBOX_E2E != '1' gate ending in return",
          ok, detail)

    try:
        mod = _load(target)
    except Exception as e:  # noqa: BLE001
        check("import: module loads with the backstops installed", False, f"{type(e).__name__}: {e}")
        return 1
    check("import: nothing connected or spawned while loading the module",
          not ESCAPES, repr(ESCAPES))
    check("import: module did not set SANDBOX_E2E (a drive's pop would hide it)",
          os.environ.get("SANDBOX_E2E") is None, repr(os.environ.get("SANDBOX_E2E")))

    # (i) var unset, Ollama "up": the env gate alone must block the probe AND the call.
    out, probes, calls, esc, thr = _drive(mod, None, ollama_up=True)
    print("\n[unset, ollama up]\n" + out.rstrip())
    check("unset: prints the exact new SKIP line", NEW_SKIP in out.splitlines(), repr(out))
    check("unset: no triage label line", LABEL_LINE not in out)
    check("unset: Ollama probe called 0 times", probes == 0, f"called {probes}")
    check("unset: live_run_and_log called 0 times", calls == 0, f"called {calls}")
    check("unset: nothing connected or spawned, no thread left behind",
          not esc and not thr, f"escapes={esc} threads={thr}")

    # Exact "1" only: near-miss values still skip without touching anything.
    for v in NEAR_MISSES:
        out, probes, calls, esc, thr = _drive(mod, v, ollama_up=True)
        check(f"SANDBOX_E2E={v!r}: skips with no probe, no call, no escape",
              NEW_SKIP in out.splitlines() and probes == 0 and calls == 0 and not esc and not thr,
              f"probes={probes} calls={calls} escapes={esc} threads={thr} out={out!r}")

    # Var set, Ollama down: falls through to the OLD skip line, still no call.
    out, probes, calls, esc, thr = _drive(mod, "1", ollama_up=False)
    check("SANDBOX_E2E=1, ollama down: old 'not reachable' skip line",
          OLD_SKIP in out.splitlines() and NEW_SKIP not in out, repr(out))
    check("SANDBOX_E2E=1, ollama down: probed once, no call, no escape",
          probes == 1 and calls == 0 and not esc, f"probes={probes} calls={calls} escapes={esc}")

    # Var set, Ollama up: the opt-in really opens the door (reaches the recorder).
    out, probes, calls, esc, thr = _drive(mod, "1", ollama_up=True)
    check("SANDBOX_E2E=1, ollama up: reaches live_run_and_log exactly once, no escape",
          calls == 1 and NEW_SKIP not in out and not esc,
          f"calls={calls} escapes={esc} out={out!r}")

    print(f"\n{'FAILED: ' + ', '.join(FAILED) if FAILED else 'all green'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
