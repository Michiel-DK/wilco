#!/usr/bin/env python3
"""docs/gotchas.md is the public mirror of CLAUDE.md's numbered gotchas (CLAUDE.md stays private; 48 files in the cut cite
"CLAUDE.md gotcha N" — CTO screen of the public clone, 28 Oct 2026). Pinned byte-identical so it cannot drift.
Runs in BOTH trees: private (pin against CLAUDE.md) and the public cut (CLAUDE.md absent by design — gotcha 19: an effect
check on each side, never a skip; the first cut with this file went to CI red on FileNotFoundError, 28 Oct evening).
Declared limit: the public side cannot detect a STALE mirror (nothing to compare against there); the guard for drift is the
private byte pin, which runs before every publish, plus the publish script copying the committed file.

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


mirror = (ROOT / "docs" / "gotchas.md").read_text(encoding="utf-8")
body = mirror[mirror.find("## Gotchas — each one cost a build"):]
nums = [int(m) for m in re.findall(r"^(\d+)\. \*\*", body, re.M)]
check("docs/gotchas.md exists, carries the Gotchas heading and is numbered 1..N without a gap (N >= 20)",
      body.startswith("## Gotchas") and nums == list(range(1, len(nums) + 1)) and len(nums) >= 20, str(nums))
check("the mirror's header says what it is and names this pin", "sandbox/test_gotchas_mirror.py" in mirror[:600] and "CLAUDE.md" in mirror[:600])

# Two trees run this file (CLAUDE.md gotcha 19: branch on presence with an EFFECT check on both sides, never a skip):
#   the private checkout — CLAUDE.md, the README template and the publish script exist: the mirror is pinned byte-identical
#   the public cut   — none of the three ship (the allowlist leaves them out by design): the cut is positively identified
#                      by all three being absent together, and the generated README.md must name the mirror.
private = (ROOT / "CLAUDE.md").exists()
tpl_p, pub_p = ROOT / "scripts" / "public-snapshot" / "README.md", ROOT / "scripts" / "publish-public-snapshot.sh"
if private:
    cl = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    start, end = cl.find("## Gotchas — each one cost a build"), cl.find("## Conventions")
    check("private: CLAUDE.md has the Gotchas section followed by Conventions", 0 <= start < end)
    section = cl[start:end].rstrip() + "\n"
    check("private: docs/gotchas.md carries the section byte-identical after its header", body == section,
          f"first difference at char {next((i for i, (a, b) in enumerate(zip(body, section)) if a != b), min(len(body), len(section)))}")
    check("private: the public README template points at docs/gotchas.md", tpl_p.exists() and "docs/gotchas.md" in tpl_p.read_text(encoding="utf-8"))
    check("private: the publish allowlist ships docs/gotchas.md", pub_p.exists() and "docs/gotchas.md" in pub_p.read_text(encoding="utf-8"))
else:
    check("public cut, positively identified: CLAUDE.md, the README template and the publish script are ALL absent (not just one)",
          not tpl_p.exists() and not pub_p.exists())
    readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
    check("public cut: the generated README.md names docs/gotchas.md as the mirror of the private CLAUDE.md", "docs/gotchas.md" in readme and "CLAUDE.md" in readme)
    check("public cut: the mirror carries no private hq path (the cut's scrub rule fired)", "see hq `" not in mirror)
print("\n" + ("FAILED: " + ", ".join(FAILED) if FAILED else "all green"))
sys.exit(1 if FAILED else 0)
