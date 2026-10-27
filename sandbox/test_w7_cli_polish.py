"""W7 — CLI polish before the public push: one-line errors, `wilco`-branded help, `wilco adopt`, message fixes.

[E] an exception escaping a runner command prints ONE line `<prog> <cmd>: …` and exits 1 (2 for a refusal), never a
    traceback; the scaffold's placeholder model is refused before any request on run / diff / live (the stub may
    still run it, and its result file carries no placeholder); an Ollama that does not answer /api/show is one line
    naming the host and `ollama serve`; WILCO_DEBUG=1 re-raises; SystemExit passes through untouched.
[H] every command's --help: usage `wilco <cmd>` through the shim, `runner.py <cmd>` run directly, at most 40 lines, no
    lane jargon; the research flags are hidden from --help, listed by --help-advanced, and still parse to their value.
[A] `wilco adopt <task> <provider/model>` writes the two fields only (comments kept), refuses a bad label, an unknown
    provider, a provider above the tier, an existing snapshot without --replace; a failed snapshot restores the file;
    `pick` prints the exact adopt line for its winner.
[M] `new`'s next step is `wilco validate`; the tier refusal prints before (instead of) the `exam:` header; `pick` on a
    best of 0 says bar 0/n; `diff` without --models says what to type, exit 2.
[X] end to end through `python3 wilco_cli.py` in a box copy of the checkout that holds no committed agent and whose
    every Ollama host is rewritten to a dead port (127.0.0.1:9): nothing in this file can reach a model.

No inference anywhere: in-process, every local server's base_url (ollama, systemone, mlx) is pointed at 127.0.0.1:9 for
the whole file and the dispatch spies raise before a request; out of process, only the box runs (same rewrite). Seen RED: recorded in the PR body.
"""
import contextlib
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
os.environ.pop("WILCO_PROG", None)
os.environ.pop("WILCO_DEBUG", None)

import yaml  # noqa: E402

import runner  # noqa: E402
import exam_new  # noqa: E402
import exam_adopt  # noqa: E402
import pick  # noqa: E402
import wilco_cli  # noqa: E402

FAILED = []
DEAD = "http://127.0.0.1:9"   # discard port: connection refused, nothing listens


