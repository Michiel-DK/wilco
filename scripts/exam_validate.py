#!/usr/bin/env python3
"""Validate one exam before anything runs it: `python3 scripts/exam_validate.py <task>`.

Loads through sandbox/runner.py's own load_exam / load_agent / load_properties (the real entry points,
CLAUDE.md gotcha 5), then reports. No inference, no network.

ERRORS (exit 1)
  structure       (also) a mode outside labels|fields|properties|trajectory; a turns case whose turns_expected
                  does not match its turns by position and text (runner._turn_expected)
  structure       a case without a string id / input / dict expected (a `turns` case may omit input unless a
                  properties.py runs), a split other than train|heldout, malformed turns or tools_offered,
                  cases.json that is not JSON, an agent.yaml that does not parse
  duplicate-id    two cases share an id (snapshots and `check` key on it)
  duplicate-input two cases share an input text (_exp resolves expectations by exact input: the second is
                  unreachable, and a labels exam would score one text against two answers)
  unknown-label   labels mode: an expected value outside the list prompt.md declares for that key, written
                  as  "<key>": "<a|b|c>"  in the answer format. Without a declared list the check cannot
                  fire; that is a warning, and the observed set is printed.
  no-split        no train case, or no heldout case
  properties      a check without a bucket; a properties.py that does not import; properties mode with 0 checks
                  (run_exam would pass every case)
WARNINGS (exit 0)
  heldout share under 1/3 · an expected key (also inside turns_expected) the scorer never reads (presence is
  not effect, gotcha 1; a properties.py reading through an alias, `e = _exp(t); e["k"]`, is not seen) ·
  a declared label no case expects · a prompt-token ESTIMATE over the champion's window (gotcha 16)

The window line: W2's preflight is not merged, so the estimate here is chars/4 over prompt.md + input
(+ turns), tagged `estimated`, against `PARAMETER num_ctx` in agents/<task>/Modelfile, else Ollama's 4,096
default, credited only when the Modelfile or agent.yaml says `ollama create <model>`. Only for provider
ollama; any other provider's window is not read here.

  exit 0  no errors (warnings may print)    exit 1  at least one error    exit 2  bad arguments
"""
import argparse
import contextlib
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "sandbox"))
import runner  # noqa: E402

# The key census. Same pattern as sandbox/test_key_audit.py `_KEY_READ` (pinned equal in
# sandbox/test_exam_tools.py): every `_exp(...)["k"]`, `_exp(...).get("k")`, `exp["k"]`, `expected.get("k")`.
KEY_READ = re.compile(r"""(?:\b_exp\([^)]*\)|\bexp(?:ected)?)\s*(?:\.get\(\s*|\[\s*)["']([a-z_]+)["']""")
# runner.py reads trajectory keys as expected.get("k") / expected["k"] (score_trajectory, score_case).
RUNNER_KEY_READ = re.compile(r"""\bexpected(?:\.get\(\s*|\[\s*)["']([a-z_]+)["']""")
LABEL_DECL = re.compile(r'"([a-z_]+)"\s*:\s*"<([^<>"]+\|[^<>"]+)>"')
OLLAMA_DEFAULT_CTX = 4096
SPLITS = ("train", "heldout")
MODES = ("labels", "fields", "properties", "trajectory")


def declared_labels(prompt_text):
    """{key: set(labels)} from answer-format lines like {"label": "<a|b|c>"}."""
    return {k: {x.strip() for x in alts.split("|")} for k, alts in LABEL_DECL.findall(prompt_text)}


def keys_read(task, mode):
    """Expected keys the scorer for this exam can read, or None for 'every key' (labels/fields compare all).
    Limit, declared: this scans the TEXT of properties.py, not the loaded check_* functions, so a key read only by
    a dead helper counts as read (helpers that checks call read keys too, so scanning check bodies alone would
    false-warn on committed exams)."""
    if mode in ("labels", "fields"):
        return None
    read = set()
    props = runner.ROOT / "evals" / task / "properties.py"
    if props.exists():
        read |= set(KEY_READ.findall(props.read_text()))
    if mode == "trajectory":
        read |= set(RUNNER_KEY_READ.findall((REPO / "sandbox" / "runner.py").read_text()))
    return read


