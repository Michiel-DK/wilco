#!/usr/bin/env python3
"""llamacpp provider (2026-10-31): a local llama-server can sit an exam, stamp a snapshot, and be checked.

    python3 sandbox/test_llamacpp_provider.py

No server, no model, no network: requests.post and the /props reader are faked; urllib is patched to
raise so no path can reach a real server (W5 lesson). Pins:
  1. the provider exists, is LOCAL tier, defaults to its own port (not Ollama's 11434, not mlx's 8080),
     and LLAMACPP_BASE_URL overrides it; no other provider reads that env var
  2. the request body is byte-identical to Ollama's for the same call (same chat path, nothing added)
  3. server `timings` in a response are carried as metrics["server_timings"]; a response WITHOUT them
     (Ollama's /v1) yields a metrics dict with EXACTLY the old key set
  4. combine_metrics: no step with timings -> old key set; all steps -> per-field sums; some -> None
  5. llamacpp_runtime stamps build_info / model sha256 / n_ctx / template sha256, and REFUSES (SystemExit)
     on a missing build_info, a missing n_ctx, or a model_path that is not a local file
  6. snapshot_preflight on a llamacpp snapshot: a missing stamp field -> RUNTIME:, each field that moved ->
     its own named refusal, an identical live stamp -> None; Ollama is never asked (version_fn raises)
  7. take_snapshot_loads stamps a llamacpp run with llamacpp_runtime and never calls ollama_unload
Each pin seen RED under a hand mutation (PR body).
"""
from __future__ import annotations
import json, os, sys, tempfile, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
import router  # noqa: E402
import runner  # noqa: E402

FAILED: list[str] = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def _no_network(*a, **k):
    raise AssertionError("network call attempted in an offline test")


urllib.request.urlopen = _no_network
runner.urllib.request.urlopen = _no_network

TIMINGS = {"cache_n": 236, "prompt_n": 12, "prompt_ms": 30.9, "prompt_per_token_ms": 2.5,
           "prompt_per_second": 400.0, "predicted_n": 35, "predicted_ms": 661.0,
           "predicted_per_token_ms": 18.9, "predicted_per_second": 52.9}


