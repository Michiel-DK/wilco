"""W3 — `scripts/exam_new.py` + `scripts/exam_validate.py`, the authoring pair.

Everything is written under a temp root (`--root`, and `runner.ROOT` for the in-process parts), so no file
appears under evals/ or agents/. The scripts are driven as subprocesses (exit codes are the contract);
loading goes through runner.load_exam / load_agent / load_properties / load_tools / run_properties /
run_exam / score_case, the real entry points (gotcha 5). No model, no network: the only adapters are the
runner's stub and a scripted one below.

  [A] new: each mode's output loads, validates clean (0 errors, 0 warnings), and runs through run_exam
  [B] new refuses to overwrite and refuses a bad name
  [C] the properties template's check through run_properties: honest passes, wrong output fails exactly
      that one check, an uncommitted input and a missing key both fail loud
  [D] the trajectory template through score_case: an honest scripted run passes both cases
  [E] validate exits 1 on each error class, one defect per fixture, and names only that class
  [F] validate warnings exit 0: unread key, heldout share, window, undeclared label list
  [G] the census regex is the same pattern as sandbox/test_key_audit.py `_KEY_READ`
  [H] every committed exam validates with exit 0

Seen RED (recorded in the PR body): each detector in exam_validate.py disabled one at a time.
"""
import contextlib
import io
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
sys.path.insert(0, str(ROOT / "scripts"))
import runner  # noqa: E402
import exam_validate  # noqa: E402
from router import _empty_usage  # noqa: E402

FAILED = []
NEW = str(ROOT / "scripts" / "exam_new.py")
VAL = str(ROOT / "scripts" / "exam_validate.py")
TMP = pathlib.Path(tempfile.mkdtemp(prefix="test_exam_tools_"))


def check(label, ok, extra=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {extra}" if not ok and extra else ""))
    if not ok:
        FAILED.append(label)


def sh(*args):
    p = subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=ROOT)
    return p.returncode, p.stdout, p.stderr


@contextlib.contextmanager
def at_root(root):
    old = runner.ROOT
    runner.ROOT = pathlib.Path(root)
    try:
        yield
    finally:
        runner.ROOT = old


def new(root, task, mode):
    return sh(NEW, task, "--mode", mode, "--root", str(root))


def validate(root, task):
    return sh(VAL, task, "--root", str(root))


def error_classes(out):
    return sorted({m.split(":")[0] for m in re.findall(r"^ERROR (\S+:)", out, re.M)})


# ---------------------------------------------------------------- [A] [B]

def test_A_new_output_loads_validates_and_runs():
    root = TMP / "a"
    for mode in ("labels", "fields", "properties", "trajectory"):
        task = f"ex-{mode}"
        rc, out, err = new(root, task, mode)
        check(f"[A] new --mode {mode} -> exit 0", rc == 0, err)
        with at_root(root):
            exam = runner.load_exam(task)
            agent = runner.load_agent(task)
            props = runner.load_properties(task)
            with contextlib.redirect_stdout(io.StringIO()):
                res = runner.run_exam(agent, exam, "stub", "stub")
        check(f"[A] {mode}: load_exam mode == {mode}", exam.get("mode", "labels") == mode, f"{exam.get('mode')}")
        check(f"[A] {mode}: one train + one heldout case, each with a case-level _comment",
              sorted(c["split"] for c in exam["cases"]) == ["heldout", "train"]
              and all("_comment" in c and "_comment" not in c["expected"] for c in exam["cases"]))
        check(f"[A] {mode}: agent.yaml loads, model is the quoted placeholder, provider ollama, tier local",
              agent["model"] == "<pick one with: wilco diff>" and agent["provider"] == "ollama"
              and agent["tier"] == "local", f"{agent}")
        check(f"[A] {mode}: properties.py only in properties mode, and it loads one bucketed check",
              (len(props) == 1) == (mode == "properties"), f"{props}")
        check(f"[A] {mode}: run_exam (stub) scores both cases and records why they failed",
              len(res["cases"]) == 2 and all(c.get("failed_checks") for c in res["cases"]), f"{res['cases']}")
        rc, out, err = validate(root, task)
        check(f"[A] {mode}: validate -> exit 0, 0 errors, 0 warnings",
              rc == 0 and f"{task}: 0 error(s), 0 warning(s)" in out, out + err)
    with at_root(root):
        tools = runner.load_tools("ex-trajectory")
    check("[A] trajectory: tools_mock loads through load_tools; lookup answers acme",
          tools.lookup(key="Acme") == {"status": "active", "owner": "Ann Peeters"})
    try:
        tools.lookup(key="Globex")
        check("[A] trajectory: _BACKEND_DOWN key raises", False, "no raise")
    except RuntimeError:
        check("[A] trajectory: _BACKEND_DOWN key raises", True)


