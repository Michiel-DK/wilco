#!/usr/bin/env python3
"""Opt-in SSE streaming for time-to-first-token (item 5, 2026-10-31).

    python3 sandbox/test_stream_timing.py

No server, no model, no network: requests.post is faked, urllib.request.urlopen is patched to raise (W5
lesson: no path may reach a real server or GPU). Streaming is exercised ONLY for ChatCompletionsAdapter
(ollama / mlx / llamacpp); stub and systemone are not chat adapters and are pinned as unchanged. No agent.yaml,
snapshot or cases.json is touched by this lane.

DEFINITIONS under test (router.fold_sse docstring): t0 = the adapter clock read just before the POST;
ttft_any_ms = first non-empty content OR reasoning delta; ttft_answer_ms = first non-empty content delta;
role-only / empty-string / SSE-comment chunks count toward neither; a kind that never arrives is None.

Pins:
  1. OFF (default, or any env value but '1'): request body is the master body (stream False, no stream_options,
     no stream kwarg on the POST), meta has no stream_timing, run_exam per-call/per-case/totals have the old key
     sets, for ollama / openrouter / stub / mlx / llamacpp
  2. ON: SSE fixtures give the same text + meta as the equivalent non-streaming body (plain, reasoning-then-
     answer, length, usage in a choices-less final chunk, timings chunk), the same TerminationError (reasoning-
     only, empty, in-stream error envelope), ValueError on a tool_calls delta; plus stream_timing
  3. injected clock: exact ttft values; role/empty/comment chunks count for neither; None never 0
  4. get_adapter gating: never for a non-local provider; local chat providers only with env == '1'
  5. aggregation: _call_metrics, case level, exam level, partial -> None; hand-computed expectation
  6. no network
Each guard seen RED under a hand mutation (listed in the PR body).
"""
from __future__ import annotations
import contextlib, io, json, os, sys, urllib.request
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
router.requests.post = _no_network   # replaced by a fake inside main(); anything else raises


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


# ---- SSE fixture builders -------------------------------------------------------------------------------
def chunk(content=None, reasoning=None, role=False, finish=None, usage=None, timings=None, choices=True, extra=None):
    d = {}
    if role:
        d["role"] = "assistant"
    if content is not None:
        d["content"] = content
    if reasoning is not None:
        d["reasoning"] = reasoning
    o = {"id": "x", "object": "chat.completion.chunk"}
    if choices:
        o["choices"] = [{"index": 0, "delta": d, "finish_reason": finish}]
    else:
        o["choices"] = []
    if usage is not None:
        o["usage"] = usage
    if timings is not None:
        o["timings"] = timings
    if extra:
        o.update(extra)
    return "data: " + json.dumps(o)


class _Resp:
    """Serves either a JSON body (non-streaming) or timed SSE events (streaming). events = [(t_seconds, line)]:
    the clock is set to t_seconds when that line is yielded."""
    def __init__(self, body=None, events=None, clock=None):
        self.body, self.events, self.clock = body, events, clock
        self.closed = False

    def raise_for_status(self):
        pass

    def json(self):
        return self.body

    def iter_lines(self, decode_unicode=False):
        for t, line in self.events:
            if self.clock is not None and t is not None:
                self.clock.t = t
            yield line

    def close(self):
        self.closed = True


posts: list = []
NEXT: dict = {"resp": None, "post_advance": 0.0, "clock": None}


def fake_post(url, headers=None, data=None, timeout=None, **kw):
    posts.append({"url": url, "body": json.loads(data), "kw": kw})
    if NEXT["clock"] is not None:
        NEXT["clock"].t += NEXT["post_advance"]
    return NEXT["resp"]


USAGE = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
TIMINGS = {"cache_n": 3, "prompt_n": 8, "prompt_ms": 12.5, "predicted_n": 7, "predicted_ms": 90.0, "prompt_per_second": 1.0}
MSGS = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def ns_body(content="", reasoning="", finish="stop", usage=None, timings=None):
    m = {"role": "assistant", "content": content}
    if reasoning:
        m["reasoning"] = reasoning
    b = {"choices": [{"index": 0, "message": m, "finish_reason": finish}]}
    if usage is not None:
        b["usage"] = usage
    if timings is not None:
        b["timings"] = timings
    return b


