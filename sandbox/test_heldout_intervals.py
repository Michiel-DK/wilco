"""as-eb-intervals (11 Nov 2026): every rendered HELD-OUT score carries its 95% Wilson interval, through
`stats.fmt_ci` (the single implementation); train scores stay a bare count. Rule: docs/tiers-and-results-table.md §2.

check()-style on purpose (CLAUDE.md gotcha 17): a failure appends to FAILED and main() returns 1; pytest is blind to it.
Every render site is driven through its REAL entry point on fixture data (gotcha 5), no inference:
  [P] scripts/pick.py      build() -> terminal() and markdown() (the results/<task>-pick.md writer)
  [S] sandbox/runner.py    _summary_line (the `run` / `check` / snapshot score line)
  [D] sandbox/runner.py    cmd_diff on the offline `stub` provider: the challenger row AND the snapshot champion row
  [G] scripts/exam_grade.py main() (`wilco grade`), in-process, results to a temp RESULTS_DIR: the summary line
  [R] scripts/build_results_page.py rendered to a temp path: task table, pick table, fine-tune table, pass^k table
(`wilco grade`'s full line is also pinned exactly in sandbox/test_exam_grade.py A2/R3.)
Seen RED 11 Nov with the origin/master copies of those four files swapped back in (PR body has the output).
The expected interval strings are literals as well as fmt_ci calls: 13/16 -> 0.57–0.93 is the brief's own figure, so a
silent change to fmt_ci's format or z is caught here too, not only a missing call."""
import argparse
import contextlib
import io
import json

import pathlib
import re
import subprocess
import sys
import tempfile
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
sys.path.insert(0, str(ROOT / "scripts"))
import stats  # noqa: E402
import runner  # noqa: E402
import pick  # noqa: E402
import exam_grade  # noqa: E402

FAILED = []


def check(label, ok, extra=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {extra}" if not ok and extra else ""))
    if not ok:
        FAILED.append(label)


def guarded(label):
    def deco(fn):
        print(f"running {fn.__name__}")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — a red run on old code may land here
            check(f"{label} (raised {type(exc).__name__}: {exc})", False, traceback.format_exc(limit=3))
        return fn
    return deco


def _capture(fn, *a, **k):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*a, **k)
    return rc, out.getvalue(), err.getvalue()


TMP = pathlib.Path(tempfile.mkdtemp(prefix="heldout-intervals-"))
CI_13_16 = "95% CI 0.57–0.93"
CI_10_16 = "95% CI 0.39–0.82"


@guarded("[0] fmt_ci literals")
def test_0_literals():
    check("[0] fmt_ci(13, 16) is the brief's 0.57–0.93", stats.fmt_ci(13, 16) == CI_13_16, stats.fmt_ci(13, 16))
    check("[0] fmt_ci(10, 16) literal", stats.fmt_ci(10, 16) == CI_10_16, stats.fmt_ci(10, 16))


def _fixture_result(provider, model, held_pass, held_n=16, train_pass=3, train_n=4):
    cases = ([{"id": f"t{i}", "split": "train", "passed": i < train_pass} for i in range(train_n)]
             + [{"id": f"h{i}", "split": "heldout", "passed": i < held_pass} for i in range(held_n)])
    return {"agent": "fixture-task", "provider": provider, "model": model, "cases": cases,
            "train": {"passed": train_pass, "total": train_n, "score": train_pass / train_n},
            "heldout": {"passed": held_pass, "total": held_n, "score": held_pass / held_n},
            "metrics_totals": {"prompt_tokens": 100, "completion_tokens": 10, "complete": True}}


@guarded("[P] pick table")
def test_P_pick():
    paths = []
    for m, k in (("a", 13), ("b", 10)):
        p = TMP / f"fixture-task__stub__{m}.json"
        p.write_text(json.dumps(_fixture_result("stub", m, k)))
        paths.append(str(p))
    prices = {"as_of": "2026-11-11", "source": "fixture",
              "models": {"stub/a": {"input": 0, "output": 0}, "stub/b": {"input": 0, "output": 0}}}
    r = pick.build("fixture-task", paths, prices)
    md, term = pick.markdown(r), pick.terminal(r)
    row_a = next((ln for ln in md.splitlines() if ln.startswith("| stub/a ")), "")
    row_b = next((ln for ln in md.splitlines() if ln.startswith("| stub/b ")), "")
    check("[P] markdown row: the held-out cell is 13/16 with its interval",
          f"| 13/16 ({CI_13_16}) |" in row_a and stats.fmt_ci(13, 16) in row_a, row_a)
    check("[P] markdown row: 10/16 carries its own interval", f"| 10/16 ({CI_10_16}) |" in row_b, row_b)
    check("[P] markdown header + separator have the same column count",
          md.splitlines()[4].count("|") == md.splitlines()[5].count("|"), "\n".join(md.splitlines()[4:6]))
    trow = next((ln for ln in term.splitlines() if ln.startswith("stub/a ")), "")
    check("[P] terminal row carries the same interval", f"13/16 ({CI_13_16})" in trow, trow)