def test_B_new_refuses_overwrite_and_bad_names():
    root = TMP / "b"
    rc, _, _ = new(root, "taken", "labels")
    before = (root / "evals" / "taken" / "cases.json").read_text()
    (root / "evals" / "taken" / "cases.json").write_text(before.replace("label_a", "edited"))
    rc, _, err = new(root, "taken", "properties")
    check("[B] new on an existing exam -> exit 2, says refusing", rc == 2 and "refusing to overwrite" in err, err)
    check("[B] ... and the existing cases.json is untouched",
          "edited" in (root / "evals" / "taken" / "cases.json").read_text()
          and not (root / "evals" / "taken" / "properties.py").exists())
    shutil.rmtree(root / "evals" / "taken")
    rc, _, err = new(root, "taken", "labels")
    check("[B] an agents/<task> dir alone also refuses", rc == 2 and "agents/taken" in err, err)
    shutil.rmtree(root / "agents" / "taken")
    new(root, "taken", "labels")
    shutil.rmtree(root / "agents" / "taken")
    (root / "evals" / "taken" / "cases.json").write_text("keep")
    rc, _, err = new(root, "taken", "labels")
    check("[B] an evals/<task> dir alone also refuses, and its cases.json is untouched",
          rc == 2 and "evals/taken" in err and (root / "evals" / "taken" / "cases.json").read_text() == "keep"
          and not (root / "agents" / "taken").exists(), err)
    (root / "only-props" / "evals" / "x").mkdir(parents=True)
    (root / "only-props" / "evals" / "x" / "properties.py").write_text("keep")
    rc, _, err = new(root / "only-props", "x", "properties")
    check("[B] an evals/<task> dir with no cases.json (only properties.py) still refuses; the file is untouched",
          rc == 2 and (root / "only-props" / "evals" / "x" / "properties.py").read_text() == "keep"
          and not (root / "only-props" / "evals" / "x" / "cases.json").exists(), err)
    for bad in ("Bad Name", "bad name", "Abc", "1abc", "x_y", "a.b", "a/../../esc", "esc\n"):
        rc, _, err = new(root / "deep", bad, "labels")
        check(f"[B] bad task name {bad!r} -> exit 2, nothing written", rc == 2 and "must match" in err
              and not (root / "deep").exists() and not (root / "esc").exists(), err)


# ---------------------------------------------------------------- [C] [D]

def test_C_properties_template_through_run_properties():
    root = TMP / "c"
    new(root, "props", "properties")
    with at_root(root):
        props = runner.load_properties("props")
        cases = runner.load_exam("props")["cases"]
    one = [{"bucket": "quality", "check": "check_mentions_required"}]
    train = next(c for c in cases if c["split"] == "train")
    ok, fails, failed = runner.run_properties(props, train["input"], {"answer": "Acme moves delivery to Friday."})
    check("[C] honest answer passes", ok and failed == [], f"{fails}")
    ok, fails, failed = runner.run_properties(props, train["input"], {"answer": "acme moves delivery to friday."})
    check("[C] the match is case-insensitive, as the template's docstring says", ok, f"{fails}")
    ok, fails, failed = runner.run_properties(props, train["input"], {"answer": "Acme called."})
    check("[C] answer missing 'Friday' fails exactly check_mentions_required",
          not ok and failed == one and "Friday" in fails[0], f"{failed} {fails}")
    ok, fails, failed = runner.run_properties(props, "an input no case has", {"answer": "Acme Friday"})
    check("[C] an uncommitted input fails loud (check raised, KeyError), never passes vacuously",
          not ok and failed == one and "check raised" in fails[0] and "not a committed case" in fails[0], f"{fails}")
    path = root / "evals" / "props" / "cases.json"
    data = json.loads(path.read_text())
    data["cases"][0]["expected"] = {}
    path.write_text(json.dumps(data))
    with at_root(root):
        props = runner.load_properties("props")   # fresh module: the lru_cache is per module load
    ok, fails, failed = runner.run_properties(props, train["input"], {"answer": "Acme Friday"})
    check("[C] a case whose expected lacks must_mention fails loud (KeyError), never passes",
          not ok and "check raised" in fails[0] and "must_mention" in fails[0], f"{fails}")