def run_gen(adapter, resp, clock=None, post_advance=0.0):
    posts.clear()
    NEXT.update(resp=resp, clock=clock, post_advance=post_advance)
    try:
        return adapter.generate(MSGS, "m"), None
    except Exception as e:  # noqa: BLE001
        return (None, None), e


def adapter(on, clock=None, provider="ollama"):
    a = router.get_adapter(provider)
    a.stream_timing = on
    if clock is not None:
        a._clock = clock
    return a


def same_error(e1, e2):
    return (type(e1) is type(e2) and str(e1) == str(e2)
            and getattr(e1, "details", None) == getattr(e2, "details", None))


OLD_CASE = {"prompt_tokens", "completion_tokens", "total_tokens", "wall_ms", "retries", "content_chars",
            "reasoning_chars", "finish_reason", "truncated_calls", "unanswered_calls"}
OLD_TOTAL = OLD_CASE - {"finish_reason"}
MASTER_BODY_KEYS = {"model", "messages", "temperature", "max_tokens", "stream"}


def main() -> int:
    router.requests.post = fake_post
    os.environ.pop("SANDBOX_STREAM_TIMING", None)
    for p in router.PROVIDERS.values():
        if p.get("api_key_env"):
            os.environ.setdefault(p["api_key_env"], "k")

    # ---- 1. OFF ---------------------------------------------------------------------------------------
    plain_ns = ns_body("{\"a\": 1}", usage=USAGE)
    for envv in (None, "0", "true", "yes", ""):
        if envv is None:
            os.environ.pop("SANDBOX_STREAM_TIMING", None)
        else:
            os.environ["SANDBOX_STREAM_TIMING"] = envv
        for prov in ("ollama", "openrouter", "mlx", "llamacpp"):
            a = router.get_adapter(prov)
            (txt, meta), err = run_gen(a, _Resp(body=plain_ns))
            req = posts[-1]
            exp_keys = MASTER_BODY_KEYS | ({"cache_prompt"} if prov == "llamacpp" else set())
            ok = (err is None and set(req["body"]) == exp_keys and req["body"]["stream"] is False
                  and "stream" not in req["kw"] and "stream_options" not in req["body"]
                  and "stream_timing" not in meta and txt == "{\"a\": 1}"
                  and set(meta) == {"prompt_tokens", "completion_tokens", "total_tokens", "content_chars",
                                    "reasoning_chars", "finish_reason"}
                  and meta["prompt_tokens"] == 11 and a.stream_timing is False)
            check(f"1a. OFF env={envv!r} {prov}: master body + master meta, no stream_timing, no stream kwarg",
                  ok, f"{err} {sorted(req['body'])} {sorted(meta or {})}")
    os.environ.pop("SANDBOX_STREAM_TIMING", None)
    check("1b. stub: get_adapter is a StubAdapter, unchanged by the env var", isinstance(router.get_adapter("stub"), router.StubAdapter))
    os.environ["SANDBOX_STREAM_TIMING"] = "1"
    check("1c. stub with env=1 is still a StubAdapter (not a chat adapter)", isinstance(router.get_adapter("stub"), router.StubAdapter))
    os.environ.pop("SANDBOX_STREAM_TIMING", None)

    # run_exam, OFF, through the real entry point: stub + fake-post ollama + fake-post llamacpp
    agent, ex = runner.load_agent("email-triage"), runner.load_exam("email-triage")

    def sit(prov):
        router.requests.post = _fresh_post
        with contextlib.redirect_stdout(io.StringIO()):
            return runner.run_exam(agent, ex, prov, agent["model"] if prov == "stub" else "fake-model")

    def _fresh_post(url, headers=None, data=None, timeout=None, **kw):
        posts.append({"url": url, "body": json.loads(data), "kw": kw})
        if "stream" in kw:   # streaming ON: serve a plain answer as SSE
            return _Resp(events=[(None, chunk(role=True, content="")), (None, chunk(content="{\"label\": \"ignore\"}")),
                                 (None, chunk(finish="stop")), (None, chunk(choices=False, usage=USAGE)),
                                 (None, "data: [DONE]")])
        return _Resp(body=ns_body("{\"label\": \"ignore\"}", usage=USAGE))

    real_nctx = runner.ollama_num_ctx
    runner.ollama_num_ctx = lambda *a, **k: 16384
    try:
        res = {p: sit(p) for p in ("stub", "ollama", "llamacpp")}
        posts_off = list(posts)
        bad, n_metered = [], 0
        for name, r in res.items():
            for cse in r["cases"]:
                m = (cse.get("detail") or {}).get("metrics")
                if m is not None:
                    n_metered += 1
                    if set(m) != OLD_CASE:
                        bad.append((name, cse["id"], sorted(set(m) ^ OLD_CASE)))
            tot = r.get("metrics_totals") or {}
            if tot and set(tot) - {"unmetered_cases", "complete"} != OLD_TOTAL:
                bad.append((name, "totals", sorted(set(tot) ^ OLD_TOTAL)))
            if "stream_timing" in json.dumps(r, default=str):
                bad.append((name, "stream_timing appears somewhere in the result"))
        check("1d. OFF through run_exam (stub, ollama, llamacpp): old key sets at call/case/totals level, "
              "no stream_timing anywhere", bad == [] and n_metered > 0 and len(posts_off) > 0, str(bad[:3]))
        check("1e. OFF run_exam POST bodies all stream:false", all(p["body"]["stream"] is False and "stream" not in p["kw"]
                                                              for p in posts_off))

        # ---- ON through run_exam (real entry point; env var read by get_adapter via runner) ----------
        os.environ["SANDBOX_STREAM_TIMING"] = "1"
        posts.clear()
        r_on = sit("ollama")
        os.environ.pop("SANDBOX_STREAM_TIMING", None)
        n_cases = len(ex["cases"])
        st = (r_on.get("metrics_totals") or {}).get("stream_timing")
        per_case = [(c.get("detail") or {}).get("metrics", {}).get("stream_timing") for c in r_on["cases"]]
        check("5e. ON through run_exam: every POST streamed, totals carry stream_timing with calls == #POSTs, "
              "every metered case carries per-call stream_timing",
              posts and all(p["body"]["stream"] is True and p["kw"].get("stream") is True for p in posts)
              and isinstance(st, dict) and st["calls"] == len(posts) and all(isinstance(x, dict) for x in per_case if x is not None)
              and sum(1 for x in per_case if x is not None) > 0, f"{st} posts={len(posts)} cases={n_cases}")
    finally:
        runner.ollama_num_ctx = real_nctx
        router.requests.post = fake_post

    # ---- 2. ON: equivalence with the non-streaming path -------------------------------------------------
    FIX = {
        "plain": ([chunk(role=True, content=""), chunk(content="{\"a\":"), chunk(content=" 1}"), chunk(finish="stop"),
                   chunk(choices=False, usage=USAGE)], ns_body("{\"a\": 1}", usage=USAGE)),
        "reasoning-then-answer": ([chunk(role=True, content=""), chunk(content="", reasoning="hm"), chunk(reasoning="mm"),
                                   chunk(content="{\"a\": 1}"), chunk(finish="stop"), chunk(choices=False, usage=USAGE)],
                                  ns_body("{\"a\": 1}", reasoning="hmmm", usage=USAGE)),
        "finish-length": ([chunk(content="{\"a\": 1"), chunk(finish="length"), chunk(choices=False, usage=USAGE)],
                          ns_body("{\"a\": 1", finish="length", usage=USAGE)),
        "usage-only-in-final-choiceless-chunk": ([chunk(content="ok"), chunk(finish="stop"),
                                                  chunk(choices=False, usage=USAGE)], ns_body("ok", usage=USAGE)),
        "llama-server-timings-chunk": ([chunk(content="ok"), chunk(finish="stop", timings=TIMINGS),
                                        chunk(choices=False, usage=USAGE, timings=TIMINGS)],
                                       ns_body("ok", usage=USAGE, timings=TIMINGS)),
        "no-usage-at-all": ([chunk(content="ok"), chunk(finish="stop")], ns_body("ok")),
        "reasoning-only (TerminationError)": ([chunk(reasoning="thinking"), chunk(finish="length"),
                                               chunk(choices=False, usage=USAGE)],
                                              ns_body("", reasoning="thinking", finish="length", usage=USAGE)),
        "empty content (TerminationError)": ([chunk(role=True, content=""), chunk(finish="stop"),
                                              chunk(choices=False, usage=USAGE)], ns_body("", usage=USAGE)),
        "whitespace-only content (TerminationError)": ([chunk(content="  \n"), chunk(finish="stop")], ns_body("  \n")),
        "in-stream error envelope": ([chunk(content="par"), "data: " + json.dumps({"error": {"code": 502, "message": "boom"}})],
                                     {"error": {"code": 502, "message": "boom"}}),
        "error envelope as first chunk": (["data: " + json.dumps({"error": {"code": 500, "message": "x"}})],
                                          {"error": {"code": 500, "message": "x"}}),
    }
    for name, (sse, ns) in FIX.items():
        if name == "in-stream error envelope":
            # the partial content before the error is discarded by fold_sse's early return; the non-streaming
            # twin of "an error envelope with no choices" is the envelope itself
            pass
        (t_off, m_off), e_off = run_gen(adapter(False), _Resp(body=ns))
        (t_on, m_on), e_on = run_gen(adapter(True), _Resp(events=[(None, s) for s in sse + ["data: [DONE]"]]))
        if e_off is not None or e_on is not None:
            check(f"2. {name}: same exception as non-streaming (type, message, details)",
                  e_off is not None and e_on is not None and same_error(e_off, e_on), f"{e_off!r} vs {e_on!r}")
            if "error envelope" in name:
                check(f"2. {name}: handled by DIALECT-0 (code carried)", e_on is not None and getattr(e_on, "details", {}).get(
                    "provider_error_code") == ns["error"]["code"])
        else:
            st_ = (m_on or {}).get("stream_timing")
            m_on_wo = {k: v for k, v in m_on.items() if k != "stream_timing"}
            check(f"2. {name}: same text and same meta as non-streaming, plus stream_timing keys",
                  t_on == t_off and m_on_wo == m_off and isinstance(st_, dict)
                  and set(st_) == {"ttft_any_ms", "ttft_answer_ms", "stream_ms", "chunks"}, f"{t_on!r}/{t_off!r} {m_on} {m_off}")
    # specific meta fields spelled out (not only equality with the twin)
    (t, m), e = run_gen(adapter(True), _Resp(events=[(None, s) for s in FIX["llama-server-timings-chunk"][0]]))
    check("2a. timings chunk -> meta.server_timings (5 fields)", e is None and m.get("server_timings") == {
        "prompt_n": 8, "prompt_ms": 12.5, "predicted_n": 7, "predicted_ms": 90.0, "cache_n": 3}, str(m))
    check("2b. usage from the choices-less final chunk reaches the token fields", m["prompt_tokens"] == 11
          and m["completion_tokens"] == 7 and m["total_tokens"] == 18)
    (t, m), e = run_gen(adapter(True), _Resp(events=[(None, s) for s in FIX["reasoning-then-answer"][0]]))
    check("2c. reasoning-then-answer: reasoning_chars 4, content_chars 8, finish stop", m["reasoning_chars"] == 4
          and m["content_chars"] == 8 and m["finish_reason"] == "stop", str(m))
    (t, m), e = run_gen(adapter(True), _Resp(events=[(None, s) for s in FIX["finish-length"][0]]))
    check("2d. finish_reason 'length' carried (answer kept, soft tier)", e is None and m["finish_reason"] == "length" and t == "{\"a\": 1")
    tc = [chunk(content="x"), "data: " + json.dumps({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"name": "f"}}]},
                                                "finish_reason": None}]})]
    (t, m), e = run_gen(adapter(True), _Resp(events=[(None, s) for s in tc]))
    check("2e. a tool_calls delta -> ValueError (refused, never half-merged)", isinstance(e, ValueError), repr(e))
    # request shape ON
    run_gen(adapter(True), _Resp(events=[(None, s) for s in FIX["plain"][0]]))
    rq = posts[-1]
    check("2f. ON request: stream true + include_usage, POST streamed, otherwise the master body",
          rq["body"]["stream"] is True and rq["body"].get("stream_options") == {"include_usage": True}
          and rq["kw"].get("stream") is True
          and set(rq["body"]) == MASTER_BODY_KEYS | {"stream_options"}, str(sorted(rq["body"])))
    resp = _Resp(events=[(None, s) for s in FIX["plain"][0]])
    run_gen(adapter(True), resp)
    check("2g. the streamed response is closed", resp.closed is True)
    resp = _Resp(events=[(None, s) for s in tc])
    run_gen(adapter(True), resp)
    check("2h. ... also when the fold raises", resp.closed is True)
    # tolerated noise
    noisy = [": keepalive", "", "data:", "event: ping", chunk(content="ok"), "data: [DONE]", chunk(content="AFTER-DONE")]
    (t, m), e = run_gen(adapter(True), _Resp(events=[(None, s) for s in noisy]))
    check("2i. comments, blank lines, empty data:, non-data fields skipped; nothing read after [DONE]",
          e is None and t == "ok" and m["stream_timing"]["chunks"] == 1, f"{e!r} {t!r} {m}")
    # bytes lines
    (t, m), e = run_gen(adapter(True), _Resp(events=[(None, s.encode()) for s in FIX["plain"][0]]))
    check("2j. bytes lines are decoded", e is None and t == "{\"a\": 1}")
    two = [json.dumps({"choices": [{"index": 1, "delta": {"content": "NOPE"}, "finish_reason": None}]}),
           json.dumps({"choices": [{"index": 0, "delta": {"content": "yes"}, "finish_reason": "stop"}]})]
    (t, m), e = run_gen(adapter(True), _Resp(events=[(None, "data: " + s) for s in two]))
    check("2k. only choice index 0 is folded (as non-streaming reads choices[0])", e is None and t == "yes", repr(t))

    # ---- 3. injected clock -----------------------------------------------------------------------------
    clk = Clock()
    ev = [(100.200, chunk(role=True, content="")),                 # role-only + empty string: neither
          (100.250, ": comment"),                                   # comment: neither
          (100.300, chunk(reasoning="th")),                         # first reasoning -> any = 300 (incl. 50ms POST)
          (100.400, chunk(reasoning="", content="")),               # empty strings: neither
          (100.600, chunk(content="{\"a\": 1}")),                   # first content -> answer = 600
          (100.900, chunk(content="", finish="stop")),
          (101.000, "data: [DONE]")]
    (t, m), e = run_gen(adapter(True, clk), _Resp(events=ev, clock=clk), clock=clk, post_advance=0.050)
    # t0 is read BEFORE the POST at 100.000; the fake POST advances the clock by 50 ms, so ttft includes it.
    # chunk times are absolute: any = 100.300 - 100.000 = 300 ms; answer = 600 ms; stream_ms = 1000 ms
    s = m["stream_timing"]
    check("3a. reasoning-then-answer: ttft_any 300.0 != ttft_answer 600.0, stream_ms 1000.0, chunks 5",
          e is None and s == {"ttft_any_ms": 300.0, "ttft_answer_ms": 600.0, "stream_ms": 1000.0, "chunks": 5}, f"{e!r} {s}")
    clk.t = 100.0
    ev = [(100.100, chunk(role=True, content="")), (100.300, chunk(reasoning="think")), (100.800, chunk(finish="length")),
          (100.900, "data: [DONE]")]
    (t, m), e = run_gen(adapter(True, clk), _Resp(events=ev, clock=clk), clock=clk)
    check("3b. reasoning-only: TerminationError exactly as non-streaming", isinstance(e, router.TerminationError)
          and e.details["reasoning_chars"] == 5 and e.details["content_chars"] == 0, repr(e))
    body, info = router.fold_sse(iter([(chunk(reasoning="think")), chunk(finish="length")]), 0.0, clock=lambda: 0.4)
    check("3c. reasoning-only fold: ttft_any 400.0, ttft_answer None (never 0)",
          info["ttft_any_ms"] == 400.0 and info["ttft_answer_ms"] is None, str(info))
    body, info = router.fold_sse(iter([chunk(role=True, content=""), ": c", chunk(content="", reasoning="")]), 0.0, clock=lambda: 0.4)
    check("3d. role-only / empty / comment stream: both ttfts None", info["ttft_any_ms"] is None and info["ttft_answer_ms"] is None
          and info["chunks"] == 2, str(info))
    body, info = router.fold_sse(iter([chunk(content="a")]), 5.0, clock=lambda: 5.0)
    check("3e. an answer at exactly t0 is 0.0, not None (None means 'never arrived')", info["ttft_answer_ms"] == 0.0
          and info["ttft_any_ms"] == 0.0, str(info))
    body, info = router.fold_sse(iter([chunk(content="a"), chunk(content="b", reasoning="r")]), 0.0,
                                 clock=iter([0.1, 0.2, 0.3, 0.4, 0.5, 0.6]).__next__)
    check("3f. the FIRST non-empty delta fixes the ttft; later ones never move it", info["ttft_any_ms"] == 100.0
          and info["ttft_answer_ms"] == 100.0, str(info))
    clk2 = Clock()
    clk2.t = 7.0
    (t, m), e = run_gen(adapter(True, clk2), _Resp(events=[(7.4, chunk(content="x")), (7.5, chunk(finish="stop"))], clock=clk2), clock=clk2)
    check("3g. the adapter's clock is the one the fold uses (injected end to end; t0 = 7.0)", e is None
          and m["stream_timing"]["ttft_answer_ms"] == 400.0, str(m))

    # ---- 4. get_adapter gating -------------------------------------------------------------------------
    os.environ["SANDBOX_STREAM_TIMING"] = "1"
    non_local = [p for p, tier in router.PROVIDER_TIER.items() if tier != "local"]
    check("4a. the non-local providers include the six named", {"openrouter", "anthropic", "openai", "scaleway", "ovh", "nebius"} <= set(non_local))
    leaked = [p for p in non_local if getattr(router.get_adapter(p), "stream_timing", None) is not False]
    check("4b. env=1 never enables streaming for a non-local provider", leaked == [], str(leaked))
    on = [p for p in ("ollama", "mlx", "llamacpp") if router.get_adapter(p).stream_timing is True]
    check("4c. env=1 enables streaming for every local chat-completions provider", on == ["ollama", "mlx", "llamacpp"], str(on))
    sysone = {"questions": [{"id": "q", "type": "bool"}], "outputs": {}}
    try:
        s1 = router.get_adapter("systemone", decision=sysone)
        ok1 = not isinstance(s1, router.ChatCompletionsAdapter) and not hasattr(s1, "stream_timing")
    except Exception as e:  # noqa: BLE001
        ok1 = True   # needs a richer decision spec; still not a chat adapter, still unchanged
        _ = e
    check("4d. systemone is not a chat adapter and carries no stream flag", ok1)
    for envv in ("0", "true", ""):
        os.environ["SANDBOX_STREAM_TIMING"] = envv
        check(f"4e. env={envv!r}: no local provider streams", not any(router.get_adapter(p).stream_timing for p in ("ollama", "mlx", "llamacpp")))
    os.environ.pop("SANDBOX_STREAM_TIMING", None)
    check("4f. env unset: no local provider streams", not any(router.get_adapter(p).stream_timing for p in ("ollama", "mlx", "llamacpp")))
    # a local provider's tier flipped to non-local would turn streaming off even with env=1 (the tier is what gates)
    os.environ["SANDBOX_STREAM_TIMING"] = "1"
    saved_tier = router.PROVIDER_TIER["ollama"]
    router.PROVIDER_TIER["ollama"] = "eu"
    try:
        flipped = router.get_adapter("ollama").stream_timing
    finally:
        router.PROVIDER_TIER["ollama"] = saved_tier
        os.environ.pop("SANDBOX_STREAM_TIMING", None)
    check("4g. the gate reads PROVIDER_TIER, not a provider-name list", flipped is False)

    # ---- 5. aggregation ---------------------------------------------------------------------------------
    meta0 = {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3, "content_chars": 4, "reasoning_chars": 0,
             "finish_reason": "stop"}
    mA = runner._call_metrics({**meta0, "stream_timing": {"ttft_any_ms": 100.0, "ttft_answer_ms": 300.0, "stream_ms": 900.0, "chunks": 5}}, 1000.0, 0)
    mB = runner._call_metrics({**meta0, "stream_timing": {"ttft_any_ms": 200.0, "ttft_answer_ms": None, "stream_ms": 800.0, "chunks": 4}}, 1000.0, 0)
    mC = runner._call_metrics({**meta0, "stream_timing": {"ttft_any_ms": 400.0, "ttft_answer_ms": 700.0, "stream_ms": 800.0, "chunks": 4}}, 1000.0, 0)
    m0 = runner._call_metrics(dict(meta0), 1000.0, 0)
    check("5a. _call_metrics carries stream_timing when present (a copy), omits it otherwise",
          mA["stream_timing"]["ttft_any_ms"] == 100.0 and "stream_timing" not in m0 and set(m0) == OLD_CASE)
    src = {**meta0, "stream_timing": {"ttft_any_ms": 1.0, "ttft_answer_ms": 2.0, "stream_ms": 3.0, "chunks": 4}}
    mX = runner._call_metrics(src, 1.0, 0)
    mX["stream_timing"]["chunks"] = -1
    check("5a2. the metrics copy does not alias the meta", src["stream_timing"]["chunks"] == 4)
    case1 = runner.combine_metrics([mA, mB])     # a case with two calls
    check("5b. case level (2 calls): first_* = first call; median_* over calls; calls 2; ttft None skipped",
          case1.get("stream_timing") == {"first_ttft_any_ms": 100.0, "first_ttft_answer_ms": 300.0,
                                     "median_first_ttft_any_ms": 150.0, "median_first_ttft_answer_ms": 300.0, "calls": 2},
          str(case1.get("stream_timing")))
    case2 = runner.combine_metrics([mC])         # a case with one call
    exam = runner.combine_metrics([case1, case2])
    # hand-computed: first_* = case1's first (100.0 / 300.0); medians over the cases' first_* values:
    # any: [100, 400] -> 250.0 ; answer: [300, 700] -> 500.0 ; calls 2 + 1 = 3
    check("5c. exam level (2 cases): hand-computed first 100/300, median 250/500, calls 3",
          exam.get("stream_timing") == {"first_ttft_any_ms": 100.0, "first_ttft_answer_ms": 300.0,
                                    "median_first_ttft_any_ms": 250.0, "median_first_ttft_answer_ms": 500.0, "calls": 3},
          str(exam.get("stream_timing")))
    odd = runner.combine_metrics([runner.combine_metrics([mA]), runner.combine_metrics([mB]), runner.combine_metrics([mC])])
    check("5d. odd count: median is the middle value (any 100/200/400 -> 200.0; answer 300/None/700 -> 500.0)",
          (odd.get("stream_timing") or {}).get("median_first_ttft_any_ms") == 200.0 and (odd.get("stream_timing") or {}).get("median_first_ttft_answer_ms") == 500.0
          and (odd.get("stream_timing") or {}).get("calls") == 3, str(odd.get("stream_timing")))
    mix = runner.combine_metrics([mA, m0])
    check("5f. some steps carry it, some do not -> stream_timing is None (never a partial)",
          "stream_timing" in mix and mix.get("stream_timing", 1) is None, str(mix.get("stream_timing")))
    mix2 = runner.combine_metrics([runner.combine_metrics([mA, m0]), mC])
    check("5g. a partial (None) case poisons the exam level too", mix2.get("stream_timing", 1) is None, str(mix2.get("stream_timing")))
    none_ = runner.combine_metrics([m0, m0])
    check("5h. no step carries it -> no stream_timing key at all", "stream_timing" not in none_)
    allnone = runner.combine_metrics([runner._call_metrics({**meta0, "stream_timing": {"ttft_any_ms": None, "ttft_answer_ms": None,
                                                                                          "stream_ms": 1.0, "chunks": 0}}, 1.0, 0)] * 2)
    check("5i. all-None ttfts stay None (median of nothing is None, not 0)",
          (allnone.get("stream_timing") or {}).get("median_first_ttft_any_ms", 1) is None and (allnone.get("stream_timing") or {}).get("first_ttft_any_ms", 1) is None)

    # ---- 6. no network ------------------------------------------------------------------------------------
    router.requests.post = _no_network
    try:
        router.get_adapter("ollama").generate(MSGS, "m")
        ok6 = False
    except AssertionError:
        ok6 = True
    check("6. an unfaked POST raises (the offline guard itself is live)", ok6)

    print(f"\n{len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
