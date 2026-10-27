"""wilco — the command line over this repo's exams. A thin shim: nothing is moved, every command runs the
existing script exactly as `python3 <script> ...` would (same argv, same exit code).

    wilco new <task> --mode labels       -> scripts/exam_new.py
    wilco validate <task>                -> scripts/exam_validate.py
    wilco pick <task> [files...]         -> scripts/pick.py
    wilco adopt <task> <provider/model>  -> scripts/exam_adopt.py
    wilco list | run | diff | check | live ...   -> sandbox/runner.py <cmd> ...

The scripts see WILCO_PROG=wilco in their environment for the run, so their usage and error lines say
`wilco <cmd>` (run directly, they say `runner.py` / the script's name, as before).

The exams, agents and runner live in a checkout, not in the package: install with `pip install -e .` from a
clone. A non-editable install finds the checkout by walking up from the current directory, and refuses (exit 2)
when there is none — it never runs against an empty tree.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

SCRIPTS = {"new": "scripts/exam_new.py", "validate": "scripts/exam_validate.py", "pick": "scripts/pick.py",
           "adopt": "scripts/exam_adopt.py"}
RUNNER = "sandbox/runner.py"
RUNNER_CMDS = ("list", "run", "diff", "check", "live")
COMMANDS = ("new", "validate", "pick", "adopt") + RUNNER_CMDS
CLONE = "git clone https://github.com/Michiel-DK/wilco && cd wilco && pip install -e ."
PROG_ENV = "WILCO_PROG"   # read by sandbox/runner.py and the scripts for their usage/error lines

USAGE = f"""usage: wilco <command> [args...]

  new <task> --mode M     scaffold an exam + agent        (scripts/exam_new.py)
  validate <task>         check an exam's structure       (scripts/exam_validate.py)
  list                    the tasks, their champions      (sandbox/runner.py list)
  run <task> ...          one model sits one exam         (sandbox/runner.py run)
  diff <task> --models .. every candidate sits it         (sandbox/runner.py diff)
  pick <task> [files...]  the cheapest that passes        (scripts/pick.py)
  adopt <task> <p/model>  make the pick the task's model  (scripts/exam_adopt.py)
  check <task>            re-sit vs the snapshot, per case (sandbox/runner.py check)
  live <task> --input ..  answer one input via routes.yaml (sandbox/runner.py live)

`wilco <command> --help` prints that command's own options; run/check/diff also take
--help-advanced (research flags)."""


def _is_root(p: Path) -> bool:
    return (p / RUNNER).is_file() and (p / "evals").is_dir()


def find_root() -> Path | None:
    """The checkout this shim runs against: its own folder (an editable install or `python3 wilco_cli.py`),
    else the nearest ancestor of the current directory that holds sandbox/runner.py and evals/."""
    here = Path(__file__).resolve().parent
    if _is_root(here):
        return here
    cwd = Path.cwd().resolve()
    for p in (cwd, *cwd.parents):
        if _is_root(p):
            return p
    return None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0 if argv else 2
    cmd, rest = argv[0], argv[1:]
    if cmd not in COMMANDS:
        print(f"wilco: unknown command {cmd!r}; one of: {', '.join(COMMANDS)}", file=sys.stderr)
        return 2
    root = find_root()
    if root is None:
        print("wilco: no checkout found (no sandbox/runner.py + evals/ here or above "
              f"{Path.cwd()}). The exams live in the repo, not the package:\n  {CLONE}", file=sys.stderr)
        return 2
    script = root / (SCRIPTS[cmd] if cmd in SCRIPTS else RUNNER)
    args = rest if cmd in SCRIPTS else [cmd, *rest]
    # exactly `python3 <script> <args>`: argv[0] is the script, its folder leads sys.path, run as __main__
    saved_argv, saved_path, saved_prog = sys.argv, list(sys.path), os.environ.get(PROG_ENV)
    sys.argv = [str(script), *args]
    sys.path.insert(0, str(script.parent))
    os.environ[PROG_ENV] = "wilco"
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as e:
        code = e.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return 1
    finally:
        sys.argv, sys.path[:] = saved_argv, saved_path
        if saved_prog is None:
            os.environ.pop(PROG_ENV, None)
        else:
            os.environ[PROG_ENV] = saved_prog
    return 0


if __name__ == "__main__":
    sys.exit(main())
