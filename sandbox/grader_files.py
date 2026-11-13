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

VERDICT STAMP (2026-11-11, as-eb-verdict-stamp): every stored verdict also carries the check version that made it.
`verdict_stamp(agent)` = {grader_hash, prompt_hash, cases_hash} is written by run_exam into every results file (and so
into snapshot-load aggregates), by the live path into every live line, and by corrections.py `add` (grader_hash +
prompt_hash). grader_hash = digest() of file_hashes(GRADER_FILES) — the SAME value `grader_hash_of()` derives from a
committed snapshot's `grader_files` map (prompt.md dropped), so no snapshot.json has to change. A file without a
grader_hash is "pre-stamp" and matches nothing. Readers warn (stale_warning) on a mismatch; scripts/pick.py refuses to
rank across mixed hashes. NOT the same thing as scripts/label_sheet.py's own `grader_hash` (that one includes prompt.md)
and not the runtime stamp (`runtime.version` / `runtime.kv_cache_type`).
"""
from __future__ import annotations
import hashlib
import json
import re
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


PRE_STAMP = "pre-stamp"
_GRADER_KEY_RES = tuple(re.compile("^" + re.escape(t).replace(re.escape("{agent}"), "[^/]+") + "$")
                        for t in GRADER_FILES)


def _sha_or_absent(f: Path) -> str:
    return hashlib.sha256(f.read_bytes()).hexdigest() if f.is_file() else "absent"


def digest(hashes: dict) -> str:
    """One sha256 hex over a {path: sha256 | "absent"} map (sorted keys; "absent" entries included)."""
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode("utf-8")).hexdigest()


def verdict_stamp(agent: str, root: Path | None = None) -> dict[str, str]:
    """{grader_hash, prompt_hash, cases_hash} for `agent` as the tree at `root` stands NOW (64-hex or "absent").
    grader_hash covers GRADER_FILES only (cases.json included); prompt.md is its own field."""
    root = ROOT if root is None else root
    return {"grader_hash": digest(file_hashes(agent, GRADER_FILES, root)),
            "prompt_hash": _sha_or_absent(root / "agents" / agent / "prompt.md"),
            "cases_hash": _sha_or_absent(root / "evals" / agent / "cases.json")}


def grader_hash_of(d: dict) -> str | None:
    """The grader_hash a stored file carries, or None (= pre-stamp). A results dict carries it as `grader_hash`; a
    snapshot dict carries a `grader_files` map, whose GRADER_FILES entries (prompt.md dropped) digest to the same value
    verdict_stamp() gives for that tree."""
    if not isinstance(d, dict):
        return None
    gh = d.get("grader_hash")
    if isinstance(gh, str) and gh:
        return gh
    gf = d.get("grader_files")
    if isinstance(gf, dict) and gf:
        return digest({k: v for k, v in gf.items() if any(r.match(k) for r in _GRADER_KEY_RES)})
    return None


def short(h: str | None) -> str:
    return PRE_STAMP if h is None else h[:12]


def stale_warning(path, d: dict, agent: str, root: Path | None = None) -> str | None:
    """One line naming `path` when its grader_hash is not the current one for `agent` (pre-stamp counts), else None."""
    cur = verdict_stamp(agent, root)["grader_hash"]
    have = grader_hash_of(d)
    if have is None:
        return (f"WARNING: {path}: pre-stamp (no grader_hash; current {short(cur)}) — verdicts made by an unknown "
                f"check version")
    if have != cur:
        return (f"WARNING: {path}: grader_hash {short(have)} != current {short(cur)} (verdicts made by a different "
                f"check version)")
    return None
