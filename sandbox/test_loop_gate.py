#!/usr/bin/env python3
"""scripts/loop_gate.py: keep only on a real stable TRAIN gain; held-out is read once and never selects.

    python3 sandbox/test_loop_gate.py

Hand-built records (no model, no server) plus one real committed snapshot. Pins:
  1. net +2 stable train, 0 down -> keep;  net +1 -> refuse;  +3 up / 1 down (net +2) -> refuse (any down refuses)
  2. exempt only if unstable in the BASELINE (the `check` rule); a baseline pass the candidate makes flaky is a
     down; a baseline fail made flaky-pass is not an up
  3. held-out without --final is refused (InputRefused, CLI exit 2) — no keep verdict on held-out exists
  4. --final: no stable held-out down -> confirm; one down -> refuse-run; the word "keep" never appears
  5. mismatched case sets, a missing `stable` or `passed`, a duplicate id, an unknown split, and any difference in
     provider / model / loads / runtime stamp -> input refused
  6. held-out moves never affect the train verdict and vice versa (split isolation)
  7. a committed snapshot compared with itself -> refuse (net 0), through the CLI (real file, exit 1)
  8. the CLI honours --final; usage errors (--split without a value, --split=heldout, a missing file) exit 2
  9. a committed snapshot is refused until stamped (no grader hash); stamped from the current tree it is accepted
 10. a gain with the exam/grader changed between the sits is refused (loop_stamp); the same gain on one grader is keep
 11. `loop_gate.py stamp` writes a gate-ready copy
Each pin seen RED under a hand mutation (PR body).
"""
from __future__ import annotations
import importlib.util, io, json, subprocess, sys, tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("loop_gate", ROOT / "scripts" / "loop_gate.py")
lg = importlib.util.module_from_spec(spec); spec.loader.exec_module(lg)
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


STAMP = {"provider": "ollama", "model": "m", "loads": 3, "temperature": 0.0, "max_tokens": 2048, "judge": None,
         "loop_stamp": {"agent": "crm-followup",
                        "files": {t.format(agent="crm-followup"): "aa" for t in lg.GRADER_FILES}},
         "runtime": {"version": "0.40.11", "kv_cache_type": "unset", "flash_attention": "unset"}}


def rec(train: dict, heldout: dict | None = None, unstable: set = frozenset(), **stamp) -> dict:
    cases = [{"id": k, "split": "train", "passed": v, "stable": k not in unstable} for k, v in train.items()]
    cases += [{"id": k, "split": "heldout", "passed": v, "stable": k not in unstable} for k, v in (heldout or {}).items()]
    return {**STAMP, **stamp, "cases": cases}


def refused(fn, needle: str = "") -> bool:
    """True only for an InputRefused whose message contains `needle` — a crash (KeyError etc.) or a refusal
    for a DIFFERENT reason does not count, so each guard is pinned by its own refusal, not a later one."""
    try:
        fn()
    except lg.InputRefused as e:
        return needle in str(e)
    except Exception:
        return False
    return False


