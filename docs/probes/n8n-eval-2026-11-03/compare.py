#!/usr/bin/env python3
"""Diff an n8n evaluation test run against the email-triage answer key and the champion snapshot.

Two input routes:
  A) n8n public API (cloud or self-hosted):
       N8N_HOST=https://<sub>.app.n8n.cloud N8N_API_KEY=... python3 compare.py --workflow <id> [--run <runId>]
     (latest completed run is used when --run is omitted; API key: Settings -> n8n API)
  B) a CSV you exported from the n8n data table after the run wrote outputs back
     (needs columns case_id and <output column>, default 'n8n_label'):
       python3 compare.py --csv results.csv [--output-col n8n_label]

Grading mirrors sandbox/runner.py score_labels: strip + lowercase exact match on the label.
Nothing here calls a model. Nothing here writes to the repo.
"""
import argparse, csv, json, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CASES = os.path.join(REPO, "evals", "email-triage", "cases.json")
SNAP = os.path.join(REPO, "evals", "email-triage", "snapshot.json")


def norm(s):
    return (s or "").strip().lower()


def extract_label(text):
    """Same leniency as the exam: the first JSON object in the text, key 'label'."""
    if isinstance(text, dict):
        return text.get("label")
    if not isinstance(text, str):
        return None
    m = re.search(r"\{[\s\S]*?\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0)).get("label")
    except json.JSONDecodeError:
        return None


def api(host, key, path):
    req = urllib.request.Request(host.rstrip("/") + "/api/v1" + path, headers={"X-N8N-API-KEY": key})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def from_api(host, key, wf, run):
    if not run:
        runs = api(host, key, f"/workflows/{wf}/test-runs?status=completed&limit=50")["data"]
        if not runs:
            sys.exit("no completed test runs for that workflow")
        run = sorted(runs, key=lambda r: r.get("completedAt") or "")[-1]["id"]
        print(f"using latest completed run {run}")
    rows, cursor = [], None
    while True:
        q = f"/workflows/{wf}/test-runs/{run}/test-cases?limit=250" + (f"&cursor={cursor}" if cursor else "")
        page = api(host, key, q)
        rows += page["data"]
        cursor = page.get("nextCursor")
        if not cursor:
            break
    out = {}
    for r in rows:
        inp, outp = r.get("inputs") or {}, r.get("outputs") or {}
        cid = inp.get("case_id") or outp.get("case_id")
        if not cid:
            print("WARN: test case without case_id in inputs/outputs; add case_id to the data table", file=sys.stderr)
            continue
        label = outp.get("n8n_label") or outp.get("label") or extract_label(outp.get("output") or outp.get("text"))
        out[cid] = {"label": label, "metrics": r.get("metrics") or {}, "status": r.get("status")}
    return out


def from_csv(path, col):
    out = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            out[row["case_id"]] = {"label": row.get(col) or extract_label(row.get("output")), "metrics": {}, "status": "csv"}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow"); ap.add_argument("--run")
    ap.add_argument("--csv"); ap.add_argument("--output-col", default="n8n_label")
    a = ap.parse_args()
    if a.csv:
        got = from_csv(a.csv, a.output_col)
    elif a.workflow:
        host, key = os.environ.get("N8N_HOST"), os.environ.get("N8N_API_KEY")
        if not (host and key):
            sys.exit("set N8N_HOST and N8N_API_KEY")
        got = from_api(host, key, a.workflow, a.run)
    else:
        sys.exit("give --workflow <id> (API) or --csv <file>")

    cases = json.load(open(CASES))["cases"]
    snap = json.load(open(SNAP))
    champ = {c["id"]: c for c in snap["cases"]}
    print(f"champion snapshot: {snap['model']} on ollama {snap['runtime']['version']}  "
          f"(train {snap['train_score']}, heldout {snap['heldout_score']})\n")
    print(f"{'case':34} {'split':7} {'key':11} {'n8n':11} {'n8n_ok':6} {'champ':5} {'agree':5}")
    agree = ok = n = missing = 0
    by_split = {}
    for c in cases:
        cid, key_label = c["id"], c["expected"]["label"]
        g = got.get(cid)
        if g is None:
            missing += 1
            print(f"{cid:34} {c['split']:7} {key_label:11} {'MISSING':11}")
            continue
        n += 1
        n8n_ok = norm(g["label"]) == norm(key_label)
        ch = champ[cid]["passed"]
        ok += n8n_ok; agree += (n8n_ok == ch)
        s = by_split.setdefault(c["split"], [0, 0]); s[0] += n8n_ok; s[1] += 1
        print(f"{cid:34} {c['split']:7} {key_label:11} {str(g['label']):11} {str(n8n_ok):6} {str(ch):5} {str(n8n_ok == ch):5}")
    print(f"\nn8n run vs key: {ok}/{n} " + "  ".join(f"{k} {v[0]}/{v[1]}" for k, v in by_split.items()))
    print(f"verdict agreement with the champion snapshot (same pass/fail per case): {agree}/{n}")
    print(f"cases missing from the n8n run: {missing}")
    print("\nNOTE: the n8n run used a DIFFERENT model unless it pointed at the local champion; agreement is a"
          " per-case comparison of two models on one key, not a reproduction of the snapshot.")


if __name__ == "__main__":
    main()
