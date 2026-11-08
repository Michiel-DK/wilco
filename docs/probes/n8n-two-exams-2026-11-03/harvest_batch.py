#!/usr/bin/env python3
"""Passes 2+ of Arm N: one n8n execution (workflow d5P2PumHfBICXwan) sits a whole exam. Usage:
  harvest_batch.py <dump-dir> <execution_id>:<pass> [...]
Reads the client-saved MCP dumps in <dump-dir>, finds each named execution, and writes armN/<exam>.pass<k>.json in
the same shape as harvest.py ({case_id: {"text", ...}}). Every item is checked against the committed case by its
input fingerprint (length + first 80 chars), and the run fails on any mismatch, duplicate or missing case. Token
usage is summed from the Anthropic Chat Model runs when the dump carries them."""
import glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
want = dict(a.split(":") for a in sys.argv[2:])
found = {}
for f in glob.glob(os.path.join(sys.argv[1], "mcp-n8n-get_workflow_execution-*.txt")):
    d = json.load(open(f))
    ex = d["execution"]
    if ex["workflowId"] == "d5P2PumHfBICXwan" and ex["id"] in want and "Result" in d["data"]["resultData"]["runData"]:
        found[ex["id"]] = d
bad = False
for eid, p in want.items():
    if eid not in found:
        print(f"execution {eid}: no dump with a Result node"); bad = True; continue
    d = found[eid]; ex = d["execution"]
    items = [i["json"] for i in d["data"]["resultData"]["runData"]["Result"][0]["data"]["main"][0]]
    exam = items[0]["exam"]
    cases = {c["id"]: c["input"] for c in json.load(open(os.path.join(ROOT, "evals", exam, "cases.json")))["cases"]}
    rows = {}
    for it in items:
        cid = it["case_id"]; inp = cases.get(cid)
        if inp is None or it["input_chars"] != len(inp) or it["input_head"] != inp[:80] or cid in rows:
            print(f"execution {eid}: fingerprint/duplicate failure on {cid!r}"); bad = True
        rows[cid] = {"text": it["text"], "execution_id": eid, "status": ex["status"], "system_chars": it["system_chars"]}
    missing = sorted(set(cases) - set(rows))
    if missing:
        print(f"execution {eid}: missing {missing}"); bad = True
    usage = None
    lm = d["data"]["resultData"]["runData"].get("Anthropic Chat Model")
    if lm:
        tu = [r["data"]["ai_languageModel"][0][0]["json"].get("tokenUsage") or {} for r in lm]
        usage = {k: sum(t.get(k, 0) for t in tu) for k in ("promptTokens", "completionTokens")} | {"calls": len(tu)}
    out = {"_meta": {"execution_id": eid, "status": ex["status"], "started": ex["startedAt"], "stopped": ex["stoppedAt"],
                     "token_usage": usage}, **dict(sorted(rows.items()))}
    json.dump(out, open(os.path.join(HERE, "armN", f"{exam}.pass{p}.json"), "w"), indent=1, ensure_ascii=False)
    print(f"{exam} pass{p}: {len(rows)}/{len(cases)} cases, exec {eid} {ex['status']}, tokens {usage}")
sys.exit(1 if bad else 0)
