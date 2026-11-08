#!/usr/bin/env python3
"""Grade Arm N (n8n's raw Haiku answers) through the REAL entry point: sandbox/runner.run_exam with
runner.adapter_for swapped for a replay adapter (gotcha 5: a separate re-grader is not a witness).

The replay adapter answers by the case INPUT (the user message), never by order, and raises on any input
it has no answer for. One asymmetry is stated, not hidden: when the answer does not parse, the runner
re-asks, and a real model gets a fresh sample. The replay returns the same text, so that case fails
where Arm R might have recovered. `reasks` in the output counts those cases.

Usage: python3 grade_replay.py <exam>   -> writes armN/<exam>.graded.json, prints the runner's own lines.
Nothing here calls a model. Nothing here writes outside this folder."""
import contextlib, io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "sandbox"))
import runner  # noqa: E402

exam_name = sys.argv[1]
# optional: argv[2] = an answers file {case_id: {"text": ...}}, argv[3] = output path (used by validate_replay.py)
answers_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "armN", f"{exam_name}.json")
out_path = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "armN", f"{exam_name}.graded.json")
answers = {k: v for k, v in json.load(open(answers_path)).items() if not k.startswith("_")}
exam = runner.load_exam(exam_name)
by_input = {}
for case in exam["cases"]:
    if case["id"] not in answers:
        raise SystemExit(f"no n8n answer for case {case['id']!r}")
    by_input[case["input"]] = (case["id"], answers[case["id"]]["text"])

calls = {}


class Replay:
    def generate(self, messages, model, temperature=0.0, max_tokens=512):
        user = [m for m in messages if m["role"] == "user"][0]["content"]
        if user not in by_input:
            raise KeyError(f"replay: no recorded answer for an input starting {user[:60]!r}")
        cid, text = by_input[user]
        calls[cid] = calls.get(cid, 0) + 1
        return text, {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None,
                      "content_chars": len(text), "reasoning_chars": 0, "finish_reason": "stop"}


runner.adapter_for = lambda *a, **k: Replay()
runner.time.sleep = lambda s: None  # the retry backoff would only wait on the same recorded text
import retry  # noqa: E402
retry.time.sleep = lambda s: None
agent = runner.load_agent(exam_name)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    result = runner.run_exam(agent, exam, "n8n-replay", "claude-haiku-5-5")
print(buf.getvalue())
result["reasks"] = sorted(c for c, n in calls.items() if n > 1)
result["arm"] = "N: n8n Cloud 2.46.4 workflow wVhvSAXixE6oaTyz, Basic LLM Chain + Anthropic Chat Model claude-haiku-5-5"
json.dump(result, open(out_path, "w"), indent=1, ensure_ascii=False)
print(f"{exam_name}: train {result['train']['passed']}/{result['train']['total']} · "
      f"heldout {result['heldout']['passed']}/{result['heldout']['total']} · re-asked (same text replayed): {result['reasks']}")
