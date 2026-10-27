"""W2 (Sprint W, 2026-10-23) — runner guards: tier enforcement, window preflight,
per-entry provider in `diff`, the `openai` provider line.

Why: `agents/<task>/agent.yaml` `tier:` ("data may not leave this tier") was a label nothing
read; an over-window prompt to Ollama is cut from the FRONT without a word (gotcha 16); and
`diff` took one provider for the whole list.

Everything runs through the REAL entry points (cmd_run, cmd_diff, run_exam, call_model,
live_run_and_log, cmd_live); only the network is replaced: `router.requests.post` (the chat
call) and `runner.ollama_num_ctx` / `urllib.request.urlopen` (the /api/show lookup). No
inference, no network, no key. Results go to a temp dir (runner.RESULTS_DIR patched).

[W] = RED on origin/master's runner.py/router.py (recorded in the PR), [C] = control, green
on both sides. Each check is wrapped so a missing name on the old code FAILS that check
instead of crashing the file (gotcha 2: the red run must name what it misses).
"""
import argparse
import contextlib
import io
import json
import pathlib
import shutil
import sys
import tempfile
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
import router  # noqa: E402
import runner  # noqa: E402

FAILED = []


def check(label, ok, extra=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {extra}" if not ok and extra else ""))
    if not ok:
        FAILED.append(label)


def guarded(label):
    """Run one test group; an exception is a FAIL of that group, never a crash."""
    def deco(fn):
        print(f"running {fn.__name__}")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — the red run on old code lands here
            check(f"{label} (raised {type(exc).__name__}: {exc})", False,
                  traceback.format_exc(limit=3))
        return fn
    return deco


_MISSING = object()


@contextlib.contextmanager
def patched(mod, **attrs):
    """Set attributes, restore after. An attribute the module does not have is created
    and deleted again, so on the OLD code the window tests still drive run_exam and the
    red is the behaviour (a request reaches requests.post), not a missing name."""
    saved = {k: getattr(mod, k, _MISSING) for k in attrs}
    try:
        for k, v in attrs.items():
            setattr(mod, k, v)
        yield
    finally:
        for k, v in saved.items():
            if v is _MISSING:
                delattr(mod, k)
            else:
                setattr(mod, k, v)


class Boom(Exception):
    pass


def boom(*_a, **_k):
    raise Boom("a request was made — the guard did not refuse first")


def _ns(**kw):
    base = dict(provider=None, model=None, snapshot=False, loads=3, timeout=None,
                dedupe_tools=False, assembly="full", split="all", scoped_rule="off")
    base.update(kw)
    return argparse.Namespace(**base)


def _capture(fn, *a, **k):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*a, **k)
    return rc, out.getvalue(), err.getvalue()


