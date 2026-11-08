#!/usr/bin/env python3
"""Re-derive every number in docs/writeups/same-exam-inside-n8n.md from committed probe files.

No model call, no network, no API key, no GPU. Answers that n8n produced on 3 Nov 2026 are graded again through
`wilco grade`'s own in-process function (`scripts/exam_grade.py: parse_answers + grade`, which drives the real
`runner.run_exam` with a replay adapter). `grade()` does not save; nothing is written to the repo.

Exit 0 when every recomputed figure equals the figure the probe records state (the EXPECT table below);
exit 1 on any drift.
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import exam_grade  # noqa: E402  (imports sandbox/runner.py)

P1 = ROOT / "docs/probes/n8n-eval-2026-11-03"
P2 = ROOT / "docs/probes/n8n-two-exams-2026-11-03"

# What the probe records say (RESULTS.md files). The script fails if the committed data disagrees.
EXPECT = {
    "email n8n vs key": (27, 28), "email train": (8, 8), "email heldout": (19, 20),
    "email exact-match vs wilco grade": (28, 28),
    "call-fields heldout N": [16, 16, 16], "call-fields heldout R": [14, 14, 14],
    "recap heldout N": [7, 6, 7], "recap heldout R": [4, 6, 6],
    "champion n8n-defaults labels equal runner": (28, 28),
    "call-fields heldout A": [16, 16, 15, 14], "call-fields heldout R 4 passes": [14, 14, 14, 13],
    "champion control train/heldout": ((7, 8), (16, 20)),
    "matched flips": 1, "matched-run2 flips": 1, "numCtx-only flips": 5,
    "recap pass-1 flips N vs R": 5, "recap unstable N": 7, "recap unstable R": 6,
}
drift: list = []


def check(name, got):
    want = EXPECT.get(name)
    if want is not None and want != got:
        drift.append(f"{name}: recorded {want}, recomputed {got}")


def wilco_grade(task: str, answers: dict) -> dict:
    """{case_id: passed} from wilco grade's own function, runner chatter suppressed."""
    with contextlib.redirect_stdout(io.StringIO()):
        res = exam_grade.grade(task, answers, "writeup")
    return {c["id"]: c["passed"] for c in res["cases"]}


def split_of(task: str) -> dict:
    return {c["id"]: c["split"] for c in json.loads((ROOT / f"evals/{task}/cases.json").read_text())["cases"]}


def held(verdicts: dict, splits: dict) -> int:
    return sum(v for k, v in verdicts.items() if splits[k] == "heldout")


# ---- 1. email-triage, labels mode: n8n Cloud run 1 (Haiku), labels written back to the data table ----------
splits = split_of("email-triage")
key = {c["id"]: c["expected"]["label"] for c in json.loads((ROOT / "evals/email-triage/cases.json").read_text())["cases"]}
with open(P1 / "run1-haiku-labels.csv", newline="") as f:
    labels = {r["case_id"]: r["n8n_label"] for r in csv.DictReader(f)}
# n8n's Categorization metric = exact match of expected vs actual. Reimplemented here as plain string equality.
exact = {k: labels[k] == key[k] for k in key}
# The CSV holds the label n8n's Code node already extracted; wrap it back in the prompt's output shape
# {"label": ...} so the runner's own parser and score_labels see what the model's answer would have parsed to.
wg = wilco_grade("email-triage", {k: json.dumps({"label": v}) for k, v in labels.items()})
n_ok = sum(wg.values())
tr = sum(v for k, v in wg.items() if splits[k] == "train"); trn = sum(1 for s in splits.values() if s == "train")
ho = held(wg, splits); hon = len(splits) - trn
same = sum(exact[k] == wg[k] for k in key)
print("1. email-triage (labels mode), n8n Cloud, claude-haiku-5-5, 28 cases")
print(f"   wilco grade on the labels n8n wrote back: {n_ok}/{len(wg)}  (train {tr}/{trn}, held-out {ho}/{hon})")
print(f"   exact-match (n8n Categorization semantics) vs wilco grade, same verdict: {same}/{len(key)}")
print(f"   misses: {[k for k, v in wg.items() if not v]}")
check("email n8n vs key", (n_ok, len(wg))); check("email train", (tr, trn)); check("email heldout", (ho, hon))
check("email exact-match vs wilco grade", (same, len(key)))

