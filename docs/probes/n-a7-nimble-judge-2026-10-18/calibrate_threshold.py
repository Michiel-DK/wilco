"""N-A7c: pick the judge's cut on TRAIN, read it once on HELD-OUT, from the stored pass-1 decisions.

No inference: reads raw_pass1.jsonl + analysis.json, writes calibration.json. Deterministic.
Rows: applicable and not window_refused, exactly as judge_probe.py analyse. Judge "passes" iff p >= cut.
Candidate cuts = every distinct train p of the cell, plus 0.5; max train kappa wins, ties -> closest
to 0.5, then the lower cut. A cell is READ iff its train rows hold >= 10 key failures.
The global cut maximises kappa on the pooled train rows of the read cells (same candidates/ties).

Usage:  python3 calibrate_threshold.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from judge_probe import auroc, kappa  # noqa: E402  same definitions as the first run

MIN_TRAIN_FAILS = 10


def rates(rows, cut):
    y = [r["key_pass"] for r in rows]
    j = [r["p_pass"] >= cut for r in rows]
    npos, nneg = sum(y), len(y) - sum(y)
    tp = sum(a and b for a, b in zip(y, j))
    tn = sum((not a) and (not b) for a, b in zip(y, j))
    k = None if npos == 0 or nneg == 0 else kappa(y, j)
    return {"n": len(rows), "key_fail": nneg, "kappa": k,
            "tpr": tp / npos if npos else None, "tnr": tn / nneg if nneg else None}


def best_cut(rows):
    cands = sorted({r["p_pass"] for r in rows} | {0.5})
    scored = [(rates(rows, c)["kappa"], c) for c in cands]
    scored = [(k, c) for k, c in scored if k is not None]
    return min(scored, key=lambda kc: (-kc[0], abs(kc[1] - 0.5), kc[1]))


def main():
    rows = [json.loads(x) for x in (HERE / "raw_pass1.jsonl").read_text().splitlines()]
    assert len(rows) == 4244, len(rows)
    rows = [r for r in rows if r["applicable"] and not r["window_refused"]]
    cells = {}
    for r in rows:
        cells.setdefault((r["exam"], r["check"]), []).append(r)

    # Reproduce the first run's per-cell n before reading anything (brief: stop on any mismatch).
    ref = {(c["exam"], c["check"], c["split"]): c for c in json.loads((HERE / "analysis.json").read_text())["cells"]
           if c["scope"] == "applicable"}
    for (exam, check), rs in cells.items():
        for split in ("heldout", "train", "both"):
            sub = [r for r in rs if split == "both" or r["split"] == split]
            if not sub:
                continue
            c = ref[(exam, check, split)]
            if (len(sub), sum(not r["key_pass"] for r in sub)) != (c["n"], c["key_fail"]):
                sys.exit(f"FAIL n mismatch {exam} {check} {split}: {len(sub)}/{c['n']}")
    assert len(ref) == sum(len({r["split"] for r in rs}) + 1 for rs in cells.values()), "analysis.json has cells we lack"

    out = {"min_train_fails": MIN_TRAIN_FAILS, "cells": []}
    read = []
    for (exam, check), rs in sorted(cells.items()):
        tr = [r for r in rs if r["split"] == "train"]
        ho = [r for r in rs if r["split"] == "heldout"]
        tf = sum(not r["key_pass"] for r in tr)
        cell = {"exam": exam, "check": check, "n_train": len(tr), "train_fails": tf,
                "n_heldout": len(ho), "heldout_fails": sum(not r["key_pass"] for r in ho),
                "read": tf >= MIN_TRAIN_FAILS, "heldout_at_0.5": rates(ho, 0.5) if ho else None,
                "heldout_auroc": auroc([r["key_pass"] for r in ho], [r["p_pass"] for r in ho]) if ho else None}
        if cell["read"]:
            k_tr, cut = best_cut(tr)
            cell |= {"cut": cut, "train_kappa": k_tr, "train_at_cut": rates(tr, cut), "heldout_at_cut": rates(ho, cut)}
            read.append((cell, tr, ho))
        out["cells"].append(cell)

    pooled = [r for _, tr, _ in read for r in tr]
    gk, gcut = best_cut(pooled)
    out["global"] = {"cut": gcut, "pooled_train_kappa": gk, "pooled_train_n": len(pooled),
                     "cells": {f"{c['exam']}/{c['check']}": rates(ho, gcut) for c, _, ho in read}}
    (HERE / "calibration.json").write_text(json.dumps(out, indent=1) + "\n")

    f = lambda v: "n/a" if v is None else f"{v:.2f}"  # noqa: E731
    print("| exam | check | n_train (fail) | n_heldout (fail) | cut | train κ | held-out κ @cut | TPR | TNR "
          "| held-out κ @0.5 | TPR @0.5 | TNR @0.5 | held-out κ @global | TPR | TNR |")
    print("|" + "---|" * 15)
    for c in out["cells"]:
        h5 = c["heldout_at_0.5"] or {}
        head = f"| {c['exam']} | {c['check']} | {c['n_train']} ({c['train_fails']}) | {c['n_heldout']} ({c['heldout_fails']}) |"
        if not c["read"]:
            print(head + f" *underpowered* | | | | | {f(h5.get('kappa'))} | {f(h5.get('tpr'))} | {f(h5.get('tnr'))} | | | |")
            continue
        hc, g = c["heldout_at_cut"], out["global"]["cells"][f"{c['exam']}/{c['check']}"]
        print(head + f" {c['cut']:.4f} | {f(c['train_kappa'])} | {f(hc['kappa'])} | {f(hc['tpr'])} | {f(hc['tnr'])}"
              f" | {f(h5['kappa'])} | {f(h5['tpr'])} | {f(h5['tnr'])} | {f(g['kappa'])} | {f(g['tpr'])} | {f(g['tnr'])} |")
    print(f"global cut {gcut:.4f}, pooled train κ {gk:.2f} on {len(pooled)} rows")


if __name__ == "__main__":
    main()
