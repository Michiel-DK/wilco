"""Re-derive every number in docs/writeups/judge-vs-key.md not marked otherwise from the committed decision files.

Reads only docs/probes/n-a7-nimble-judge-2026-10-18/{raw_pass1,raw_pass2}.jsonl (the stored judge
decisions, each carrying the key verdict as it stood when the probe ran) and cross-checks the result
against the committed analysis.json and calibration.json of the same probe. Standard library only,
no model call, no API key, no GPU. kappa / AUROC / cut selection are re-implemented here on purpose
(not imported) so this is an independent recomputation; any drift from the committed aggregates
raises.

Usage (repo root):  python3 scripts/writeups/judge-vs-key.py
"""
import json
import statistics
import sys
from pathlib import Path

PROBE = Path(__file__).resolve().parents[2] / "docs/probes/n-a7-nimble-judge-2026-10-18"
THRESHOLD = 0.5
MIN_FAILS = 10  # power rule registered before the run: a cell is read only with >= 10 key failures


def kappa(y, j):
    n = len(y)
    po = sum(a == b for a, b in zip(y, j)) / n
    py, pj = sum(y) / n, sum(j) / n
    pe = py * pj + (1 - py) * (1 - pj)
    return None if pe == 1 else (po - pe) / (1 - pe)


def auroc(y, p):
    pos = [s for s, t in zip(p, y) if t]
    neg = [s for s, t in zip(p, y) if not t]
    if not pos or not neg:
        return None
    return sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg))


def rates(rows, cut):
    y = [r["key_pass"] for r in rows]
    j = [r["p_pass"] >= cut for r in rows]
    npos, nneg = sum(y), len(y) - sum(y)
    tp = sum(a and b for a, b in zip(y, j))
    tn = sum((not a) and (not b) for a, b in zip(y, j))
    return {"n": len(rows), "key_fail": nneg, "agree": tp + tn,
            "kappa": None if npos == 0 or nneg == 0 else kappa(y, j),
            "tpr": tp / npos if npos else None, "tnr": tn / nneg if nneg else None,
            "auroc": auroc(y, [r["p_pass"] for r in rows])}


def best_cut(rows):
    cands = sorted({r["p_pass"] for r in rows} | {THRESHOLD})
    scored = [(rates(rows, c)["kappa"], c) for c in cands]
    return min(((k, c) for k, c in scored if k is not None), key=lambda kc: (-kc[0], abs(kc[1] - 0.5), kc[1]))


def close(a, b):
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1e-9)


def f2(x):
    return "n/a" if x is None else f"{x:.2f}"


