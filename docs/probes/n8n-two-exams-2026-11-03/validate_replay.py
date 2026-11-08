#!/usr/bin/env python3
"""Is grade_replay.py a faithful witness? Two checks, no model calls.

(1) Agreement: replay Arm R's OWN recorded answers (`got` per case in armR/<exam>.json) through grade_replay.py.
    The per-case verdicts must equal Arm R's verdicts on every case.
(2) Seen red: take one case that passes under (1), pad its answer past the recap compression budget (recap) or
    blank one field (call-fields), and replay again. Exactly that case must flip to FAIL, and no other case may move.
Exit 0 only if both hold for both exams."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ok = True


def replay(exam, answers):
    with tempfile.TemporaryDirectory() as td:
        a, o = os.path.join(td, "a.json"), os.path.join(td, "o.json")
        json.dump(answers, open(a, "w"), ensure_ascii=False)
        r = subprocess.run([sys.executable, os.path.join(HERE, "grade_replay.py"), exam, a, o], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(r.stderr[-2000:])
        return {c["id"]: c["passed"] for c in json.load(open(o))["cases"]}


for exam in ("call-fields", "recap"):
    R = json.load(open(os.path.join(HERE, "armR", f"{exam}.json")))
    want = {c["id"]: c["passed"] for c in R["cases"]}
    answers = {c["id"]: {"text": c["got"] if isinstance(c["got"], str) else json.dumps(c["got"], ensure_ascii=False)}
               for c in R["cases"]}
    got = replay(exam, answers)
    diff = [k for k in want if want[k] != got.get(k)]
    print(f"{exam}: agreement {len(want) - len(diff)}/{len(want)}", "diff:", diff)
    ok &= not diff
    victim = next(k for k in want if want[k])
    bad = dict(answers)
    if exam == "recap":
        g = json.loads(bad[victim]["text"]) if bad[victim]["text"].lstrip().startswith("{") else None
        if g is not None:
            key = next(k for k, v in g.items() if isinstance(v, str))
            g[key] = g[key] + " " + "Nothing else to add today." * 60
            bad[victim] = {"text": json.dumps(g, ensure_ascii=False)}
        else:
            bad[victim] = {"text": bad[victim]["text"] + " " + "Nothing else to add today." * 60}
    else:
        g = json.loads(bad[victim]["text"])
        key = next(k for k, v in g.items() if v not in ("not stated", ""))
        g[key] = "zzz-wrong"
        bad[victim] = {"text": json.dumps(g, ensure_ascii=False)}
    got2 = replay(exam, bad)
    moved = [k for k in want if got2.get(k) != got.get(k)]
    print(f"{exam}: seen-red mutant on {victim!r} -> moved {moved}")
    ok &= moved == [victim] and got2[victim] is False

print("VALID" if ok else "NOT VALID")
sys.exit(0 if ok else 1)
