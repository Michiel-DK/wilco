#!/usr/bin/env python3
"""Collect n8n execution dumps (MCP get_workflow_execution, saved by the client to tool-results/*.txt) into
armN/<exam>.json = {case_id: {"text", "execution_id", "status", "input_chars", "system_chars", "started", "stopped"}}.
Keyed by the case_id the workflow's own Result node returned, never by file order. Merges into what is already there."""
import glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
src = sys.argv[1]
store = {}
for exam in ("call-fields", "recap"):
    p = os.path.join(HERE, "armN", f"{exam}.json")
    store[exam] = json.load(open(p)) if os.path.exists(p) else {}
for f in sorted(glob.glob(os.path.join(src, "mcp-n8n-get_workflow_execution-*.txt"))):
    d = json.load(open(f))
    ex = d["execution"]
    if ex["workflowId"] != "wVhvSAXixE6oaTyz":
        continue
    r = d["data"]["resultData"]["runData"]["Result"][0]["data"]["main"][0][0]["json"]
    store[r["exam"]][r["case_id"]] = {"text": r["text"], "execution_id": ex["id"], "status": ex["status"],
                                     "input_chars": r["input_chars"], "system_chars": r["system_chars"],
                                     "started": ex["startedAt"], "stopped": ex["stoppedAt"]}
for exam, rows in store.items():
    json.dump(dict(sorted(rows.items())), open(os.path.join(HERE, "armN", f"{exam}.json"), "w"), indent=1, ensure_ascii=False)
    cases = [c["id"] for c in json.load(open(os.path.join(HERE, "../../../evals", exam, "cases.json")))["cases"]]
    missing = [c for c in cases if c not in rows]
    print(exam, f"{len(rows)}/{len(cases)}", "missing:", " ".join(missing))
