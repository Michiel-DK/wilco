#!/usr/bin/env python3
"""The improvement loop's keep/refuse rule as a pure function over two exam records. No model, no server.

    python3 scripts/loop_gate.py <baseline.json> <candidate.json>            # TRAIN gate (the default)
    python3 scripts/loop_gate.py <baseline.json> <candidate.json> --final    # the ONE held-out confirmation
    python3 scripts/loop_gate.py stamp <agent> <snapshot.json> <out.json>     # add loop_stamp right after a sit

Design: docs/research/improvement-loop-design-2026-10-31.md. Inputs are rule-A SNAPSHOTS (the shape of
evals/<agent>/snapshot.json): same `provider`, `model`, `loads`, `runtime`, `temperature`, `max_tokens`, `judge` (and
`library_sha` when present) in both, else refused — a runtime bump or a changed decoding setting must never be
selected as a gain; a scoped-rule arm record is refused as `check` refuses it. Both records must also carry the same
`loop_stamp` (sha256 of the exam's cases/properties/tools mock, the agent.yaml, runner/numnorm/router — written by
`stamp` right after each sit): a committed snapshot has no such stamp, so it is refused until re-sat and stamped. Each case needs `id`, `split`, boolean `passed`, `stable`.

TRAIN gate (step 4): a case is exempt only if UNSTABLE IN THE BASELINE (the `check` rule). For the rest:
    up   = baseline failed, candidate passes on every load (passed and stable)
    down = baseline passed, candidate does not pass on every load (a pass made flaky is a down)
    keep  iff  downs == 0  and  ups - downs >= 2

Held-out: this script REFUSES to compute a keep verdict on held-out (CLAUDE.md "Heldout is untouchable";
selecting on held-out over N iterations is adaptive overfitting). `--final` reads held-out once and returns
`confirm` (no stable held-out case down) or `refuse-run` (any stable held-out case down) — never `keep`.

Exit code: 0 = keep / confirm, 1 = refuse / refuse-run, 2 = input refused (mismatched case sets, missing
`stable`, unknown split). The verdict is also printed as one JSON line.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

MIN_NET_GAIN = 2
ROOT = Path(__file__).resolve().parents[1]

# The files whose bytes define what a case's verdict MEANS for one agent. A snapshot records none of them
# (snapshot_payload stamps the harness SHA only), so `check` cannot tell a prompt gain from a grader change;
# the loop gate can, by requiring both records to carry the same hashes of these files (PR #140 re-verify 3:
# flipping two train fails + a changed key was otherwise `keep`). prompt.md is deliberately NOT here: it is
# the loop's one modification point.
sys.path.insert(0, str(ROOT / "sandbox"))
from grader_files import GRADER_FILES  # noqa: E402  (the ONE list, shared with runner's snapshot stamp)


def compute_loop_stamp(agent: str, root: Path = ROOT) -> dict:
    """{path: sha256 | "absent"} for every GRADER_FILES entry of `agent`. Absent files are recorded as such,
    so a file appearing or disappearing between the two sits also changes the stamp."""
    from grader_files import file_hashes
    out = file_hashes(agent, GRADER_FILES, root)
    if out[f"evals/{agent}/cases.json"] == "absent":
        raise InputRefused(f"no exam for agent {agent!r} under {root}")
    return {"agent": agent, "files": out}


class InputRefused(ValueError):
    pass


def _cases(rec: dict, split: str) -> dict[str, dict]:
    cases = rec.get("cases")
    if not isinstance(cases, list):
        raise InputRefused("record has no cases list")
    out = {}
    for c in cases:
        if not isinstance(c, dict):
            raise InputRefused(f"a case is not an object: {c!r}")
        if c.get("split") not in ("train", "heldout"):
            raise InputRefused(f"case {c.get('id')!r} has unknown split {c.get('split')!r}")
        if c["split"] != split:
            continue
        if "stable" not in c:
            raise InputRefused(f"case {c['id']!r} carries no `stable`: a single-load record proves no stability "
                               f"(use a rule-A snapshot or a `run --snapshot` aggregate)")
        if not isinstance(c["stable"], bool):
            raise InputRefused(f"case {c['id']!r} has non-boolean `stable` {c['stable']!r}")
        if not isinstance(c.get("passed"), bool):
            raise InputRefused(f"case {c['id']!r} carries no boolean `passed`")
        if not isinstance(c.get("id"), str):
            raise InputRefused(f"case id is not a string: {c.get('id')!r}")
        if c["id"] in out:
            raise InputRefused(f"duplicate case id {c['id']!r}")
        out[c["id"]] = c
    return out


STAMP_KEYS = ("provider", "model", "loads", "runtime", "temperature", "max_tokens", "judge")
# Present in some snapshots only (omitted-when-absent in snapshot_payload): if either record has it, both must
# carry the same value.
OPTIONAL_STAMP_KEYS = ("library_sha",)


def _same_loop_stamp(base: dict, cand: dict) -> None:
    for rec, name in ((base, "baseline"), (cand, "candidate")):
        if not isinstance(rec.get("loop_stamp"), dict) or not isinstance(rec["loop_stamp"].get("files"), dict):
            raise InputRefused(f"{name} carries no `loop_stamp` (hashes of the exam + grader files at sit time); "
                               f"write it with `loop_gate.py stamp <agent> <in> <out>` right after the sit")
        st = rec["loop_stamp"]
        need = f"evals/{st.get('agent')}/cases.json"
        if st["files"].get(need) in (None, "absent") or set(st["files"]) != {t.format(agent=st.get("agent")) for t in GRADER_FILES}:
            raise InputRefused(f"{name}'s `loop_stamp` is incomplete: it must hash exactly the current GRADER_FILES "
                               f"for agent {st.get('agent')!r} (re-stamp with `loop_gate.py stamp`)")
    if base["loop_stamp"] != cand["loop_stamp"]:
        diff = sorted(k for k in set(base["loop_stamp"]["files"]) | set(cand["loop_stamp"]["files"])
                      if base["loop_stamp"]["files"].get(k) != cand["loop_stamp"]["files"].get(k))
        raise InputRefused(f"`loop_stamp` differs (agent or grader files changed between the sits: {diff or 'agent'}) — "
                           f"a flip could be the grader, not the prompt")


def _same_stamp(base: dict, cand: dict) -> None:
    """Both records must come from the same provider, model, load count and runtime stamp (Ollama version,
    KV-cache type, flash attention — gotchas 15, 21). Otherwise a runtime bump could be selected as a 'gain'.
    A record without `runtime` is refused: only a rule-A snapshot carries it."""
    for rec, name in ((base, "baseline"), (cand, "candidate")):
        if rec.get("scoped_rule") is not None:
            raise InputRefused(f"{name} is a scoped-rule ARM record (scoped_rule={rec['scoped_rule']!r}): `check` refuses "
                               f"these as a baseline and the gate does the same")
    for k in OPTIONAL_STAMP_KEYS:
        if (k in base or k in cand) and base.get(k) != cand.get(k):
            raise InputRefused(f"`{k}` differs: baseline {base.get(k)!r} vs candidate {cand.get(k)!r}")
    for k in STAMP_KEYS:
        if k not in base or k not in cand:
            raise InputRefused(f"record lacks `{k}`: the gate compares rule-A snapshots only "
                               f"(baseline has it: {k in base}, candidate has it: {k in cand})")
        if base[k] != cand[k]:
            raise InputRefused(f"`{k}` differs: baseline {base[k]!r} vs candidate {cand[k]!r} — "
                               f"re-snapshot the baseline on the same stamp first")


def compare(base: dict, cand: dict, split: str) -> dict:
    _same_stamp(base, cand)
    _same_loop_stamp(base, cand)
    b, c = _cases(base, split), _cases(cand, split)
    if set(b) != set(c):
        raise InputRefused(f"{split} case sets differ: only in baseline {sorted(set(b) - set(c))}, "
                           f"only in candidate {sorted(set(c) - set(b))}")
    if not b:
        raise InputRefused(f"no {split} cases")
    ups, downs, unstable = [], [], []
    for cid in sorted(b):
        # Exempt ONLY on the baseline's stability — the same rule as `check` (runner.compare_to_snapshot).
        # A baseline-stable case is judged by whether the candidate passes it on EVERY load:
        #   up   = baseline failed (stably), candidate passes on all loads
        #   down = baseline passed (stably), candidate does not pass on all loads — a pass the candidate made
        #          flaky IS a down (stricter than `check`'s majority verdict on purpose: a kept gain must not
        #          cost reliability; PR #140 refuter: unstable-in-either let 3 broken passes through as 'keep')
        if not b[cid]["stable"]:
            unstable.append(cid)
            continue
        cand_solid = c[cid]["passed"] and c[cid]["stable"]
        if not b[cid]["passed"] and cand_solid:
            ups.append(cid)
        elif b[cid]["passed"] and not cand_solid:
            downs.append(cid)
    return {"split": split, "n": len(b), "ups": ups, "downs": downs, "unstable": unstable,
            "net": len(ups) - len(downs)}


def train_gate(base: dict, cand: dict) -> dict:
    r = compare(base, cand, "train")
    r["verdict"] = "keep" if (not r["downs"] and r["net"] >= MIN_NET_GAIN) else "refuse"
    r["rule"] = f"keep iff 0 stable train cases down and net stable gain >= {MIN_NET_GAIN}"
    return r


def final_heldout(base: dict, cand: dict) -> dict:
    r = compare(base, cand, "heldout")
    r["verdict"] = "refuse-run" if r["downs"] else "confirm"
    r["rule"] = "read once at the end: any stable held-out case down refuses the whole run; never a keep verdict"
    return r


def gate(base: dict, cand: dict, split: str = "train", final: bool = False) -> dict:
    if split == "heldout" and not final:
        raise InputRefused("held-out is never a selection gate: pass --final for the one end-of-run confirmation")
    if final:
        return final_heldout(base, cand)
    if split != "train":
        raise InputRefused(f"unknown split {split!r}")
    return train_gate(base, cand)


def stamp_main(argv: list[str]) -> int:
    """loop_gate.py stamp <agent> <in.json> <out.json>: copy a snapshot with the CURRENT tree's loop_stamp added.
    Run it right after the sit, before anything else in the tree changes."""
    if len(argv) != 3:
        print(json.dumps({"verdict": "input-refused", "reason": "usage: stamp <agent> <in.json> <out.json>"}))
        return 2
    agent, src, dst = argv
    try:
        rec = json.loads(Path(src).read_text())
        rec["loop_stamp"] = compute_loop_stamp(agent)
        Path(dst).write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    except (InputRefused, OSError, ValueError) as e:
        print(json.dumps({"verdict": "input-refused", "reason": str(e)}))
        return 2
    print(json.dumps({"stamped": dst, "agent": agent}))
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["stamp"]:
        return stamp_main(argv[1:])
    import argparse

    class _Parser(argparse.ArgumentParser):
        def error(self, message):            # usage errors are input refusals (exit 2), never a traceback
            raise InputRefused(f"usage: {message}")

    ap = _Parser(prog="loop_gate.py", description="keep/refuse over two rule-A snapshots", add_help=True)
    ap.add_argument("baseline")
    ap.add_argument("candidate")
    ap.add_argument("--final", action="store_true", help="the one end-of-run held-out confirmation")
    ap.add_argument("--split", choices=("train", "heldout"), default=None)
    try:
        a = ap.parse_args(argv)
        final = a.final
        split = a.split or ("heldout" if final else "train")
        base, cand = (json.loads(Path(p).read_text()) for p in (a.baseline, a.candidate))
        r = gate(base, cand, split=split, final=final)
    except (InputRefused, OSError, ValueError) as e:
        print(json.dumps({"verdict": "input-refused", "reason": str(e)}))
        return 2
    print(json.dumps(r))
    return 0 if r["verdict"] in ("keep", "confirm") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