def check(label, ok, extra=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {extra}" if not ok and extra else ""))
    if not ok:
        FAILED.append(label)


def committed_state():
    """sha256 of every committed agent.yaml and snapshot.json: this file must leave all of them as it found them."""
    files = sorted(list((ROOT / "agents").glob("*/agent.yaml")) + list((ROOT / "evals").glob("*/snapshot.json")))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


STATE_BEFORE = committed_state()

# ------------------------------------------------------------------ the in-process safety net (whole file)
# PROVIDERS is one dict shared by router and runner: every adapter, the window preflight and _ollama_native_base_url
# read it at call time, so with these two entries on a dead port no in-process code path can reach a real server.
REAL_HOSTS = {k: runner.PROVIDERS[k]["base_url"] for k in ("ollama", "systemone", "mlx")}   # every local server
for k in REAL_HOSTS:
    runner.PROVIDERS[k]["base_url"] = DEAD + "/v1"


class _Reached(Exception):
    """raised by a dispatch spy: the code got past the point where it must have refused"""


@contextlib.contextmanager
def patched(obj, **attrs):
    saved = {k: getattr(obj, k) for k in attrs}
    try:
        for k, v in attrs.items():
            setattr(obj, k, v)
        yield
    finally:
        for k, v in saved.items():
            setattr(obj, k, v)


def run_main(argv, env=None):
    """runner.main() with sys.argv set, through the real CLI entry. Returns (rc, stdout, stderr, raised)."""
    out, err, raised, rc = io.StringIO(), io.StringIO(), None, None
    saved_argv, saved_env = sys.argv, {k: os.environ.get(k) for k in (env or {})}
    sys.argv = ["runner.py", *argv]
    os.environ.update(env or {})
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = runner.main()
    except SystemExit as e:
        raised, rc = e, e.code
    except BaseException as e:  # noqa: BLE001 — reported by the caller
        raised = e
    finally:
        sys.argv = saved_argv
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return rc, out.getvalue(), err.getvalue(), raised


TMP = pathlib.Path(tempfile.mkdtemp(prefix="test_w7_"))
TASK = "w7-demo"   # not a committed task name
with contextlib.redirect_stdout(io.StringIO()):
    assert exam_new.main([TASK, "--mode", "labels", "--root", str(TMP)]) == 0
PLACEHOLDER = yaml.safe_load((TMP / "agents" / TASK / "agent.yaml").read_text())["model"]
real_root, real_results = runner.ROOT, runner.RESULTS_DIR
runner.ROOT, runner.RESULTS_DIR = TMP, TMP / "results"

try:
    # ------------------------------------------------------------------ [M] the placeholder detector is the scaffold's
    check("[M] the scaffold's model is detected as the placeholder", runner.is_placeholder_model(PLACEHOLDER), repr(PLACEHOLDER))
    check("[M] real ids and empties: gemma4:e4b / google/gemma-4 are models, '' and None are not",
          not runner.is_placeholder_model("gemma4:e4b") and not runner.is_placeholder_model("google/gemma-4")
          and runner.is_placeholder_model("") and runner.is_placeholder_model(None) and runner.is_placeholder_model("  "))

    # ------------------------------------------------------------------ [E] one line, never a traceback
    reached = []

    def spy(*a, **k):
        reached.append(a[:3])
        raise _Reached()

    with patched(runner, adapter_for=spy, run_exam=spy, ollama_num_ctx=spy):
        rc, out, err, exc = run_main(["run", TASK])
        lines = err.strip().splitlines()
        check("[E] run on the placeholder: exit 2, refused before any adapter / request", rc == 2 and exc is None and reached == [],
              f"rc={rc} exc={exc!r} reached={reached}")
        check("[E] ... one stderr line, `runner.py run: agents/<task>/agent.yaml still has the placeholder model`",
              len(lines) == 1 and lines[0].startswith(f"runner.py run: agents/{TASK}/agent.yaml still has the placeholder model"),
              repr(err))
        check("[E] ... naming the next commands: wilco diff --models, wilco adopt, --provider stub",
              all(s in err for s in (f"wilco diff {TASK} --models", "wilco adopt", "--provider stub")), repr(err))
        check("[E] ... and no `exam:` header on stdout (nothing looks like a run starting)", "exam:" not in out, repr(out))

        rc, out, err, exc = run_main(["diff", TASK, "--models", f"ollama/{PLACEHOLDER}"])
        check("[E] diff with a placeholder entry: exit 2, one line, no row run, blaming --models (not agent.yaml)",
              rc == 2 and exc is None and reached == [] and len(err.strip().splitlines()) == 1
              and err.startswith("runner.py diff: --models names a placeholder") and "agent.yaml" not in err,
              f"rc={rc} {err!r} {reached}")
        rc, out, err, exc = run_main(["run", TASK, "--model", "<m>"])
        check("[E] run --model '<m>' (the diff hint copied literally): exit 2, blames --model, not agent.yaml",
              rc == 2 and reached == [] and err.startswith("runner.py run: --model names a placeholder")
              and "agent.yaml" not in err, f"rc={rc} {err!r}")
        rc, out, err, exc = run_main(["run", TASK, "--snapshot"])
        check("[E] run --snapshot on the placeholder: exit 2 before any load (no version/stamp/adapter call)",
              rc == 2 and reached == [] and "still has the placeholder model" in err, f"rc={rc} {err!r} {reached}")
        with patched(runner, _all_agents=lambda: [TASK]):
            rc, out, err, exc = run_main(["run-all"])
        check("[E] run-all with a placeholder agent: exit 2 before the first exam runs", rc == 2 and reached == []
              and out == "" and "still has the placeholder model" in err, f"rc={rc} {out[:80]!r} {err!r}")
        rc, out, err, exc = run_main(["bakeoff", TASK])
        check("[E] bakeoff on the placeholder: exit 2 before any adapter", rc == 2 and reached == []
              and "still has the placeholder model" in err, f"rc={rc} {err!r} {exc!r}")
        rc, out, err, exc = run_main(["bakeoff", TASK, "--model", "<m>"])
        check("[E] bakeoff --model '<m>': blames --model", rc == 2 and reached == [] and "--model names a placeholder" in err,
              f"rc={rc} {err!r}")
        rc, out, err, exc = run_main(["probe", TASK, "-k", "2"])
        check("[E] probe on the placeholder: exit 2 before any sample", rc == 2 and reached == []
              and "still has the placeholder model" in err, f"rc={rc} {err!r} {exc!r}")
        rc, out, err, exc = run_main(["run", TASK, "--provider", "openrouter", "--allow-tier-breach"])
        check("[E] a HOSTED provider with the placeholder (tier breach allowed): refused before any paid request",
              rc == 2 and reached == [] and "still has the placeholder model" in err, f"rc={rc} {err!r}")
        # two candidates, the real one FIRST: nothing may run before the placeholder is refused
        with contextlib.redirect_stdout(io.StringIO()):
            exam_new.main(["a-real", "--mode", "labels", "--root", str(TMP)])
        ar = TMP / "agents" / "a-real" / "agent.yaml"
        ar.write_text(ar.read_text().replace(f'model: "{PLACEHOLDER}"', 'model: "gemma4:e4b"'))
        with patched(runner, _all_agents=lambda: ["a-real", TASK]):
            rc, out, err, exc = run_main(["run-all"])
        check("[E] run-all, a real agent sorted first: the placeholder refuses before the first exam runs",
              rc == 2 and reached == [] and out == "", f"rc={rc} {out[:80]!r} {reached}")
        rc, out, err, exc = run_main(["diff", TASK, "--models", f"ollama/gemma4:e4b,ollama/{PLACEHOLDER}"])
        check("[E] diff, a real entry first: the placeholder entry refuses before row 1 runs", rc == 2 and reached == [],
              f"rc={rc} {err!r} {reached}")
        rc, out, err, exc = run_main(["diff", TASK, "--models", ","])
        check("[E] diff --models ',' (no entries): the name-the-candidates line, exit 2", rc == 2 and "name the candidates" in err,
              f"rc={rc} {err!r}")
        with patched(runner, load_routes=lambda name: []):
            rc, out, err, exc = run_main(["live", TASK, "--model", "<m>", "--input", "x"])
        check("[E] live --model '<m>': blames --model", rc == 2 and reached == [] and err.startswith("runner.py live: --model names"),
              f"rc={rc} {err!r}")
        with patched(runner, load_routes=lambda name: [{"provider": "ollama", "model": PLACEHOLDER},
                                                       {"provider": "stub", "model": "stub"}]):
            rc, out, err, exc = run_main(["live", TASK, "--input", "x"])
        check("[E] live: a placeholder routes TIER 0 is the champion's, so agent.yaml is named", rc == 2 and reached == []
              and err.startswith(f"runner.py live: agents/{TASK}/agent.yaml still has"), f"rc={rc} {err!r}")
        with patched(runner, load_routes=lambda name: []):
            rc, out, err, exc = run_main(["live", TASK, "--provider", "ollama", "--input", "x"])
        check("[E] live --provider ollama (no --model): agent.yaml is named, never a --model the user did not type",
              rc == 2 and reached == [] and err.startswith(f"runner.py live: agents/{TASK}/agent.yaml still has"), f"rc={rc} {err!r}")
        rc, out, err, exc = run_main(["probe", TASK, "--models", "<m>", "-k", "2"])
        check("[E] probe --models '<m>': blames --models", rc == 2 and reached == [] and err.startswith("runner.py probe: --models names"),
              f"rc={rc} {err!r}")
        rc, out, err, exc = run_main(["diff", TASK, "--models", " , "])
        check("[E] diff --models ' , ': the name-the-candidates line", rc == 2 and "name the candidates" in err, f"rc={rc} {err!r}")
        with contextlib.redirect_stdout(io.StringIO()):
            exam_new.main(["a-props", "--mode", "properties", "--root", str(TMP)])
        apy = TMP / "agents" / "a-props" / "agent.yaml"
        apy.write_text(apy.read_text().replace(f'model: "{PLACEHOLDER}"', 'model: "gemma4:e4b"'))
        rc, out, err, exc = run_main(["bakeoff", "a-props", "--strategies", "filter-then-recap", "--filter-agent", TASK])
        check("[E] bakeoff: a placeholder FILTER agent is refused before its adapter", rc == 2
              and f"agents/{TASK}/agent.yaml still has the placeholder model" in err, f"rc={rc} {err!r} {exc!r}")
        rc, out, err, exc = run_main(["bakeoff", "a-props", "--strategies", "x, filter-then-recap", "--filter-agent", TASK])
        check("[E] bakeoff: the filter refusal also fires on a spaced strategy list ('x, filter-then-recap')", rc == 2
              and f"agents/{TASK}/agent.yaml still has the placeholder model" in err, f"rc={rc} {err!r}")
        reached.clear()
        rc, out, err, exc = run_main(["bakeoff", "a-props", "--strategies", "single", "--filter-agent", TASK])
        check("[E] bakeoff WITHOUT filter-then-recap never loads or refuses the filter agent (as before W7)",
              "placeholder" not in err, f"rc={rc} {err!r}")
        reached.clear()
        rc, out, err, exc = run_main(["probe", TASK, "--provider", "stub", "-k", "2"])
        check("[E] probe --provider stub on the scaffold: NOT refused (the stub may run it), reaches the run",
              "placeholder" not in err and reached != [], f"rc={rc} {err[-160:]!r} {reached[:1]}")
        reached.clear()
        rc, out, err, exc = run_main(["probe", TASK, "--provider", "ollama", "-k", "2"])
        check("[E] probe --provider ollama on the scaffold: refused (only the stub is exempt)", rc == 2 and reached == []
              and "still has the placeholder model" in err, f"rc={rc} {err!r}")
        rc, out, err, exc = run_main(["probe", TASK, "--models", f"gemma4:e4b,{PLACEHOLDER}", "-k", "2"])
        check("[E] probe --models real,<placeholder>: refused before the real model's cells run", rc == 2 and reached == [],
              f"rc={rc} {err!r} {reached[:1]}")
        import probe as probe_mod  # noqa: E402,PLC0415
        pn = probe_mod.probe_filename({"agent": TASK, "provider": "stub", "model": PLACEHOLDER, "temperature": 0.0, "k": 2})
        check("[E] a stub probe of the scaffold: no placeholder in the probe file name", pn == f"probe__{TASK}__stub__placeholder-model__t0__k2.json"
              and not any(c in pn for c in "<> "), pn)

    # the one-line handler: multi-line messages, a second copy of runner's classes, Ctrl-C
    def raiser(e):
        def f(*a, **k):
            raise e
        return f

    with patched(runner, load_exam=raiser(ValueError("line one\nline two\n  line three"))):
        rc, out, err, exc = run_main(["run", TASK, "--provider", "stub"])
    check("[E] a multi-line exception message prints as ONE line", rc == 1 and len(err.strip().splitlines()) == 1
          and "line one line two line three" in err, repr(err))
    Refused2 = type("Refused", (Exception,), {})               # what `import runner` makes when runner.py is __main__
    Placeholder2 = type("PlaceholderModel", (Refused2,), {})
    with patched(runner, load_exam=raiser(Placeholder2("from a second copy\nof runner"))):
        rc, out, err, exc = run_main(["run", TASK, "--provider", "stub"])
    check("[E] a Refused from a second copy of the runner module (probe/worker import it): exit 2, no type prefix",
          rc == 2 and err.strip() == "runner.py run: from a second copy of runner", f"rc={rc} {err!r}")
    with patched(runner, load_exam=raiser(KeyboardInterrupt())):
        rc, out, err, exc = run_main(["run", TASK, "--provider", "stub"])
    check("[E] Ctrl-C passes through main() untouched (never a one-line exit 1)", isinstance(exc, KeyboardInterrupt) and err == "",
          f"{exc!r} {err!r}")

    def version_timeout(req, timeout=None):
        if "/api/version" in str(getattr(req, "full_url", req)):
            raise TimeoutError("timed out")
        raise AssertionError("only /api/version may be asked")

    with patched(runner.urllib.request, urlopen=version_timeout):
        rc, out, err, exc = run_main(["run", TASK, "--model", "gemma-w7-test", "--snapshot"])
    check("[E] a HUNG Ollama (timeout on /api/version): the same one line", rc == 1 and len(err.strip().splitlines()) == 1
          and "cannot reach Ollama at http://127.0.0.1:9 (timed out)" in err and "`ollama serve`" in err, f"rc={rc} {err!r}")

    def version_500(req, timeout=None):
        raise runner.urllib.error.HTTPError(str(req), 500, "boom", {}, None)

    with patched(runner.urllib.request, urlopen=version_500):
        rc, out, err, exc = run_main(["run", TASK, "--model", "gemma-w7-test", "--snapshot"])
    check("[E] /api/version answers HTTP 500: one line naming the host and the code", rc == 1
          and len(err.strip().splitlines()) == 1 and "answered /api/version with HTTP 500" in err
          and "http://127.0.0.1:9" in err, f"rc={rc} {err!r}")
    p_none = runner.save_result({"agent": TASK, "provider": "stub", "model": None, "cases": []}, subdir="none")
    check("[E] save_result with model None: placeholder-model file name, no AttributeError",
          p_none.name == f"{TASK}__stub__placeholder-model.json", p_none.name)

    with patched(runner, adapter_for=spy, run_exam=spy, ollama_num_ctx=spy):
        with patched(runner, load_routes=lambda name: []):
            rc, out, err, exc = run_main(["live", TASK, "--input", "the printer is on fire"])
        check("[E] live on the placeholder: exit 2, one line, nothing run or logged",
              rc == 2 and exc is None and reached == [] and err.startswith("runner.py live: agents/")
              and not (TMP / "results" / "live").exists(), f"rc={rc} {err!r} {reached}")
        with patched(runner, load_routes=lambda name: [{"provider": "stub", "model": "stub"},
                                                       {"provider": "ollama", "model": PLACEHOLDER}]):
            rc, out, err, exc = run_main(["live", TASK, "--input", "x"])
        check("[E] live: a placeholder FALLBACK tier refuses the whole run before tier 0 runs, blaming routes.yaml",
              rc == 2 and reached == [] and err.startswith("runner.py live: routes.yaml names a placeholder"),
              f"rc={rc} {err!r} {reached}")

    rc, out, err, exc = run_main(["run", TASK, "--provider", "stub"])
    names = sorted(p.name for p in (TMP / "results").glob("*.json"))
    check("[E] the stub still runs the placeholder scaffold (what the refusal suggests): exit 0", rc == 0 and exc is None,
          f"rc={rc} {err[-200:]!r}")
    check("[E] ... and the result file name carries no placeholder: <task>__stub__placeholder-model.json",
          names == [f"{TASK}__stub__placeholder-model.json"] and all(c not in "".join(names) for c in "<> "), repr(names))
    check("[E] ... the result JSON still records the model as written (only the file name is sanitized)",
          names and json.loads((TMP / "results" / names[0]).read_text())["model"] == PLACEHOLDER)

    # Ollama down: the real adapter (dead port), the real preflight, no spy.
    rc, out, err, exc = run_main(["run", TASK, "--model", "gemma-w7-test"])
    lines = err.strip().splitlines()
    check("[E] Ollama not answering: exit 1, exactly one stderr line, no traceback", rc == 1 and exc is None and len(lines) == 1
          and "Traceback" not in err, f"rc={rc} exc={exc!r} {err!r}")
    check("[E] ... the line names the host and `ollama serve`",
          lines[:1] and lines[0].startswith("runner.py run: cannot reach Ollama at http://127.0.0.1:9") and "`ollama serve`" in err,
          repr(err))

    def http_404(req, timeout=None):
        raise runner.urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    with patched(runner.urllib.request, urlopen=http_404):
        rc, out, err, exc = run_main(["run", TASK, "--model", "gemma-w7-test"])
    check("[E] /api/show answers non-200: one line naming the host, the code, `ollama pull <model>` and `ollama serve`",
          rc == 1 and len(err.strip().splitlines()) == 1 and "http://127.0.0.1:9" in err and "HTTP 404" in err
          and "`ollama pull gemma-w7-test`" in err and "`ollama serve`" in err, f"rc={rc} {err!r}")

    class _Body:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"<html>not json</html>"

    with patched(runner.urllib.request, urlopen=lambda req, timeout=None: _Body()):
        rc, out, err, exc = run_main(["run", TASK, "--model", "gemma-w7-test"])
    check("[E] /api/show answers with an unreadable body: one line saying so, never 'cannot reach'",
          rc == 1 and len(err.strip().splitlines()) == 1 and "unreadable /api/show reply" in err and "cannot reach" not in err,
          f"rc={rc} {err!r}")

    rc, out, err, exc = run_main(["run", TASK, "--model", "gemma-w7-test", "--snapshot"])
    check("[E] run --snapshot with Ollama not answering (/api/version is asked first): the same one line",
          rc == 1 and exc is None and len(err.strip().splitlines()) == 1
          and err.startswith("runner.py run: cannot reach Ollama at http://127.0.0.1:9") and "`ollama serve`" in err,
          f"rc={rc} {exc!r} {err!r}")
    sp = TMP / "evals" / TASK / "snapshot.json"
    sp.write_text(json.dumps({"provider": "ollama", "model": "gemma-w7-test", "train_score": 0, "heldout_score": 0,
                              "runtime": {"name": "ollama", "version": "0.0-test", "kv_cache_type": "unset",
                                          "flash_attention": "unset"},
                              "cases": [{"id": c["id"], "split": c["split"], "passed": False, "stable": True}
                                        for c in runner.load_exam(TASK)["cases"]]}))
    with patched(runner, ollama_server_settings=lambda *a, **k: {"kv_cache_type": "unset", "flash_attention": "unset"}):
        rc, out, err, exc = run_main(["check", TASK])
    sp.unlink()
    check("[E] check with Ollama not answering: one line naming the host and `ollama serve`, no URLError dump",
          rc == 1 and exc is None and len(err.strip().splitlines()) == 1
          and err.startswith("runner.py check: cannot reach Ollama at http://127.0.0.1:9") and "`ollama serve`" in err,
          f"rc={rc} {exc!r} {err!r}")

    rc, out, err, exc = run_main(["run", TASK, "--model", "gemma-w7-test"], env={"WILCO_DEBUG": "0"})
    check("[E] WILCO_DEBUG=0 is not debug: one line, no exception", rc == 1 and exc is None and "cannot reach Ollama" in err,
          f"rc={rc} {exc!r}")
    rc, out, err, exc = run_main(["run", TASK, "--model", "gemma-w7-test"], env={"WILCO_DEBUG": "1"})
    check("[E] WILCO_DEBUG=1: the exception propagates (full traceback), nothing printed in its place",
          isinstance(exc, runner.OllamaUnreachable) and isinstance(exc, RuntimeError) and err == "", f"{exc!r} {err!r}")

    def boom(name):
        raise KeyError("cases")

    with patched(runner, load_exam=boom):
        rc, out, err, exc = run_main(["run", TASK, "--provider", "stub"])
        rc_d, _o, _e, exc_d = run_main(["run", TASK, "--provider", "stub"], env={"WILCO_DEBUG": "1"})
    check("[E] any other exception: exit 1, one line with its type and the WILCO_DEBUG hint",
          rc == 1 and exc is None and err.strip() == "runner.py run: KeyError: 'cases' (WILCO_DEBUG=1 prints the traceback)",
          f"rc={rc} {err!r}")
    check("[E] ... and WILCO_DEBUG=1 re-raises that one too", isinstance(exc_d, KeyError), repr(exc_d))
    rc, out, err, exc = run_main(["run", "no-such-task", "--provider", "stub"])
    check("[E] SystemExit (the runner's own `error: …` exits) passes through untouched",
          isinstance(exc, SystemExit) and str(exc.code).startswith("error: no agent at"), repr(exc))

    # ------------------------------------------------------------------ [M] messages
    with patched(runner, adapter_for=spy, run_exam=spy):
        rc, out, err, exc = run_main(["diff", TASK])
        check("[M] diff without --models: exit 2, one line saying what to type, no row run",
              rc == 2 and reached == [] and err.strip() == f"runner.py diff: name the candidates: wilco diff {TASK} --models "
              "ollama/<m>,openrouter/<id>", f"rc={rc} {err!r}")
        rc, out, err, exc = run_main(["run", TASK, "--provider", "openrouter", "--model", "x/y"])
        check("[M] the tier refusal prints INSTEAD of the `exam:` header: exit 2, stdout empty, the W2 sentence on stderr",
              rc == 2 and out == "" and "refused before any request" in err and reached == [], f"rc={rc} out={out!r} {err!r}")
    nl = io.StringIO()
    with contextlib.redirect_stdout(nl):
        exam_new.main(["w7-next", "--mode", "labels", "--root", str(TMP / "next")])
    check("[M] new: the next step is `wilco validate <task>`",
          nl.getvalue().strip().splitlines()[-1] == "next: replace the example cases, then wilco validate w7-next", nl.getvalue())

    def cand(label, held, n=3):
        return dict(label=label, provider=label.split("/")[0], held=held, n=n, cases=n, splits={}, totals=None,
                    snapshot=False, path=label, usd=None, tag="cost unknown")

    zero = [cand("stub/a", 0), cand("stub/b", 0)]
    best, bar, _p = pick.apply_rule(zero)
    term = pick.terminal(dict(task="t", cands=zero, best=best, bar=bar, bar_gap=pick.BAR_GAP, pick=None, flags=[], n=3,
                              prices_as_of="x", prices_source="y"))
    check("[M] pick on a best of 0: bar 0/3, never -1", bar == 0 and "bar 0/3 (best − 1)" in term and "bar -" not in term, term)
    best, bar, _p = pick.apply_rule([cand("stub/a", 5, 9), cand("stub/b", 3, 9)])
    check("[M] ... the rule itself unchanged: best 5 -> bar 4", (best, bar) == (5, 4), f"{best} {bar}")

    # ------------------------------------------------------------------ [A] adopt (temp root, snapshot step faked)
    A = TMP / "adopt"
    with contextlib.redirect_stdout(io.StringIO()):
        exam_new.main([TASK, "--mode", "labels", "--root", str(A)])
    ypath = A / "agents" / TASK / "agent.yaml"
    scaffold = ypath.read_text()
    snaps = []

    def fake_snap(root, task):
        snaps.append((pathlib.Path(root), task))
        return 0

    def adopt(*args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = exam_adopt.main([TASK, *args, "--root", str(A)])
        return rc, out.getvalue(), err.getvalue()

    real_snap = exam_adopt.run_snapshot
    exam_adopt.run_snapshot = fake_snap
    try:
        rc, out, err = adopt("ollama/gemma4:e4b")
        new = ypath.read_text()
        y0, y1 = yaml.safe_load(scaffold), yaml.safe_load(new)
        diff = [(a, b) for a, b in zip(scaffold.splitlines(), new.splitlines()) if a != b]
        check("[A] adopt ollama/gemma4:e4b: exit 0, provider + model written", rc == 0 and (y1["provider"], y1["model"])
              == ("ollama", "gemma4:e4b"), f"rc={rc} {err!r}")
        check("[A] ... exactly one line changed (the model line; provider was already ollama), same line count, comments kept",
              len(diff) == 1 and diff[0][1] == 'model: "gemma4:e4b"' and len(scaffold.splitlines()) == len(new.splitlines())
              and "# local | eu | frontier" in new and "# Quoted on purpose" in new, repr(diff))
        check("[A] ... every other field unchanged (tier, temperature, max_tokens, ...)",
              {k: v for k, v in y0.items() if k not in ("provider", "model")} == {k: v for k, v in y1.items() if k not in ("provider", "model")})
        check("[A] ... then the snapshot step, once, on THIS root and task", snaps == [(A, TASK)], repr(snaps))
        check("[A] ... prints the old line and the new ones", f"- model: \"{PLACEHOLDER}\"" in out and '+ model: "gemma4:e4b"' in out, out)

        ypath.write_text(scaffold); snaps.clear()
        rc, out, err = adopt("openrouter/google/gemma-4", "--allow-tier-breach")
        y1 = yaml.safe_load(ypath.read_text())
        check("[A] a label is split on its FIRST '/': openrouter + google/gemma-4", rc == 0 and (y1["provider"], y1["model"])
              == ("openrouter", "google/gemma-4"), f"rc={rc} {err!r}")
        check("[A] ... a tier breach passes with the flag, and takes NO snapshot (the runner never snapshots a breach)",
              snaps == [] and "no snapshot" in out and y1["tier"] == "local", f"{snaps} {out!r}")

        for label, why in (("openrouter/google/gemma-4", "above the tier"), ("gemma4", "no slash"), ("ollama/", "no model"),
                           ("/gemma4", "no provider"), ("nosuch/m", "unknown provider"), (f"ollama/{PLACEHOLDER}", "placeholder")):
            ypath.write_text(scaffold); snaps.clear()
            rc, out, err = adopt(label)
            check(f"[A] refused ({why}): {label!r} -> exit 2, agent.yaml byte for byte, no snapshot",
                  rc == 2 and ypath.read_text() == scaffold and snaps == [] and err.startswith("adopt: REFUSED"), f"rc={rc} {err!r}")
        ypath.write_text(scaffold)
        for label, extra in (("ollama/<m>", ()), ("openrouter/<m>", ("--allow-tier-breach",))):   # no spaces: isolates the guard
            rc, out, err = adopt(label, *extra)
            check(f"[A] a placeholder label without spaces {label!r}: refused as a placeholder, nothing written",
                  rc == 2 and ypath.read_text() == scaffold and "names a placeholder" in err and snaps == [], f"rc={rc} {err!r}")
        oe = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(oe):
            rc_missing = exam_adopt.main(["no-such-task-w7", "ollama/x", "--root", str(A)])
        check("[A] adopt on a task with no agent.yaml: exit 2, one line naming it, no traceback",
              rc_missing == 2 and len(oe.getvalue().strip().splitlines()) == 1
              and "no agents/no-such-task-w7/agent.yaml" in oe.getvalue(), f"rc={rc_missing} {oe.getvalue()!r}")
        _rc, _o, err = adopt("openrouter/x")
        check("[A] ... the tier refusal is the runner's own W2 sentence", "refused before any request" in err and "local-tier" in err, err)

        snap = A / "evals" / TASK / "snapshot.json"
        snap.write_text(json.dumps({"provider": "ollama", "model": "old-champ", "cases": []}))
        ypath.write_text(scaffold.replace(f'model: "{PLACEHOLDER}"', "model: old-champ   # signed 1 Oct")); before = ypath.read_text()
        snaps.clear()
        rc, out, err = adopt("ollama/new-model")
        check("[A] a committed snapshot exists: refused without --replace, naming it and printing the old line",
              rc == 2 and ypath.read_text() == before and snaps == [] and "ollama/old-champ" in err
              and "model: old-champ   # signed 1 Oct" in err and "--replace" in err, f"rc={rc} {err!r}")
        rc, out, err = adopt("ollama/new-model", "--replace")
        check("[A] ... --replace adopts, and the line's trailing comment survives",
              rc == 0 and 'model: "new-model"   # signed 1 Oct' in ypath.read_text() and snaps == [(A, TASK)], ypath.read_text())
        check("[A] ... and --replace prints the line it replaced", "- model: old-champ   # signed 1 Oct" in out, out)

        ypath.write_text(before)

        def interrupted(root, task):
            raise KeyboardInterrupt

        exam_adopt.run_snapshot = interrupted
        try:
            adopt("ollama/new-model", "--replace")
            ki = False
        except KeyboardInterrupt:
            ki = True
        check("[A] Ctrl-C during the snapshot: agent.yaml restored byte for byte, the interrupt re-raised",
              ki and ypath.read_text() == before)
        exam_adopt.run_snapshot = fake_snap

        ypath.write_text(before)
        exam_adopt.run_snapshot = lambda root, task: 1
        rc, out, err = adopt("ollama/new-model", "--replace")
        check("[A] a failed snapshot: its exit code, agent.yaml restored byte for byte",
              rc == 1 and ypath.read_text() == before and "restored" in err, f"rc={rc} {err!r}")
        exam_adopt.run_snapshot = fake_snap
        snap.unlink()

        ypath.write_text(scaffold + 'model: "again"\n'); snaps.clear()
        rc, out, err = adopt("ollama/x")
        check("[A] two top-level model: lines: refused, nothing written", rc == 2 and "2 top-level `model:` lines" in err
              and snaps == [], err)
        for shape, text in (("a multi-line (block scalar) model value", scaffold.replace(f'model: "{PLACEHOLDER}"', "model: >-\n  foo")),
                            ("an agent.yaml that does not parse", scaffold + "tier: [unclosed\n")):
            ypath.write_text(text); snaps.clear()
            rc, out, err = adopt("ollama/x")
            check(f"[A] {shape}: refused exit 2 (one line, no traceback), nothing written", rc == 2 and ypath.read_text() == text
                  and snaps == [] and err.startswith("adopt: REFUSED") and "Traceback" not in err
                  and len(err.strip().splitlines()) == 1, f"rc={rc} {err!r}")
        ypath.write_text(scaffold); snaps.clear()
        (A / "routes.yaml").write_text(f"{TASK}:\n  - provider: ollama\n    model: old-champ\n  - provider: stub\n    model: stub\n")
        rc, out, err = adopt("ollama/gemma4:e4b")
        check("[A] routes.yaml tier 0 is still the old model: refused, naming the line to edit; nothing written",
              rc == 2 and ypath.read_text() == scaffold and snaps == [] and "routes.yaml routes" in err
              and "ollama/old-champ" in err and "provider: ollama, model: gemma4:e4b" in err, f"rc={rc} {err!r}")
        (A / "routes.yaml").write_text(f"{TASK}:\n  - provider: openrouter\n    model: gemma4:e4b\n")
        rc, out, err = adopt("ollama/gemma4:e4b")
        check("[A] routes tier 0 with the same model on ANOTHER provider: still refused", rc == 2 and ypath.read_text() == scaffold
              and "openrouter/gemma4:e4b" in err, f"rc={rc} {err!r}")
        (A / "routes.yaml").write_text(f"{TASK}: [unclosed\n")
        rc, out, err = adopt("ollama/gemma4:e4b")
        check("[A] a routes.yaml that does not parse: refused, one line, nothing written", rc == 2 and ypath.read_text() == scaffold
              and err.startswith("adopt: REFUSED — routes.yaml does not parse") and len(err.strip().splitlines()) == 1,
              f"rc={rc} {err!r}")
        snaps.clear()
        (A / "routes.yaml").write_text(f"{TASK}:\n  - provider: ollama\n    model: gemma4:e4b\n")
        rc, out, err = adopt("ollama/gemma4:e4b")
        check("[A] ... once tier 0 names the new model, adopt goes through", rc == 0 and snaps == [(A, TASK)], f"rc={rc} {err!r}")
        (A / "routes.yaml").unlink()
        ypath.write_text(scaffold)
        for label in ("ollama/gemma4:e4b ", " ollama/gemma4:e4b", "ollama/gemma4 e4b"):
            rc, out, err = adopt(label)
            check(f"[A] whitespace in the label {label!r}: refused, nothing written", rc == 2 and ypath.read_text() == scaffold
                  and "whitespace" in err, f"rc={rc} {err!r}")
        ypath.write_text(scaffold)
    finally:
        exam_adopt.run_snapshot = real_snap
    r = io.StringIO()
    with contextlib.redirect_stderr(r):
        rc_none = exam_adopt.run_snapshot(A, TASK)
    check("[A] the real snapshot step refuses a root without sandbox/runner.py (never falls back to this repo)",
          rc_none == 2 and "no " in r.getvalue(), r.getvalue())
    check("[A] the adopt test left the scaffold as it was", ypath.read_text() == scaffold)

    # pick prints the adopt line (committed matrix files, offline)
    matrix = sorted(str(p) for p in ROOT.glob("docs/probes/matrix-2026-09-27/results/crm-followup__*.json"))
    po = io.StringIO()
    with contextlib.redirect_stdout(po):
        prc = pick.main(["crm-followup", *matrix, "--out", str(TMP / "p.md")])
    pl = po.getvalue().splitlines()
    winner = next((ln[len("pick: "):] for ln in pl if ln.startswith("pick: ")), None)
    check("[A] pick prints the exact adopt line for its winner, right after it",
          prc == 0 and winner and f"adopt it: wilco adopt crm-followup {winner}" in pl
          and pl.index(f"adopt it: wilco adopt crm-followup {winner}") == pl.index(f"pick: {winner}") + 1, po.getvalue()[-300:])
    check("[A] ... and none when there is no pick", "adopt" not in term, term)
    ai = pl.index(f"adopt it: wilco adopt crm-followup {winner}") if winner and f"adopt it: wilco adopt crm-followup {winner}" in pl else -1
    check("[A] a hosted winner on a local-tier task: the adopt line says adopt will refuse it without --allow-tier-breach",
          ai >= 0 and ai + 1 < len(pl) and pl[ai + 1].strip().startswith(f"({winner.split('/')[0]} is frontier-tier, the task is local-tier")
          and "--allow-tier-breach" in pl[ai + 1], pl[ai:ai + 2])
    check("[A] ... and no such note within the tier (or with the tier unknown)",
          pick.above_tier("ollama", "local") is None and pick.above_tier("openrouter", None) is None
          and pick.above_tier("openrouter", "frontier") is None)
    check("[A] ... an eu provider on a local task gets the note; an unknown provider gets none (never a crash)",
          pick.above_tier("scaleway", "local") is not None and pick.above_tier("no-such-provider", "local") is None)
    # the tier is READ from agents/<task>/agent.yaml: the same matrix, the same winner, two agent.yaml tiers
    real_repo, fake = pick.REPO, TMP / "pickrepo"
    (fake / "agents" / "crm-followup").mkdir(parents=True)
    notes = {}
    try:
        pick.REPO = str(fake)
        for name, tier_line in (("frontier", "tier: frontier\n"), ("no-key", "")):
            (fake / "agents" / "crm-followup" / "agent.yaml").write_text(f"provider: ollama\nmodel: gemma4:e2b\n{tier_line}")
            o = io.StringIO()
            with contextlib.redirect_stdout(o):
                pick.main(["crm-followup", *matrix, "--out", str(TMP / "p3.md"),
                           "--prices", str(ROOT / "pricing" / "prices.json")])
            notes[name] = "-tier, the task is " in o.getvalue()
    finally:
        pick.REPO = real_repo
    check("[A] pick reads the task's tier: a frontier-tier agent.yaml gets no note for the hosted winner",
          notes.get("frontier") is False, repr(notes))
    check("[A] ... an agent.yaml with no tier key is the strictest tier, as the runner reads it: the note prints",
          notes.get("no-key") is True, repr(notes))
    po = io.StringIO()
    with contextlib.redirect_stdout(po):
        prc = pick.main(["email-triage", str(ROOT / "evals" / "email-triage" / "snapshot.json"), "--out", str(TMP / "p2.md")])
    champ = yaml.safe_load((ROOT / "agents" / "email-triage" / "agent.yaml").read_text())
    check("[A] the pick IS the task's model (the champion's own snapshot): 'nothing to adopt', never an adopt line",
          f"pick: {champ['provider']}/{champ['model']}" in po.getvalue()
          and "already the task's model (agents/email-triage/agent.yaml): nothing to adopt" in po.getvalue()
          and "adopt it:" not in po.getvalue(), po.getvalue()[-300:])
    t4 = pick.terminal(dict(task="t", cands=zero, best=0, bar=0, bar_gap=1, pick=dict(label="openrouter/x"), flags=[], n=3,
                            prices_as_of="x", prices_source="y", current="ollama/x"))
    check("[A] same model id on ANOTHER provider than agent.yaml's: the adopt line prints (it is a change)",
          "adopt it: wilco adopt t openrouter/x" in t4 and "nothing to adopt" not in t4, t4)
    check("[A] pick on a task with no agent.yaml: no current label, no traceback (the adopt line prints as usual)",
          pick.current_label("no-such-task-w7") is None)
finally:
    runner.ROOT, runner.RESULTS_DIR = real_root, real_results

# ------------------------------------------------------------------ [H] help
JARGON = re.compile(r"\b(?:E\d{1,2}|AS-\d|J\d{1,2})\b|\bW\d+:|A/B arm|\blane\b")
# the guard must see the strings master's help carried (origin/master 92414cb, sandbox/runner.py main())
for old in ("(E27 A/B arm; single-turn cases and turn 0 unaffected)", "AS-3 arm: show one rule inside the tool loop",
            "W2: run a provider above the agent's tier (refused by default)"):
    check(f"[H] the jargon guard matches master's old help string {old[:24]!r}", JARGON.search(old) is not None)
for c in wilco_cli.COMMANDS:
    for flag in ("--help", "--help-advanced") if c in ("run", "check", "diff") else ("--help",):
        o = io.StringIO()
        with contextlib.redirect_stdout(o), contextlib.redirect_stderr(io.StringIO()):
            hrc = wilco_cli.main([c, flag])
        h = o.getvalue()
        n = len(h.rstrip("\n").splitlines())
        check(f"[H] wilco {c} {flag}: exit 0, usage `wilco {c}`, {n} <= 40 lines", hrc == 0 and h.startswith(f"usage: wilco {c} ")
              and n <= 40, f"rc={hrc} {h[:60]!r} {n}")
        check(f"[H] wilco {c} {flag}: no lane jargon", not JARGON.search(h), JARGON.search(h) and JARGON.search(h).group(0))
check("[H] the shim restores WILCO_PROG after each command (unset here before, unset after)", "WILCO_PROG" not in os.environ)
os.environ["WILCO_PROG"] = "preset-by-caller"
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    wilco_cli.main(["list", "--help"])
check("[H] ... and a WILCO_PROG the caller had set comes back as it was", os.environ.get("WILCO_PROG") == "preset-by-caller",
      repr(os.environ.get("WILCO_PROG")))
os.environ.pop("WILCO_PROG", None)
env = {k: v for k, v in os.environ.items() if k != "WILCO_PROG"}
d = subprocess.run([sys.executable, str(ROOT / "sandbox" / "runner.py"), "run", "--help"], capture_output=True, text=True,
                   env=env, timeout=60)
check("[H] runner.py run directly: usage `runner.py run`, as before", d.returncode == 0 and d.stdout.startswith("usage: runner.py run "),
      d.stdout[:60])
check("[H] wilco's own usage lists adopt with its script", re.search(r"^  adopt .*\(scripts/exam_adopt\.py\)$", wilco_cli.USAGE, re.M)
      is not None)

check("[H] the hidden set is the brief's: run --assembly/--scoped-rule/--dedupe-tools/--loads, check --tolerance/--provider",
      {k: set(v) for k, v in runner.ADVANCED_FLAGS.items()} == {
          "run": {"--assembly", "--scoped-rule", "--dedupe-tools", "--loads"},
          "check": {"--dedupe-tools", "--tolerance", "--provider"}, "diff": {"--assembly", "--dedupe-tools"}})
VALUES = {"--assembly": ("scoped", "assembly", "scoped"), "--scoped-rule": ("sham", "scoped_rule", "sham"),
          "--dedupe-tools": (None, "dedupe_tools", True), "--loads": ("5", "loads", 5),
          "--tolerance": ("0.5", "tolerance", 0.5), "--provider": ("stub", "provider", "stub")}
for adv in (False, True):
    p = runner.build_parser(prog="wilco", advanced=adv)
    for cmd, flags in runner.ADVANCED_FLAGS.items():
        for f in flags:
            val, dest, want = VALUES[f]
            argv = [cmd, "t", f] + ([val] if val is not None else []) + (["--models", "stub/x"] if cmd == "diff" else [])
            ns = p.parse_args(argv)
            check(f"[H] {cmd} {f} parses to {dest}={want!r} ({'advanced' if adv else 'hidden'} parser)",
                  getattr(ns, dest, "<missing>") == want, repr(getattr(ns, dest, "<missing>")))
for cmd, flags in runner.ADVANCED_FLAGS.items():
    plain = runner.build_parser(prog="wilco")._subparsers._group_actions[0].choices[cmd].format_help()
    adv = runner.build_parser(prog="wilco", advanced=True)._subparsers._group_actions[0].choices[cmd].format_help()
    for f in flags:
        check(f"[H] {cmd} --help hides {f}; --help-advanced lists it", f not in plain and f in adv)
    check(f"[H] {cmd} --help says where the advanced flags are", f"advanced flags: wilco {cmd} --help-advanced" in plain)

# ------------------------------------------------------------------ [X] end to end, through the shim, in a box
BOX = TMP / "box"
BOX.mkdir()
for name in ("wilco_cli.py", "routes.yaml"):
    shutil.copy(ROOT / name, BOX / name)
for name in ("sandbox", "scripts", "pricing"):
    shutil.copytree(ROOT / name, BOX / name, ignore=shutil.ignore_patterns("__pycache__", "test_*.py", "public-snapshot"))
(BOX / "evals").mkdir()
(BOX / "agents").mkdir()
rewired = 0
for py in BOX.rglob("*.py"):
    t = py.read_text()
    if "localhost:11434" in t or "127.0.0.1:8080" in t:   # Ollama (ollama, systemone) and the mlx server
        py.write_text(t.replace("localhost:11434", "127.0.0.1:9").replace("127.0.0.1:8080", "127.0.0.1:9"))
        rewired += 1
leftover = [str(p.relative_to(BOX)) for p in BOX.rglob("*.py") if "11434" in p.read_text() or ":8080" in p.read_text()]
box_ok = rewired >= 1 and leftover == [] and not list((BOX / "agents").iterdir())
check("[X] the box: no committed agent, every Ollama host rewired to 127.0.0.1:9 (else nothing below runs)", box_ok,
      f"rewired={rewired} leftover={leftover}")


def wilco(*args, env_extra=None):
    e = {k: v for k, v in os.environ.items() if k not in ("WILCO_PROG", "WILCO_DEBUG")}
    e.update(env_extra or {})
    r = subprocess.run([sys.executable, str(BOX / "wilco_cli.py"), *map(str, args)], capture_output=True, text=True,
                       timeout=300, cwd=BOX, env=e)
    return r.returncode, r.stdout, r.stderr


if box_ok:
    T = "ticket-priority"
    rc, out, err = wilco("new", T, "--mode", "labels")
    check("[X] wilco new: exit 0, next step `wilco validate`", rc == 0 and f"then wilco validate {T}" in out, f"{rc} {err!r}")
    rc, out, err = wilco("run", T)
    check("[X] wilco run on the fresh scaffold (the walkthrough's traceback, rc 120): exit 2, one line, no traceback",
          rc == 2 and "Traceback" not in err and len(err.strip().splitlines()) == 1
          and err.startswith(f"wilco run: agents/{T}/agent.yaml still has the placeholder model"), f"rc={rc} {err!r}")
    rc, out, err = wilco("live", T, "--input", "printer on fire")
    check("[X] wilco live on the fresh scaffold: exit 2, one line `wilco live: …`", rc == 2 and "Traceback" not in err
          and err.startswith("wilco live: agents/") and len(err.strip().splitlines()) == 1, f"rc={rc} {err!r}")
    rc, out, err = wilco("run", T, "--model", "gemma-w7-test")
    check("[X] Ollama not answering, through the shim: exit 1, one line naming the host and `ollama serve`",
          rc == 1 and "Traceback" not in err and len(err.strip().splitlines()) == 1
          and err.startswith("wilco run: cannot reach Ollama at http://127.0.0.1:9") and "`ollama serve`" in err, f"rc={rc} {err!r}")
    rc, out, err = wilco("run", T, "--model", "gemma-w7-test", env_extra={"WILCO_DEBUG": "1"})
    check("[X] ... WILCO_DEBUG=1: the full traceback, ending in OllamaUnreachable", rc == 1 and "Traceback (most recent call last)" in err
          and "OllamaUnreachable" in err, f"rc={rc} {err[-200:]!r}")
    rc, out, err = wilco("diff", T)
    check("[X] wilco diff without --models: exit 2, the line to type", rc == 2 and err.strip() ==
          f"wilco diff: name the candidates: wilco diff {T} --models ollama/<m>,openrouter/<id>", f"rc={rc} {err!r}")
    rc, out, err = wilco("run", T, "--provider", "openrouter", "--model", "x")
    check("[X] tier refusal through the shim: exit 2, no `exam:` header", rc == 2 and out == "" and "refused before any request" in err,
          f"rc={rc} {out!r}")
    rc, out, err = wilco("run", T, "--provider", "stub")
    check("[X] the stub run of the scaffold: exit 0, file name without the placeholder",
          rc == 0 and f"-> results/{T}__stub__placeholder-model.json" in out, f"rc={rc} {out[-200:]!r} {err!r}")
    rc, out, err = wilco("pick", T, BOX / "results" / f"{T}__stub__placeholder-model.json", "--out", BOX / "p.md")
    check("[X] wilco pick on it: bar 0/1, not -1/1", "bar 0/1" in out and "bar -1" not in out, out[:120])
    rc, out, err = wilco("adopt", T, "stub/stub")
    y = yaml.safe_load((BOX / "agents" / T / "agent.yaml").read_text())
    snap = BOX / "evals" / T / "snapshot.json"
    check("[X] wilco adopt <task> stub/stub: exit 0, agent.yaml says stub/stub, the REAL snapshot step wrote snapshot.json",
          rc == 0 and (y["provider"], y["model"]) == ("stub", "stub") and snap.is_file()
          and json.loads(snap.read_text()).get("model") == "stub", f"rc={rc} {out[-300:]!r} {err[-300:]!r}")
    rc, out, err = wilco("check", T)
    check("[X] wilco check on the adopted baseline: exit 0", rc == 0 and "ok: heldout" in out, f"rc={rc} {out[-200:]!r} {err[-200:]!r}")
    rc, out, err = wilco("adopt", T, "stub/other")
    check("[X] a second adopt over the snapshot: refused without --replace, exit 2", rc == 2 and "--replace" in err, f"rc={rc} {err!r}")
    rc, out, err = wilco("adopt", "--help")
    check("[X] wilco adopt --help: usage `wilco adopt`", rc == 0 and out.startswith("usage: wilco adopt "), out[:60])

shutil.rmtree(TMP, ignore_errors=True)
for k, v in REAL_HOSTS.items():
    runner.PROVIDERS[k]["base_url"] = v
check("[A] every committed agent.yaml and snapshot.json is byte-identical after this file", committed_state() == STATE_BEFORE)

print(f"\n{len(FAILED)} FAILED" if FAILED else "\nall passed")
sys.exit(1 if FAILED else 0)
