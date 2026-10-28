#!/usr/bin/env python3
"""Aggregate the 2026-10-28 hosted open-weight re-sit (OpenRouter list rates, no --direct): per model x exam held-out score, metered tokens, and the
dollar line from repo-radar cost_per_10k.py --direct (the only sanctioned dollar source; printed line pasted, never retyped)."""
import glob, json, os, subprocess, sys
P = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(P, "results")
RADAR = os.path.expanduser("~/code/Michiel-DK/repo-radar/scripts/cost_per_10k.py")
LEDGER_ID = {"google_gemma-4-26b-a4b-it": "google/gemma-4-26b-a4b-it", "google_gemma-4-31b-it": "google/gemma-4-31b-it",
             "mistralai_mistral-small-3.2-24b-instruct": "mistralai/mistral-small-3.2-24b-instruct", "qwen_qwen3-14b": "qwen/qwen3-14b",
             "deepseek_deepseek-v4-pro-0813": "deepseek/deepseek-v4-pro-0813", "z-ai_glm-5.3": "z-ai/glm-5.3"}
EXAMS = ["expense-categorization", "email-triage", "reply-draft", "recap", "recap-en", "crm-followup"]
rows = {}
for f in sorted(glob.glob(os.path.join(R, "*.json"))):
    base = os.path.basename(f)[:-5]; exam, tag = base.split("__", 1)
    d = json.load(open(f)); h = d["heldout"]; mt = d.get("metrics_totals") or {}
    cost = "n/a"
    if LEDGER_ID.get(tag):
        out = subprocess.run([sys.executable, RADAR, LEDGER_ID[tag], "--volumes", f], capture_output=True, text=True).stdout.strip().splitlines()
        cost = next((l for l in out if LEDGER_ID[tag] in l), out[-1] if out else "?")
    fails = [c["id"] for c in d["cases"] if not c["passed"]]
    rows.setdefault(tag, {})[exam] = dict(passed=h["passed"], total=h["total"], prompt=mt.get("prompt_tokens"), completion=mt.get("completion_tokens"),
                                          wall_s=round((mt.get("wall_ms") or 0) / 1000), unmetered=mt.get("unmetered_cases"), cost=cost, fails=fails, file=os.path.basename(f))
for tag, ex in rows.items():
    pooled = sum(v["passed"] for v in ex.values()), sum(v["total"] for v in ex.values())
    print(f"\n## {tag}  pooled {pooled[0]}/{pooled[1]} over {len(ex)} exams")
    for e in EXAMS:
        if e not in ex: print(f"  {e:24} MISSING"); continue
        v = ex[e]
        print(f"  {e:24} {v['passed']:2}/{v['total']:<2}  {v['prompt'] or 0:>7} p / {v['completion'] or 0:>6} c  {v['wall_s']:>5}s  {v['cost']}")
        if v["fails"]: print(f"  {'':24} fails: {', '.join(v['fails'])}")
        if v["unmetered"]: print(f"  {'':24} ⚠️ unmetered_cases={v['unmetered']}")