class Scripted:
    """A fixed sequence of raw replies, one per generate() call."""

    def __init__(self, replies):
        self.replies = list(replies)

    def generate(self, messages, model, temperature=0.0, max_tokens=512):
        return self.replies.pop(0), {**_empty_usage(), "finish_reason": "stop"}


def test_D_trajectory_template_honest_run_passes():
    root = TMP / "d"
    new(root, "traj", "trajectory")
    with at_root(root):
        agent = runner.load_agent("traj")
        cases = {c["split"]: c for c in runner.load_exam("traj")["cases"]}
        tools = runner.load_tools("traj")
    scripts = {
        "train": ['{"tool": "lookup", "args": {"key": "Acme"}}', '{"answer": "Acme is active."}'],
        "heldout": ['{"tool": "lookup", "args": {"key": "Globex"}}',
                    '{"answer": "The lookup failed, so I could not retrieve the status for Globex."}'],
    }
    for split, replies in scripts.items():
        _, trace, passed, fails, failed = runner.score_case(agent, cases[split], Scripted(replies), "scripted", tools)
        check(f"[D] trajectory {split}: honest scripted run passes", passed and failed == [], f"{fails} {failed}")
    two = {"id": "two-accounts", "split": "train", "input": "What is the status of Acme and of Globex?",
           "expected": {"tools_called": ["lookup"], "max_steps": 4}}
    ad = Scripted(['{"tool": "lookup", "args": {"key": "Acme"}}', '{"answer": "Acme is active."}'])
    _, _, passed, fails, failed = runner.score_case(agent, two, ad, "scripted", tools)
    check("[D] trajectory: the template's known_entities arms scope_coverage (an answer dropping Globex "
          "fails scope_coverage and nothing else)",
          not passed and [x["check"] for x in failed] == ["scope_coverage"], f"{failed} {fails}")
    ad = Scripted(['{"tool": "lookup", "args": {"key": "Globex"}}', '{"answer": "Globex is churned, owner Bob Smit."}'])
    _, _, passed, fails, failed = runner.score_case(agent, cases["heldout"], ad, "scripted", tools)
    check("[D] trajectory heldout: an answer that invents the status after the outage fails error_recovery and nothing else",
          not passed and {x["check"] for x in failed} == {"error_recovery"}, f"{failed}")


# ---------------------------------------------------------------- [E] [F]

def _labels_fixture(name, mutate=None, prompt=None):
    root = TMP / "e" / name
    new(root, "lab", "labels")
    path = root / "evals" / "lab" / "cases.json"
    data = json.loads(path.read_text())
    data["cases"].append({"id": "extra-train", "split": "train", "input": "Third input.", "expected": {"label": "label_a"}})
    if mutate:
        mutate(data["cases"])
    path.write_text(json.dumps(data))
    if prompt is not None:
        (root / "agents" / "lab" / "prompt.md").write_text(prompt)
    return root


