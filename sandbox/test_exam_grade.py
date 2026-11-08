"""`wilco grade` — score answers made OUTSIDE our runner (n8n first), with the real grader. No model, no network.

Every check goes through the real entry point `wilco_cli.main(['grade', ...])` with a temp answers file; results are
written to a temp RESULTS_DIR (the repo's results/ is never touched).

[A] agreement: email-triage answers built from each case's committed expected label -> train 8/8, heldout 20/20, rc 0;
    the per-case verdicts equal what runner.run_exam gives the same answers through an independent replay.
[R] seen-red: ONE changed label -> exactly that case fails, every other verdict unchanged (gotcha 3). One unparseable
    answer fails alone and does not make the grade wait on retry backoff.
[O] the replay keys by input, not order: a shuffled answers file gives identical verdicts.
[F] the four formats (JSON object incl. {"text"} values and _meta, JSON list, n8n execute --rawOutput with leading log
    lines, an n8n API/MCP execution object, CSV) give identical per-case verdicts and identical graded outputs.
[X] refusals: unknown case id, missing case, unrecognised format, absent n8n node, trajectory exam, unknown task, a
    judge-graded exam -> rc 2, exactly one stderr line, no traceback, no result file.
[Z] zero network: urllib.request.urlopen and requests.Session.request raise for the whole file; none was reached.
[S] runner.adapter_for and retry's backoff sleep are the original objects after success, refusal and an exception.
[I] integrations/n8n: the workflow is JSON, every connection names existing nodes, no credential id / secret / token;
    the README states the defaults-reproduce-28/28 and numCtx-moved-5/28 findings with their source.

pytest is blind to this file (CLAUDE.md gotcha 17): failures go in FAILED and main() returns the exit code.
Seen RED: recorded in the PR body.
"""
import contextlib
import csv
import importlib.util
import io
import json
import os
import pathlib
import random
import re
import shutil
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
os.environ.pop("WILCO_PROG", None)

import requests  # noqa: E402
import urllib.request  # noqa: E402

import runner  # noqa: E402
import retry  # noqa: E402
import wilco_cli  # noqa: E402

FAILED = []
TASK = "email-triage"
NET_CALLS = []