def champion_window(task, agent):
    """(window, why, warning). A Modelfile's num_ctx is credited only when the Modelfile or agent.yaml says
    `ollama create <agent.yaml model>`: a Modelfile beside a model that was never built from it changes nothing."""
    if agent.get("provider") != "ollama":
        return None, f"provider {agent.get('provider')!r}: window not read here", None
    mf = runner.ROOT / "agents" / task / "Modelfile"
    default = ("Ollama default 4,096 (no num_ctx in a Modelfile; the compat endpoint ignores num_ctx in the "
               "request)")
    if not mf.exists():
        return OLLAMA_DEFAULT_CTX, default, None
    text = mf.read_text()
    m = re.search(r"^\s*PARAMETER\s+num_ctx\s+(\d+)", text, re.M | re.I)
    if not m:
        return OLLAMA_DEFAULT_CTX, default, None
    model = str(agent.get("model"))
    built = re.compile(r"ollama\s+create\s+" + re.escape(model) + r"(?![\w.:-])", re.I)
    yaml_text = (runner.ROOT / "agents" / task / "agent.yaml").read_text()
    if built.search(text) or built.search(yaml_text):
        return int(m.group(1)), f"num_ctx {m.group(1)} from agents/{task}/Modelfile (model {model})", None
    return OLLAMA_DEFAULT_CTX, default, (
        f"window: agents/{task}/Modelfile sets num_ctx {m.group(1)}, but neither it nor agent.yaml says "
        f"`ollama create {model}`, so model {model!r} is not shown to run at it; estimated against 4,096. Add "
        f"the line `# ollama create {model} -f agents/{task}/Modelfile` to the Modelfile once you have built it")


def _text(v):
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def _sent_text(c):
    """What the model is sent as user text: the turns for a `turns` case (runner._run_turns sends only those;
    its `input` is a joined copy), else the input."""
    return "\n".join(c["turns"]) if c.get("turns") else c["input"]