def test_E_validate_exits_1_on_each_error_class():
    clean = _labels_fixture("clean")
    rc, out, _ = validate(clean, "lab")
    check("[E] the clean 3-case fixture -> exit 0, 0 errors, 0 warnings (an always-1 validate fails here; "
          "heldout 1/3 is not under 1/3)", rc == 0 and "lab: 0 error(s), 0 warning(s)" in out, out)

    def dup_input(cs):
        cs[2]["input"] = cs[0]["input"]

    def dup_id(cs):
        cs[2]["id"] = cs[0]["id"]

    def unknown_label(cs):
        cs[2]["expected"]["label"] = "label_z"

    def bad_split(cs):
        cs[2]["split"] = "test"

    def no_input(cs):
        del cs[2]["input"]

    def no_heldout(cs):
        cs[1]["split"] = "train"

    def no_id(cs):
        del cs[2]["id"]

    def str_expected(cs):
        cs[2]["expected"] = "label_a"

    def no_train(cs):
        for c in cs:
            c["split"] = "heldout"

    for name, fn, cls in (("dup-input", dup_input, "duplicate-input"), ("dup-id", dup_id, "duplicate-id"),
                          ("unknown-label", unknown_label, "unknown-label"), ("bad-split", bad_split, "structure"),
                          ("no-input", no_input, "structure"), ("no-id", no_id, "structure"),
                          ("str-expected", str_expected, "structure"), ("no-heldout", no_heldout, "no-split"),
                          ("no-train", no_train, "no-split"), ("no-split-key", lambda cs: cs[2].pop("split"), "structure"),
                          ("mode-typo", lambda cs: None, None)):
        if cls is None:
            continue
        rc, out, err = validate(_labels_fixture(name, fn), "lab")
        check(f"[E] {name} -> exit 1, ERROR classes == [{cls}]", rc == 1 and error_classes(out) == [cls],
              f"rc={rc} classes={error_classes(out)} {out}{err}")
    def upper(cs):
        for c in cs:
            if c["expected"]["label"] == "label_a":
                c["expected"]["label"] = "LABEL_A"
    rc, out, _ = validate(_labels_fixture("upper", upper), "lab")
    check("[E] labels compare case-insensitively, like score_labels: LABEL_A is a known label, and label_a "
          "is not reported unused", rc == 0 and error_classes(out) == [] and "but no case expects" not in out, out)
    rc, out, _ = validate(_labels_fixture("padded", lambda cs: cs[2]["expected"].update(label=" label_a ")), "lab")
    check("[E] labels compare stripped, like score_labels: ' label_a ' is a known label",
          rc == 0 and error_classes(out) == [], out)
    def bad_split_and_label(cs):
        cs[2]["split"] = "test"
        cs[2]["expected"]["label"] = "label_z"
    rc, out, _ = validate(_labels_fixture("bad-split-excluded", bad_split_and_label), "lab")
    check("[E] a bad-split case is excluded from every later check (its unknown label is not ALSO reported)",
          error_classes(out) == ["structure"] and "per split: train 1 · heldout 1" in out, out)
    root = _labels_fixture("bad-json")
    (root / "evals" / "lab" / "cases.json").write_text('{"cases": [')
    rc, out, err = validate(root, "lab")
    check("[E] cases.json that is not JSON -> exit 1 structure, not a traceback",
          rc == 1 and error_classes(out) == ["structure"] and "Traceback" not in err, out + err)
    root = _labels_fixture("bad-yaml")
    (root / "agents" / "lab" / "agent.yaml").write_text("name: lab\ndescription: a: b\n")
    rc, out, err = validate(root, "lab")
    check("[E] a malformed agent.yaml -> exit 1 structure, not a traceback",
          rc == 1 and error_classes(out) == ["structure"] and "Traceback" not in err, out + err)
    root = TMP / "e" / "nobucket"
    new(root, "props", "properties")
    p = root / "evals" / "props" / "properties.py"
    p.write_text(p.read_text().replace('check_mentions_required.bucket = "quality"', ""))
    rc, out, err = validate(root, "props")
    check("[E] a check without a bucket -> exit 1 properties (load_checks' refusal, surfaced)",
          rc == 1 and error_classes(out) == ["properties"], out + err)
    root = _labels_fixture("mode-typo")
    path = root / "evals" / "lab" / "cases.json"
    data = json.loads(path.read_text()); data["mode"] = "trajectroy"; path.write_text(json.dumps(data))
    rc, out, err = validate(root, "lab")
    check("[E] a mode typo -> exit 1 structure (the runner would score it as labels)",
          rc == 1 and error_classes(out) == ["structure"] and "trajectroy" in out, out + err)
    root = TMP / "e" / "zero-checks"
    new(root, "props", "properties")
    p = root / "evals" / "props" / "properties.py"
    p.write_text(p.read_text().replace("def check_mentions_required", "def chk_mentions_required")
                 .replace("check_mentions_required.bucket", "chk_mentions_required.bucket"))
    rc, out, err = validate(root, "props")
    check("[E] properties mode with 0 loaded checks -> exit 1 properties (every case would pass)",
          rc == 1 and error_classes(out) == ["properties"] and "0 check_* functions" in out, out + err)
    p.unlink()
    rc, out, err = validate(root, "props")
    check("[E] properties mode with no properties.py -> exit 1 properties", rc == 1 and "properties" in error_classes(out),
          out + err)
    root = TMP / "e" / "syntax"
    new(root, "props", "properties")
    (root / "evals" / "props" / "properties.py").write_text("def check_x(:\n")
    rc, out, err = validate(root, "props")
    check("[E] a properties.py that does not import -> exit 1 properties, not a traceback",
          rc == 1 and error_classes(out) == ["properties"] and "Traceback" not in err, out + err)
    root = TMP / "e" / "props-turns"
    new(root, "props", "properties")
    path = root / "evals" / "props" / "cases.json"
    data = json.loads(path.read_text())
    data["cases"].append({"id": "tn", "split": "train", "turns": ["a", "b"],
                          "turns_expected": [{"turn": "a", "expected": {}}, {"turn": "b", "expected": {}}],
                          "expected": {"must_mention": ["x"]}})
    path.write_text(json.dumps(data))
    rc, out, err = validate(root, "props")
    check("[E] a turns case without input in an exam WITH a properties.py -> exit 1 structure needs input "
          "(run_exam hands case['input'] to run_properties)",
          rc == 1 and error_classes(out) == ["structure"] and "'tn' needs input" in out, out + err)
    for name, mut in (("turns-str", lambda c: c.update(turns="Status of Acme?")),
                      ("turns-int", lambda c: c.update(turns=["Status of Acme?", 3])),
                      ("turns-drift", lambda c: c["turns_expected"][1].update(turn="something else")),
                      ("turns-short", lambda c: c["turns_expected"].pop())):
        root = TMP / "e" / name
        new(root, "tr", "trajectory")
        path = root / "evals" / "tr" / "cases.json"
        data = json.loads(path.read_text())
        case = {"id": "mt", "split": "train", "input": "Status of Acme? | And Globex?",
                "turns": ["Status of Acme?", "And Globex?"],
                "turns_expected": [{"turn": "Status of Acme?", "expected": {"max_steps": 2}},
                                   {"turn": "And Globex?", "expected": {"max_steps": 2}}], "expected": {}}
        mut(case)
        data["cases"].append(case)
        path.write_text(json.dumps(data))
        rc, out, err = validate(root, "tr")
        check(f"[E] {name} -> exit 1 structure, not a traceback",
              rc == 1 and error_classes(out) == ["structure"] and "'mt'" in out and "Traceback" not in err
              and (name not in ("turns-str", "turns-int") or "turns as a non-empty list of strings" in out), out + err)
    rc, _, err = validate(TMP / "e" / "clean", "no-such-task")
    check("[E] an unknown task -> exit 2", rc == 2 and "no agents/no-such-task" in err, err)