# ---- 2. call-fields (fields mode) and recap (properties mode): Arm N (n8n) vs Arm R (our runner) ---------
print("\n2. same model, two paths: n8n (N) vs our runner (R), held-out, 3 passes")
for task, nh in (("call-fields", 19), ("recap", 16)):
    splits = split_of(task)
    hN, hR, agree_tot, reproduce = [], [], 0, []
    for p in ("", ".pass2", ".pass3"):
        n_raw = exam_grade.parse_answers((P2 / f"armN/{task}{p}.json").read_text(), "Result")
        n_now = wilco_grade(task, n_raw)                             # wilco grade today
        n_then = {c["id"]: c["passed"] for c in json.loads((P2 / f"armN/{task}{p}.graded.json").read_text())["cases"]}
        r = {c["id"]: c["passed"] for c in json.loads((P2 / f"armR/{task}{p}.json").read_text())["cases"]}
        reproduce.append(sum(n_now[k] == n_then[k] for k in n_then))
        hN.append(held(n_now, splits)); hR.append(held(r, splits))
        agree_tot += sum(n_now[k] == r[k] for k in r if splits[k] == "heldout")
    print(f"   {task}: wilco grade reproduces the probe's graded verdicts on n8n's answers: "
          f"{'/'.join(map(str, reproduce))} of {len(n_then)} per pass")
    print(f"   {task}: held-out N {' · '.join(map(str, hN))} = {sum(hN)}/{3 * nh}   "
          f"R {' · '.join(map(str, hR))} = {sum(hR)}/{3 * nh}   "
          f"same verdict per case N vs R: {agree_tot}/{3 * nh}")
    check(f"{task} heldout N", hN); check(f"{task} heldout R", hR)
    if reproduce != [len(n_then)] * 3:
        drift.append(f"{task}: wilco grade does not reproduce the probe grade {reproduce}")
    if task == "recap":
        fc: dict = {}
        for c in json.loads((P2 / "armN/recap.graded.json").read_text())["cases"]:
            if c["split"] == "heldout":
                for f in c.get("failed_checks") or []:
                    fc[f["check"]] = fc.get(f["check"], 0) + 1
        print(f"   recap pass 1, n8n arm, held-out failed checks: {dict(sorted(fc.items()))}")

# ---- 2b. Arm A (Anthropic native API, probe code), recap flips and instability ---------------------------------
splits = split_of("call-fields")
hA = [held({c["id"]: c["passed"] for c in json.loads((P2 / f"armA/call-fields.pass{i}.graded.json").read_text())["cases"]}, splits)
      for i in (1, 2, 3, 4)]
hR4 = [held({c["id"]: c["passed"] for c in json.loads((P2 / f"armR/call-fields{p}.json").read_text())["cases"]}, splits)
       for p in ("", ".pass2", ".pass3", ".pass4")]
print(f"   call-fields held-out, 4 passes: A (native API) {' · '.join(map(str, hA))} = {sum(hA)}/76   "
      f"R {' · '.join(map(str, hR4))} = {sum(hR4)}/76")
check("call-fields heldout A", hA); check("call-fields heldout R 4 passes", hR4)
splits = split_of("recap")
def passes(arm, graded):
    out = []
    for p in ("", ".pass2", ".pass3"):
        f = P2 / f"{arm}/recap{p}{'.graded' if graded else ''}.json"
        out.append({c["id"]: c["passed"] for c in json.loads(f.read_text())["cases"] if c["split"] == "heldout"})
    return out
rN, rR = passes("armN", True), passes("armR", False)
flips = sum(rN[0][k] != rR[0][k] for k in rN[0])
unst = lambda ps: sum(len({p[k] for p in ps}) > 1 for k in ps[0])
print(f"   recap held-out pass 1: N vs R differ on {flips} cases; unstable over 3 passes: N {unst(rN)}/16, R {unst(rR)}/16")
check("recap pass-1 flips N vs R", flips); check("recap unstable N", unst(rN)); check("recap unstable R", unst(rR))

# ---- 3. the local champion inside self-hosted n8n (step 2), node defaults ------------------------------------
ctrl = {c["id"]: c["got"].get("label") if isinstance(c["got"], dict) else c["got"]
        for c in json.loads((P2 / "step2/control-runner.json").read_text())["cases"]}
dflt = exam_grade.parse_answers((P2 / "step2/n8n-defaults.json").read_text(), "Result")
def lab(t):
    try:
        return json.loads(t[t.index("{"): t.rindex("}") + 1]).get("label")
    except ValueError:
        return None
eq = sum(lab(dflt[k]) == ctrl[k] for k in ctrl)
print("\n3. local 2B champion, self-hosted n8n, Ollama node at defaults vs our runner (email-triage)")
print(f"   labels equal: {eq}/{len(ctrl)}")
check("champion n8n-defaults labels equal runner", (eq, len(ctrl)))
cr = json.loads((P2 / "step2/control-runner.json").read_text())
ctl = ((cr["train"]["passed"], cr["train"]["total"]), (cr["heldout"]["passed"], cr["heldout"]["total"]))
print(f"   our runner (control): train {ctl[0][0]}/{ctl[0][1]}, held-out {ctl[1][0]}/{ctl[1][1]}")
check("champion control train/heldout", ctl)
for name, f in (("matched", "n8n-matched"), ("matched-run2", "n8n-matched-run2"), ("numCtx-only", "ablation-abNumCtx00000001")):
    a = exam_grade.parse_answers((P2 / f"step2/{f}.json").read_text(), "Result")
    moved = sorted(k for k in ctrl if lab(a[k]) != ctrl[k])
    print(f"   node options {name}: labels that differ from the runner: {len(moved)} {moved}")
    check(f"{name} flips", len(moved))

if drift:
    print("\nDRIFT:\n  " + "\n  ".join(drift)); sys.exit(1)
print("\nall figures match the probe records")