def check(label, ok, extra=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {extra}" if not ok and extra else ""))
    if not ok:
        FAILED.append(label)


def _net(*a, **k):
    NET_CALLS.append(a[:1])
    raise AssertionError("network reached during a grade")


urllib.request.urlopen = _net
requests.Session.request = _net

ORIG_ADAPTER = runner.adapter_for
ORIG_SLEEP = retry.call_with_retry.__kwdefaults__["sleep"]
TMP = pathlib.Path(tempfile.mkdtemp(prefix="exam_grade_test_"))
runner.RESULTS_DIR = TMP / "results"

EXAM = json.loads((ROOT / "evals" / TASK / "cases.json").read_text())
CASES = EXAM["cases"]
KEY = {c["id"]: json.dumps({"label": c["expected"]["label"]}) for c in CASES}
FLIP_ID = "client-quote-request"   # a train case whose key is reply_now


def grade_cli(answers_path, *extra, task=TASK):
    """wilco_cli.main(['grade', ...]) -> (rc, stdout, stderr, per-case {id: (passed, got)} from the written file or None)."""
    out, err = io.StringIO(), io.StringIO()
    shutil.rmtree(runner.RESULTS_DIR, ignore_errors=True)
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = wilco_cli.main(["grade", task, str(answers_path), *extra])
        except Exception as exc:   # a traceback is a red check, not a crashed test file
            rc = -99
            err.write(f"Traceback: {type(exc).__name__}: {exc}\n")
    files = sorted(runner.RESULTS_DIR.glob("external/*.json")) if runner.RESULTS_DIR.exists() else []
    per = None
    if files:
        res = json.loads(files[0].read_text())
        per = {c["id"]: (c["passed"], json.dumps(c["got"], sort_keys=True)) for c in res["cases"]}
    return rc, out.getvalue(), err.getvalue(), per, files


def write(name, text):
    p = TMP / name
    p.write_text(text)
    return p


def obj_file(name, answers):
    return write(name, json.dumps(answers))


# ---------------------------------------------------------------- [A] agreement
print("[A] agreement")
rc, out, err, base, files = grade_cli(obj_file("key.json", KEY))
check("A1 key answers -> rc 0", rc == 0, f"rc={rc} err={err!r}")
check("A2 summary line is train 8/8 · heldout 20/20", f"{TASK}: train 8/8 · heldout 20/20" in out.splitlines(), out[-200:])
check("A3 all 28 cases pass", base is not None and len(base) == 28 and all(p for p, _ in base.values()))
check("A4 result file is results/external/<task>__external__<stem>.json",
      [f.name for f in files] == [f"{TASK}__external__key.json"], str([f.name for f in files]))
# pick.py reads glob(results/<task>__*.json) at the TOP level as candidate model runs (scripts/pick.py, `paths =`);
# taxonomy.py globs results/*.json. A graded outside answer set must never land there (review finding, PR #176).
check("A6 nothing written at the top level of results/ (pick/taxonomy would adopt it as a model run)",
      not list(runner.RESULTS_DIR.glob("*.json")), str(list(runner.RESULTS_DIR.glob("*.json"))))


class _IndependentReplay:
    def __init__(self, m):
        self.m = m

    def generate(self, messages, model, temperature=0.0, max_tokens=512):
        u = [x for x in messages if x["role"] == "user"][0]["content"]
        t = self.m[u]
        return t, {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None,
                   "content_chars": len(t), "reasoning_chars": 0, "finish_reason": "stop"}


def direct_verdicts(answers):
    """run_exam driven by this file's own replay (not exam_grade's): the verdicts a grade must equal."""
    m = {c["input"]: answers[c["id"]] for c in CASES}
    runner.adapter_for = lambda *a, **k: _IndependentReplay(m)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            res = runner.run_exam(runner.load_agent(TASK), runner.load_exam(TASK), "external", "direct")
    finally:
        runner.adapter_for = ORIG_ADAPTER
    return {c["id"]: (c["passed"], json.dumps(c["got"], sort_keys=True)) for c in res["cases"]}


check("A5 per-case verdicts equal run_exam's on the same answers", direct_verdicts(KEY) == base)

# ---------------------------------------------------------------- [R] seen-red
print("[R] one change, one failure")
wrong = {**KEY, FLIP_ID: json.dumps({"label": "ignore"})}
rc, out, err, flipped, _ = grade_cli(obj_file("flip.json", wrong))
failing = sorted(i for i, (p, _) in flipped.items() if not p)
check("R1 exactly the changed case fails", rc == 0 and failing == [FLIP_ID], str(failing))
check("R2 every other verdict is unchanged", all(flipped[i] == base[i] for i in base if i != FLIP_ID))
check("R3 summary counts the failure", f"{TASK}: train 7/8 · heldout 20/20" in out.splitlines(), out[-200:])
check("R4 grader's verdicts equal run_exam's on the flipped answers", direct_verdicts(wrong) == flipped)
junk = {**KEY, FLIP_ID: "I think this is urgent."}
t0 = time.time()
rc, out, err, jv, _ = grade_cli(obj_file("junk.json", junk))
el = time.time() - t0
check("R5 an unparseable answer fails alone", rc == 0 and sorted(i for i, (p, _) in jv.items() if not p) == [FLIP_ID])
check("R6 the re-ask does not wait on retry backoff", el < 1.5, f"{el:.2f}s")

# ---------------------------------------------------------------- [O] order
print("[O] input, not order")
ids = list(wrong)
random.Random(7).shuffle(ids)
assert ids != list(wrong)
rc, out, err, shuf, _ = grade_cli(obj_file("shuffled.json", {i: wrong[i] for i in ids}))
check("O1 shuffled answers file -> identical verdicts", rc == 0 and shuf == flipped)

# ---------------------------------------------------------------- [F] formats
print("[F] formats")
rows = [{"case_id": i, "text": wrong[i]} for i in wrong]
as_object = {"_meta": {"note": "ignored"}, **{i: {"text": wrong[i]} for i in wrong}}
as_list = rows
items = [{"json": {"case_id": r["case_id"], "input_chars": 1, "input_head": "x", "text": r["text"]}} for r in rows]
execution = {"id": "1", "status": "success",
             "data": {"resultData": {"runData": {"Start": [{"data": {"main": [[{"json": {}}]]}}],
                                                 "Result": [{"data": {"main": [items]}}]}}}}
raw = ("Initializing n8n process\nn8n ready on 0.0.0.0, port 5678 {\"a\": 1}\nVersion: 2.46.4\n"
       + json.dumps(execution, indent=2))
buf = io.StringIO()
w = csv.writer(buf)
w.writerow(["case_id", "text"])
for r in rows:
    w.writerow([r["case_id"], r["text"]])
formats = {
    "object": json.dumps(as_object), "list": json.dumps(as_list), "n8n-raw": raw,
    "n8n-api": json.dumps(execution), "n8n-wrapped": json.dumps({"execution": execution}),
    "csv": buf.getvalue(),
}
for name, text in formats.items():
    rc, out, err, per, _ = grade_cli(write(f"fmt-{name}.txt", text))
    check(f"F-{name}: same verdicts as the object-format grade", rc == 0 and per == flipped, f"rc={rc} err={err!r}")
rc, out, err, per, _ = grade_cli(write("other-node.txt", json.dumps(
    {"data": {"resultData": {"runData": {"Mine": [{"data": {"main": [items]}}]}}}})), "--node", "Mine")
check("F-node: --node reads another node", rc == 0 and per == flipped, err)

# ---------------------------------------------------------------- [X] refusals
print("[X] refusals")


def refused(label, rc, err, files, must=()):
    lines = [l for l in err.splitlines() if l.strip()]
    check(f"X {label}: rc 2", rc == 2, f"rc={rc}")
    check(f"X {label}: one stderr line, no traceback", len(lines) == 1 and "Traceback" not in err, repr(err))
    check(f"X {label}: nothing written", not files and not list(runner.RESULTS_DIR.glob("*.json")))
    for m in must:
        check(f"X {label}: names {m!r}", m in err, repr(err))


rc, out, err, _, f = grade_cli(obj_file("unk.json", {**KEY, "no-such-case": "x", "other-ghost": "y"}))
refused("unknown case id", rc, err, f, ("no-such-case", "other-ghost"))
rc, out, err, _, f = grade_cli(obj_file("miss.json", {k: v for k, v in KEY.items() if k not in (FLIP_ID, "seo-cold-spam")}))
refused("missing case", rc, err, f, (FLIP_ID, "2 of 28"))
many = {k: v for i, (k, v) in enumerate(KEY.items()) if i >= 9}
rc, out, err, _, f = grade_cli(obj_file("miss9.json", many))
refused("9 missing cases", rc, err, f, ("9 of 28", "..."))
rc, out, err, _, f = grade_cli(write("what.txt", "hello, this is not answers\n"))
refused("unrecognised format", rc, err, f, ("unrecognised",))
rc, out, err, _, f = grade_cli(write("broken.json", "{not json"))
refused("broken JSON", rc, err, f)
rc, out, err, _, f = grade_cli(write("badval.json", json.dumps({"a": 3})))
refused("object with a non-text value", rc, err, f)
rc, out, err, _, f = grade_cli(write("dup.json", json.dumps(rows + rows[:1])))
refused("duplicate case id", rc, err, f, (rows[0]["case_id"],))
rc, out, err, _, f = grade_cli(write("nonode.txt", json.dumps(execution)), "--node", "Nope")
refused("absent n8n node", rc, err, f, ("Nope", "Result", "Start"))
rc, out, err, _, f = grade_cli(obj_file("opt.json", KEY), "--bogus")
refused("bad option", rc, err, f)
rc, out, err, _, f = grade_cli(TMP / "does-not-exist.json")
refused("file not found", rc, err, f)

rc, out, err, _, f = grade_cli(write("empty.json", "   \n"))
refused("empty file", rc, err, f, ("empty",))
dup = "{" + ", ".join(f'"{k}": {json.dumps(v)}' for k, v in KEY.items()) + f', "{FLIP_ID}": {json.dumps(json.dumps({"label": "ignore"}))}' + "}"
rc, out, err, _, f = grade_cli(write("dup.json", dup))
refused("duplicate key in a JSON object", rc, err, f, (FLIP_ID, "twice"))
rc, out, err, _, f = grade_cli(obj_file("crm.json", {"a": "b"}), task="crm-followup")
refused("trajectory exam", rc, err, f, ("crm-followup",))
rc, out, err, _, f = grade_cli(obj_file("t.json", {"a": "b"}), task="no-such-task")
refused("unknown task", rc, err, f, ("no-such-task",))

# judge-graded exam: a synthetic single-turn tree whose exam folder holds a rubric.md
spec = importlib.util.spec_from_file_location("exam_grade_under_test", ROOT / "scripts" / "exam_grade.py")
eg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eg)
fake = TMP / "fakeroot"
(fake / "evals" / "judged").mkdir(parents=True)
(fake / "agents" / "judged").mkdir(parents=True)
(fake / "evals" / "judged" / "cases.json").write_text(json.dumps({"cases": [{"id": "a", "input": "x"}]}))
(fake / "agents" / "judged" / "agent.yaml").write_text("name: judged\n")
real_root = eg.ROOT
eg.ROOT = fake
(fake / "evals" / "judged" / "rubric.md").write_text("rubric")
try:
    eg.check_exam("judged")
    judged_refused = False