def main() -> int:
    base_t = {"a": False, "b": False, "c": False, "d": True, "e": True}
    H = {"h1": True, "h2": False}
    base = rec(base_t, H)

    r = lg.gate(base, rec({**base_t, "a": True, "b": True}, H))
    check("1a. +2 stable up, 0 down -> keep", r["verdict"] == "keep" and r["net"] == 2, str(r))
    r = lg.gate(base, rec({**base_t, "a": True}, H))
    check("1b. +1 -> refuse", r["verdict"] == "refuse", str(r))
    r = lg.gate(base, rec({**base_t, "a": True, "b": True, "c": True, "d": False}, H))
    check("1c. +3 up / 1 down (net +2) -> refuse: any stable down refuses", r["verdict"] == "refuse" and r["net"] == 2, str(r))

    r = lg.gate(rec(base_t, H, unstable={"a"}), rec({**base_t, "a": True, "b": True, "c": True}, H))
    check("2a. a case unstable in the baseline is not counted (ups b,c only)", r["ups"] == ["b", "c"] and r["unstable"] == ["a"], str(r))
    r = lg.gate(base, rec({**base_t, "a": True, "b": True, "d": False}, H, unstable={"d"}))
    check("2b. a stable pass the candidate made flaky IS a down -> refuse (exempt only on the BASELINE's stability)",
          r["verdict"] == "refuse" and r["downs"] == ["d"], str(r))
    r = lg.gate(base, rec({**base_t, "a": True, "b": True, "d": True}, H, unstable={"d"}))
    check("2c. a stable pass that stays majority-pass but flaky is still a down", r["downs"] == ["d"], str(r))
    r = lg.gate(base, rec({**base_t, "a": True, "b": True, "c": True}, H, unstable={"c"}))
    check("2d. a fail made flaky-pass is NOT an up (only a pass on every load counts)", r["ups"] == ["a", "b"], str(r))
    # the PR #140 refuter's reproduction, shape-for-shape: 2 fails up, 3 stable passes -> passed False / stable False
    r = lg.gate(base, rec({**base_t, "a": True, "b": True, "d": False, "e": False}, H, unstable={"d", "e"}))
    check("2e. refuter repro: 2 up + 2 stable passes broken into flaky fails -> refuse, both counted down",
          r["verdict"] == "refuse" and r["downs"] == ["d", "e"], str(r))

    check("3a. held-out as a selection gate is refused, by the held-out guard itself", refused(lambda: lg.gate(base, base, split="heldout"), "never a selection gate"))
    r = lg.gate(base, rec(base_t, {"h1": True, "h2": True}), final=True)
    check("4a. --final, held-out gain -> confirm (not keep)", r["verdict"] == "confirm", str(r))
    r = lg.gate(base, rec(base_t, {"h1": False, "h2": False}), final=True)
    check("4b. --final, one stable held-out down -> refuse-run", r["verdict"] == "refuse-run" and r["downs"] == ["h1"], str(r))
    check("4c. no code path returns 'keep' for held-out", "keep" not in json.dumps(lg.final_heldout(base, rec(base_t, {"h1": True, "h2": True}))["verdict"]))

    check("5a. mismatched train case sets refused", refused(lambda: lg.gate(base, rec({**base_t, "z": True}, H)), "case sets differ"))
    nostab = {**STAMP, "cases": [{"id": "a", "split": "train", "passed": True}]}
    check("5b. a case without `stable` refused (single-load record)", refused(lambda: lg.gate(nostab, nostab), "no `stable`"))
    dup = {"cases": [{"id": "a", "split": "train", "passed": True, "stable": True}] * 2}
    dup = {**STAMP, **dup}
    check("5c. duplicate id refused", refused(lambda: lg.gate(dup, dup), "duplicate"))
    nopass = {**STAMP, "cases": [{"id": "a", "split": "train", "stable": True}]}
    check("5e. a case without boolean `passed` refused", refused(lambda: lg.gate(nopass, nopass), "boolean `passed`"))
    newrt = rec({**base_t, "a": True, "b": True}, H, runtime={**STAMP["runtime"], "version": "0.40.2"})
    check("5f. a different runtime stamp is refused (a runtime bump is never a gain)", refused(lambda: lg.gate(base, newrt), "`runtime` differs"))
    check("5g. a different model is refused", refused(lambda: lg.gate(base, rec(base_t, H, model="other")), "`model` differs"))
    check("5h. a different load count is refused", refused(lambda: lg.gate(base, rec(base_t, H, loads=1)), "`loads` differs"))
    gain = {**base_t, "a": True, "b": True}
    check("5j. a different temperature is refused (rule A is temp 0)", refused(lambda: lg.gate(base, rec(gain, H, temperature=0.7)), "`temperature` differs"))
    check("5k. a different max_tokens is refused", refused(lambda: lg.gate(base, rec(gain, H, max_tokens=16)), "`max_tokens` differs"))
    check("5l. a different judge is refused", refused(lambda: lg.gate(base, rec(gain, H, judge="x")), "`judge` differs"))
    check("5m. a scoped-rule arm record is refused", refused(lambda: lg.gate(base, rec(gain, H, scoped_rule="sham")), "scoped-rule ARM"))
    check("5n. library_sha present on one side only is refused", refused(lambda: lg.gate(base, rec(gain, H, library_sha="abc")), "`library_sha` differs"))
    badst = {**STAMP, "cases": [{"id": "a", "split": "train", "passed": True, "stable": "no"}]}
    check("5o. non-boolean `stable` is refused", refused(lambda: lg.gate(badst, badst), "non-boolean `stable`"))
    notdict = {**STAMP, "cases": ["a"]}
    check("5p. a non-object case is refused (no traceback)", refused(lambda: lg.gate(notdict, notdict), "not an object"))
    nort = {k: v for k, v in base.items() if k != "runtime"}
    check("5i. a record without a runtime stamp is refused", refused(lambda: lg.gate(nort, nort), "lacks `runtime`"))
    odd = {**STAMP, "cases": [{"id": "a", "split": "train", "passed": True, "stable": True},
                     {"id": "b", "split": "dev", "passed": True, "stable": True}]}
    check("5d. unknown split refused (with a valid train case beside it, so 'no train cases' cannot save it)",
          refused(lambda: lg.gate(odd, odd), "unknown split"))

    r = lg.gate(base, rec({**base_t, "a": True, "b": True}, {"h1": False, "h2": True}))
    check("6a. held-out moves do not touch the train verdict", r["verdict"] == "keep" and r["split"] == "train", str(r))
    r = lg.gate(base, rec({**base_t, "d": False, "e": False}, {"h1": True, "h2": True}), final=True)
    check("6b. train downs do not touch the held-out confirmation", r["verdict"] == "confirm", str(r))

    snap = ROOT / "evals" / "crm-followup" / "snapshot.json"
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "loop_gate.py"), str(snap), str(snap)],
                       capture_output=True, text=True)
    out = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {}
    check("7a. committed (unstamped) crm snapshot via the CLI -> input-refused, exit 2", p.returncode == 2
          and out.get("verdict") == "input-refused" and "loop_stamp" in out.get("reason", ""), f"rc={p.returncode} {out}")
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "loop_gate.py"), str(snap), str(snap), "--split", "heldout"],
                       capture_output=True, text=True)
    check("7b. CLI --split heldout without --final -> input-refused, exit 2", p.returncode == 2 and "input-refused" in p.stdout,
          f"rc={p.returncode} {p.stdout[-200:]}")

    # 8. the CLI honours --final and turns usage errors into exit 2
    def cli(*args):
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "loop_gate.py"), *args], capture_output=True, text=True)
        last = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else "{}"
        try:
            return p.returncode, json.loads(last)
        except ValueError:
            return p.returncode, {"raw": p.stdout[-200:] + p.stderr[-200:]}
    with tempfile.TemporaryDirectory() as td:
        bp, up_, dn = Path(td) / "b.json", Path(td) / "up.json", Path(td) / "dn.json"
        bp.write_text(json.dumps(base))
        up_.write_text(json.dumps(rec(base_t, {"h1": True, "h2": True})))
        dn.write_text(json.dumps(rec(base_t, {"h1": False, "h2": False})))
        rc, o = cli(str(bp), str(up_), "--final")
        check("8a. CLI --final, held-out gain -> confirm, exit 0, split heldout", rc == 0 and o.get("verdict") == "confirm"
              and o.get("split") == "heldout", f"rc={rc} {o}")
        rc, o = cli(str(bp), str(dn), "--final")
        check("8b. CLI --final, held-out down -> refuse-run, exit 1", rc == 1 and o.get("verdict") == "refuse-run", f"rc={rc} {o}")
        rc, o = cli(str(bp), str(up_), "--split")
        check("8c. CLI --split with no value -> input-refused exit 2, no traceback", rc == 2 and o.get("verdict") == "input-refused", f"rc={rc} {o}")
        rc, o = cli(str(bp), str(up_), "--split=heldout")
        check("8d. CLI --split=heldout (no --final) -> input-refused exit 2, never a silent train gate",
              rc == 2 and o.get("verdict") == "input-refused", f"rc={rc} {o}")
        rc, o = cli(str(bp), str(Path(td) / "missing.json"))
        check("8e. CLI missing file -> input-refused exit 2", rc == 2 and o.get("verdict") == "input-refused", f"rc={rc} {o}")

    # 9. every committed snapshot, once stamped, is accepted against itself; unstamped it is refused
    bad, unstamped_ok = [], []
    for snapf in sorted((ROOT / "evals").glob("*/snapshot.json")):
        sd = json.loads(snapf.read_text())
        if not refused(lambda: lg.gate(sd, sd), "no `loop_stamp`"):
            unstamped_ok.append(snapf.parent.name)
        st = {**sd, "loop_stamp": lg.compute_loop_stamp(snapf.parent.name)}
        try:
            lg.gate(st, st); lg.gate(st, st, final=True)
        except Exception as e:  # noqa: BLE001
            bad.append(f"{snapf.parent.name}: {e}")
    n_snap = len(list((ROOT / "evals").glob("*/snapshot.json")))
    check("9a. a committed (unstamped) snapshot is refused: it records no grader hash", unstamped_ok == [] and n_snap >= 8, str(unstamped_ok))
    check("9b. every committed snapshot, stamped from the current tree, is accepted against itself (train + final)",
          bad == [] and n_snap >= 8, str(bad))

    # 10. the re-verify-3 reproduction: two train fails flip AND the exam key changed between the sits -> refused
    crm = json.loads((ROOT / "evals" / "crm-followup" / "snapshot.json").read_text())
    st_base = {**crm, "loop_stamp": lg.compute_loop_stamp("crm-followup")}
    fails = [c["id"] for c in crm["cases"] if c["split"] == "train" and not c["passed"] and c["stable"]][:2]
    cand_cases = [dict(c, passed=True) if c["id"] in fails else c for c in crm["cases"]]
    with tempfile.TemporaryDirectory() as td:
        troot = Path(td)
        for tpl in lg.GRADER_FILES:
            rel = tpl.format(agent="crm-followup")
            src = ROOT / rel
            if src.is_file():
                (troot / rel).parent.mkdir(parents=True, exist_ok=True)
                (troot / rel).write_bytes(src.read_bytes())
        same = lg.compute_loop_stamp("crm-followup", troot)
        ck = troot / "evals" / "crm-followup" / "cases.json"
        ck.write_text(ck.read_text().replace('"Devos"', '"De Vos"', 1) + " ")
        changed = lg.compute_loop_stamp("crm-followup", troot)
    check("10a. a byte-identical copy of the grader files gives the same loop_stamp", same["files"] == st_base["loop_stamp"]["files"])
    check("10b. editing cases.json changes the loop_stamp", changed["files"] != same["files"])
    cand_same = {**crm, "cases": cand_cases, "loop_stamp": st_base["loop_stamp"]}
    cand_changed = {**crm, "cases": cand_cases, "loop_stamp": changed}
    r = lg.gate(st_base, cand_same)
    check("10c. same grader, two stable train fails now pass -> keep (the legitimate gain)", r["verdict"] == "keep" and len(fails) == 2, str(r))
    check("10d. the same flips with the exam key changed between the sits -> refused (could be the grader)",
          refused(lambda: lg.gate(st_base, cand_changed), "`loop_stamp` differs"))
    listid = {**STAMP, "cases": [{"id": ["x"], "split": "train", "passed": True, "stable": True}]}
    check("10e. a non-string case id is refused (no traceback)", refused(lambda: lg.gate(listid, listid), "not a string"))
    # 10f. EVERY grader file, edited (or created, if absent) between the sits, changes the stamp -> refused
    missed = []
    for tpl in lg.GRADER_FILES:
        rel = tpl.format(agent="crm-followup")
        with tempfile.TemporaryDirectory() as td:
            troot = Path(td)
            for t2 in lg.GRADER_FILES:
                r2 = t2.format(agent="crm-followup")
                if (ROOT / r2).is_file():
                    (troot / r2).parent.mkdir(parents=True, exist_ok=True)
                    (troot / r2).write_bytes((ROOT / r2).read_bytes())
            before = {**st_base, "loop_stamp": lg.compute_loop_stamp("crm-followup", troot)}
            f = troot / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes((f.read_bytes() if f.exists() else b"") + b"\n# changed between sits\n")
            after = {**crm, "cases": cand_cases, "loop_stamp": lg.compute_loop_stamp("crm-followup", troot)}
            if not refused(lambda: lg.gate(before, after), "`loop_stamp` differs"):
                missed.append(rel)
    check(f"10f. editing any of the {len(lg.GRADER_FILES)} grader files between the sits is refused (incl. retry.py)",
          missed == [] and "sandbox/retry.py" in {t for t in lg.GRADER_FILES}, str(missed))
    empty = {**STAMP, "loop_stamp": {"agent": "crm-followup", "files": {}}}
    empty = {**empty, "cases": [{"id": "a", "split": "train", "passed": True, "stable": True}]}
    check("10g. a forged empty loop_stamp on both sides is refused", refused(lambda: lg.gate(empty, empty), "incomplete"))

    # 11. the stamp subcommand writes a gate-ready copy
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "s.json"
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "loop_gate.py"), "stamp", "crm-followup",
                            str(ROOT / "evals" / "crm-followup" / "snapshot.json"), str(out)], capture_output=True, text=True)
        ok = p.returncode == 0 and out.exists() and "loop_stamp" in json.loads(out.read_text())
        rc2, o2 = cli(str(out), str(out)) if ok else (None, {})
    check("11. `stamp` writes a copy the gate accepts (vs itself: refuse, exit 1, no input refusal)", ok and rc2 == 1
          and o2.get("verdict") == "refuse", f"rc={p.returncode} {p.stdout[-200:]} gate={rc2} {o2}")

    print(f"\n{len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
