#!/usr/bin/env python3
"""The OWASP side-car register (evals/owasp_codes.json) stays in step with the exams.

    python3 evals/test_owasp_codes.py

Pins, each seen RED by hand before commit (PR body lists the mutations):
  1. every case with "class": "injection" in any evals/<exam>/cases.json has a register entry
  2. every register entry resolves to a real case, and that case is class=injection
  3. every code is in the register's own vocabulary AND carries an edition suffix (numbers moved
     between the 2025 and 2026 LLM lists: Excessive Agency LLM06:2025 -> LLM03:2026)
  4. every entry carries a non-empty `why`
  5. the vocabulary has exactly ten LLM and ten ASI codes, numbered 01..10 once each
  7. an ASI (agentic) code sits only on a case from a tool-offering exam
  0. case ids are unique within each exam
  6. no cases.json carries an OWASP code inline (the register is a side-car so cases stay
     byte-identical and no snapshot moves)
No model, no server. Exams enumerated with os.walk over evals/ (gotcha 6), never a glob.
"""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "evals" / "owasp_codes.json"
FAILED: list[str] = []
DUPES: list[str] = []
CODE_RE = re.compile(r"^(LLM|ASI)(0[1-9]|10):20\d\d$")


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def exam_cases() -> dict[str, dict]:
    """'<exam>/<id>' -> case, for every evals/<exam>/cases.json found by walking the tree."""
    out: dict[str, dict] = {}
    for dirpath, dirnames, filenames in os.walk(ROOT / "evals"):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__pycache__"]
        if "cases.json" in filenames:
            exam = Path(dirpath).relative_to(ROOT / "evals").as_posix()
            for c in json.loads((Path(dirpath) / "cases.json").read_text())["cases"]:
                key = f"{exam}/{c['id']}"
                if key in out:
                    DUPES.append(key)
                out[key] = c
    return out


def main() -> int:
    reg = json.loads(REGISTER.read_text())
    vocab, entries = reg["vocabulary"], reg["cases"]
    cases = exam_cases()
    check("at least one exam enumerated", len(cases) > 100, str(len(cases)))
    check("0. case ids are unique within each exam (a twin would hide behind the dict)", DUPES == [], str(DUPES))
    tool_exams = {k.split("/")[0] for k, c in cases.items() if c.get("tools_offered") or "tools_called" in (c.get("expected") or {})}
    asi_no_tools = sorted(k for k, e in entries.items()
                          if any(x.startswith("ASI") for x in e.get("codes", [])) and k.split("/")[0] not in tool_exams)
    check("7. an ASI code sits only on a case from an exam that offers tools", asi_no_tools == [], str(asi_no_tools))

    injection = sorted(k for k, c in cases.items() if c.get("class") == "injection")
    check("the exams carry injection cases at all", len(injection) > 0)
    missing = [k for k in injection if k not in entries]
    check("1. every class=injection case has a register entry", missing == [], str(missing))

    dangling = [k for k in entries if k not in cases]
    check("2a. every register entry resolves to a real case", dangling == [], str(dangling))
    not_inj = [k for k in entries if k in cases and cases[k].get("class") != "injection"]
    check("2b. every register entry is a class=injection case", not_inj == [], str(not_inj))

    bad_shape = sorted({code for e in entries.values() for code in e.get("codes", []) if not CODE_RE.match(code)})
    check("3a. every code carries an edition suffix (LLMnn:YYYY / ASInn:YYYY)", bad_shape == [], str(bad_shape))
    unknown = sorted({code for e in entries.values() for code in e.get("codes", []) if code not in vocab})
    check("3b. every code is in the register's vocabulary", unknown == [], str(unknown))
    empty = [k for k, e in entries.items() if not e.get("codes")]
    check("3c. every entry has at least one code", empty == [], str(empty))

    no_why = [k for k, e in entries.items() if not str(e.get("why", "")).strip()]
    check("4. every entry says why", no_why == [], str(no_why))

    for fam in ("LLM", "ASI"):
        nums = sorted(k.split(":")[0][3:] for k in vocab if k.startswith(fam))
        check(f"5. vocabulary has {fam}01..{fam}10 exactly once each", nums == [f"{i:02d}" for i in range(1, 11)], str(nums))
    check("5b. every vocabulary key matches the code shape", all(CODE_RE.match(k) for k in vocab),
          str([k for k in vocab if not CODE_RE.match(k)]))

    inline = sorted(k for k, c in cases.items() if re.search(r'"(LLM|ASI)\d\d(:20\d\d)?"', json.dumps(c)))
    check("6. no case carries an OWASP code inline (side-car only)", inline == [], str(inline))

    print(f"\n{len(injection)} injection cases, {len(entries)} register entries, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
