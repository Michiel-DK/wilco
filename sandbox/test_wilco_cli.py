"""W5 — the `wilco` command (wilco_cli.py) and its package metadata (pyproject.toml).

[P] pyproject.toml: name wilco-exams 0.1.0, python >= 3.10, the deps are requirements.txt's, `wilco = wilco_cli:main`,
    the package is the shim only (py-modules, no auto-discovery), setuptools >= 64 (PEP 660 editable installs).
[D] every one of the eight commands runs the script it names, through the real entry point (`python3 wilco_cli.py`,
    from a foreign cwd): same stdout and the same exit code as `python3 <script> ...`, including the refusals
    (pick's exit 2 on unequal case sets, run's exit 2 on the tier guard, before any request).
[U] an unknown command, or none, exits 2; `--help` names all eight.
[R] the checkout is found from the shim's own folder or by walking up from the cwd; with neither, exit 2 and the
    clone line (a non-editable install never runs against an empty tree).

All offline: the stub provider, committed result files, a temp --root for `new`. This file ships in the public cut.
Seen RED (recorded in the PR body): each check by a mutant of wilco_cli.py / pyproject.toml, one at a time.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHIM = ROOT / "wilco_cli.py"
PY = sys.executable
FOREIGN = tempfile.mkdtemp(prefix="test_wilco_cwd_")

FAILED = []


def check(label, ok, extra=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {extra}" if not ok and extra else ""))
    if not ok:
        FAILED.append(label)


def sh(argv, cwd=FOREIGN):
    r = subprocess.run([PY, *map(str, argv)], capture_output=True, text=True, timeout=300, cwd=cwd)
    return r.returncode, r.stdout, r.stderr


def wilco(*args, cwd=FOREIGN):
    return sh([SHIM, *args], cwd=cwd)


def same(label, shim_args, direct_argv, want_rc):
    """the shim's run == the script's own run: exit code (== want_rc), stdout and stderr byte for byte."""
    a, b = wilco(*shim_args), sh(direct_argv)
    check(f"[D] {label}: exit {want_rc} through the shim, as direct", a[0] == b[0] == want_rc, f"shim rc={a[0]} direct rc={b[0]}"
          f" stderr={a[2][-200:]!r}")
    check(f"[D] {label}: stdout and stderr identical to the direct run", a[1:] == b[1:] and (a[1] + a[2]).strip() != "",
          f"{(a[1] + a[2])[-200:]!r} vs {(b[1] + b[2])[-200:]!r}")
    return a


# ------------------------------------------------------------------ [P] pyproject.toml (tomllib, or pip's vendored tomli on 3.10)

try:
    import tomllib  # 3.11+
except ModuleNotFoundError:  # 3.10: the TOML parser pip vendors (a real parser: an invalid file raises here, loudly)
    from pip._vendor import tomli as tomllib
pp = (ROOT / "pyproject.toml").read_text()
try:
    toml = tomllib.loads(pp)
    toml_err = None
except Exception as e:  # noqa: BLE001 — reported as a FAIL, never a skip
    toml, toml_err = {}, f"{type(e).__name__}: {e}"
check("[P] pyproject.toml parses as TOML", toml_err is None, toml_err or "")
proj, st = toml.get("project", {}), toml.get("tool", {}).get("setuptools", {})
check("[P] name is wilco-exams", proj.get("name") == "wilco-exams", repr(proj.get("name")))
check("[P] version is 0.1.0", proj.get("version") == "0.1.0", repr(proj.get("version")))
check("[P] requires-python >= 3.10", proj.get("requires-python") == ">=3.10", repr(proj.get("requires-python")))
check("[P] the console script: wilco = wilco_cli:main", proj.get("scripts") == {"wilco": "wilco_cli:main"}, repr(proj.get("scripts")))
reqs = sorted(ln.strip() for ln in (ROOT / "requirements.txt").read_text().splitlines() if ln.strip() and not ln.startswith("#"))
check("[P] dependencies are exactly requirements.txt's (requests, PyYAML)", sorted(proj.get("dependencies", [])) == reqs
      and len(reqs) == 2, f"{proj.get('dependencies')} vs {reqs}")
check("[P] the package is the shim only: py-modules = [\"wilco_cli\"], no packages/find",
      st.get("py-modules") == ["wilco_cli"] and "packages" not in st, repr(st))
check("[P] readme is README.md (the PyPI page) and it exists", proj.get("readme") == "README.md" and (ROOT / "README.md").is_file(),
      repr(proj.get("readme")))
check("[P] project URLs: the results site and the wilco repo", proj.get("urls") == {
      "Homepage": "https://roger3000.com/wilco", "Source": "https://github.com/Michiel-DK/wilco"}, repr(proj.get("urls")))
check("[P] licence is the SPDX string MIT (the table form is deprecated, removal 2027-02-18)", proj.get("license") == "MIT",
      repr(proj.get("license")))
bs = toml.get("build-system", {})
check("[P] build backend setuptools >= 77 (PEP 660 editable installs + PEP 639 licence string)",
      bs.get("requires") == ["setuptools>=77"] and bs.get("build-backend") == "setuptools.build_meta", repr(bs))

# ------------------------------------------------------------------ [D] the eight commands, each through the shim

sys.path.insert(0, str(ROOT))
import wilco_cli  # noqa: E402

check("[D] the shim has exactly the nine commands (W7 added adopt)",
      sorted(wilco_cli.COMMANDS) == sorted(["new", "validate", "pick", "adopt", "list", "run", "diff", "check", "live"]),
      repr(wilco_cli.COMMANDS))

RUNNER = ROOT / "sandbox" / "runner.py"
out = same("list", ["list"], [RUNNER, "list"], 0)
exams = sorted(p.parent.name for p in (ROOT / "evals").glob("*/cases.json"))
listed = sorted(ln.split()[0] for ln in out[1].splitlines() if "[exam ok" in ln)
check("[D] list names every committed exam (eight in this repo)", listed == exams and len(exams) == 8, f"{listed} vs {exams}")

same("validate email-triage", ["validate", "email-triage"], [ROOT / "scripts" / "exam_validate.py", "email-triage"], 0)
v_bad, v_dir = wilco("validate", "no-such-task"), sh([ROOT / "scripts" / "exam_validate.py", "no-such-task"])
check("[D] validate on a missing exam: the script's own non-zero exit, through the shim", v_bad[0] == v_dir[0] != 0,
      f"{v_bad[0]} vs {v_dir[0]}")

tmp_a, tmp_b = tempfile.mkdtemp(prefix="test_wilco_new_a_"), tempfile.mkdtemp(prefix="test_wilco_new_b_")
n_a = wilco("new", "demo-task", "--mode", "labels", "--root", tmp_a)
n_b = sh([ROOT / "scripts" / "exam_new.py", "demo-task", "--mode", "labels", "--root", tmp_b])
files = lambda d: sorted((str(p.relative_to(d)), p.read_text()) for p in pathlib.Path(d).rglob("*") if p.is_file())
check("[D] new: exit 0 and the same files, byte for byte, as exam_new.py", n_a[0] == n_b[0] == 0 and files(tmp_a) == files(tmp_b)
      and len(files(tmp_a)) >= 2, f"rc {n_a[0]}/{n_b[0]}, {len(files(tmp_a))} files")
check("[D] new: a second run refuses to overwrite, exit 2", wilco("new", "demo-task", "--mode", "labels", "--root", tmp_a)[0] == 2)

MATRIX = sorted(ROOT.glob("docs/probes/matrix-2026-09-27/results/crm-followup__*.json"))
PICK = ROOT / "scripts" / "pick.py"
md = pathlib.Path(tempfile.mkdtemp(prefix="test_wilco_pick_")) / "p.md"
p_ok = same("pick over the committed matrix", ["pick", "crm-followup", *MATRIX, "--out", md], [PICK, "crm-followup", *MATRIX, "--out", md], 0)
check("[D] pick prints its winner line", any(ln.startswith("pick: ") for ln in p_ok[1].splitlines()), p_ok[1][-200:])
same("pick refuses unequal case sets (matrix + the champion's snapshot)",
     ["pick", "crm-followup", *MATRIX, ROOT / "evals" / "crm-followup" / "snapshot.json", "--out", md],
     [PICK, "crm-followup", *MATRIX, ROOT / "evals" / "crm-followup" / "snapshot.json", "--out", md], 2)

r_stub = wilco("run", "email-triage", "--provider", "stub", "--model", "stub")
check("[D] run with the stub: exit 0, train and held-out scored, a result file named",
      r_stub[0] == 0 and re.search(r"^train\s+\d+/\d+\s+heldout\s+\d+/\d+\s+-> results/email-triage__stub__stub\.json$", r_stub[1], re.M)
      is not None, f"rc={r_stub[0]} {r_stub[1][-200:]!r}")
r_tier = wilco("run", "email-triage", "--provider", "openrouter", "--model", "x")
check("[D] run above the exam's tier: the runner's exit 2, refused before any request",
      r_tier[0] == 2 and "refused before any request" in r_tier[2], f"rc={r_tier[0]} {r_tier[2][-200:]!r}")
for c in ("diff", "check", "live"):
    # W7: the shim passes WILCO_PROG=wilco, so its usage says `wilco <c>` where the direct run says `runner.py <c>`
    # (argparse re-wraps the usage to the prog's width, hence the whitespace-normalised comparison); otherwise identical.
    a, b = wilco(c, "--help"), sh([RUNNER, c, "--help"])
    norm = lambda s, prog: " ".join(s.replace(f"{prog} {c}", "<P>").split())  # noqa: E731
    check(f"[D] {c} --help reaches runner.py's own parser: exit 0 both ways", a[0] == b[0] == 0, f"{a[0]} {b[0]}")
    check(f"[D] {c} --help: usage `wilco {c}` through the shim, `runner.py {c}` direct",
          a[1].startswith(f"usage: wilco {c} ") and b[1].startswith(f"usage: runner.py {c} "), f"{a[1][:40]!r} {b[1][:40]!r}")
    check(f"[D] {c} --help: the same parser either way (identical but for the prog)",
          norm(a[1], "wilco") == norm(b[1], "runner.py") and a[2] == b[2] == "", f"{a[1][-120:]!r} vs {b[1][-120:]!r}")
same("run on a missing agent (the runner's string SystemExit: message on stderr, exit 1, before any provider)",
     ["run", "no-such-agent", "--provider", "stub", "--model", "stub"], [RUNNER, "run", "no-such-agent", "--provider", "stub", "--model", "stub"], 1)
n_crash, n_crash_d = (wilco("new", "demo", "--mode", "labels", "--root", "/dev/null/x"),
                      sh([ROOT / "scripts" / "exam_new.py", "demo", "--mode", "labels", "--root", "/dev/null/x"]))
check("[D] an uncaught exception in the script: exit 1 and its traceback, as direct (never swallowed)",
      n_crash[0] == n_crash_d[0] == 1 and "NotADirectoryError" in n_crash[2] and "NotADirectoryError" in n_crash_d[2],
      f"rc {n_crash[0]}/{n_crash_d[0]} {n_crash[2][-150:]!r}")
c_none = wilco("check")
check("[D] check without a task: runner.py's argparse error, exit 2 (W7: names `task`, usage `wilco check`)",
      c_none[0] == 2 and "required: task" in c_none[2] and "usage: wilco check" in c_none[2], c_none[2][-200:])

# ------------------------------------------------------------------ [U] usage

u_none, u_help = wilco(), wilco("--help")
check("[U] `wilco help` and `-h` print the usage, exit 0", all(wilco(h)[0] == 0 and "usage: wilco" in wilco(h)[1] for h in ("help", "-h")))
for c in wilco_cli.COMMANDS:
    m = re.search(rf"^  {c}\b.*\(([^)\s]+)", u_help[1], re.M)
    want = wilco_cli.SCRIPTS.get(c, wilco_cli.RUNNER)
    check(f"[U] --help names the script `{c}` really runs ({want})", m is not None and m.group(1) == want, m and m.group(1))
check("[U] no command: usage, exit 2", u_none[0] == 2 and "usage: wilco" in u_none[1])
# In-process, with dispatch stubbed: a shim that passed `run-all` through would start real local inference on every
# exam (it did, once, while this check was being seen red as a subprocess — 23 Oct). Here nothing can be reached.
import contextlib, io  # noqa: E401,E402
reached = []
real_run_path = wilco_cli.runpy.run_path
wilco_cli.runpy.run_path = lambda *a, **k: reached.append(a)
try:
    for bad in ("run-all", "check-all", "frobnicate"):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc_bad = wilco_cli.main([bad, "x"])
        check(f"[U] {bad!r} is not a shim command: exit 2, named, no script reached",
              rc_bad == 2 and f"unknown command {bad!r}" in err.getvalue() and reached == [], f"rc={rc_bad} {err.getvalue()!r} {reached}")
finally:
    wilco_cli.runpy.run_path = real_run_path
check("[U] --help: exit 0 and every command listed",
      u_help[0] == 0 and all(re.search(rf"^  {c}\b", u_help[1], re.M) for c in wilco_cli.COMMANDS), u_help[1])

# ------------------------------------------------------------------ [R] finding the checkout

lone = pathlib.Path(tempfile.mkdtemp(prefix="test_wilco_lone_"))
shutil.copy(SHIM, lone / "wilco_cli.py")
r_lone = sh([lone / "wilco_cli.py", "list"], cwd=lone)
check("[R] a shim with no checkout beside it or above the cwd: exit 2, says so, prints the clone line",
      r_lone[0] == 2 and "no checkout found" in r_lone[2] and r_lone[1] == ""
      and wilco_cli.CLONE == "git clone https://github.com/Michiel-DK/wilco && cd wilco && pip install -e ."
      and wilco_cli.CLONE in r_lone[2],
      f"rc={r_lone[0]} {r_lone[2]!r}")
r_walk = sh([lone / "wilco_cli.py", "list"], cwd=ROOT / "evals" / "email-triage")
check("[R] the same lone shim run from inside a checkout finds it by walking up (what a non-editable install does)",
      r_walk[0] == 0 and r_walk[1] == out[1], f"rc={r_walk[0]} {r_walk[2][-200:]!r}")
# a folder with sandbox/runner.py but no evals/ is not a checkout (its runner.py here only prints, so a mutant is harmless)
half = pathlib.Path(tempfile.mkdtemp(prefix="test_wilco_half_"))
(half / "sandbox").mkdir()
(half / "sandbox" / "runner.py").write_text("print('HALF-CHECKOUT RUNNER')\n")
r_half = sh([lone / "wilco_cli.py", "list"], cwd=half)
check("[R] sandbox/runner.py without evals/ is not a checkout: exit 2, nothing run", r_half[0] == 2 and "HALF-CHECKOUT" not in r_half[1],
      f"rc={r_half[0]} {r_half[1][-100:]!r}")
shutil.rmtree(half)
# the shim's own checkout wins over one above the cwd (a decoy whose runner.py only prints, so a mutant is harmless)
decoy = pathlib.Path(tempfile.mkdtemp(prefix="test_wilco_decoy_"))
(decoy / "sandbox").mkdir()
(decoy / "evals").mkdir()
(decoy / "sandbox" / "runner.py").write_text("print('DECOY RUNNER')\n")
r_decoy = wilco("list", cwd=decoy)
check("[R] an editable install runs its own checkout, not one found from the cwd", r_decoy[0] == 0 and r_decoy[1] == out[1]
      and "DECOY" not in r_decoy[1], f"rc={r_decoy[0]} {r_decoy[1][-100:]!r}")
shutil.rmtree(decoy)
r_top = sh([lone / "wilco_cli.py", "list"], cwd=ROOT)
check("[R] ... and from the checkout root itself (the README's `cd wilco`, then `wilco list`)", r_top[0] == 0 and r_top[1] == out[1],
      f"rc={r_top[0]} {r_top[2][-200:]!r}")
shutil.rmtree(lone)
for d in (tmp_a, tmp_b, FOREIGN, md.parent):
    shutil.rmtree(d, ignore_errors=True)

print(f"\n{len(FAILED)} FAILED" if FAILED else "\nall passed")
sys.exit(1 if FAILED else 0)