def test_F_validate_warnings_exit_0():
    root = TMP / "f"
    new(root, "props", "properties")
    path = root / "evals" / "props" / "cases.json"
    data = json.loads(path.read_text())
    data["cases"][0]["expected"]["must_mentoin"] = ["typo"]
    data["cases"][1]["expected"]["max_steps"] = 3
    data["cases"] += [{"id": f"t{i}", "split": "train", "input": f"Train input {i} " + "x" * 20000,
                       "expected": {"must_mention": ["x"]}} for i in range(3)]
    path.write_text(json.dumps(data))
    rc, out, _ = validate(root, "props")
    check("[F] warnings only -> exit 0", rc == 0 and error_classes(out) == [], out)
    check("[F] unread key: expected.must_mentoin is read by no scorer", "unread-key: expected.must_mentoin" in out, out)
    check("[F] the key properties.py does read is not flagged", "expected.must_mention " not in out, out)
    check("[F] a trajectory key (max_steps) on a properties exam is unread: runner keys count only in trajectory mode",
          "unread-key: expected.max_steps" in out, out)
    check("[F] heldout share 1/5 under 1/3", "heldout share 1/5" in out, out)
    check("[F] window: ~5k-token inputs OVER the 4,096 default", "estimated OVER 4096" in out, out)
    (root / "agents" / "props" / "Modelfile").write_text("FROM some:model\nPARAMETER num_ctx 16384\n")
    rc, out, _ = validate(root, "props")
    check("[F] a Modelfile num_ctx is NOT credited when nothing says the agent's model was built from it: "
          "4,096 kept, OVER stays, mismatch warned, exit 0",
          rc == 0 and "estimated OVER 4096" in out and "is not shown to run at it" in out, out)
    rc, out, _ = validate(root, "props")
    (root / "agents" / "props" / "Modelfile").write_text(
        "# ollama create my-model-ctx16k -f agents/props/Modelfile\nFROM some:model\nparameter num_ctx 16384\n")
    ay = root / "agents" / "props" / "agent.yaml"
    ay.write_text(ay.read_text().replace('model: "<pick one with: wilco diff>"', "model: my-model-ctx16k"))
    rc, out, _ = validate(root, "props")
    check("[F] a Modelfile that says `ollama create <the agent's model>` is credited (keyword case-insensitive): "
          "16384 read, OVER gone, no mismatch warning",
          "num_ctx 16384 from agents/props/Modelfile" in out and "OVER" not in out and "not shown" not in out, out)
    ay.write_text(ay.read_text().replace("provider: ollama", "provider: openrouter"))
    rc, out, _ = validate(root, "props")
    check("[F] a non-ollama provider: window not read, no window warning",
          rc == 0 and "window not read here" in out and "WARN  window" not in out, out)
    root = _labels_fixture("nodecl", prompt="Classify.\nRespond with {\"label\": \"<the label>\"}\n")
    rc, out, _ = validate(root, "lab")
    check("[F] labels prompt without a declared list -> exit 0 + warning that unknown-label cannot fire",
          rc == 0 and "unknown-label cannot fire" in out, out)
    rc, out, _ = validate(_labels_fixture("unused", prompt='Respond with {"label": "<label_a|label_b|label_c>"}\n'), "lab")
    check("[F] a declared label no case expects warns", rc == 0 and "declares ['label_c'] but no case expects it" in out, out)
    rc, out, _ = validate(_labels_fixture("quarter", lambda cs: cs.append(
        {"id": "t4", "split": "train", "input": "Fourth.", "expected": {"label": "label_b"}})), "lab")
    check("[F] heldout 1/4 warns", rc == 0 and "heldout share 1/4 is under 1/3" in out, out)
    _window_boundaries()
    _trajectory_census_and_turns()


