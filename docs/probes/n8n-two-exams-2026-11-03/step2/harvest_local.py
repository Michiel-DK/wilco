#!/usr/bin/env python3
"""Step 2: parse `n8n execute --rawOutput` (self-hosted n8n 2.46.4 in Docker) into <arm>.json = {case_id: {"text"}},
checking each item against the committed case by input fingerprint (length + first 80 chars). Fails loud on any
mismatch, duplicate or missing case. Usage: harvest_local.py <raw-file> <arm-name>"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
t = open(sys.argv[1]).read()
run = json.loads(t[t.index("{"):])
rd = run["data"]["resultData"]["runData"]
items = [i["json"] for i in rd["Result"][0]["data"]["main"][0]]
cases = {c["id"]: c["input"] for c in json.load(open(os.path.join(ROOT, "evals", "email-triage", "cases.json")))["cases"]}
rows, bad = {}, []
for it in items:
    cid, inp = it["case_id"], cases.get(it["case_id"])
    if inp is None or it["input_chars"] != len(inp) or it["input_head"] != inp[:80] or cid in rows:
        bad.append(cid)
    rows[cid] = {"text": it["text"]}
missing = sorted(set(cases) - set(rows))
lm = rd.get("Ollama Chat Model", [])
tu = [r["data"]["ai_languageModel"][0][0]["json"].get("tokenUsage") or {} for r in lm]
meta = {"status": run["status"], "started": run["startedAt"], "stopped": run["stoppedAt"], "calls": len(lm),
        "token_usage": {k: sum(x.get(k, 0) for x in tu) for k in ("promptTokens", "completionTokens")}}
json.dump({"_meta": meta, **dict(sorted(rows.items()))}, open(os.path.join(HERE, f"{sys.argv[2]}.json"), "w"), indent=1, ensure_ascii=False)
print(sys.argv[2], f"{len(rows)}/{len(cases)}", meta, "BAD:", bad, "MISSING:", missing)
sys.exit(1 if bad or missing else 0)