def main():
    p1 = [json.loads(x) for x in (PROBE / "raw_pass1.jsonl").read_text().splitlines()]
    p2 = [json.loads(x) for x in (PROBE / "raw_pass2.jsonl").read_text().splitlines()]
    refused = sum(r["window_refused"] for r in p1)
    used = [r for r in p1 if r["applicable"] and not r["window_refused"]]
    print(f"decisions pass 1: {len(p1)} | window-refused: {refused} | vacuous (not applicable): "
          f"{sum(not r['applicable'] and not r['window_refused'] for r in p1)} | applicable, judged: {len(used)}")
    judged = {(r["exam"], r["model"], r["case"]) for r in p1 if not r["window_refused"]}
    models = {e: len({r["model"] for r in p1 if r["exam"] == e}) for e in sorted({r["exam"] for r in p1})}
    print(f"checks: {len({(r['exam'], r['check']) for r in p1})} | outputs in the decision file: "
          f"{len({(r['exam'], r['model'], r['case']) for r in p1})}, judged (not refused): {len(judged)} | models per exam: {models}")
    # Stability: pass 2 (recap only) vs pass 1.
    k1 = {(r["exam"], r["model"], r["case"], r["check"]): r for r in p1}
    both = [(k1[(r["exam"], r["model"], r["case"], r["check"])], r) for r in p2 if not r["window_refused"]]
    flips = sum((a["p_pass"] >= THRESHOLD) != (b["p_pass"] >= THRESHOLD) for a, b in both)
    dp = max(abs(a["p_pass"] - b["p_pass"]) for a, b in both)
    print(f"pass 2: {len(p2)} decisions, exams {sorted({r['exam'] for r in p2})}, flips {flips}/{len(both)}, max |dp| {dp:.3f}")

    cells = {}
    for r in used:
        cells.setdefault((r["exam"], r["check"]), []).append(r)

    # Cross-check against the committed aggregate before printing anything from it.
    ref = {(c["exam"], c["check"], c["split"]): c for c in json.loads((PROBE / "analysis.json").read_text())["cells"]
           if c["scope"] == "applicable"}
    for (exam, check), rs in cells.items():
        for split in ("heldout", "train", "both"):
            sub = [r for r in rs if split == "both" or r["split"] == split]
            if not sub:
                continue
            got, c = rates(sub, THRESHOLD), ref[(exam, check, split)]
            for f in ("n", "key_fail", "kappa", "tpr", "tnr", "auroc", "agree"):
                same = close(got[f], c[f]) if (got[f] is None or isinstance(got[f], float)) else got[f] == c[f]
                if not same:
                    sys.exit(f"FAIL drift vs analysis.json: {exam} {check} {split} {f}: {got[f]} != {c[f]}")
    print(f"cross-check vs analysis.json: {len(ref)} applicable cells, 0 mismatches")

    print("\npowered checks (>= 10 key failures), applicable, both splits pooled, threshold 0.5:")
    powered, under, oneclass = [], [], []
    for (exam, check), rs in sorted(cells.items()):
        s_ = rates(rs, THRESHOLD)
        name = f"{exam}/{check.removeprefix('check_')}"
        if s_["kappa"] is None:
            oneclass.append(name)
        elif s_["key_fail"] < MIN_FAILS:
            under.append(f"{name} ({s_['key_fail']})")
        else:
            powered.append(((exam, check), s_))
            print(f"  {name:<30} n {s_['n']:>3}  fails {s_['key_fail']:>2}  kappa {f2(s_['kappa'])}  TPR {f2(s_['tpr'])}"
                  f"  TNR {f2(s_['tnr'])}  AUROC {f2(s_['auroc'])}")
    print(f"one-class key ({len(oneclass)}): {', '.join(oneclass)}")
    print(f"underpowered ({len(under)}, key failures): {', '.join(under)}")
    nnp = cells[("reply-draft", "check_no_invented_numbers")]
    print(f"reply-draft no_invented_numbers TPR {f2(rates(nnp, THRESHOLD)['tpr'])} | abstention AUROC recap "
          f"{f2(rates(cells[('recap', 'check_abstention')], THRESHOLD)['auroc'])}, transcript-en "
          f"{f2(rates(cells[('transcript-en', 'check_abstention')], THRESHOLD)['auroc'])}")
    ai = rates(cells[("transcript-en", "check_action_items")], THRESHOLD)
    print(f"\ntranscript-en action_items raw agreement: {ai['agree']}/{ai['n']} = {ai['agree'] / ai['n']:.0%} "
          f"at kappa {ai['kappa']:.2f}; key pass rate {(ai['n'] - ai['key_fail']) / ai['n']:.0%}")

    # N-A7c: cut chosen on train (max train kappa), read once on held-out.
    cal = {(c["exam"], c["check"]): c for c in json.loads((PROBE / "calibration.json").read_text())["cells"]}
    print("\ntrain-chosen cut, read on held-out (cells with >= 10 train key failures):")
    read = []
    for (exam, check), rs in sorted(cells.items()):
        tr = [r for r in rs if r["split"] == "train"]
        ho = [r for r in rs if r["split"] == "heldout"]
        if sum(not r["key_pass"] for r in tr) < MIN_FAILS:
            continue
        _, cut = best_cut(tr)
        h = rates(ho, cut)
        c = cal[(exam, check)]
        if not (close(cut, c["cut"]) and close(h["kappa"], c["heldout_at_cut"]["kappa"])):
            sys.exit(f"FAIL drift vs calibration.json: {exam} {check}")
        read.append((tr, ho))
        print(f"  {exam}/{check.removeprefix('check_')}: cut {cut:.4f} -> held-out kappa {h['kappa']:.2f} (TPR {h['tpr']:.2f}, TNR {h['tnr']:.2f}, "
              f"{h['key_fail']} key failures)")
    gk, gcut = best_cut([r for tr, _ in read for r in tr])
    gl = ", ".join(f"{rates(ho, gcut)['kappa']:.2f}" for _, ho in read)
    print(f"  one global cut {gcut:.3f} (pooled train kappa {gk:.2f}) -> held-out kappa per cell: {gl}")
    print("cross-check vs calibration.json: 0 mismatches")


if __name__ == "__main__":
    main()