class _Resp:
    def __init__(self, timings=None):
        self.t = timings

    def raise_for_status(self):
        pass

    def json(self):
        b = {"choices": [{"message": {"role": "assistant", "content": "{\"label\": \"ignore\"}"}, "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 12, "completion_tokens": 35, "total_tokens": 47}}
        if self.t is not None:
            b["timings"] = self.t
        return b


captured: list = []
NEXT = {"timings": None}


def fake_post(url, headers=None, data=None, timeout=None):
    captured.append((url, json.loads(data)))
    return _Resp(NEXT["timings"])


def props(**over):
    d = {"build_info": "b9999-abcdef0", "model_path": over.pop("model_path", None),
         "default_generation_settings": {"n_ctx": 16384}, "chat_template": "{{ messages }}"}
    d.update(over)
    return d


def main() -> int:
    router.requests.post = fake_post
    os.environ.pop("LLAMACPP_BASE_URL", None)
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]

    # 1
    check("1a. PROVIDERS has llamacpp", "llamacpp" in router.PROVIDERS)
    check("1b. llamacpp is LOCAL tier", router.PROVIDER_TIER.get("llamacpp") == "local", str(router.PROVIDER_TIER.get("llamacpp")))
    a = router.get_adapter("llamacpp")
    check("1c. default base_url is its own port (not Ollama's, not mlx's)", a.base_url == "http://127.0.0.1:8081/v1"
          and a.base_url not in (router.PROVIDERS["ollama"]["base_url"], router.PROVIDERS["mlx"]["base_url"]), a.base_url)
    os.environ["LLAMACPP_BASE_URL"] = "http://127.0.0.1:9931/v1"
    check("1d. LLAMACPP_BASE_URL overrides it", router.get_adapter("llamacpp").base_url == "http://127.0.0.1:9931/v1")
    check("1e. no other provider reads LLAMACPP_BASE_URL", router.get_adapter("ollama").base_url == router.PROVIDERS["ollama"]["base_url"].rstrip("/"))
    check("1f. the env override does not mutate the PROVIDERS table", router.PROVIDERS["llamacpp"]["base_url"] == "http://127.0.0.1:8081/v1")
    os.environ["LLAMACPP_BASE_URL"] = ""
    check("1g. an EMPTY LLAMACPP_BASE_URL is ignored (default kept, never an empty URL)",
          router.get_adapter("llamacpp").base_url == "http://127.0.0.1:8081/v1")
    os.environ.pop("LLAMACPP_BASE_URL", None)

    # 1h. the /props reader: URL derivation, env override, timeout (recording fake urlopen)
    seen = []

    class _PR:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"build_info": "b1"}'

    def rec_urlopen(url, timeout=None):
        seen.append((url, timeout)); return _PR()
    runner.urllib.request.urlopen = rec_urlopen
    try:
        runner._llamacpp_props()
        runner._llamacpp_props("http://127.0.0.1:9000/v1/")
        runner._llamacpp_props("http://127.0.0.1:9001")
        os.environ["LLAMACPP_BASE_URL"] = "http://10.0.0.5:7000/v1"
        runner._llamacpp_props()
        os.environ.pop("LLAMACPP_BASE_URL", None)
    finally:
        runner.urllib.request.urlopen = _no_network
    check("1h. /props URL: default, trailing /v1/ stripped, no-/v1 root kept, env override honoured; timeout 10",
          seen == [("http://127.0.0.1:8081/props", 10), ("http://127.0.0.1:9000/props", 10),
                   ("http://127.0.0.1:9001/props", 10), ("http://10.0.0.5:7000/props", 10)], str(seen))

    # 2
    captured.clear()
    router.get_adapter("llamacpp").generate(msgs, "gemma4-e2b")
    router.get_adapter("ollama").generate(msgs, "gemma4-e2b")
    (u1, b1), (u2, b2) = captured
    check("2a. llamacpp posts to <base>/chat/completions", u1 == "http://127.0.0.1:8081/v1/chat/completions", u1)
    check("2b. the body is Ollama's body + exactly `cache_prompt: false` (nothing else added)",
          json.dumps(b1, sort_keys=True) == json.dumps({**b2, "cache_prompt": False}, sort_keys=True), f"{b1} vs {b2}")
    check("2c. no other provider sends cache_prompt", "cache_prompt" not in b2)

    # 3
    NEXT["timings"] = TIMINGS
    _, meta_t = router.get_adapter("llamacpp").generate(msgs, "m")
    NEXT["timings"] = None
    _, meta_n = router.get_adapter("ollama").generate(msgs, "m")
    check("3a. server timings carried (5 fields, values verbatim)", meta_t.get("server_timings") ==
          {"prompt_n": 12, "prompt_ms": 30.9, "predicted_n": 35, "predicted_ms": 661.0, "cache_n": 236}, str(meta_t.get("server_timings")))
    check("3b. a response without timings carries no server_timings key", "server_timings" not in meta_n, str(sorted(meta_n)))
    m_t = runner._call_metrics(meta_t, 700.0, 0)
    m_n = runner._call_metrics(meta_n, 700.0, 0)
    OLD = {"prompt_tokens", "completion_tokens", "total_tokens", "wall_ms", "retries", "content_chars",
           "reasoning_chars", "finish_reason", "truncated_calls", "unanswered_calls"}
    check("3c. metrics without timings have EXACTLY the old key set", set(m_n) == OLD, str(sorted(set(m_n) ^ OLD)))
    check("3d. metrics with timings = old keys + server_timings", set(m_t) == OLD | {"server_timings"}, str(sorted(m_t)))

    # 4
    c0 = runner.combine_metrics([m_n, m_n])
    check("4a. combine without timings: old combined key set, no server_timings", "server_timings" not in c0, str(sorted(c0)))
    c2 = runner.combine_metrics([m_t, m_t])
    check("4b. combine with timings on every step: per-field sums", c2.get("server_timings") ==
          {"prompt_n": 24, "prompt_ms": 61.8, "predicted_n": 70, "predicted_ms": 1322.0, "cache_n": 472}, str(c2.get("server_timings")))
    m_null = runner._call_metrics({**meta_t, "server_timings": {**meta_t["server_timings"], "prompt_ms": None}}, 700.0, 0)
    cn = runner.combine_metrics([m_t, m_null])
    check("4d. a null timing field on one step makes that field None (unknown is not zero), others still sum",
          cn.get("server_timings", {}).get("prompt_ms") is None and cn["server_timings"]["predicted_ms"] == 1322.0,
          str(cn.get("server_timings")))
    alias = runner._call_metrics(meta_t, 700.0, 0)
    alias["server_timings"]["prompt_ms"] = -1
    check("4e. the metrics dict copies server_timings (mutating it does not touch the response meta)",
          meta_t["server_timings"]["prompt_ms"] == 30.9)
    c1 = runner.combine_metrics([m_t, m_n])
    check("4c. combine with timings on SOME steps: None (unknown), never a partial sum", "server_timings" in c1
          and c1["server_timings"] is None, str(c1.get("server_timings")))

    # 5
    with tempfile.TemporaryDirectory() as td:
        gguf = Path(td) / "m.gguf"
        gguf.write_bytes(b"GGUF" + b"\0" * 64)
        SET = {"cache_type_k": "unset", "cache_type_v": "unset", "flash_attn": "unset", "server_args_sha": "a" * 64}
        rt = runner.llamacpp_runtime(props_fn=lambda: props(model_path=str(gguf)), settings_fn=lambda: dict(SET))
        import hashlib
        check("5a. stamp: version = build_info", rt.get("version") == "b9999-abcdef0", str(rt))
        check("5b. stamp: model_sha = sha256 of the served file", rt.get("model_sha") == hashlib.sha256(gguf.read_bytes()).hexdigest())
        check("5c. stamp: n_ctx and chat_template_sha and loads_are_samples", rt.get("n_ctx") == 16384
              and rt.get("chat_template_sha") == hashlib.sha256(b"{{ messages }}").hexdigest() and rt.get("loads_are_samples") is True, str(rt))

        def refuses(**over):
            try:
                runner.llamacpp_runtime(props_fn=lambda: props(**{"model_path": str(gguf), **over}),
                                        settings_fn=lambda: dict(SET))
            except SystemExit:
                return True
            return False
        check("5d. no build_info -> SystemExit", refuses(build_info=""))
        check("5e. no n_ctx -> SystemExit", refuses(default_generation_settings={}))
        check("5f. model_path not a local file -> SystemExit", refuses(model_path=str(Path(td) / "missing.gguf")))
        cwd = os.getcwd()
        os.chdir(td)
        try:
            check("5g. a RELATIVE model_path is refused even when it resolves here", Path("m.gguf").is_file() and refuses(model_path="m.gguf"))
        finally:
            os.chdir(cwd)
        check("5h. the stamp carries cache_type_k / cache_type_v / flash_attn / server_args_sha from the settings reader",
              all(rt.get(k) == SET[k] for k in SET), str(rt))
        def P(fn):
            out = runner.llamacpp_server_settings(fn)
            out.pop("server_args_sha", None)
            return out
        tok = lambda *t: (lambda: ["/opt/llama-server", *t, "PATH=/usr/bin"])  # noqa: E731
        check("5i. CLI short flags parsed", P(tok("-ctk", "q8_0", "-ctv", "q4_0", "-fa", "on")) ==
              {"cache_type_k": "q8_0", "cache_type_v": "q4_0", "flash_attn": "on"}, str(P(tok("-ctk", "q8_0", "-ctv", "q4_0", "-fa", "on"))))
        check("5j. long flags and --flag=value parsed", P(tok("--cache-type-k=q8_0", "--cache-type-v", "f16", "--flash-attn=off")) ==
              {"cache_type_k": "q8_0", "cache_type_v": "f16", "flash_attn": "off"})
        check("5k. env vars used when no flag; nothing -> 'unset'", P(tok("LLAMA_ARG_CACHE_TYPE_K=q4_0")) ==
              {"cache_type_k": "q4_0", "cache_type_v": "unset", "flash_attn": "unset"})
        check("5l. the CLI flag wins over the env var", P(tok("-ctk", "f16", "LLAMA_ARG_CACHE_TYPE_K=q4_0"))["cache_type_k"] == "f16")

        def p_refuses(t):
            try:
                P(t)
            except SystemExit:
                return True
            return False
        check("5m. a flag given twice -> SystemExit", p_refuses(tok("-ctk", "q8_0", "--cache-type-k", "f16")))
        def no_tools(name):
            raise AssertionError(f"tool lookup {name!r} reached for a remote host")
        try:
            runner._llamacpp_listener_tokens("http://10.0.0.5:8081/v1", which_fn=no_tools)
            msg = ""
        except SystemExit as e:
            msg = str(e)
        except AssertionError as e:
            msg = f"ASSERT {e}"
        check("5n. a non-loopback llamacpp host -> SystemExit naming loopback, before any lsof/ps lookup",
              "not loopback" in msg, msg)
        # 5p. the argv sha: changes on any other flag (-ub, --lora), on an LLAMA_ARG_* env var, not on unrelated env
        A = runner.llamacpp_server_args_sha
        base_t = ["/opt/llama-server", "-m", "/m.gguf", "-c", "16384", "PATH=/usr/bin", "HOME=/x"]
        check("5p. server_args_sha moves on -ub / --lora / LLAMA_ARG_* and NOT on an unrelated env var",
              A(base_t[:5] + ["-ub", "512"] + base_t[5:]) != A(base_t)
              and A(base_t[:5] + ["--lora", "/a.gguf"] + base_t[5:]) != A(base_t)
              and A(base_t + ["LLAMA_ARG_N_GPU_LAYERS=99"]) != A(base_t)
              and A(base_t + ["TERM=xterm"]) == A(base_t))
        tk = ["/opt/llama-server", "-ub", "512", "PATH=/usr/bin", "LLAMA_ARG_N_GPU_LAYERS=99"]
        check("5p2. the settings reader stamps server_args_sha of the listener's own tokens",
              runner.llamacpp_server_settings(lambda: list(tk))["server_args_sha"] == A(tk))
        check("5q. a flag with no value (last token, or followed by another flag / an env token) -> SystemExit",
              p_refuses(tok("-fa")) and p_refuses(tok("-fa", "-c", "16384")) and p_refuses(lambda: ["/s", "-ctk", "PATH=/x"]))

        # 5r. the DARWIN listener path through a fake subprocess: argv of each call pinned, refusals pinned
        calls = []

        class _CP:
            def __init__(self, out, rc=0):
                self.stdout, self.returncode = out, rc

        def fake_run(scenario):
            def run(argv, capture_output=True, text=True, timeout=None):
                calls.append(argv)
                if "lsof" in argv[0]:
                    return _CP({"one": "4242\n", "two": "4242\n4343\n", "none": "", "wrong": "4242\n"}[scenario])
                if argv[1:4] == ["-p", "4242", "-o"]:
                    return _CP("llama-server\n" if scenario != "wrong" else "docker\n")
                return _CP("/opt/llama-server -ctk q8_0 -m /m.gguf PATH=/usr/bin LLAMA_ARG_FLASH_ATTN=on\n")
            return run
        which = lambda name: f"/usr/bin/{name}"  # noqa: E731
        saved_run = runner.subprocess.run
        try:
            runner.subprocess.run = fake_run("one")
            calls.clear()
            toks = runner._llamacpp_listener_tokens("http://127.0.0.1:8081/v1", platform="darwin", which_fn=which)
            got_calls = list(calls)
            refusals = {}
            for sc in ("two", "none", "wrong"):
                runner.subprocess.run = fake_run(sc)
                try:
                    runner._llamacpp_listener_tokens("http://127.0.0.1:8081/v1", platform="darwin", which_fn=which)
                    refusals[sc] = ""
                except SystemExit as e:
                    refusals[sc] = str(e)
        finally:
            runner.subprocess.run = saved_run
        check("5r. darwin: lsof on the llamacpp port, then ps comm, then `ps -E -ww -p <pid> -o command=`",
              got_calls == [["/usr/bin/lsof", "-nP", "-iTCP:8081", "-sTCP:LISTEN", "-t"],
                            ["/usr/bin/ps", "-p", "4242", "-o", "comm="],
                            ["/usr/bin/ps", "-E", "-ww", "-p", "4242", "-o", "command="]], str(got_calls))
        check("5s. darwin tokens parse to the stamp (q8_0 from argv, flash-attn from env)",
              P(lambda: toks) == {"cache_type_k": "q8_0", "cache_type_v": "unset", "flash_attn": "on"}, str(toks))
        check("5t. 2 listeners / 0 listeners / a listener that is not llama-server -> SystemExit, each named",
              "found ['4242', '4343']" in refusals["two"] and "found []" in refusals["none"]
              and "not 'llama-server'" in refusals["wrong"], str(refusals))
        pr = Path(td) / "proc" / "4242"
        pr.mkdir(parents=True)
        (pr / "cmdline").write_bytes(b"/opt/llama-server\0-ctk\0q8_0\0-m\0/m.gguf\0")
        (pr / "environ").write_bytes(b"PATH=/usr/bin\0LLAMA_ARG_FLASH_ATTN=on\0")
        lt = runner._linux_proc_tokens("4242", Path(td) / "proc")
        check("5o. linux: argv from cmdline AND env from environ, both parsed",
              P(lambda: lt) == {"cache_type_k": "q8_0", "cache_type_v": "unset", "flash_attn": "on"}, str(lt))

        # 6
        exam = runner.load_exam("email-triage")
        snap = {"provider": "llamacpp", "model": "m", "runtime": dict(rt),
                "cases": [{"id": c["id"], "split": c["split"], "passed": True} for c in exam["cases"]]}

        def no_ollama():
            raise AssertionError("ollama asked for a llamacpp snapshot")
        same = lambda: dict(rt)  # noqa: E731
        check("6a. identical live stamp -> no refusal; Ollama never asked",
              runner.snapshot_preflight(snap, exam, version_fn=no_ollama, server_settings_fn=no_ollama,
                                        llamacpp_runtime_fn=same) is None)
        SEVEN = ["version", "model_sha", "n_ctx", "chat_template_sha", "cache_type_k", "cache_type_v", "flash_attn",
                 "server_args_sha"]
        check("6-. the stamp-field list is exactly the eight named fields (pinned by name, not by the constant)",
              list(runner.LLAMACPP_STAMP_FIELDS) == SEVEN, str(runner.LLAMACPP_STAMP_FIELDS))
        moved = []
        for f in SEVEN:
            live = {**rt, f: "different"}
            cause = runner.snapshot_preflight(snap, exam, version_fn=no_ollama, llamacpp_runtime_fn=lambda live=live: live)
            if not (cause or "").startswith(f.upper() + ":"):
                moved.append((f, cause))
        check("6b. each stamped field that moved gets its own named refusal", moved == [], str(moved))
        missing = []
        for f in SEVEN:
            s2 = {**snap, "runtime": {k: v for k, v in rt.items() if k != f}}
            cause = runner.snapshot_preflight(s2, exam, version_fn=no_ollama, llamacpp_runtime_fn=same)
            if not (cause or "").startswith("RUNTIME:"):
                missing.append((f, cause))
        check("6c. a snapshot missing any stamped field -> RUNTIME: (never read as a match)", missing == [], str(missing))

        # 7
        unloaded = []
        saved = (runner.ollama_unload, runner.run_exam, runner.save_result)
        runner.ollama_unload = lambda m: unloaded.append(m)
        runner.run_exam = lambda *a, **k: {"agent": "email-triage", "provider": "llamacpp", "model": "m",
                                           "cases": [{"id": "x", "split": "train", "passed": True}],
                                           "train": {"passed": 1, "total": 1, "score": 1.0},
                                           "heldout": {"passed": 0, "total": 0, "score": None}}
        runner.save_result = lambda *a, **k: None
        try:
            _agg, runtime = runner.take_snapshot_loads(runner.load_agent("email-triage"), exam, "llamacpp", "m", 3,
                                                       llamacpp_runtime_fn=same, server_settings_fn=no_ollama)
        finally:
            runner.ollama_unload, runner.run_exam, runner.save_result = saved
        check("7a. take_snapshot_loads stamps the llamacpp runtime", runtime == rt, str(runtime))
        check("7b. ... and never unloads through Ollama", unloaded == [], str(unloaded))

    # 8. REAL ENTRY POINT: run_exam on the stub and on a fake-post Ollama adapter -> per-case metrics have
    #    EXACTLY the old key set (no server_timings), so nothing upstream of _call_metrics adds a key either
    import contextlib, io
    OLD_CASE = {"prompt_tokens", "completion_tokens", "total_tokens", "wall_ms", "retries", "content_chars",
                "reasoning_chars", "finish_reason", "truncated_calls", "unanswered_calls"}
    OLD_TOTAL = OLD_CASE - {"finish_reason"}
    agent, ex = runner.load_agent("email-triage"), runner.load_exam("email-triage")
    with contextlib.redirect_stdout(io.StringIO()):
        res_stub = runner.run_exam(agent, ex, "stub", agent["model"])
    NEXT["timings"] = None
    real_nctx = runner.ollama_num_ctx
    runner.ollama_num_ctx = lambda *a, **k: 16384   # the window lookup is /api/show on the live server; faked
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            res_oll = runner.run_exam(agent, ex, "ollama", "fake-model")
    finally:
        runner.ollama_num_ctx = real_nctx
    bad = []
    for name, res in (("stub", res_stub), ("ollama", res_oll)):
        for cse in res["cases"]:
            m = (cse.get("detail") or {}).get("metrics")
            if m is not None and set(m) != OLD_CASE:
                bad.append((name, cse["id"], sorted(set(m) ^ OLD_CASE)))
        if res["metrics_totals"] and set(res["metrics_totals"]) - {"unmetered_cases", "complete"} != OLD_TOTAL:
            bad.append((name, "totals", sorted(set(res["metrics_totals"]) ^ OLD_TOTAL)))
    n_oll = sum(1 for cse in res_oll["cases"] if (cse.get("detail") or {}).get("metrics"))
    check("8a. through run_exam: stub + fake Ollama per-case and total metrics keep EXACTLY the old key sets",
          bad == [] and n_oll > 0, str(bad[:3]))
    NEXT["timings"] = TIMINGS
    with contextlib.redirect_stdout(io.StringIO()):
        res_ll = runner.run_exam(agent, ex, "llamacpp", "fake-model")
    NEXT["timings"] = None
    st = (res_ll.get("metrics_totals") or {}).get("server_timings")
    check("8b. through run_exam on llamacpp: totals carry summed server_timings", isinstance(st, dict)
          and st["predicted_n"] == 35 * len(ex["cases"]), str(st))

    print(f"\n{len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
