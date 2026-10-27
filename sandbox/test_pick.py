"""W1 — `scripts/pick.py`, the pick rule as a command.

The rule (BAR_GAP in scripts/pick.py): bar = best held-out score − 1; the cheapest candidate at or above the bar with a
KNOWN cost takes the task. Every fixture is written into a temp dir by this file (no model, no network, nothing under
results/). Driven through the real entry point `pick.main([...])` (gotcha 5), exit codes and the written markdown
included; `pick.build` is used only where the test reads a field the terminal prints anyway.

Seen RED (recorded in the PR body): BAR_GAP 1 -> 0 and best − BAR_GAP -> best + BAR_GAP flip the picks; a recursive
token walker fails [E]; an intersect-instead-of-refuse fails [D]; unknown price as 0 fails [C]; max instead of min
fails [A].
"""
import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pick  # noqa: E402

FAILED = []


def check(label, ok, extra=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {extra}" if not ok and extra else ""))
    if not ok:
        FAILED.append(label)


TMP = pathlib.Path(tempfile.mkdtemp(prefix="test_pick_"))
IDS = [("t1", "train"), ("t2", "train"), ("h1", "heldout"), ("h2", "heldout"), ("h3", "heldout"), ("h4", "heldout")]
# price: 1 USD per 1M input, 4 USD per 1M output (asymmetric, and tokens split 3:1, so a swapped or input-only formula
# gives a different figure); cost/10k = (pt * 1 + ct * 4) / 1e6 / 6 cases * 1e4
PRICES = {"as_of": "2026-09-27", "source": "test fixture", "unit": "USD per 1M tokens", "models": {
    f"openrouter/{m}": {"input": 1.0, "output": 4.0, "as_of": "2026-09-27"} for m in ("a", "b", "c", "d", "nototals", "tie", "free")}}
PRICES["models"]["openrouter/free"] = {"input": 0, "output": 0, "as_of": "2026-09-27"}
PRICES["models"]["newcloud/a"] = {"input": 1.0, "output": 4.0, "as_of": "2026-09-27"}
PRICES["models"]["ollama/local-x"] = {"input": 0, "output": 0, "note": "runs on the user's machine; electricity not metered"}
EXAM = TMP / "repo"; (EXAM / "evals" / "t").mkdir(parents=True)
(EXAM / "evals" / "t" / "cases.json").write_text(json.dumps({"agent": "t", "cases": [{"id": i, "split": s} for i, s in IDS + [("h5", "heldout")]]}))
pick.REPO = str(EXAM)   # snapshots are checked against <REPO>/evals/<task>/cases.json; --prices / --out are always passed
PRICES_PATH = TMP / "prices.json"
PRICES_PATH.write_text(json.dumps(PRICES))


def split_tokens(usd):
    """(prompt, completion) in a 3:1 ratio that cost `usd` per 10k tasks at 1/4 USD per 1M over 6 cases:
    3k * 1 + k * 4 = 7k = usd * 1e6 * 6 / 1e4."""
    k = usd * 1e6 * 6 / 1e4 / 7
    assert abs(k - round(k)) < 1e-9, f"pick a usd that gives whole tokens: {usd}"
    return 3 * int(round(k)), int(round(k))


def fixture(name, provider, model, held_pass, usd=None, ids=IDS, totals=True, agent="t", heldout_block=True):
    """held_pass = number of held-out cases passed (first k). Per-case detail.metrics carry the SAME tokens as
    metrics_totals split across cases, so a walker that sums every token key gets exactly 2x (gotcha 13)."""
    pt, ct = split_tokens(usd) if usd is not None else (0, 0)
    cases, k = [], 0
    for i, (cid, split) in enumerate(ids):
        passed = split == "train" or (k < held_pass)
        if split == "heldout": k += 1
        share = (pt // len(ids) + (pt % len(ids) if i == 0 else 0), ct // len(ids) + (ct % len(ids) if i == 0 else 0))
        cases.append({"id": cid, "split": split, "passed": passed,
                      "detail": {"metrics": {"prompt_tokens": share[0], "completion_tokens": share[1], "total_tokens": sum(share)}}})
    nh = sum(1 for _, s in ids if s == "heldout")
    d = {"agent": agent, "provider": provider, "model": model, "mode": "properties", "cases": cases}
    if heldout_block: d["heldout"] = {"passed": min(held_pass, nh), "total": nh, "score": 0.0}
    if totals: d["metrics_totals"] = {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct}
    p = TMP / f"{name}.json"; p.write_text(json.dumps(d)); return str(p)


def run(*args):
    out = TMP / "out.md"
    if out.exists(): out.unlink()
    buf_o, buf_e = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf_o), contextlib.redirect_stderr(buf_e):
        rc = pick.main(["t", *args, "--prices", str(PRICES_PATH), "--out", str(out)])
    return rc, buf_o.getvalue(), buf_e.getvalue(), (out.read_text() if out.exists() else "")


def verdicts(md):
    v = {}
    for line in md.splitlines():
        c = [x.strip() for x in line.strip("|").split("|")]
        if len(c) == 5 and c[0].startswith(("openrouter/", "ollama/")): v[c[0].split(" ")[0]] = c
    return v


# best = 4/4 (a, c); bar = 3; b = 3/4 at $1 is the cheapest at the bar; d = 2/4 at $0.10 is cheaper but below.
A = fixture("a", "openrouter", "a", 4, usd=4.97)
B = fixture("b", "openrouter", "b", 3, usd=0.98)
C = fixture("c", "openrouter", "c", 4, usd=2.94)
D = fixture("d", "openrouter", "d", 2, usd=0.07)

print("[A] the rule picks the cheapest candidate at the bar")
rc, so, se, md = run(A, B, C, D)
v = verdicts(md)
check("[A] exit 0 and a markdown table written", rc == 0 and "| candidate |" in md, f"rc={rc} {se}")
check("[A] pick = openrouter/b (3/4, $0.98; bar 3 = best 4 − 1)", "**Pick: openrouter/b**" in md and "pick: openrouter/b" in so, so)
check("[A] verdict column: b PICK, a and c best", v.get("openrouter/b", [""] * 5)[4].startswith("PICK")
      and v["openrouter/a"][4].startswith("best") and v["openrouter/c"][4].startswith("best"), str(v))
check("[A] the terminal prints the same table as the markdown (b's row on both)", "openrouter/b" in so and "3/4" in so)

print("[B] a cheaper below-bar candidate is NOT picked")
check("[B] d (2/4 at $0.07) is 'below', not the pick", v.get("openrouter/d", [""] * 5)[4].startswith("below")
      and "**Pick: openrouter/d**" not in md, str(v.get("openrouter/d")))
rc_b, _, _, md_b = run(B, D)   # alone with d: best 3, bar 2, d at the bar and cheaper -> d wins (the rule, not a d-ban)
check("[B] control: with best 3/4, d (2/4) is at the bar and IS picked", "**Pick: openrouter/d**" in md_b, md_b)

print("[C] a candidate missing from prices.json -> cost unknown, excluded, never 0")
U = fixture("u", "openrouter", "unpriced", 4, usd=0.07)
NT = fixture("nt", "openrouter", "nototals", 4, usd=0.07, totals=False)
rc, so, se, md = run(A, B, C, U, NT)
v = verdicts(md)
check("[C] the unpriced candidate (4/4, would be cheapest at $0.07) is not the pick", "**Pick: openrouter/b**" in md, md)
check("[C] its row says cost unknown + excluded, and its $/10k cell is '—' (not 0, not ≈0)",
      "cost unknown" in v.get("openrouter/unpriced", [""] * 5)[3] and "excluded" in v["openrouter/unpriced"][4]
      and v["openrouter/unpriced"][2] == "—", str(v.get("openrouter/unpriced")))
check("[C] the flag is printed on the terminal AND in the markdown",
      "openrouter/unpriced: cost unknown (not in prices.json) — EXCLUDED" in so
      and "openrouter/unpriced: cost unknown (not in prices.json) — EXCLUDED" in md, so)
check("[C] a priced model with no metrics_totals is cost unknown too (never re-summed from per-case keys)",
      "no metrics_totals" in v.get("openrouter/nototals", [""] * 5)[3] and v["openrouter/nototals"][2] == "—",
      str(v.get("openrouter/nototals")))
rc_c, _, _, md_c = run(U, D)   # the only at-bar candidate has no known cost -> no pick, exit 3
check("[C] no known-cost candidate at the bar -> exit 3, 'No pick'", rc_c == 3 and "**No pick**" in md_c, f"rc={rc_c}")

print("[D] mismatched case sets are refused (exit 2), never intersected")
EXTRA = fixture("extra", "openrouter", "c", 4, usd=2.94, ids=IDS + [("h5", "heldout")])
rc, so, se, md = run(A, B, EXTRA)
check("[D] one extra held-out id -> exit 2", rc == 2, f"rc={rc} so={so[:200]}")
check("[D] message names the comparable-set rule and the extra id", "never intersects" in se and "'h5'" in se, se)
check("[D] nothing written on a refusal", md == "", md[:80])
MOVED = fixture("moved", "openrouter", "c", 4, usd=2.94, ids=[("t1", "train"), ("t2", "heldout"), ("h1", "heldout"),
                                                            ("h2", "heldout"), ("h3", "heldout"), ("h4", "train")])
rc, _, se, _ = run(A, MOVED)
check("[D] same ids, a split moved -> exit 2", rc == 2 and "different split" in se, f"rc={rc} {se[:200]}")
rc, _, se, _ = run(A, fixture("a2", "openrouter", "a", 3, usd=0.98))
check("[D] two files for one provider/model -> exit 2", rc == 2 and "two files for openrouter/a" in se, se)
rc, _, se, _ = run(A, fixture("other", "openrouter", "b", 3, usd=0.98, agent="recap"))
check("[D] a file for another task -> exit 2", rc == 2 and "`recap` result" in se, se)
bad = json.loads(pathlib.Path(B).read_text()); bad["heldout"]["passed"] = 4
BAD = TMP / "bad.json"; BAD.write_text(json.dumps(bad))
rc, _, se, _ = run(A, str(BAD))
check("[D] a heldout block that disagrees with its cases -> exit 2", rc == 2 and "heldout block says 4/4" in se, se)

print("[E] cost uses metrics_totals ONLY (gotcha 13: per-case keys would double it)")
E = fixture("e", "openrouter", "a", 4, usd=2.45)
r = pick.build("t", [E], PRICES)
got = r["cands"][0]["usd"]
check("[E] $/10k == 2.45 = (prompt x 1 + completion x 4) single count, not 4.90", abs(got - 2.45) < 1e-6, f"got {got}")
walked = sum(v for c in json.loads(pathlib.Path(E).read_text())["cases"] for k, v in c["detail"]["metrics"].items()
             if k in ("prompt_tokens", "completion_tokens"))
check("[E] control: the fixture's per-case keys alone already sum to the full total (a walker would get 2x)",
      walked == sum(split_tokens(2.45)), f"walked={walked}")
rc, so, _, md = run(E)
check("[E] the markdown prints 2.45, tagged list price 2026-09-27", "| 2.45 | list price 2026-09-27 |" in md, md)

print("[F] the bar constant decides the pick (seen RED by inverting it)")
check("[F] BAR_GAP is 1 (the public rule: best, or one case from it)", pick.BAR_GAP == 1, str(pick.BAR_GAP))
rc, so, _, md = run(A, B, C, D, "--bar-gap", "0")
check("[F] --bar-gap 0 (bar = best): the pick flips b -> c (cheapest of the 4/4s)", "**Pick: openrouter/c**" in md, md)
rc, _, se, _ = run(A, B, "--bar-gap", "-1")
check("[F] a negative gap is refused", rc == 2 and ">= 0" in se, se)

print("[G] flags: hosted, within noise; a local snapshot prices ≈0")
rc, so, _, md = run(A, B, C, D)
check("[G] hosted flag names the stable-case gate caveat", pick.HOSTED_FLAG in md and pick.HOSTED_FLAG in so)
check("[G] a one-case gap to the pick is 'within noise' (a 4/4 vs the 3/4 pick)",
      "openrouter/a 4/4 vs the pick 3/4: a one-case gap, within noise" in md, md)
rc, so, _, md = run(A, C, D)   # pick c 4/4; d 2/4 is two cases away
check("[G] a two-case gap is not flagged as noise", "**Pick: openrouter/c**" in md and "openrouter/d 2/4 vs the pick" not in md, md)
SNAP = TMP / "snapshot.json"
SNAP.write_text(json.dumps({"provider": "ollama", "model": "local-x", "loads": "3", "date": "2026-10-08",
                            "cases": [{"id": i, "split": s, "passed": True, "stable": True} for i, s in IDS]}))
rc, so, _, md = run(A, B, str(SNAP))
v = verdicts(md)
check("[G] a snapshot (no metrics_totals) of a zero-priced local model is ≈0 local and wins at 4/4",
      "**Pick: ollama/local-x**" in md and v.get("ollama/local-x", [""] * 5)[3] == pick.LOCAL_TAG, md)
rc, so, _, md = run(str(SNAP))
check("[G] a local-only set carries no hosted flag", pick.HOSTED_FLAG not in md, md)

print("[H] default discovery reads top-level results/<task>__*.json only")
FAKE = TMP / "repo"; (FAKE / "results" / "snapshot_loads").mkdir(parents=True, exist_ok=True)
(FAKE / "results" / "t__openrouter__b.json").write_text(pathlib.Path(B).read_text())
(FAKE / "results" / "snapshot_loads" / "t__openrouter__a__load1.json").write_text(pathlib.Path(A).read_text())
_real = pick.REPO; pick.REPO = str(FAKE)
try:
    rc, so, _, md = run()
finally:
    pick.REPO = _real
check("[H] with no files given, only the top-level file is a candidate (the subdir per-load file is not)",
      rc == 0 and "openrouter/b" in md and "openrouter/a" not in md, md)

print("[I] edge cases: price formula, tie-break, noise, provider classes, duplicate ids, the committed prices file")
pt, ct = split_tokens(2.45)
swapped = (pt * 4 + ct * 1) / 1e6 / 6 * 1e4; input_only = (pt + ct) * 1 / 1e6 / 6 * 1e4
check("[I] control: a swapped-rate or input-only formula would NOT give 2.45 on the [E] fixture",
      abs(swapped - 2.45) > 0.5 and abs(input_only - 2.45) > 0.5, f"{swapped} {input_only}")
T = fixture("tie", "openrouter", "tie", 4, usd=0.98)   # same cost as b (3/4), one case better
rc, _, _, md = run(A, B, T)
check("[I] equal cost at the bar: the higher held-out wins the tie (tie 4/4 over b 3/4)", "**Pick: openrouter/tie**" in md, md)
check("[I] a candidate tied with the pick (0-case gap) is not flagged 'within noise'",
      "openrouter/a 4/4 vs the pick" not in md, md)   # a is 4/4, the pick is 4/4
rc, _, _, md = run(A, B, C, D)
check("[I] a candidate one case BELOW the pick is flagged too (d 2/4 vs b 3/4)",
      "openrouter/d 2/4 vs the pick 3/4: a one-case gap, within noise" in md, md)
F0 = fixture("free", "openrouter", "free", 4, usd=0.07)
rc, so, _, md = run(A, F0)
v = verdicts(md)
check("[I] a hosted model priced 0 is NOT '≈0 local' and keeps the hosted flag",
      v.get("openrouter/free", [""] * 5)[3] == "list price 2026-09-27" and any(l.startswith("- hosted (") and "openrouter/free" in l and pick.HOSTED_FLAG in l for l in md.splitlines()), md)
NC = fixture("nc", "newcloud", "a", 4, usd=0.07)
rc, _, _, md = run(NC)
check("[I] a provider the router does not know is treated as hosted (flag present)", pick.HOSTED_FLAG in md and "newcloud/a" in md, md)
dup = json.loads(pathlib.Path(B).read_text()); dup["cases"].append(dict(dup["cases"][2])); dup.pop("heldout")
DUP = TMP / "dup.json"; DUP.write_text(json.dumps(dup))
rc, _, se, _ = run(A, str(DUP))
check("[I] a duplicate case id inside one file -> exit 2", rc == 2 and "appears twice" in se, se)
real = json.loads((ROOT / "pricing" / "prices.json").read_text())
lr = json.loads((ROOT / "docs/probes/matrix-2026-09-27/list_rates.json").read_text())
check("[I] committed prices.json: unit + as_of, and every hosted row equals list_rates.json exactly (key openrouter/<id>)",
      real["unit"] == "USD per 1M tokens" and real["as_of"] == "2026-09-27"
      and all(real["models"].get(f"openrouter/{k}") == {"input": r["prompt_per_m"], "output": r["completion_per_m"], "as_of": r["date"]}
              for k, r in lr.items()), "mismatch")
mx = json.loads((ROOT / "docs/probes/matrix-2026-09-27/results/recap__openai_gpt-5.6-sol-2026-09-27.json").read_text())
check("[I] committed prices.json keys match what a real result file carries (provider/model of a matrix file)",
      f"{mx['provider']}/{mx['model']}" in real["models"], f"{mx['provider']}/{mx['model']}")
check("[I] committed prices.json: every local row is 0/0 with the electricity note",
      all(m["input"] == 0 and m["output"] == 0 and "electricity not metered" in m["note"]
          for k, m in real["models"].items() if k.startswith("ollama/")) and any(k.startswith("ollama/") for k in real["models"]))


print("[J] a partly metered total (runner: metrics_totals.complete False) is a floor, not a cost")
FL = fixture("floor", "openrouter", "tie", 4, usd=0.07)
fl = json.loads(pathlib.Path(FL).read_text()); fl["metrics_totals"].update(unmetered_cases=5, complete=False); pathlib.Path(FL).write_text(json.dumps(fl))
rc, so, _, md = run(A, C, FL)
v = verdicts(md)
check("[J] the floor candidate (4/4, $0.07 on 1 of 6 cases) is NOT the pick; c (4/4, $2.94 complete) is",
      "**Pick: openrouter/c**" in md and "excluded" in v.get("openrouter/tie", [""] * 5)[4], md)
check("[J] its tag names the floor and the unmetered count", "cost floor only (5 of 6 cases unmetered)" in v["openrouter/tie"][3], str(v["openrouter/tie"]))
Z = fixture("zero", "openrouter", "tie", 4, usd=None)
rc, _, _, md = run(A, Z)
check("[J] a hosted run that metered 0 tokens is cost unknown, not ≈0", "0 tokens metered" in md and "**Pick: openrouter/a**" in md, md)

print("[K] bad inputs refuse cleanly (exit 2), never a traceback or a silent score")
EMPTY = TMP / "empty.json"; EMPTY.write_text("")
rc, _, se, _ = run(A, str(EMPTY))
check("[K] an empty file -> exit 2, 'not readable JSON'", rc == 2 and "not readable JSON" in se, se)
nb = json.loads(pathlib.Path(B).read_text()); nb["cases"][3]["passed"] = 1; nb.pop("heldout")
NB = TMP / "nb.json"; NB.write_text(json.dumps(nb))
rc, _, se, _ = run(A, str(NB))
check("[K] a non-bool passed -> exit 2", rc == 2 and "not a bool" in se, se)
np_ = json.loads(pathlib.Path(B).read_text()); del np_["cases"][2]["passed"]
NP = TMP / "np.json"; NP.write_text(json.dumps(np_))
rc, _, se, _ = run(A, str(NP))
check("[K] a case without passed -> exit 2", rc == 2 and "without id/split/passed" in se, se)
WS = TMP / "wrong_snapshot.json"
WS.write_text(json.dumps({"provider": "ollama", "model": "local-x", "loads": "3",
                          "cases": [{"id": f"x{i}", "split": s, "passed": True} for i, (_, s) in enumerate(IDS)]}))
rc, _, se, _ = run(str(WS))
check("[K] a snapshot whose ids are not in evals/<task>/cases.json -> exit 2", rc == 2 and "not in evals/t/cases.json" in se, se)
_r = pick.REPO; pick.REPO = str(TMP / "nowhere")
try:
    rc, _, se, _ = run(str(SNAP))
finally:
    pick.REPO = _r
check("[K] a snapshot for a task with no committed exam -> exit 2 (cannot be checked)", rc == 2 and "does not exist" in se, se)


def main() -> int:
    print(f"\n{'FAILED: ' + ', '.join(FAILED) if FAILED else 'all green'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
