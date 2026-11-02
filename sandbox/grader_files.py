"""The ONE list of files whose bytes define what an exam verdict means for an agent (2026-10-31).

Used by two readers, never re-typed:
  * scripts/loop_gate.py — the improvement loop's `loop_stamp`: a candidate is only compared with a baseline
    sat on byte-identical grader files (a flip could otherwise be the grader, not the prompt).
  * sandbox/runner.py — `snapshot_payload(..., grader_files=...)` records the hashes in a new snapshot, and
    `check` / `check-all` print WHICH of them changed when a stable case drifts. ATTRIBUTION ONLY: a changed
    hash never refuses `check` (that would demand a GPU re-snapshot after every runner PR); `check` already
    fails on any stable case that moves.

prompt.md is NOT in GRADER_FILES: it is the loop's modification point. `snapshot_files()` adds it for the
snapshot, where a prompt change is one more cause worth naming.
"""
from __future__ import annotations
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GRADER_FILES = ("evals/{agent}/cases.json", "evals/{agent}/properties.py", "evals/{agent}/tools_mock.py",
                "evals/{agent}/rubric.md", "agents/{agent}/agent.yaml", "agents/{agent}/decision.yaml",
                "sandbox/runner.py", "sandbox/numnorm.py", "sandbox/router.py", "sandbox/retry.py",
                "sandbox/judges.py", "sandbox/library.py")
# retry.py: call_with_retry + extract_json turn raw output into the scored answer; judges.py + rubric.md: the
# judge path (dormant today, hashed so it cannot wake silently); decision.yaml: the systemone provider;
# library.py: lesson retrieval changes the prompt when an agent has a library.
SNAPSHOT_EXTRA = ("agents/{agent}/prompt.md",)


def file_hashes(agent: str, templates=GRADER_FILES, root: Path | None = None) -> dict[str, str]:
    """{repo-relative path: sha256 | "absent"} — an absent file is recorded, so one appearing or
    disappearing between two sits also shows up. `root` None = this module's ROOT, read at CALL time."""
    root = ROOT if root is None else root
    out = {}
    for tpl in templates:
        rel = tpl.format(agent=agent)
        f = root / rel
        out[rel] = hashlib.sha256(f.read_bytes()).hexdigest() if f.is_file() else "absent"
    return out


def snapshot_files(agent: str, root: Path | None = None) -> dict[str, str]:
    return file_hashes(agent, GRADER_FILES + SNAPSHOT_EXTRA, root)


def changed(old: dict[str, str], new: dict[str, str]) -> list[str]:
    """Paths whose hash differs (or that exist in only one of the two maps), sorted."""
    return sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