class _FakeResp:
    def __init__(self, payload):
        self._p = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def _chat_ok(content):
    return {"choices": [{"message": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


class _CountingPost:
    def __init__(self, content):
        self.content, self.calls = content, 0

    def __call__(self, *a, **k):
        self.calls += 1
        return _FakeResp(_chat_ok(self.content))


TMP = pathlib.Path(tempfile.mkdtemp(prefix="w2-guards-"))
LONG_ID = "longcall-support-heldout-2"   # transcript-en, ~8.9k tokens by chars/4 incl. system


def _transcript_long_exam():
    exam = runner.load_exam("transcript-en")
    cases = [c for c in exam["cases"] if c["id"] == LONG_ID]
    assert len(cases) == 1, f"{LONG_ID} missing from evals/transcript-en/cases.json"
    return {**exam, "cases": cases}


def _real_ollama_adapter(*_a, **_k):
    # The production adapter on the production Ollama base_url; only requests.post differs.
    return router.ChatCompletionsAdapter(router.PROVIDERS["ollama"]["base_url"], timeout=7)


# ------------------------------------------------------------------ 1. tier map + openai

@guarded("[W] tier map / openai provider")
def test_1_tier_map_covers_every_provider():
    tiers = getattr(router, "PROVIDER_TIER", None)
    order = getattr(router, "TIER_ORDER", None)
    check("[W] router.TIER_ORDER == ('local','eu','frontier')", order == ("local", "eu", "frontier"),
          repr(order))
    check("[W] every PROVIDERS key has a tier in TIER_ORDER (a new provider cannot slip through)",
          tiers is not None and all(tiers.get(p) in (order or ()) for p in router.PROVIDERS),
          f"missing: {[p for p in router.PROVIDERS if not tiers or tiers.get(p) not in (order or ())]}")
    want = {"ollama": "local", "mlx": "local", "systemone": "local", "stub": "local",
            "scaleway": "eu", "ovh": "eu", "nebius": "eu",
            "openrouter": "frontier", "openai": "frontier"}
    check("[W] the spec's provider->tier rows", tiers is not None
          and all(tiers.get(k) == v for k, v in want.items()), repr(tiers))
    check("[W] PROVIDERS['openai'] is one config line (base_url + key env)",
          router.PROVIDERS.get("openai") == {"base_url": "https://api.openai.com/v1",
                                             "api_key_env": "OPENAI_API_KEY"},
          repr(router.PROVIDERS.get("openai")))
    # The template lives at scripts/public-snapshot/README.md here; in the public cut it IS
    # the root README.md (the publish script renders it there). Read whichever exists; a
    # missing sentence is a FAIL either way, never a skip (gotcha 19).
    tpl = ROOT / "scripts" / "public-snapshot" / "README.md"
    readme = (tpl if tpl.exists() else ROOT / "README.md").read_text()
    check("[W] the README template says any OpenAI-compatible endpoint is one line in PROVIDERS",
          "any OpenAI-compatible endpoint is one line there" in readme
          and "--allow-tier-breach" in readme and "PARAMETER num_ctx 16384" in readme)
    for name in runner._all_agents():
        check(f"[C] agents/{name}/agent.yaml tier is local (every committed exam)",
              runner.load_agent(name).get("tier") == "local")


# ------------------------------------------------------------------ 2. tier guard on run

@guarded("[W] run refuses a frontier provider on a local exam")
def test_2_run_refuses_above_tier_before_any_request():
    built = []
    with patched(runner, get_adapter=lambda *a, **k: built.append(a) or boom(),
                 run_exam=boom, save_result=boom):
        rc, out, err = _capture(runner.cmd_run, _ns(agent="email-triage", provider="openrouter"))
    check("[W] run email-triage --provider openrouter -> exit 2", rc == 2, f"rc={rc}")
    check("[W] no adapter built, no exam run", built == [])
    check("[W] one sentence names the exam tier and the provider's",
          "local-tier" in err and "frontier-tier" in err and "--allow-tier-breach" in err, err)
    for prov in ("openai", "scaleway"):
        with patched(runner, get_adapter=boom, run_exam=boom, save_result=boom):
            rc, _o, _e = _capture(runner.cmd_run, _ns(agent="email-triage", provider=prov))
        check(f"[W] run email-triage --provider {prov} -> exit 2", rc == 2, f"rc={rc}")


@guarded("[W] --allow-tier-breach runs and records tier_breach")
def test_3_allow_flag_records_the_breach_and_within_tier_does_not():
    saved = []

    def fake_run_exam(agent, exam, provider, model, **kw):
        return {"agent": agent["name"], "provider": provider, "model": model,
                "train": {"passed": 0, "total": 0}, "heldout": {"passed": 0, "total": 0},
                "cases": []}

    def fake_save(result, **kw):
        saved.append(dict(result))
        return runner.ROOT / "results" / "x.json"
    with patched(runner, run_exam=fake_run_exam, save_result=fake_save):
        rc, _o, err = _capture(runner.cmd_run, _ns(agent="email-triage", provider="openrouter",
                                                   allow_tier_breach=True))
    check("[W] with --allow-tier-breach -> rc 0 and the result says tier_breach: true",
          rc == 0 and saved and saved[-1].get("tier_breach") is True, f"rc={rc} saved={saved}")
    check("[W] the breach is announced on stderr", "tier breach allowed" in err, err)
    saved.clear()
    with patched(runner, run_exam=fake_run_exam, save_result=fake_save):
        rc, _o, _e = _capture(runner.cmd_run, _ns(agent="email-triage", provider="stub"))
    check("[C] a within-tier run carries NO tier_breach key (byte-identical result)",
          rc == 0 and saved and "tier_breach" not in saved[-1], repr(saved))


@guarded("[W] missing/unknown tier is refused")
def test_4_unreadable_tier_is_refused_never_assumed():
    TB = getattr(runner, "TierBreach")
    try:
        runner.tier_check({"name": "x", "tier": "galaxy"}, "ollama")
        ok = False
    except TB:
        ok = True
    check("[W] an unknown tier value raises TierBreach even for a local provider", ok)
    check("[W] NO tier key = the strictest tier: local provider allowed",
          runner.tier_check({"name": "x"}, "ollama") is False)
    try:
        runner.tier_check({"name": "x"}, "nebius")
        ok = False
    except TB:
        ok = True
    check("[W] NO tier key + an eu provider -> TierBreach (missing label never lets data out)", ok)
    try:
        runner.tier_check({"name": "x", "tier": "frontier"}, "no-such-provider")
        ok = False
    except TB:
        ok = True
    check("[W] a provider with no PROVIDER_TIER entry raises TierBreach", ok)
    check("[W] eu exam: eu provider allowed, frontier refused",
          runner.tier_check({"name": "x", "tier": "eu"}, "ovh") is False)
    try:
        runner.tier_check({"name": "x", "tier": "eu"}, "openai")
        ok = False
    except TB:
        ok = True
    check("[W] eu exam + openai -> TierBreach", ok)


@guarded("[W] --snapshot refuses the allow flags")
def test_5_snapshot_never_breached_or_truncated():
    for flag in ("allow_tier_breach", "allow_truncation"):
        with patched(runner, take_snapshot_loads=boom, run_exam=boom):
            rc, _o, err = _capture(runner.cmd_run, _ns(agent="email-triage", snapshot=True,
                                                       **{flag: True}))
        check(f"[W] run --snapshot --{flag.replace('_', '-')} -> exit 2 before any load",
              rc == 2, f"rc={rc} err={err}")


# ------------------------------------------------------------------ 3. diff per-entry provider

@guarded("[W] diff --models provider/model parsing")
def test_6_parse_model_entries():
    def p(*a):   # the `note:` line is printed by the code under test; keep checks visible
        with contextlib.redirect_stdout(io.StringIO()):
            return runner.parse_model_entries(*a)
    got = p("ollama/gemma4:e2b-it-qat,openrouter/google/gemma-4-26b-a4b-it", None, "ollama")
    check("[W] the spec example -> two providers", got == [
        ("ollama", "gemma4:e2b-it-qat"), ("openrouter", "google/gemma-4-26b-a4b-it")], repr(got))
    got = p("gemma4:e2b-it-qat, llama3.1:latest", None, "ollama")
    check("[W] no prefix -> the agent's provider (today's behaviour)",
          got == [("ollama", "gemma4:e2b-it-qat"), ("ollama", "llama3.1:latest")], repr(got))
    got = p("hf.co/GnLOLot/MiniCPM5-1B:Q8_0", None, "ollama")
    check("[W] hf.co/... is a model id, not a provider",
          got == [("ollama", "hf.co/GnLOLot/MiniCPM5-1B:Q8_0")], repr(got))
    got = p("openai/gpt-5.4-mini,google/gemma-4-26b-a4b-it", "openrouter", "ollama")
    check("[W] WITH --provider every entry is a model id on it: openai/gpt-5.4-mini stays an "
          "OpenRouter id (never the openai provider)",
          got == [("openrouter", "openai/gpt-5.4-mini"),
                  ("openrouter", "google/gemma-4-26b-a4b-it")], repr(got))


@guarded("[W] diff checks every row's tier before the first row runs")
def test_7_diff_refuses_before_row_one():
    ran = []
    with patched(runner, run_exam=lambda *a, **k: ran.append(a) or boom(), save_result=boom):
        rc, _o, err = _capture(runner.cmd_diff, _ns(
            agent="email-triage", models="stub/gemma4:e2b-it-qat,openrouter/google/gemma-4-26b-a4b-it"))
    check("[W] diff with a frontier row on a local exam -> exit 2", rc == 2, f"rc={rc}")
    check("[W] ...and row 1 (stub, within tier) was NOT run first", ran == [], f"{len(ran)} rows ran")


@guarded("[W] diff end to end: one table, provider per row, unchanged file names")
def test_8_diff_end_to_end_on_stub():
    out_dir = TMP / "results"
    with patched(runner, RESULTS_DIR=out_dir), patched(router.requests, post=boom):
        rc, out, _e = _capture(runner.cmd_diff, _ns(
            agent="email-triage", models="stub/gemma4:e2b-it-qat,stub/llama3.1:latest"))
    names = sorted(p.name for p in out_dir.glob("*.json"))
    check("[W] rc 0 and result files stay <task>__<provider>__<model>.json (pick reads them)",
          rc == 0 and names == ["email-triage__stub__gemma4_e2b-it-qat.json",
                                "email-triage__stub__llama3.1_latest.json"], f"rc={rc} {names}")
    table = out[out.find("\nprovider"):] if "\nprovider" in out else ""
    check("[W] the table has a provider column and each row names its provider",
          table.startswith("\nprovider") and table.count("\nstub ") >= 2, out[-900:])


# ------------------------------------------------------------------ 4. window preflight

@guarded("[W] window preflight refuses an over-window Ollama case before the request")
def test_9_window_refusal_is_isolated_and_offline():
    agent = runner.load_agent("transcript-en")
    exam = _transcript_long_exam()
    with patched(runner, adapter_for=_real_ollama_adapter, ollama_num_ctx=lambda m: 4096), \
            patched(router.requests, post=boom), contextlib.redirect_stdout(io.StringIO()) as buf:
        result = runner.run_exam(agent, exam, "ollama", "gemma4:e2b-it-qat")
    case = result["cases"][0]
    check("[W] the case fails with failed_checks == [termination/window] and NOTHING else",
          case["passed"] is False
          and case.get("failed_checks") == [{"bucket": "termination", "check": "window"}]
          and "window_exceeded" not in case,   # refused, never stamped as if it had run
          repr(case.get("failed_checks")))
    term = (case.get("detail") or {}).get("termination") or {}
    check("[W] the record names cause, estimate > window, and the Modelfile recipe",
          term.get("cause") == "window" and term.get("num_ctx") == 4096
          and term.get("prompt_tokens_est", 0) > 4096
          and "PARAMETER num_ctx 16384" in term.get("fix", "") and "-ctx16k" in term.get("fix", ""),
          repr(term))
    check("[W] the console names the fix", "PARAMETER num_ctx 16384" in buf.getvalue())
    check("[C] got is {} (no answer exists)", case.get("got") == {})


@guarded("[W] a 16k window passes the same case; --allow-truncation runs and stamps")
def test_10_window_pass_and_allow_truncation():
    agent = runner.load_agent("transcript-en")
    exam = _transcript_long_exam()
    post = _CountingPost(json.dumps({"summary": "x"}))
    with patched(runner, adapter_for=_real_ollama_adapter, ollama_num_ctx=lambda m: 16384), \
            patched(router.requests, post=post), contextlib.redirect_stdout(io.StringIO()):
        result = runner.run_exam(agent, exam, "ollama", "gemma4-e4b-ctx16k")
    case = result["cases"][0]
    check("[C] at num_ctx 16384 the request is made and no window check fires",
          post.calls >= 1 and {"bucket": "termination", "check": "window"}
          not in (case.get("failed_checks") or []) and "window_exceeded" not in case,
          f"calls={post.calls} {case.get('failed_checks')}")
    post = _CountingPost(json.dumps({"summary": "x"}))
    with patched(runner, adapter_for=_real_ollama_adapter, ollama_num_ctx=lambda m: 4096), \
            patched(router.requests, post=post), contextlib.redirect_stdout(io.StringIO()):
        result = runner.run_exam(agent, exam, "ollama", "gemma4:e2b-it-qat",
                                 allow_truncation=True)
    case = result["cases"][0]
    check("[W] --allow-truncation: the request IS made and the case is stamped window_exceeded",
          post.calls >= 1 and case.get("window_exceeded") is True
          and {"bucket": "termination", "check": "window"} not in (case.get("failed_checks") or []),
          f"calls={post.calls} keys={sorted(case)}")


@guarded("[W] num_ctx lookup: Modelfile value, 4096 default, fail loud")
def test_11_num_ctx_lookup():
    class _U:
        def __init__(self, payload):
            self.payload = payload

        def __call__(self, req, timeout=None):
            self.url = req.full_url
            self.body = json.loads(req.data)
            p = self.payload

            class R:
                def __enter__(s):
                    return s

                def __exit__(s, *a):
                    return False

                def read(s):
                    return json.dumps(p).encode()
            return R()
    u = _U({"parameters": "temperature                    1\nnum_ctx                        16384"})
    with patched(runner.urllib.request, urlopen=u):
        n = runner.ollama_num_ctx("gemma4-e2b-ctx16k")
    check("[W] num_ctx read from /api/show parameters", n == 16384 and u.url.endswith("/api/show")
          and u.body == {"model": "gemma4-e2b-ctx16k"}, f"{n} {getattr(u, 'url', None)}")
    with patched(runner.urllib.request, urlopen=_U({"parameters": "top_k 64\ntop_p 0.95"})):
        n = runner.ollama_num_ctx("gemma4:e2b-it-qat")
    check("[W] no num_ctx in the Modelfile -> 4096", n == 4096, repr(n))
    with patched(runner.urllib.request, urlopen=_U({"license": "x"})):
        n = runner.ollama_num_ctx("m")
    check("[W] no parameters block at all -> 4096", n == 4096, repr(n))

    def down(req, timeout=None):
        raise runner.urllib.error.URLError("connection refused")
    with patched(runner.urllib.request, urlopen=down):
        try:
            runner.install_window_guard(_real_ollama_adapter(), "ollama", "m")
            ok = False
        except RuntimeError as exc:
            ok = "num_ctx" in str(exc)
    check("[W] an unreadable window refuses the run (never a guessed window)", ok)


@guarded("[W] preflight scope")
def test_12_preflight_scope():
    real = _real_ollama_adapter()
    check("[W] real chat adapter on the Ollama URL is guarded",
          runner._window_guarded(real, "ollama") is True)
    check("[W] systemone (same server, decision endpoint) is not",
          runner._window_guarded(real, "systemone") is False)
    check("[W] stub / openrouter / a non-chat fake / a canned-URL chat adapter are not",
          runner._window_guarded(router.StubAdapter(), "stub") is False
          and runner._window_guarded(real, "openrouter") is False
          and runner._window_guarded(object(), "ollama") is False
          and runner._window_guarded(router.ChatCompletionsAdapter("http://canned/v1"),
                                     "ollama") is False)
    # the stub path never asks Ollama anything
    with patched(runner, ollama_num_ctx=boom), contextlib.redirect_stdout(io.StringIO()):
        res = runner.run_exam(runner.load_agent("email-triage"), runner.load_exam("email-triage"),
                              "stub", "gemma4:e2b-it-qat")
    check("[C] a stub run never calls the window lookup",
          res["train"]["total"] + res["heldout"]["total"] > 0)


@guarded("[W] committed champions pass preflight on every committed case")
def test_13_committed_cases_fit_their_champions():
    # The window each champion runs at, as `ollama show <model> --parameters` printed it on
    # 2026-10-23: the three -ctx16k Modelfiles 16384; the -it-qat tags carry no num_ctx -> 4096.
    windows = {"gemma4-e4b-ctx16k": 16384, "gemma4-e2b-ctx16k": 16384,
               "gemma4:e2b-it-qat": 4096, "gemma4:e4b-it-qat": 4096}
    worst = {}
    for name in runner._all_agents():
        agent = runner.load_agent(name)
        n = windows[agent["model"]]
        for case in runner.load_exam(name)["cases"]:
            text = case.get("input") if isinstance(case.get("input"), str) else json.dumps(case.get("input"))
            est = runner.estimate_prompt_tokens([{"content": agent["system_prompt"]},
                                                 {"content": text}])
            worst[name] = max(worst.get(name, (0, n)), (est, n))
    over = {k: v for k, v in worst.items() if v[0] > v[1]}
    check("[W] no committed case's FIRST call ([system, input]) exceeds its champion's window "
          "(later tool-loop calls are not covered here)",
          not over, repr(over))
    check("[C] the long band is in range: transcript-en worst > 4096 (would fail a 4k model)",
          worst["transcript-en"][0] > 4096, repr(worst["transcript-en"]))


# ------------------------------------------------------------------ 5. live

@guarded("[W] live: tier 0 breach refused, a breaching fallback is never called")
def test_14_live_tier_guard():
    TB = getattr(runner, "TierBreach")
    with patched(runner, adapter_for=boom):
        try:
            runner.live_run_and_log("email-triage", "hello", provider="openrouter",
                                    model="x/y", log=False)
            ok = False
        except TB:
            ok = True
    check("[W] live --provider openrouter on a local exam raises TierBreach, no adapter built", ok)
    rc, _o, err = None, "", ""
    with patched(runner, adapter_for=boom):
        rc, _o, err = _capture(runner.cmd_live, argparse.Namespace(
            agent="email-triage", input="hello", model="x/y", provider="openrouter"))
    check("[W] cmd_live exits 2 with one sentence", rc == 2 and "frontier-tier" in err, f"rc={rc} {err}")


@guarded("[W] live: the committed routes walk never calls a breaching hosted fallback")
def test_14b_live_routes_walk_stops_at_the_tier_boundary():
    # committed routes.yaml: email-triage tier 2 is openrouter (hosted). Tiers 0+1 die;
    # tier 2 must be REFUSED, not called, and the refusal must be on the logged line.
    built = []

    class Dead:
        def generate(self, *a, **k):
            raise runner.TerminationError("scripted death", {"finish_reason": "length",
                                                             "completion_tokens": 0,
                                                             "content_chars": 0})

    def fake_adapter_for(agent, provider=None, timeout=None):
        built.append(provider)
        if provider != "ollama":
            raise Boom(f"adapter built for {provider}")
        return Dead()
    live_dir = TMP / "live-results"
    with patched(runner, adapter_for=fake_adapter_for, RESULTS_DIR=live_dir), \
            contextlib.redirect_stdout(io.StringIO()):
        try:
            runner.live_run_and_log("email-triage", "Please confirm the invoice.")
            raised = None
        except Exception as exc:  # noqa: BLE001
            raised = exc
    check("[W] only the two local tiers were built", built == ["ollama", "ollama"], repr(built))
    check("[W] all run tiers dead -> TerminationError (the outcome of the last tier that ran)",
          isinstance(raised, runner.TerminationError), repr(raised))
    lines = (live_dir / "live" / "email-triage.jsonl").read_text().splitlines() \
        if (live_dir / "live" / "email-triage.jsonl").exists() else []
    line = json.loads(lines[-1]) if lines else {}
    att = line.get("attempts") or []
    check("[W] the logged line records tier 2 refused as tier_breach, model = last tier run",
          len(att) == 3 and att[2].get("refused") == "tier_breach"
          and "frontier-tier" in (att[2].get("reason") or "")
          and att[2].get("provider") == "openrouter" and line.get("model") == "llama3.1:latest"
          and line.get("tier") == 1, json.dumps(line)[:600])


@guarded("[W] live: an over-window input is refused with exit 2")
def test_15_live_window():
    text = next(c for c in runner.load_exam("transcript-en")["cases"] if c["id"] == LONG_ID)["input"]
    with patched(runner, adapter_for=lambda agent, provider=None, timeout=None: _real_ollama_adapter(),
                 ollama_num_ctx=lambda m: 4096), patched(router.requests, post=boom):
        rc, _o, err = _capture(runner.cmd_live, argparse.Namespace(
            agent="transcript-en", input=text, model="gemma4:e2b-it-qat", provider=None))
    check("[W] live transcript-en long input on a 4k model -> exit 2 naming the recipe, no request",
          rc == 2 and "PARAMETER num_ctx 16384" in err, f"rc={rc} {err[:300]}")


# ------------------------------------------------------------------ 6. round-2 (test-honesty refuter)

class _ScriptedPost:
    """requests.post replacement returning scripted assistant contents in order."""

    def __init__(self, contents):
        self.contents, self.calls = list(contents), 0

    def __call__(self, *a, **k):
        self.calls += 1
        return _FakeResp(_chat_ok(self.contents.pop(0) if self.contents else
                                  json.dumps({"answer": "done"})))


@guarded("[W] preflight runs on EVERY call: a tool loop that outgrows the window is refused")
def test_16_every_call_not_just_the_first():
    agent = runner.load_agent("crm-followup")
    exam = runner.load_exam("crm-followup")
    case = next(c for c in exam["cases"] if "turns" not in c and c.get("input"))
    first = runner.estimate_prompt_tokens([{"content": runner._trajectory_system_prompt(agent, case)},
                                           {"content": case["input"]}])
    # call 1 fits (num_ctx = first + 200); the model's tool call carries ~5k tokens of text,
    # which is appended to the history, so call 2 overflows and must never be sent.
    pad = "x" * 20000
    post = _ScriptedPost([json.dumps({"tool": "crm_lookup", "args": {"company": "Acme"},
                                      "note": pad})])
    with patched(runner, adapter_for=_real_ollama_adapter, ollama_num_ctx=lambda m: first + 200), \
            patched(router.requests, post=post), contextlib.redirect_stdout(io.StringIO()):
        res = runner.run_exam(agent, {**exam, "cases": [case]}, "ollama", "gemma4-e2b-ctx16k")
    c = res["cases"][0]
    check("[W] call 1 sent, call 2 (over the window) refused: exactly one request",
          post.calls == 1, f"calls={post.calls}")
    fc = c.get("failed_checks") or []
    check("[W] ...the case fails, the FIRST entry is termination/window (answer_present co-fires, "
          "the declared D2 shape), and the tool evidence gathered before is kept",
          c["passed"] is False and fc[:1] == [{"bucket": "termination", "check": "window"}]
          and all(e["bucket"] != "termination" or e["check"] == "window" for e in fc)
          and ((c.get("detail") or {}).get("termination") or {}).get("cause") == "window"
          and ((c.get("detail") or {}).get("termination") or {}).get("num_ctx") == first + 200
          and ((c.get("detail") or {}).get("termination") or {}).get("prompt_tokens_est", 0) > first + 200
          and (c.get("detail") or {}).get("tools_called"), repr(fc) + " " + str(c.get("detail"))[:300])


def _two_case_transcript_exam():
    exam = runner.load_exam("transcript-en")
    long_c = next(c for c in exam["cases"] if c["id"] == LONG_ID)
    agent = runner.load_agent("transcript-en")
    short = min(exam["cases"], key=lambda c: len(c["input"]))
    est_short = runner.estimate_prompt_tokens([{"content": agent["system_prompt"]},
                                               {"content": short["input"]}])
    assert est_short < 4096, est_short
    return {**exam, "cases": [long_c, short]}, short["id"]


@guarded("[W] window_exceeded is per case (reset between cases)")
def test_17_per_case_reset():
    agent = runner.load_agent("transcript-en")
    exam, short_id = _two_case_transcript_exam()
    post = _CountingPost(json.dumps({"summary": "x"}))
    with patched(runner, adapter_for=_real_ollama_adapter, ollama_num_ctx=lambda m: 4096), \
            patched(router.requests, post=post), contextlib.redirect_stdout(io.StringIO()):
        res = runner.run_exam(agent, exam, "ollama", "gemma4:e2b-it-qat", allow_truncation=True)
    by_id = {c["id"]: c for c in res["cases"]}
    check("[W] the long case is stamped, the short case after it is NOT",
          by_id[LONG_ID].get("window_exceeded") is True and "window_exceeded" not in by_id[short_id],
          repr({k: v.get("window_exceeded") for k, v in by_id.items()}))


@guarded("[W] boundary: est == num_ctx passes, est == num_ctx + 1 is refused")
def test_18_boundary():
    msgs = [{"content": "a" * 400}]   # exactly 100 tokens by chars/4
    est = runner.estimate_prompt_tokens(msgs)
    check("[W] chars/4, rounded up: 400 chars -> 100, 401 -> 101",
          est == 100 and runner.estimate_prompt_tokens([{"content": "a" * 401}]) == 101)
    for n, refuse in ((100, False), (99, True)):
        ad = _real_ollama_adapter()
        ad.window_guard = {"num_ctx": n, "allow": False, "exceeded": False, "model": "m"}
        post = _CountingPost(json.dumps({"ok": 1}))
        with patched(router.requests, post=post):
            try:
                runner.call_model({}, ad, "m", [{"role": "user", "content": "a" * 400}])
                refused = False
            except runner.WindowExceeded:
                refused = True
        check(f"[W] est 100 vs num_ctx {n}: {'refused, no request' if refuse else 'sent'}",
              refused is refuse and post.calls == (0 if refuse else 1),
              f"refused={refused} calls={post.calls}")


@guarded("[W] cmd_run / cmd_diff pass --allow-truncation through to the real run_exam")
def test_19_allow_truncation_wiring():
    two = _two_case_transcript_exam()[0]   # built before load_exam is patched
    for cmd, kw in ((runner.cmd_run, {}), (runner.cmd_diff, {"models": "gemma4:e2b-it-qat"})):
        # under ROOT (cmd_run prints the path relative to it); results/ is gitignored
        out_dir = ROOT / "results" / f"_test_w2_trunc_{cmd.__name__}"
        shutil.rmtree(out_dir, ignore_errors=True)
        post = _CountingPost(json.dumps({"summary": "x"}))
        with patched(runner, adapter_for=_real_ollama_adapter, ollama_num_ctx=lambda m: 4096,
                     RESULTS_DIR=out_dir, load_exam=lambda name: two), \
                patched(router.requests, post=post):
            rc, _o, err = _capture(cmd, _ns(agent="transcript-en", model="gemma4:e2b-it-qat",
                                            allow_truncation=True, **kw))
        files = list(out_dir.glob("*.json"))
        cases = json.loads(files[0].read_text())["cases"] if len(files) == 1 else []
        shutil.rmtree(out_dir, ignore_errors=True)
        stamped = [c["id"] for c in cases if c.get("window_exceeded")]
        check(f"[W] {cmd.__name__} --allow-truncation: rc 0, the long case sent and stamped",
              rc == 0 and stamped == [LONG_ID] and post.calls == 2,
              f"rc={rc} stamped={stamped} calls={post.calls} files={files} {err[-300:]}")


@guarded("[W] diff --allow-tier-breach records tier_breach on the breaching row only")
def test_20_diff_allow_breach():
    saved = []

    def fake_run_exam(agent, exam, provider, model, **kw):
        return {"agent": agent["name"], "provider": provider, "model": model,
                "train": {"passed": 0, "total": 1, "score": 0.0},
                "heldout": {"passed": 0, "total": 1, "score": 0.0}, "cases": []}
    with patched(runner, run_exam=fake_run_exam,
                 save_result=lambda r, **k: saved.append(dict(r)) or TMP / "y.json"):
        rc, out, _e = _capture(runner.cmd_diff, _ns(
            agent="email-triage", models="stub/gemma4:e2b-it-qat,openrouter/google/gemma-4-26b-a4b-it",
            allow_tier_breach=True))
    flags = [(r["provider"], r.get("tier_breach")) for r in saved]
    check("[W] rc 0; only the openrouter row carries tier_breach: true",
          rc == 0 and flags == [("stub", None), ("openrouter", True)], f"rc={rc} {flags}")
    check("[W] the table marks the breaching row", "TIER BREACH" in out, out[-500:])


@guarded("[W] live --allow-tier-breach runs the hosted provider and logs tier_breach")
def test_21_live_allow_breach():
    built = []

    class Ok:
        def generate(self, *a, **k):
            return (json.dumps({"label": "billing"}),
                    {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})

    def fake_adapter_for(agent, provider=None, timeout=None):
        built.append(provider)
        return Ok()
    live_dir = TMP / "live-allow"
    with patched(runner, adapter_for=fake_adapter_for, RESULTS_DIR=live_dir):
        rc, _o, err = _capture(runner.cmd_live, argparse.Namespace(
            agent="email-triage", input="Invoice question", model="x/y", provider="openrouter",
            allow_tier_breach=True))
    path = live_dir / "live" / "email-triage.jsonl"
    line = json.loads(path.read_text().splitlines()[-1]) if path.exists() else {}
    check("[W] the openrouter adapter was built and the logged line says tier_breach: true",
          built == ["openrouter"] and line.get("tier_breach") is True,
          f"rc={rc} built={built} line={str(line)[:300]} {err[-200:]}")


# ------------------------------------------------------------------ 7. round-2 (regression refuter)

@guarded("[W] live: a window refusal on a FALLBACK tier is recorded and the line is still logged")
def test_22_live_fallback_window_refusal_keeps_the_record():
    text = next(c for c in runner.load_exam("transcript-en")["cases"] if c["id"] == LONG_ID)["input"]
    # committed routes.yaml transcript-en: tier 0 gemma4-e4b-ctx16k (16384), tier 1 qwen3:8b
    # (no num_ctx -> 4096). Tier 0 answers empty (a real TerminationError from the real
    # adapter); tier 1 is over its window and must be refused, not sent.
    post = _ScriptedPost([""])
    live_dir = TMP / "live-window"
    with patched(runner, adapter_for=lambda agent, provider=None, timeout=None: _real_ollama_adapter(),
                 ollama_num_ctx=lambda m: 16384 if "ctx16k" in m else 4096, RESULTS_DIR=live_dir), \
            patched(router.requests, post=post), contextlib.redirect_stdout(io.StringIO()):
        try:
            runner.live_run_and_log("transcript-en", text)
            raised = None
        except Exception as exc:  # noqa: BLE001
            raised = exc
    path = live_dir / "live" / "transcript-en.jsonl"
    line = json.loads(path.read_text().splitlines()[-1]) if path.exists() else {}
    att = line.get("attempts") or []
    check("[W] the JSONL line is written: tier 0 dead, tier 1 refused as window, one request",
          len(att) == 2 and att[0].get("termination") and att[1].get("refused") == "window"
          and att[1].get("model") == "qwen3:8b" and att[1].get("num_ctx") == 4096
          and att[1].get("prompt_tokens_est", 0) > 4096 and post.calls == 1,
          f"calls={post.calls} line={json.dumps(line)[:500]}")
    check("[W] the outcome is tier 0's death (TerminationError), not a WindowExceeded crash",
          isinstance(raised, runner.TerminationError), repr(raised))


@guarded("[W] intake: an over-window request exits 2 (refused), no traceback")
def test_23_intake_refuses_with_exit_2():
    text = "Please summarise this call.\n" + "We discussed the renewal at length. " * 600
    with patched(runner, adapter_for=lambda agent, provider=None, timeout=None: _real_ollama_adapter(),
                 ollama_num_ctx=lambda m: 4096), patched(router.requests, post=boom):
        try:
            rc, _o, err = _capture(runner.cmd_intake, argparse.Namespace(input=text))
        except BaseException as exc:  # noqa: BLE001
            rc, err = f"raised {type(exc).__name__}", str(exc)
    check("[W] cmd_intake -> rc 2 naming the Modelfile recipe", rc == 2 and "PARAMETER num_ctx" in err,
          f"rc={rc} {err[:300]}")


@guarded("[W] bakeoff: the long-band probe gets the window preflight too")
def test_24_bakeoff_preflight():
    sent = []

    def post(url, data=None, **kw):
        body = json.loads(data)
        sent.append(sum(len(m.get("content") or "") for m in body["messages"]))
        return _FakeResp(_chat_ok(json.dumps({"summary": "x", "action_items": []})))
    model = "w2-test-4k"   # a name no real run uses: the output file is removed afterwards
    out = runner.ROOT / "results" / f"bakeoff__transcript-en__{model}.json"
    ns = argparse.Namespace(agent="transcript-en", strategies="single-shot", model=model,
                            filter_agent="email-triage", long_min=4200, timeout=None)
    try:
        with patched(runner, ollama_num_ctx=lambda m: 4096), patched(router.requests, post=post):
            rc, outp, _e = _capture(runner.cmd_bakeoff, ns)
    finally:
        out.unlink(missing_ok=True)
    over = [c for c in sent if c / 4 > 4096]
    check("[W] no over-window prompt reaches requests.post; refused cases are named termination:window",
          not over and "termination:window" in outp, f"rc={rc} sent={len(sent)} over={len(over)}")
    check("[C] the short cases still ran (the guard refuses per case, not the run)", len(sent) > 0,
          f"sent={len(sent)}")


@guarded("[W] intake stage 2: an over-window hand-over to the specialist exits 2")
def test_25_intake_stage_two():
    text = "Please recap my day.\n" + "Meeting with Peeters about the renewal went long. " * 400

    class Dispatcher:   # stage 1: task-intake hands the whole request to recap
        def generate(self, *a, **k):
            return (json.dumps({"agent": "recap", "input": text}),
                    {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})

    def fake_adapter_for(agent, provider=None, timeout=None):
        return Dispatcher() if agent["name"] == "task-intake" else _real_ollama_adapter()
    with patched(runner, adapter_for=fake_adapter_for, ollama_num_ctx=lambda m: 4096,
                 live_output_checks=lambda *a, **k: [], RESULTS_DIR=TMP / "intake2"), \
            patched(router.requests, post=boom):
        try:
            rc, _o, err = _capture(runner.cmd_intake, argparse.Namespace(input=text))
        except BaseException as exc:  # noqa: BLE001
            rc, err = f"raised {type(exc).__name__}", str(exc)
    check("[W] stage 2 (recap, 4096) refuses -> rc 2 naming the recipe, no request",
          rc == 2 and "PARAMETER num_ctx" in err, f"rc={rc} {err[:300]}")


@guarded("[W] bakeoff: the TRIAGE adapter (filter-then-recap) is guarded too")
def test_26_bakeoff_triage_adapter():
    triage_model = runner.load_agent("email-triage")["model"]
    sent = []

    def post(url, data=None, **kw):
        body = json.loads(data)
        sent.append(body["model"])
        reply = {"label": "ignore"} if body["model"] == triage_model else {"recap": "x"}
        return _FakeResp(_chat_ok(json.dumps(reply)))
    model = "w2-test-recap"
    out = runner.ROOT / "results" / f"bakeoff__recap__{model}.json"
    ns = argparse.Namespace(agent="recap", strategies="filter-then-recap", model=model,
                            filter_agent="email-triage", long_min=4200, timeout=None)
    try:
        # a 10-token window for the triage model only: every triage call must be refused
        with patched(runner, ollama_num_ctx=lambda m: 10 if m == triage_model else 10 ** 6), \
                patched(router.requests, post=post):
            rc, outp, _e = _capture(runner.cmd_bakeoff, ns)
    finally:
        out.unlink(missing_ok=True)
    check("[W] no triage request is sent; the cases are named termination:window",
          triage_model not in sent and "termination:window" in outp,
          f"rc={rc} triage_sent={sent.count(triage_model)} {outp[-300:]}")


@guarded("[W] diff: the champion is (provider, model) — a stub/<champion> row is a challenger")
def test_27_diff_champion_identity():
    import copy
    real_run_exam = runner.run_exam

    def fake_run_exam(agent, exam, provider, model, **kw):
        res = real_run_exam(agent, exam, "stub", model, **kw)   # stub: offline, deterministic
        if provider == "stub":
            return res
        res = copy.deepcopy(res)                                 # an "ollama" row that fails all
        res["provider"] = provider
        for c in res["cases"]:
            c["passed"] = False
        for sp in ("train", "heldout"):
            res[sp]["passed"], res[sp]["score"] = 0, 0.0
        return res
    out_dir = TMP / "diff-identity"
    with patched(runner, run_exam=fake_run_exam, RESULTS_DIR=out_dir):
        rc, out, _e = _capture(runner.cmd_diff, _ns(
            agent="email-triage", models="gemma4:e2b-it-qat,stub/gemma4:e2b-it-qat"))
    current = [ln for ln in out.splitlines() if "<- current" in ln]
    check("[W] exactly one row is tagged current, the agent-provider one",
          len(current) == 1 and current[0].startswith("ollama "), "\n".join(current))
    check("[W] the verdict swaps to the stub row by its provider-qualified name",
          "swap gemma4:e2b-it-qat -> stub/gemma4:e2b-it-qat" in out, out[-600:])
    with patched(runner, run_exam=fake_run_exam, RESULTS_DIR=out_dir):
        rc, out, _e = _capture(runner.cmd_diff, _ns(agent="email-triage",
                                                    models="stub/gemma4:e2b-it-qat"))
    check("[C] a lone stub/<champion> row does not stand in for the champion: the snapshot is loaded",
          "(snapshot)" in out, out[-600:])


@guarded("[W] --snapshot refuses a run with window-refused cases")
def test_28_snapshot_refuses_window_refusals():
    res = {"cases": [{"id": "a", "detail": {"termination": {"cause": "window"}}},
                     {"id": "b", "passed": True}]}
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            runner.refuse_snapshot_on_outage(res)
        refused = False
    except SystemExit as exc:
        refused = "window" in str(exc)
    check("[W] refuse_snapshot_on_outage exits naming the window refusal", refused)


@guarded("[W] diff --models openrouter/ (no model) is refused, exit 2")
def test_29_empty_model_after_prefix():
    for models in ("openrouter/", "openrouter/ "):
        with patched(runner, run_exam=boom, save_result=boom):
            rc, _o, err = _capture(runner.cmd_diff, _ns(agent="email-triage", models=models))
        check(f"[W] --models {models!r}: rc 2, names the empty entry", rc == 2 and "no model" in err,
              f"rc={rc} {err}")


@guarded("[W] live trajectory: a window refusal AFTER sent calls is logged as a death, not lost")
def test_30_live_midloop_window_is_logged():
    agent = runner.load_agent("crm-followup")
    text = "What is the status of Janssens Bakery?"
    first = runner.estimate_prompt_tokens([{"content": agent["system_prompt"]}, {"content": text}])
    post = _ScriptedPost([json.dumps({"tool": "crm_lookup", "args": {"company": "Janssens Bakery"},
                                      "note": "x" * 20000})])
    live_dir = TMP / "live-midloop"
    with patched(runner, adapter_for=lambda agent, provider=None, timeout=None: _real_ollama_adapter(),
                 ollama_num_ctx=lambda m: first + 200, RESULTS_DIR=live_dir), \
            patched(router.requests, post=post):
        try:
            rc, _o, err = _capture(runner.cmd_live, argparse.Namespace(
                agent="crm-followup", input=text, model="gemma4:e2b-it-qat", provider=None))
        except SystemExit as exc:   # cmd_live's dead-run path is sys.exit(<sentence>)
            rc, err = 1, str(exc.code)
    path = live_dir / "live" / "crm-followup.jsonl"
    line = json.loads(path.read_text().splitlines()[-1]) if path.exists() else {}
    term = line.get("termination") or (line.get("trace") or {}).get("termination") or {}
    check("[W] one request sent, the JSONL line is written with termination cause window",
          post.calls == 1 and term.get("cause") == "window", f"calls={post.calls} line={str(line)[:400]}")
    check("[W] the command still exits non-zero (a run that emitted no answer)",
          rc not in (0, None) or "emitted no answer" in err, f"rc={rc} {err[:200]}")


@guarded("[W] multi-turn: a window refusal on turn 2 is seen by --snapshot refusal and the console")
def test_31_turns_case_window_refusal():
    agent = runner.load_agent("crm-followup")
    exam = runner.load_exam("crm-followup")
    case = next(c for c in exam["cases"] if c.get("turns") and len(c["turns"]) >= 2)
    t0 = case["turns"][0] if isinstance(case["turns"][0], str) else json.dumps(case["turns"][0])
    first = runner.estimate_prompt_tokens([{"content": runner._trajectory_system_prompt(agent, case)},
                                           {"content": t0}])
    # turn 0 answers at length; turn 1's first call then overflows num_ctx = first + 300
    post = _ScriptedPost([json.dumps({"answer": "y" * 4000})])
    with patched(runner, adapter_for=_real_ollama_adapter, ollama_num_ctx=lambda m: first + 300), \
            patched(router.requests, post=post), contextlib.redirect_stdout(io.StringIO()) as buf:
        res = runner.run_exam(agent, {**exam, "cases": [case]}, "ollama", "gemma4-e2b-ctx16k")
    c = res["cases"][0]
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            runner.refuse_snapshot_on_outage(res)
        refused = False
    except SystemExit as exc:
        refused = "window" in str(exc)
    check("[W] --snapshot refuses it (it would otherwise commit as a stable FAIL)", refused,
          str(c.get("detail"))[:400])
    wr = getattr(runner, "window_refused", lambda _c: False)
    check("[W] the case fails and runner.window_refused sees the per-turn refusal",
          c["passed"] is False and wr(c), str(c.get("detail"))[:400])
    check("[W] the console line names the window and the turn", "termination: window (turn" in buf.getvalue(),
          buf.getvalue()[-300:])


@guarded("[W] trajectory: a FIRST call over the window is refused before any request (exam + live)")
def test_32_trajectory_first_call_refused():
    agent = runner.load_agent("crm-followup")
    exam = runner.load_exam("crm-followup")
    case = next(c for c in exam["cases"] if "turns" not in c and c.get("input"))
    first = runner.estimate_prompt_tokens([{"content": runner._trajectory_system_prompt(agent, case)},
                                           {"content": case["input"]}])
    post = _CountingPost(json.dumps({"answer": "x"}))
    with patched(runner, adapter_for=_real_ollama_adapter, ollama_num_ctx=lambda m: first - 50), \
            patched(router.requests, post=post), contextlib.redirect_stdout(io.StringIO()):
        res = runner.run_exam(agent, {**exam, "cases": [case]}, "ollama", "gemma4-e2b-ctx16k")
    c = res["cases"][0]
    term = (c.get("detail") or {}).get("termination") or {}
    check("[W] exam: 0 requests, failed_checks EXACTLY [termination/window], recipe in the record",
          post.calls == 0 and c.get("failed_checks") == [{"bucket": "termination", "check": "window"}]
          and "PARAMETER num_ctx 16384" in term.get("fix", ""),
          f"calls={post.calls} {c.get('failed_checks')} {term}")
    text = case["input"]
    live_dir = TMP / "live-first"
    post = _CountingPost(json.dumps({"answer": "x"}))
    with patched(runner, adapter_for=lambda agent, provider=None, timeout=None: _real_ollama_adapter(),
                 ollama_num_ctx=lambda m: first - 50, RESULTS_DIR=live_dir), \
            patched(router.requests, post=post):
        try:
            rc, _o, err = _capture(runner.cmd_live, argparse.Namespace(
                agent="crm-followup", input=text, model="gemma4:e2b-it-qat", provider=None))
        except SystemExit as exc:
            rc, err = f"SystemExit({str(exc.code)[:80]})", ""
    check("[W] live: exit 2 naming the recipe, 0 requests, no JSONL line (nothing ran)",
          rc == 2 and "PARAMETER num_ctx" in err and post.calls == 0
          and not (live_dir / "live" / "crm-followup.jsonl").exists(), f"rc={rc} calls={post.calls}")


def main() -> int:
    print(f"\n{'FAILED: ' + ', '.join(FAILED) if FAILED else 'all green'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