@guarded("[S] runner _summary_line")
def test_S_summary():
    line = runner._summary_line(_fixture_result("stub", "a", 13))
    check("[S] held-out k/n followed by its interval", f"heldout 13/16 ({CI_13_16})" in line, line)
    check("[S] train stays a bare count (exactly one interval on the line)",
          line.startswith("train   3/4  heldout") and line.count("95% CI") == 1, line)


@guarded("[D] runner cmd_diff")
def test_D_diff():
    ns = argparse.Namespace(agent="email-triage", models="stub/gemma4:e2b-it-qat", provider=None, model=None,
                            snapshot=False, loads=3, timeout=None, dedupe_tools=False, assembly="full", split="all",
                            scoped_rule="off", allow_truncation=False)   # the fields test_w2_runner_guards._ns passes
    saved = runner.RESULTS_DIR
    runner.RESULTS_DIR = TMP / "diff"
    try:
        _rc, out, _err = _capture(runner.cmd_diff, ns)
    finally:
        runner.RESULTS_DIR = saved
    snap = json.loads((ROOT / "evals" / "email-triage" / "snapshot.json").read_text())
    held = [c for c in snap["cases"] if c["split"] == "heldout"]
    k, n = sum(1 for c in held if c["passed"]), len(held)
    srow = next((ln for ln in out.splitlines() if "<- current (snapshot)" in ln), "")
    check("[D] the snapshot champion row prints held-out k/n and its interval (was a bare fraction)",
          f"{k}/{n}" in srow and stats.fmt_ci(k, n) in srow, srow or out[-600:])
    crow = next((ln for ln in out.splitlines() if ln.startswith("stub ")), "")
    check("[D] the challenger row's interval is fmt_ci's text", "95% CI " in crow and crow.count("95% CI") == 1,
          crow or out[-600:])


@guarded("[G] exam_grade summary")
def test_G_grade():
    exam = json.loads((ROOT / "evals" / "email-triage" / "cases.json").read_text())
    key = {c["id"]: json.dumps({"label": c["expected"]["label"]}) for c in exam["cases"]}
    ans = TMP / "answers.json"
    ans.write_text(json.dumps(key))
    held = [c for c in exam["cases"] if c["split"] == "heldout"]
    saved = runner.RESULTS_DIR
    runner.RESULTS_DIR = TMP / "grade-results"   # the repo's results/ is never written
    try:
        rc, out, err = _capture(exam_grade.main, ["email-triage", str(ans)])
    finally:
        runner.RESULTS_DIR = saved
    line = next((ln for ln in out.splitlines() if ln.startswith("email-triage: train ")), "")
    want = f"heldout {len(held)}/{len(held)} ({stats.fmt_ci(len(held), len(held))})"
    check("[G] grade line: held-out k/n followed by fmt_ci's interval, train bare",
          rc == 0 and line.endswith(want) and line.count("95% CI") == 1, f"rc={rc} {line or out[-300:]} {err[-200:]}")


@guarded("[R] results page")
def test_R_page():
    out = TMP / "page.html"
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_results_page.py"), str(out)],
                       capture_output=True, text=True, cwd=ROOT)
    page = out.read_text() if out.exists() else ""
    check("[R] the builder rendered to the temp path", p.returncode == 0 and bool(page), p.stderr[-300:])
    # email-triage local champion row of the task table: 10/11 held-out (docs/probes/matrix-2026-09-27/tables.md)
    want = f'<b>10</b>/11<br><span class="muted">{stats.fmt_ci(10, 11)}</span>'
    check("[R] task table: held-out cell carries its interval", want in page, want)
    check("[R] pick table: the pick's held-out cell carries its interval",
          f'<td>10/11<br><span class="muted">{stats.fmt_ci(10, 11)}</span></td>' in page)
    check("[R] fine-tune table: before and after both carry intervals",
          f'{stats.fmt_ci(12, 18)} → {stats.fmt_ci(9, 18)}' in page)
    check("[R] pass^k table: a k/n cell carries its interval",
          f'10/13<br><span class="muted">{stats.fmt_ci(10, 13)}</span>' in page)
    check("[R] hosted table: a k/n cell carries its interval (also the bold pass^6 cell)",
          f'<td><b>6/13<br><span class="muted">{stats.fmt_ci(6, 13)}</span></b></td>' in page)
    check("[R] pick table: the GPT-5.6-Sol cell carries its interval",
          re.search(r'<td>13/19 · [^<]*<br><span class="muted">' + re.escape(stats.fmt_ci(13, 19)) + r'</span></td></tr>', page)
          is not None)
    check("[R] task table: the pass^k column carries its interval",
          f'<td>pass^3 10/11<br><span class="muted">{stats.fmt_ci(10, 11)}</span></td>' in page)
    check("[R] point tooltip carries its interval", f'/11 held-out ({stats.fmt_ci(10, 11)}) · ' in page)
    # the quality-bar chart is drawn for the CRM brief (18 held-out); its pick label is 15/18
    check("[R] quality-bar label carries its interval", f'>15/18 ({stats.fmt_ci(15, 18)}) · ' in page)


def main():
    if FAILED:
        print(f"\nFAILED {len(FAILED)}:")
        for f in FAILED:
            print(f"  - {f}")
        return 1
    print("\nall held-out interval checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