def _props_with_input(name, input_text):
    """A properties exam whose train case input is `input_text`; returns (root, chars of prompt.md)."""
    root = TMP / "w" / name
    new(root, "w", "properties")
    path = root / "evals" / "w" / "cases.json"
    data = json.loads(path.read_text())
    data["cases"][0]["input"] = input_text
    path.write_text(json.dumps(data))
    return root, len((root / "agents" / "w" / "prompt.md").read_text())


def _credit_rule():
    big = "x" * 20000
    def setup(name, modelfile, model, yaml_extra=""):
        root, _ = _props_with_input(name, big)
        (root / "agents" / "w" / "Modelfile").write_text(modelfile)
        ay = root / "agents" / "w" / "agent.yaml"
        ay.write_text(ay.read_text().replace('model: "<pick one with: wilco diff>"', f"model: {model}") + yaml_extra)
        rc, out, _ = validate(root, "w")
        return out if rc == 0 else f"rc={rc} (a warning-only fixture must exit 0)\n" + out
    credited = lambda out: "num_ctx 16384 from agents/w/Modelfile" in out and "OVER" not in out and "not shown" not in out
    refused = lambda out: "estimated OVER 4096" in out and "is not shown to run at it" in out
    out = setup("cr-other", "# ollama create other-model -f agents/w/Modelfile\nFROM x\nPARAMETER num_ctx 16384\n", "my-model")
    check("[F] credit: a Modelfile that builds ANOTHER model is not credited", refused(out), out)
    out = setup("cr-prefix", "# ollama create my-model-ctx16k -f agents/w/Modelfile\nFROM x\nPARAMETER num_ctx 16384\n", "my-model")
    check("[F] credit: a tag that only starts with the agent's model is not credited", refused(out), out)
    out = setup("cr-yaml", "FROM x\nPARAMETER num_ctx 16384\n", "my-model",
                "# ollama create my-model -f agents/w/Modelfile\n")
    check("[F] credit: the `ollama create <model>` line in agent.yaml alone is credited", credited(out), out)
    out = setup("cr-commented", "# ollama create my-model -f agents/w/Modelfile\nFROM x\n# PARAMETER num_ctx 16384\n", "my-model")
    check("[F] credit: a commented-out PARAMETER num_ctx is not a window", "estimated OVER 4096" in out
          and "num_ctx 16384" not in out and out.startswith("  mode"), out)
    out = setup("cr-dotted", "# ollama create my-model.v2 -f agents/w/Modelfile\nFROM x\nPARAMETER num_ctx 16384\n", "my-model")
    check("[F] credit: my-model.v2 is not my-model", refused(out), out)
    out = setup("cr-case", "# Ollama Create my-model -f agents/w/Modelfile\nFROM x\nPARAMETER num_ctx 16384\n", "my-model")
    check("[F] credit: `Ollama Create` (any case) is credited", credited(out), out)