def validate(task, per_case=False):
    """Returns (errors, warnings, info) as lists of strings. Raises SystemExit (from runner) on a missing exam."""
    errors, warnings, info = [], [], []
    try:
        exam = runner.load_exam(task)
    except json.JSONDecodeError as e:
        return [f"structure: evals/{task}/cases.json is not valid JSON: {e}"], warnings, info
    mode = exam.get("mode", "labels")
    if mode not in MODES:
        # runner.run_exam scores any unknown mode as labels, silently
        return [f"structure: mode {mode!r} is not one of {MODES} (the runner would score it as labels)"], warnings, info
    cases = exam.get("cases")
    if not isinstance(cases, list) or not cases:
        return [f"structure: evals/{task}/cases.json has no 'cases' list"], warnings, info
    try:
        agent = runner.load_agent(task)
    except Exception as e:   # a malformed agent.yaml is an error to report, not a traceback
        return [f"structure: agents/{task}/agent.yaml or prompt.md does not load: {type(e).__name__}: {e}"], warnings, info
    # load_properties refuses a check without a bucket (SystemExit); surface it as an error, not a crash.
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            props = runner.load_properties(task)
    except SystemExit as e:
        errors.append(f"properties: {e.code}")
        props = None
    except Exception as e:   # a properties.py that does not import is an error to report, not a traceback
        errors.append(f"properties: evals/{task}/properties.py does not load: {type(e).__name__}: {e}")
        props = None
    if props is None:
        props = []
    elif mode == "properties" and not props:
        # run_exam sets passed = True in properties mode and leaves the verdict to the checks: none = every case passes
        errors.append(f"properties: properties mode loads 0 check_* functions from evals/{task}/properties.py, so "
                      f"every case passes whatever the output")
    info.append(f"mode {mode} · {len(cases)} cases · {len(props)} property checks")

    good = []
    for i, c in enumerate(cases):
        where = f"case[{i}] {c.get('id')!r}" if isinstance(c, dict) else f"case[{i}]"
        if not isinstance(c, dict):
            errors.append(f"structure: {where} is not an object")
            continue
        bad = [k for k, t in (("id", str), ("expected", dict)) if not isinstance(c.get(k), t)]
        turns = c.get("turns")
        if turns is not None and not (isinstance(turns, list) and turns and all(isinstance(t, str) for t in turns)):
            bad.append("turns as a non-empty list of strings")
        # A `turns` case may omit `input` (runner._run_turns never reads it) unless a properties.py runs on it:
        # run_exam hands case["input"] to run_properties for every case.
        if not isinstance(c.get("input"), str) and (turns is None or props):
            bad.append("input")
        if bad:
            errors.append(f"structure: {where} needs {', '.join(bad)}")
            continue
        if c.get("split") not in SPLITS:
            errors.append(f"structure: {where} split {c.get('split')!r} is not one of {SPLITS}")
            continue
        if mode == "trajectory":
            try:
                runner._trajectory_system_prompt(agent, c)
            except ValueError as e:
                errors.append(f"structure: {where} {e}")
                continue
        if turns is not None:
            # The runner resolves each turn's expectations by position AND text (runner._turn_expected); a drift
            # raises inside run_exam and the case fails for every model, a stable fail nobody can pass.
            try:
                for k, t in enumerate(turns):
                    runner._turn_expected(c, k, t)
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                errors.append(f"structure: {where} turns / turns_expected: {type(e).__name__}: {e}")
                continue
            if "input" not in c:
                warnings.append(f"structure: {where} is a turns case without input: the runner never reads it, but "
                                f"a tool that lists an exam's inputs (the private dev server's exam view) reads c['input'] on every case")
        good.append(c)

    per_split = Counter(c["split"] for c in good)
    info.append("per split: " + " · ".join(f"{s} {per_split.get(s, 0)}" for s in SPLITS))
    for s in SPLITS:
        if not per_split.get(s):
            errors.append(f"no-split: no {s} case")
    if good and per_split.get("heldout", 0) * 3 < len(good):
        warnings.append(f"heldout share {per_split.get('heldout', 0)}/{len(good)} is under 1/3")

    for field, label in (("id", "duplicate-id"), ("input", "duplicate-input")):
        seen = defaultdict(list)
        for c in good:
            # _exp and run_properties key on `input`; a turns case without one is keyed on its turns
            seen[c["id"] if field == "id" else c.get("input", _sent_text(c))].append(c["id"])
        for val, ids in seen.items():
            if len(ids) > 1:
                shown = val if field == "id" else val[:60] + ("…" if len(val) > 60 else "")
                errors.append(f"{label}: {ids} share {field} {shown!r}")

    if mode == "labels":
        decl = declared_labels(agent["system_prompt"])
        observed = defaultdict(set)
        for c in good:
            for k, v in c["expected"].items():
                observed[k].add(v if isinstance(v, str) else json.dumps(v))
        for k in sorted(observed):
            if k not in decl:
                warnings.append(f"labels: prompt.md declares no list for {k!r} (write \"{k}\": \"<a|b|c>\"); "
                                f"unknown-label cannot fire. Observed: {sorted(observed[k])}")
                continue
            allowed = {x.lower() for x in decl[k]}
            for c in good:
                v = c["expected"].get(k)
                if v is not None and _text(v).strip().lower() not in allowed:
                    errors.append(f"unknown-label: {c['id']!r} expects {k}={v!r}, not in prompt.md's "
                                  f"{sorted(decl[k])}")
            unused = sorted(x for x in decl[k] if x.lower() not in {o.lower() for o in observed[k]})
            if unused:
                warnings.append(f"labels: {k} declares {unused} but no case expects it")

    read = keys_read(task, mode)
    if read is not None:
        unread = defaultdict(list)
        for c in good:
            blocks = [c["expected"]] + [t.get("expected") or {} for t in c.get("turns_expected") or []
                                        if isinstance(t, dict)]
            for k in {k for b in blocks if isinstance(b, dict) for k in b}:
                if k not in read:
                    unread[k].append(c["id"])
        for c in good:
            if c.get("turns") and c["expected"]:
                warnings.append(f"unread-key: {c['id']!r} is a turns case: its top-level expected "
                                f"{sorted(c['expected'])} is never read (runner._run_turns scores turns_expected only)")
        for k, ids in sorted(unread.items()):
            warnings.append(f"unread-key: expected.{k} on {len(ids)} case(s) is read by no scorer "
                            f"({'properties.py' if mode == 'properties' else 'runner.py or properties.py'}); "
                            f"first: {ids[0]!r}")

    window, why, mismatch = champion_window(task, agent)
    if mismatch:
        warnings.append(mismatch)
    if window is None:
        info.append(f"window: {why}")
    else:
        over, near = [], []
        top = (0, None)
        for c in good:
            # The system prompt as the runner builds it for THIS case (a trajectory case's tools_offered roster
            # is appended by runner._trajectory_system_prompt).
            system = runner._trajectory_system_prompt(agent, c) if mode == "trajectory" else agent["system_prompt"]
            chars = len(system) + len(_sent_text(c))
            est = chars // 4
            if per_case:
                info.append(f"  estimate {c['id']}: ~{est} / {window} tokens")
            top = max(top, (est, c["id"]))
            if est > window:
                over.append(f"{c['id']} ~{est}")
            elif est > window * 3 // 4:
                near.append(f"{c['id']} ~{est}")
        info.append(f"window: {why}; largest prompt ~{top[0]} tokens ({top[1]}), estimated (chars/4; measured "
                    f"here at ~3.7 chars/token, so it reads ~8% low)"
                    + ("; tool results NOT counted, a trajectory grows past this with every call"
                       if mode == "trajectory" else "")
                    + ("; turns counted, assistant replies between them not" if any(c.get("turns") for c in good) else ""))
        if over:
            warnings.append(f"window: {len(over)} case(s) estimated OVER {window} tokens, the front of the "
                            f"prompt is cut: {over[:5]}. Fix: a Modelfile with PARAMETER num_ctx (gotcha 16)")
        if near:
            warnings.append(f"window: {len(near)} case(s) estimated within 1/4 of {window} tokens "
                            f"(the answer needs room too): {near[:5]}")
    return errors, warnings, info


def main(argv=None):
    # W7: `wilco validate` in the usage line under the shim (WILCO_PROG)
    ap = argparse.ArgumentParser(prog=f"{os.environ['WILCO_PROG']} validate" if os.environ.get("WILCO_PROG") else None,
                                 description=__doc__.split("\n")[0])
    ap.add_argument("task")
    ap.add_argument("--root", default=str(REPO), help="repo root to read from (tests use a temp dir)")
    ap.add_argument("--per-case", action="store_true", help="print every case's prompt-token estimate")
    a = ap.parse_args(argv)
    runner.ROOT = Path(a.root)
    if not (runner.ROOT / "agents" / a.task / "agent.yaml").exists():
        print(f"exam_validate: no agents/{a.task}/agent.yaml under {runner.ROOT}", file=sys.stderr)
        return 2
    errors, warnings, info = validate(a.task, per_case=a.per_case)
    for line in info:
        print(f"  {line}")
    for line in warnings:
        print(f"WARN  {line}")
    for line in errors:
        print(f"ERROR {line}")
    print(f"{a.task}: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
