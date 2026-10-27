#!/usr/bin/env python3
"""exam_adopt.py — make a measured model the task's model (`wilco adopt`, README step 3b). No inference of its own.

    python3 scripts/exam_adopt.py <task> <provider>/<model> [--replace] [--allow-tier-breach] [--root DIR]

Writes ONLY the top-level `provider:` and `model:` lines of agents/<task>/agent.yaml (line-level, so comments survive;
never `tier`, never cases or splits), then runs `<root>/sandbox/runner.py run <task> --snapshot`: the baseline that
`wilco check` re-sits. The label is split on its FIRST '/' (OpenRouter ids carry their own: openrouter/google/gemma-4).

Refusals, exit 2, nothing written:
  - the label is not `<provider>/<model>`, or the model is a placeholder;
  - the provider is not in sandbox/router.py PROVIDERS;
  - the provider sits above the task's tier (the runner's own sentence). --allow-tier-breach writes it anyway and then
    takes NO snapshot: the runner never snapshots a tier breach (`run --snapshot` refuses one);
  - evals/<task>/snapshot.json exists (a committed baseline) and --replace is not given; the old lines are printed;
  - routes.yaml routes the task and its tier 0 is not the new label (`live` would keep the old model; edit tier 0 first);
  - agent.yaml or routes.yaml does not parse, or the rewrite would not read back with every other field unchanged;
  - the label carries whitespace;
  - agent.yaml has not exactly one top-level `provider:` and one `model:` line.
A snapshot that fails puts agent.yaml back byte for byte and exits with the runner's code."""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "sandbox"))
from router import PROVIDERS  # noqa: E402
from runner import TierBreach, is_placeholder_model, tier_check  # noqa: E402  (the runner's own guards, one sentence)

# a top-level key line: `key: value   # comment` — the value may be quoted; the comment is kept as written
LINE_RE = {k: re.compile(rf"""^{k}:[ \t]*(?:"(?:[^"\\]|\\.)*"|'[^']*'|[^#\n]*?)?([ \t]+#[^\n]*)?[ \t]*$""", re.M)
           for k in ("provider", "model")}


class Refusal(Exception):
    """exit 2 with the message, nothing written"""


def split_label(label):
    if label != label.strip() or any(c.isspace() for c in label):
        raise Refusal(f"{label!r} carries whitespace; a model id never does")
    prov, sep, model = label.partition("/")
    if not sep or not prov.strip() or not model.strip():
        raise Refusal(f"{label!r} is not <provider>/<model> (e.g. ollama/gemma4:e4b or openrouter/google/gemma-4)")
    if is_placeholder_model(model):
        raise Refusal(f"{label!r} names a placeholder, not a model")
    if prov not in PROVIDERS:
        raise Refusal(f"provider {prov!r} is not in sandbox/router.py PROVIDERS ({', '.join(sorted(PROVIDERS))})")
    return prov, model


def rewrite(text, provider, model):
    """agent.yaml text with the two lines replaced; (new_text, old_lines). Refuses unless each key has exactly one line."""
    out, old = text, []
    for key, value in (("provider", provider), ("model", json.dumps(model))):
        hits = list(LINE_RE[key].finditer(out))
        if len(hits) != 1:
            raise Refusal(f"agent.yaml has {len(hits)} top-level `{key}:` lines; adopt edits exactly one")
        m = hits[0]
        old.append(m.group(0))
        out = out[:m.start()] + f"{key}: {value}{m.group(1) or ''}" + out[m.end():]
    return out, old


def run_snapshot(root, task):
    """The snapshot step: the runner of the checkout being edited, never this file's own repo. Returns its exit code.
    Tests replace this function; a root without sandbox/runner.py is refused, never redirected."""
    runner = Path(root) / "sandbox" / "runner.py"
    if not runner.is_file():
        print(f"adopt: no {runner} to take the snapshot with", file=sys.stderr)
        return 2
    return subprocess.run([sys.executable, str(runner), "run", task, "--snapshot"]).returncode


