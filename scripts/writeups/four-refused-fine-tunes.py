#!/usr/bin/env python3
"""Re-derive the numbers in docs/writeups/four-refused-fine-tunes.md from committed results files.

Standard library only. No API key, no GPU, no model call. Run from the repo root:

    python3 scripts/writeups/four-refused-fine-tunes.py

Rule (the same one as docs/probes/i2v4-crm-lora-2026-09-21/compare.py): the held-out gate REFUSES an
adapter when any held-out case that is STABLE on both arms passed on the base and fails on the adapter.
v1 has only one-pass results files (no `stable` field, no rule-A snapshot), so its held-out downs are
printed as one-pass downs and kept out of the stable count.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
P = ROOT / "docs" / "probes"

ARMS = [
    # label, base file, adapter file, rule-A snapshot?
    ("v1", "i2-crm-lora-2026-09-20/results-base.json", "i2-crm-lora-2026-09-20/results-adapter.json", False),
    ("v2", "i2v2-crm-lora-2026-09-21/snapshot-base.json", "i2v2-crm-lora-2026-09-21/snapshot-adapter.json", True),
    ("v3", "i2v3-crm-lora-2026-09-21/snapshot-base.json", "i2v3-crm-lora-2026-09-21/snapshot-adapter.json", True),
    ("v4", "i2v4-crm-lora-2026-09-21/snapshot-base.json", "i2v4-crm-lora-2026-09-21/snapshot-adapter.json", True),
    ("v4b", "i2v4-crm-lora-2026-09-21/snapshot-base.json", "i2v4-crm-lora-2026-09-21/snapshot-adapter-iter200.json", True),
]


def load(rel):
    return json.loads((P / rel).read_text())


def score(cases, split):
    n = [c for c in cases.values() if c["split"] == split]
    return f"{sum(1 for c in n if c['passed'])}/{len(n)}"


def main():
    refused = 0
    for label, bf, af, snap in ARMS:
        b = {c["id"]: c for c in load(bf)["cases"]}
        a = {c["id"]: c for c in load(af)["cases"]}
        if set(b) != set(a):
            sys.exit(f"{label}: case sets differ")
        up = down = ho_down = stable_ho_down = 0
        unstable = sum(1 for c in list(b.values()) + list(a.values()) if not c.get("stable", True))
        for cid in b:
            x, y = b[cid], a[cid]
            if x["passed"] == y["passed"]:
                continue
            if y["passed"]:
                up += 1
                continue
            down += 1
            if x["split"] == "heldout":
                ho_down += 1
                if snap and x.get("stable", True) and y.get("stable", True):
                    stable_ho_down += 1
        kind = "rule-A, 3 samples" if snap else "one pass, not rule-A"
        verdict = (f"stable held-out down {stable_ho_down} -> REFUSED" if snap
                   else f"held-out down {ho_down} (one pass) -> REFUSED by its registered prediction")
        if (snap and stable_ho_down) or (not snap and ho_down):
            refused += label != "v4b"
        print(f"{label:4} [{kind}] train {score(b, 'train')} -> {score(a, 'train')} | "
              f"held-out {score(b, 'heldout')} -> {score(a, 'heldout')} | up {up} down {down} | "
              f"unstable {unstable} | {verdict}")

    # v4 reused v3's base snapshot; check that the two committed files agree case for case
    b3 = {c["id"]: c["passed"] for c in load(ARMS[2][1])["cases"]}
    b4 = {c["id"]: c["passed"] for c in load(ARMS[3][1])["cases"]}
    b2 = {c["id"]: c["passed"] for c in load(ARMS[1][1])["cases"]}
    print(f"base snapshots v2 == v3 == v4 case for case: {b2 == b3 == b4}")

    # v1 token effect, from metrics_totals ONLY (never sum per-case metrics)
    mb = load(ARMS[0][1])["metrics_totals"]
    ma = load(ARMS[0][2])["metrics_totals"]
    pct = 100 * (ma["completion_tokens"] - mb["completion_tokens"]) / mb["completion_tokens"]
    print(f"v1 completion tokens {mb['completion_tokens']} -> {ma['completion_tokens']} ({pct:+.0f}%), "
          f"reasoning chars {mb['reasoning_chars']} -> {ma['reasoning_chars']}")
    print(f"adapters refused by the held-out gate: {refused} of 4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