def _window_boundaries():
    _credit_rule()
    _, sys_chars = _props_with_input("probe", "x")
    root, _ = _props_with_input("over-by-prompt", "x" * (4 * 4096 + 4 - sys_chars))
    rc, out, _ = validate(root, "w")
    check("[F] window: prompt.md + input = 4097 estimated tokens -> OVER (the system prompt is counted; "
          "the input alone is under 4096), a warning: exit 0", rc == 0 and "estimated OVER 4096" in out, out)
    rc, out, _ = sh(VAL, "w", "--root", str(root), "--per-case")
    check("[F] --per-case prints every case's estimate", rc == 0 and "estimate example-train-1: ~4097 / 4096" in out
          and "estimate example-heldout-1: ~" in out, out)
    root, _ = _props_with_input("exactly", "x" * (4 * 4096 - sys_chars))
    rc, out, _ = validate(root, "w")
    check("[F] window: exactly 4096 estimated tokens is not OVER, but is near (a warning: exit 0)",
          rc == 0 and "OVER" not in out and "within 1/4 of 4096" in out, out)
    root, _ = _props_with_input("near", "x" * (4 * 3073 - sys_chars))
    rc, out, _ = validate(root, "w")
    check("[F] window: 3073 estimated tokens warns near, not OVER, exit 0",
          rc == 0 and "within 1/4 of 4096" in out and "OVER" not in out, out)
    for est in (3072, 3000):
        root, _ = _props_with_input(f"far-{est}", "x" * (4 * est - sys_chars))
        rc, out, _ = validate(root, "w")
        check(f"[F] window: {est} estimated tokens is neither near nor OVER", "WARN  window" not in out, out)