def adopt(task, label, root, replace=False, allow_breach=False):
    root = Path(root)
    path = root / "agents" / task / "agent.yaml"
    if not path.is_file():
        raise Refusal(f"no agents/{task}/agent.yaml under {root} (create the task with: wilco new {task} --mode …)")
    provider, model = split_label(label)
    before = path.read_text()
    try:
        current = yaml.safe_load(before) or {}
    except yaml.YAMLError as exc:
        raise Refusal(f"agents/{task}/agent.yaml does not parse as YAML ({' '.join(str(exc).split())[:160]})") from exc
    try:
        breach = tier_check({**current, "name": task}, provider, allow_breach)
    except TierBreach as exc:
        raise Refusal(str(exc)) from exc
    routes_path = root / "routes.yaml"
    try:
        routes = (yaml.safe_load(routes_path.read_text()) or {}) if routes_path.is_file() else {}
    except yaml.YAMLError as exc:
        raise Refusal(f"routes.yaml does not parse as YAML ({' '.join(str(exc).split())[:160]})") from exc
    tiers = routes.get(task) if isinstance(routes, dict) else None
    if tiers:
        # `live` walks routes.yaml when the task has an entry, and its tier 0 must BE the champion
        # (evals/test_live_routing.py). adopt edits agent.yaml only, so a stale tier 0 would keep `live`
        # on the old model while adopt reports success. Refused: the table is the operator's to edit.
        t0 = tiers[0] if isinstance(tiers, list) and tiers and isinstance(tiers[0], dict) else {}
        if (t0.get("provider"), t0.get("model")) != (provider, model):
            raise Refusal(f"routes.yaml routes `{task}` with tier 0 = {t0.get('provider')}/{t0.get('model')}, and tier 0 "
                          f"must be the task's model; set it to provider: {provider}, model: {model} there first "
                          f"(adopt edits agent.yaml only), then adopt again")
    snap = root / "evals" / task / "snapshot.json"
    after, old = rewrite(before, provider, model)
    if snap.exists() and not replace:
        try:
            was = json.loads(snap.read_text())
            was = f"{was.get('provider')}/{was.get('model')}"
        except (OSError, ValueError, AttributeError):
            was = "unreadable"
        raise Refusal(f"evals/{task}/snapshot.json is a committed baseline (it names {was}); agent.yaml now says "
                      f"{' · '.join(o.strip() for o in old)} — pass --replace to adopt {label} over it")
    try:
        new = yaml.safe_load(after) or {}
    except yaml.YAMLError:
        new = None   # e.g. a block-scalar `model: >-` line: the one-line rewrite leaves its body behind
    rest = lambda d: {k: v for k, v in d.items() if k not in ("provider", "model")}  # noqa: E731
    if not isinstance(new, dict) or (new.get("provider"), new.get("model")) != (provider, model) \
            or rest(current) != rest(new):
        raise Refusal(f"the rewrite of agents/{task}/agent.yaml would not read back as {label} with every other field "
                      f"unchanged (a multi-line provider:/model: value?) — edit those two lines by hand; nothing written")
    path.write_text(after)
    print(f"agents/{task}/agent.yaml:")
    for o in old:
        print(f"  - {o.strip()}")
    print(f"  + provider: {provider}\n  + model: {json.dumps(model)}")
    if breach:
        print(f"no snapshot: {label} is above the task's tier, and the runner never snapshots a tier breach. "
              f"`wilco check {task}` has no baseline for it" + (f" (evals/{task}/snapshot.json still names the old model)"
                                                                 if snap.exists() else ""))
        return 0
    via = "wilco" if os.environ.get("WILCO_PROG") else "python3 sandbox/runner.py"
    print(f"snapshot: {via} run {task} --snapshot", flush=True)   # flushed: the runner's output follows, in order
    try:
        rc = run_snapshot(root, task)
    except BaseException:   # Ctrl-C (or anything) during a multi-minute snapshot: the file goes back too
        path.write_text(before)
        print(f"adopt: the snapshot was interrupted; agents/{task}/agent.yaml restored as it was", file=sys.stderr)
        raise
    if rc != 0:
        path.write_text(before)
        print(f"adopt: the snapshot failed (exit {rc}); agents/{task}/agent.yaml restored as it was", file=sys.stderr)
        return rc
    print(f"adopted {label} — `wilco check {task}` re-sits this baseline")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog=f"{os.environ['WILCO_PROG']} adopt" if os.environ.get("WILCO_PROG") else None,
                                 description="write a measured model into agents/<task>/agent.yaml, then snapshot it")
    ap.add_argument("task")
    ap.add_argument("label", metavar="provider/model", help="as `wilco pick` prints it, e.g. ollama/gemma4:e4b")
    ap.add_argument("--replace", action="store_true", help="adopt over an existing evals/<task>/snapshot.json")
    ap.add_argument("--allow-tier-breach", action="store_true",
                    help="write a provider above the task's tier (no snapshot is taken)")
    ap.add_argument("--root", default=str(REPO), help="repo root to edit (tests use a temp dir)")
    a = ap.parse_args(argv)
    try:
        return adopt(a.task, a.label, a.root, replace=a.replace, allow_breach=a.allow_tier_breach)
    except Refusal as e:
        print(f"adopt: REFUSED — {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
