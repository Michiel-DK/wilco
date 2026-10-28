#!/usr/bin/env python3
"""docs/gotchas.md is the public mirror of CLAUDE.md's numbered gotchas (CLAUDE.md stays private; 48 files in the cut cite
"CLAUDE.md gotcha N" — CTO screen of the public clone, 28 Oct 2026). Pinned byte-identical so it cannot drift.

    python3 sandbox/test_gotchas_mirror.py
"""
from __future__ import annotations
import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


cl = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
start, end = cl.find("## Gotchas — each one cost a build"), cl.find("## Conventions")
check("CLAUDE.md has the Gotchas section followed by Conventions", 0 <= start < end)
section = cl[start:end].rstrip() + "\n"
mirror = (ROOT / "docs" / "gotchas.md").read_text(encoding="utf-8")
body = mirror[mirror.find("## Gotchas — each one cost a build"):]
check("docs/gotchas.md carries the section byte-identical after its header", body == section,
      f"first difference at char {next((i for i, (a, b) in enumerate(zip(body, section)) if a != b), min(len(body), len(section)))}")
check("the mirror's header says what it is and names the pin", "sandbox/test_gotchas_mirror.py" in mirror[:600] and "CLAUDE.md" in mirror[:600])
nums = [int(m) for m in re.findall(r"^(\d+)\. \*\*", section, re.M)]
check("the gotchas are numbered 1..N without a gap (the numbers the docstrings cite)", nums == list(range(1, len(nums) + 1)) and len(nums) >= 20, str(nums))
tpl = (ROOT / "scripts" / "public-snapshot" / "README.md").read_text(encoding="utf-8")
check("the public README template points at docs/gotchas.md", "docs/gotchas.md" in tpl)
pub = (ROOT / "scripts" / "publish-public-snapshot.sh").read_text(encoding="utf-8")
check("the publish allowlist ships docs/gotchas.md", "docs/gotchas.md" in pub)
print("\n" + ("FAILED: " + ", ".join(FAILED) if FAILED else "all green"))
sys.exit(1 if FAILED else 0)