except eg.Refuse as exc:
    judged_refused = "judge" in str(exc)
check("X judge-graded exam: rubric.md -> Refuse naming the judge", judged_refused)
(fake / "evals" / "judged" / "rubric.md").unlink()
# the judge loader keys on agent.yaml's name, not the folder: a rubric under evals/<name>/ must also refuse
(fake / "evals" / "jname").mkdir(parents=True)
(fake / "agents" / "jfolder").mkdir(parents=True)
(fake / "evals" / "jfolder").mkdir(parents=True)
(fake / "evals" / "jfolder" / "cases.json").write_text(json.dumps({"cases": [{"id": "a", "input": "x"}]}))
(fake / "agents" / "jfolder" / "agent.yaml").write_text("name: jname\n")
(fake / "evals" / "jname" / "rubric.md").write_text("rubric")
try:
    eg.check_exam("jfolder"); why = ""
except eg.Refuse as exc:
    why = str(exc)
check("X judge rubric found by agent name (folder != name) -> Refuse", "judge" in why, why)
(fake / "evals" / "sampled").mkdir(parents=True)
(fake / "agents" / "sampled").mkdir(parents=True)
(fake / "evals" / "sampled" / "cases.json").write_text(json.dumps({"samples": 3, "cases": [{"id": "a", "input": "x"}]}))
(fake / "agents" / "sampled" / "agent.yaml").write_text("name: sampled\n")
try:
    eg.check_exam("sampled"); why = ""
