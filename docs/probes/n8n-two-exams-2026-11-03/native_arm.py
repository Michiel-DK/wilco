#!/usr/bin/env python3
"""Arm A: the same messages sent straight to Anthropic's NATIVE Messages API (no LangChain, no n8n, no compat
endpoint). It isolates the endpoint as the one difference from Arm R (the runner on the OpenAI-compatible endpoint).
system = agents/<exam>/prompt.md, user = case input, max_tokens = agent.yaml, no temperature (Arm R sends none either:
the compat endpoint drops it). Writes armA/<exam>.pass<k>.json = {case_id: {"text"}} + _meta token usage.
Usage: native_arm.py <exam> <pass>. Probe code, not runner code: no provider entry and no adapter class (CLAUDE.md)."""
import json, os, sys, concurrent.futures as cf, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
exam, p = sys.argv[1], sys.argv[2]
system = open(os.path.join(ROOT, "agents", exam, "prompt.md"), encoding="utf-8").read()
max_tokens = {"call-fields": 4096, "recap": 2048}[exam]
cases = json.load(open(os.path.join(ROOT, "evals", exam, "cases.json")))["cases"]
key = os.environ["ANTHROPIC_API_KEY"]

def call(case):
    body = json.dumps({"model": "claude-haiku-5-5", "max_tokens": max_tokens, "system": system,
                       "messages": [{"role": "user", "content": case["input"]}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if attempt == 2 or e.code not in (429, 500, 502, 503, 529):
                raise SystemExit(f"{case['id']}: HTTP {e.code} {e.read()[:300]!r}")
    text = "".join(b.get("text", "") for b in d["content"] if b.get("type") == "text")
    return case["id"], text, d.get("usage", {}), d.get("stop_reason"), [b.get("type") for b in d["content"]]

with cf.ThreadPoolExecutor(5) as ex:
    out = list(ex.map(call, cases))
usage = {k: sum(u.get(k, 0) for _, _, u, _, _ in out) for k in ("input_tokens", "output_tokens")}
meta = {"usage": usage, "stop_reasons": sorted({s for *_, s, _ in out}), "block_types": sorted({t for *_, bt in out for t in bt})}
json.dump({"_meta": meta, **{cid: {"text": t} for cid, t, *_ in out}}, open(os.path.join(HERE, "armA", f"{exam}.pass{p}.json"), "w"), indent=1, ensure_ascii=False)
print(exam, f"pass{p}", meta)
