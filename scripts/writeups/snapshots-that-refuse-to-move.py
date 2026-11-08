#!/usr/bin/env python3
"""Re-derive the numbers in docs/writeups/snapshots-that-refuse-to-move.md.

For each committed re-snapshot commit, diff every evals/<exam>/snapshot.json it touched
against the same file in the commit's first parent, case by case (matched by id):
  - moved    = a case stable on both sides whose `passed` changed
  - unstable = cases whose 3 loads disagreed (stable: false) in the NEW snapshot
  - added / removed ids, split changes
Reads git objects only (pinned commit SHAs, never a branch name). No model call, no API key, no GPU.
Needs this repository's history: the pinned commits do not exist in a clone without it.
Usage:  python3 scripts/writeups/snapshots-that-refuse-to-move.py
"""
import json
import subprocess
import sys

RESNAPSHOTS = [  # (label, commit)
    # 7 Sep: first rule-A re-take on 0.33.2; the parent snapshots are single-run and pre-stamp
    # (no `stable` field, so they count as stable). This commit surfaced the 0.33.2 re-roll.
    ("7 Sep  rule-A re-take on 0.33.2 vs the pre-stamp snapshots", "ebb8248"),
    # the three whole-suite re-snapshots on a runtime bump
    ("2 Oct  L0, Ollama 0.33.2 -> 0.35.0", "f72f1df"),
    ("10 Oct KV-cache stamp, 0.35.0 -> 0.40.2", "310ef4c"),
    ("1 Nov  energy re-snapshot, 0.40.2 -> 0.40.11", "f249005"),
]


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.returncode, r.stdout


def load(rev, path):
    rc, out = git("show", f"{rev}:{path}")
    return json.loads(out) if rc == 0 else None


def cases_by_id(snap):
    ids = [c["id"] for c in snap["cases"]]
    if len(ids) != len(set(ids)):
        sys.exit(f"duplicate case ids in a snapshot: refusing to diff")
    return {c["id"]: c for c in snap["cases"]}


def runtime_str(snap):
    rt = snap.get("runtime") or {}
    if not rt:
        return "(no stamp)"
    s = rt.get("version", "?")
    if "kv_cache_type" in rt:
        s += f" kv={rt['kv_cache_type']} fa={rt.get('flash_attention')}"
    return s


def diff_commit(label, sha):
    rc, out = git("diff-tree", "--no-commit-id", "--name-only", "-r", sha)
    if rc != 0:
        sys.exit(f"commit {sha} not found — run from the repo root with full history")
    paths = sorted(p for p in out.split() if p.startswith("evals/") and p.endswith("/snapshot.json"))
    print(f"\n== {label}  (commit {sha} vs {sha}^)")
    print(f"{'exam':24} {'cases':>9} {'compared':>8} {'moved':>5} {'unstable':>8} {'added':>5} {'removed':>7}  runtime old -> new")
    tot = dict(cases=0, compared=0, moved=0, unstable=0, added=0, removed=0, baseline=0)
    moves = []
    for p in paths:
        exam = p.split("/")[1]
        new = load(sha, p)
        old = load(f"{sha}^", p)
        nc = cases_by_id(new)
        unstable = sum(1 for c in nc.values() if not c.get("stable", True))
        tot["cases"] += len(nc)
        tot["unstable"] += unstable
        if old is None:
            tot["baseline"] += len(nc)
            print(f"{exam:24} {len(nc):>9} {'-':>8} {'-':>5} {unstable:>8} {'-':>5} {'-':>7}  (first baseline) -> {runtime_str(new)}")
            continue
        oc = cases_by_id(old)
        added = set(nc) - set(oc)
        removed = set(oc) - set(nc)
        compared = moved = 0
        for cid in sorted(set(nc) & set(oc)):
            a, b = oc[cid], nc[cid]
            if a.get("split") != b.get("split"):
                moves.append(f"{exam}: {cid} split {a.get('split')} -> {b.get('split')}")
            if a.get("stable", True) and b.get("stable", True):
                compared += 1
                if a["passed"] != b["passed"]:
                    moved += 1
                    moves.append(f"{exam}: {cid} ({b.get('split')}) "
                                 f"{'PASS' if a['passed'] else 'FAIL'} -> {'PASS' if b['passed'] else 'FAIL'}")
        for k, v in (("compared", compared), ("moved", moved), ("added", len(added)), ("removed", len(removed))):
            tot[k] += v
        print(f"{exam:24} {len(oc):>4}->{len(nc):<4} {compared:>8} {moved:>5} {unstable:>8} {len(added):>5} {len(removed):>7}  {runtime_str(old)} -> {runtime_str(new)}")
    print(f"TOTAL: {tot['cases']} cases in the new snapshots; {tot['compared']} compared, "
          f"{tot['moved']} moved; {tot['unstable']} unstable; {tot['baseline']} first-baseline; "
          f"{tot['added']} added, {tot['removed']} removed")
    for m in moves:
        print("  moved:", m)
    return tot


if __name__ == "__main__":
    for label, sha in RESNAPSHOTS:
        diff_commit(label, sha)