except eg.Refuse as exc:
    why = str(exc)
check("X pass@k exam (samples 3) -> Refuse", "samples" in why, why)
for nm, exam_doc in (("traj", {"mode": "trajectory", "cases": [{"id": "a", "input": "x"}]}),
                     ("turned", {"cases": [{"id": "a", "turns": [{"input": "x"}]}]}),
                     ("tooled", {"cases": [{"id": "a", "input": "x", "tools": ["t"]}]})):
    (fake / "evals" / nm).mkdir(parents=True)
    (fake / "agents" / nm).mkdir(parents=True)
    (fake / "evals" / nm / "cases.json").write_text(json.dumps(exam_doc))
    (fake / "agents" / nm / "agent.yaml").write_text(f"name: {nm}\n")
    try:
        eg.check_exam(nm)
        why = ""
    except eg.Refuse as exc:
        why = str(exc)
    check(f"X exam shape {nm!r} (no rubric) is refused as not single-turn", "single-turn" in why, why)
eg.ROOT = real_root

# ---------------------------------------------------------------- [S] restored
print("[S] state restored")
check("S1 adapter_for is the original after every call so far", runner.adapter_for is ORIG_ADAPTER)
check("S2 retry backoff sleep is the original after every call so far",
      retry.call_with_retry.__kwdefaults__["sleep"] is ORIG_SLEEP)
saved_run_exam = runner.run_exam


def boom(*a, **k):
    raise RuntimeError("boom")


runner.run_exam = boom
try:
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            wilco_cli.main(["grade", TASK, str(obj_file("key2.json", KEY))])
        raised = False
    except RuntimeError:
        raised = True
finally:
    runner.run_exam = saved_run_exam
check("S3 an exception inside run_exam propagates", raised)
check("S4 adapter_for restored after the exception", runner.adapter_for is ORIG_ADAPTER)
check("S5 retry sleep restored after the exception", retry.call_with_retry.__kwdefaults__["sleep"] is ORIG_SLEEP)

# a replay miss (an input the grader asks for that has no answer) aborts, writes nothing, and still restores
real_gen = eg.Replay.generate