def _trajectory_census_and_turns():
    root = TMP / "t"
    new(root, "tr", "trajectory")
    path = root / "evals" / "tr" / "cases.json"
    data = json.loads(path.read_text())
    data["cases"][0]["expected"]["tools_caled"] = ["lookup"]
    data["cases"].append({"id": "multi", "split": "train", "input": "Status of Acme?",
                          "turns": ["Status of Acme?", "y" * (4 * 4096)],
                          "turns_expected": [{"turn": "Status of Acme?", "expected": {"max_stepz": 2}},
                                             {"turn": "y" * (4 * 4096), "expected": {"max_steps": 2}}],
                          "expected": {"max_steps": 3}})
    data["cases"].append({"id": "roster", "split": "heldout", "input": "Status of Acme?",
                          "tools_offered": ["decoy(x: str) — " + "z" * (4 * 4096)], "expected": {"max_steps": 3}})
    path.write_text(json.dumps(data))
    rc, out, _ = validate(root, "tr")
    check("[F] trajectory: a misspelled expected key warns unread", "unread-key: expected.tools_caled" in out, out)
    check("[F] trajectory: a misspelled key inside turns_expected warns unread", "unread-key: expected.max_stepz" in out, out)
    check("[F] trajectory: keys the runner reads are not flagged",
          not re.search(r"unread-key: expected\.(max_steps|tools_called|error_recovery|answer_contains) ", out), out)
    check("[F] trajectory: a long turn is counted in the estimate (multi OVER)", "multi ~" in out and "OVER" in out, out)
    check("[F] trajectory: the tools_offered roster is counted (roster OVER)", "roster ~" in out, out)
    check("[F] trajectory: a turns case with a non-empty top-level expected warns that it is never read",
          "'multi' is a turns case" in out, out)
    data["cases"] = [c for c in data["cases"] if c["id"] != "roster"]
    data["cases"].append({"id": "noinput", "split": "heldout", "turns": ["Status of Acme?", "And Globex?"],
                          "turns_expected": [{"turn": "Status of Acme?", "expected": {"max_steps": 2}},
                                             {"turn": "And Globex?", "expected": {"max_steps": 2}}],
                          "expected": {}})
    path.write_text(json.dumps(data))
    rc, out, _ = validate(root, "tr")
    check("[F] trajectory: a turns case without input is valid (runner._run_turns never reads it), and an "
          "empty top-level expected is not flagged",
          rc == 0 and error_classes(out) == [] and "'noinput' is a turns case: its top-level" not in out, out)
    check("[F] trajectory: ... but it warns that a listing reads input", "'noinput' is a turns case without input" in out
          and "reads c['input'] on every case" in out and "serve.py" not in out, out)
    data["cases"].append({"id": "badroster", "split": "train", "input": "Status of Acme?",
                          "tools_offered": "decoy(x)", "expected": {"max_steps": 3}})
    path.write_text(json.dumps(data))
    rc, out, err = validate(root, "tr")
    check("[F] trajectory: a malformed tools_offered -> exit 1 structure, not a traceback",
          rc == 1 and error_classes(out) == ["structure"] and "tools_offered" in out and "Traceback" not in err,
          out + err)


# ---------------------------------------------------------------- [G] [H]

def test_G_census_regex_is_test_key_audits():
    src = (ROOT / "sandbox" / "test_key_audit.py").read_text()
    m = re.search(r'^_KEY_READ = re\.compile\(r"""(.*?)"""\)', src, re.M)
    check("[G] test_key_audit.py still defines _KEY_READ", m is not None)
    check("[G] exam_validate.KEY_READ is the same pattern", m is not None and m.group(1) == exam_validate.KEY_READ.pattern,
          f"{m and m.group(1)!r} vs {exam_validate.KEY_READ.pattern!r}")


def test_H_every_committed_exam_validates():
    out = subprocess.run(["find", "evals", "-name", "cases.json", "-not", "-path", "*/.claude/*"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split()
    tasks = sorted(pathlib.Path(x).parent.name for x in out)
    check("[H] precondition: find sees >= 8 exams", len(tasks) >= 8, f"{tasks}")
    for t in tasks:
        rc, o, e = sh(VAL, t)
        check(f"[H] validate {t} -> exit 0", rc == 0, o + e)


def main() -> int:
    for fn in (test_A_new_output_loads_validates_and_runs, test_B_new_refuses_overwrite_and_bad_names,
               test_C_properties_template_through_run_properties, test_D_trajectory_template_honest_run_passes,
               test_E_validate_exits_1_on_each_error_class, test_F_validate_warnings_exit_0,
               test_G_census_regex_is_test_key_audits, test_H_every_committed_exam_validates):
        print(fn.__name__)
        fn()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'FAILED: ' + ', '.join(FAILED) if FAILED else 'all green'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