def drop_inputs(self, messages, model, temperature=0.0, max_tokens=512):
    self.by_input.pop([m for m in messages if m["role"] == "user"][0]["content"], None)
    return real_gen(self, messages, model, temperature, max_tokens)


eg.Replay.generate = drop_inputs
try:
    shutil.rmtree(runner.RESULTS_DIR, ignore_errors=True)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as _e:
        try:
            eg.grade(TASK, KEY, "x")
            miss_refused = False
        except eg.Refuse:
            miss_refused = True
        except Exception:
            miss_refused = False
finally:
    eg.Replay.generate = real_gen
check("S6 a replay miss is a refusal, not a silent case failure", miss_refused)
check("S7 adapter_for restored after a replay miss", runner.adapter_for is ORIG_ADAPTER)

# ---------------------------------------------------------------- [Z] network
print("[Z] zero network")
check("Z1 no urlopen / requests call was reached by any grade in this file", NET_CALLS == [], str(NET_CALLS))

# ---------------------------------------------------------------- [I] integration
print("[I] integrations/n8n")
wf_path = ROOT / "integrations" / "n8n" / "wilco-exam-ollama.json"
readme = (ROOT / "integrations" / "n8n" / "README.md").read_text()
try:
    wf = json.loads(wf_path.read_text())
    valid = True
except ValueError:
    wf, valid = {}, False
check("I1 workflow is valid JSON", valid)
names = {n["name"] for n in wf.get("nodes", [])}
bad_edges = []
for src, kinds in wf.get("connections", {}).items():
    if src not in names:
        bad_edges.append(src)
    for outs in kinds.values():
        for group in outs:
            for edge in group:
                if edge["node"] not in names:
                    bad_edges.append(edge["node"])
check("I2 every connection names existing nodes", valid and not bad_edges and len(wf["connections"]) >= 5, str(bad_edges))
check("I3 node names are unique", valid and len(names) == len(wf["nodes"]))
blob = wf_path.read_text()
secret = re.compile(r"(?i)instanceid|api[_-]?key|\"token\"|password|secret|bearer |sk-[a-z0-9]|eyJ[a-zA-Z0-9]{10}|https?://[^\"]*(localhost|127\.0\.0\.1|n8n\.cloud)")
check("I4 no secret, instance id or token", not secret.search(blob), str(secret.search(blob)))
creds = [n.get("credentials", {}) for n in wf.get("nodes", []) if n.get("credentials")]
check("I5 credentials are named, never identified", creds and all("id" not in c for cs in creds for c in cs.values()), str(creds))
check("I6 the Ollama node is left at defaults", any(n["type"].endswith("lmChatOllama") and n["parameters"].get("options") == {}
                                                   for n in wf.get("nodes", [])))
check("I7 the first Set node carries exam, wilco_commit, model",
      any(n["name"] == "Exam" and {a["name"] for a in n["parameters"]["assignments"]["assignments"]} == {"exam", "wilco_commit", "model"}
          for n in wf.get("nodes", [])))
check("I8 Result node carries case_id, input_chars, input_head, text",
      any(n["name"] == "Result" and {a["name"] for a in n["parameters"]["assignments"]["assignments"]}
          == {"case_id", "input_chars", "input_head", "text"} for n in wf.get("nodes", [])))
check("I9 README states defaults reproduced 28 of 28, with its source",
      "28 of 28" in readme and "n8n-two-exams-2026-11-03/step2/RESULTS.md" in readme and "0.40.14" in readme)
check("I10 README states numCtx 4096 moved 5 of 28", "numCtx" in readme and "5 of 28" in readme)
check("I11 README names the grade command and the n8n export", "wilco grade" in readme and "n8n execute" in readme)
check("I13 README names the results/external/ location (not the top level)", "results/external/<task>__external__" in readme and "`results/<task>__external__" not in readme)
check("I12 wilco_cli lists grade in COMMANDS, SCRIPTS and USAGE",
      "grade" in wilco_cli.COMMANDS and wilco_cli.SCRIPTS.get("grade") == "scripts/exam_grade.py"
      and "grade <task> <file>" in wilco_cli.USAGE)

shutil.rmtree(TMP, ignore_errors=True)


def main():
    print(f"\n{len(FAILED)} failed" if FAILED else "\nall passed")
    for f in FAILED:
        print("  FAILED:", f)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
