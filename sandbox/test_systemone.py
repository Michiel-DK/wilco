#!/usr/bin/env python3
"""SYSTEMONE TIER — witness tests for the decision-model adapter (2026-09-30).

WHAT SHIPS: a `systemone` entry in router.PROVIDERS ("kind": "systemone") and a
SystemOneAdapter that talks to Ollama's `/v1/systemone` decision endpoint (nimble,
tev1): state + named typed questions in, one answer + probability per question out,
no generation. Per-agent question specs live in `agents/<name>/decision.yaml`, loaded
by runner.adapter_for ONLY when the resolved provider is of kind systemone. Every
committed agent.yaml is untouched, so every gate loads a byte-identical config.

WHY A NEW ADAPTER CLASS when CLAUDE.md says "model swaps are config, never a new
adapter class": this is not a model swap. /v1/systemone is a different wire protocol
(no messages, no completion) — the same reason mlx got a PROVIDERS line but a chat
model got no new class. The rule protects the gate from score-moving changes wearing a
config costume; the DEFAULT-UNCHANGED assertions below are what keep that promise.

Each check says what a WRONG build would do and which assertion catches it.
Deterministic: no server, no inference. requests.post is captured.
"""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
import router as R  # noqa: E402
import runner  # noqa: E402

FAILED = []


def check(label, ok, extra=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {extra}" if not ok and extra else ""))
    if not ok:
        FAILED.append(label)


CANNED = {
    "model": "tev1:0.8b",
    "answers": {
        "label": {"type": "choice", "choice": "reply_now",
                  "probabilities": {"reply_now": 0.91, "reply_later": 0.07, "ignore": 0.02},
                  "confidence": 0.84},
        "recurring": {"type": "noul", "noul": 0.93},
        "urgency": {"type": "score", "score": 0.815,
                    "legend": {"0": "Routine", "1": "Soon", "2": "Urgent"},
                    "probabilities": {"0": 0.1, "1": 0.7, "2": 0.2}, "confidence": 0.5},
    },
    "usage": {"input_tokens": 120, "output_tokens": 3},
}


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def capture(adapter, payload=CANNED):
    seen = {}

    def fake_post(url, headers=None, data=None, json=None, timeout=None):
        seen["url"] = url
        seen["timeout"] = timeout
        seen["body"] = json if json is not None else __import__("json").loads(data)
        return _Resp(payload)

    orig = R.requests.post
    R.requests.post = fake_post
    try:
        text, meta = adapter.generate([{"role": "system", "content": "sys"},
                                       {"role": "user", "content": "I was charged twice."}],
                                      "tev1:0.8b")
    finally:
        R.requests.post = orig
    return seen, text, meta


DECISION = {
    "state_key": "input",
    "questions": {
        "label": {"type": "choice", "instructions": "Which label?",
                  "criteria": {"reply_now": "a", "reply_later": "b", "ignore": "c"}},
        "recurring": {"type": "noul", "instructions": "Recurring charge?"},
        "urgency": {"type": "score", "instructions": "How urgent?",
                    "criteria": ["Routine", "Soon", "Urgent"]},
    },
    "outputs": {"label": "label", "recurring": "recurring", "urgency": "urgency"},
}

# 1. The provider exists and is of the new kind; the OLD providers are untouched.
check("systemone is a PROVIDERS entry of kind systemone",
      R.PROVIDERS.get("systemone", {}).get("kind") == "systemone")
check("no pre-existing provider gained a kind key (default path byte-identical)",
      all("kind" not in cfg for name, cfg in R.PROVIDERS.items() if name != "systemone"))

# 2. get_adapter: the decision arg is ignored by every chat provider (a WRONG build that
#    threaded it into the request body would move every committed score).
a = R.get_adapter("stub", decision=DECISION)
check("decision is ignored by the stub/chat path", isinstance(a, R.StubAdapter))
try:
    R.get_adapter("systemone")
    check("systemone without a decision spec is refused", False)
except ValueError:
    check("systemone without a decision spec is refused", True)
except Exception as e:  # noqa: BLE001 — a WRONG build that builds the adapter on None crashes here; record it, do not abort
    check("systemone without a decision spec is refused", False, f"{type(e).__name__}: {e}")

# 2b. The chat path is byte-identical with and without a decision argument: same request
#     body to the same URL (a WRONG build that threaded `decision` into the chat body would
#     move every committed score). Captured through the ollama provider, offline.
CHAT_CANNED = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
               "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
_plain, _, _ = capture(R.get_adapter("ollama", timeout=7), CHAT_CANNED)
_with, _, _ = capture(R.get_adapter("ollama", timeout=7, decision=DECISION), CHAT_CANNED)
check("ollama chat request is byte-identical with and without a decision arg",
      _plain == _with and "/chat/completions" in _plain["url"], json.dumps(_with)[:200])

# 3. The request shape: POST {base}/systemone with model, state[state_key] = the LAST
#    user message (the exam input), and the questions verbatim. A WRONG build that sent
#    the system prompt as state, or hit /chat/completions, is caught here.
ad = R.get_adapter("systemone", decision=DECISION, timeout=7)
seen, text, meta = capture(ad)
check("POSTs to /v1/systemone", seen["url"].endswith("/v1/systemone"), seen.get("url"))
check("timeout is threaded through", seen["timeout"] == 7)
check("state carries the user message under state_key",
      seen["body"].get("state") == {"input": "I was charged twice."}, str(seen["body"].get("state")))
check("questions are sent verbatim", seen["body"].get("questions") == DECISION["questions"])
check("model is sent", seen["body"].get("model") == "tev1:0.8b")

# 4. The answer mapping: the text returned is JSON that score_labels / score_fields read
#    unchanged. choice -> the chosen key; noul -> bool at the 0.5 threshold; score -> the
#    legend word of the argmax probability.
out = json.loads(text)
check("choice maps to its key", out.get("label") == "reply_now", text)
check("noul maps to a bool", out.get("recurring") is True, text)
check("score maps to the argmax legend word", out.get("urgency") == "Soon", text)
check("no extra keys leak into the scored output", set(out) == {"label", "recurring", "urgency"}, str(out))

# 5. Metrics: usage is reported under the harness's names; finish_reason is None (no
#    generation happened — reporting "stop" would assert a termination fact nothing
#    measured, D1); per-question confidence rides in meta for the escalation gate.
check("usage mapped to prompt/completion/total",
      (meta["prompt_tokens"], meta["completion_tokens"], meta["total_tokens"]) == (120, 3, 123), str(meta))
check("finish_reason is None", meta.get("finish_reason") is None)
check("per-question confidence is in meta",
      meta.get("decision", {}).get("label", {}).get("confidence") == 0.84, str(meta.get("decision")))

# 6. Passthrough: task-intake's verbatim hand-over is a code rule, not a question.
#    `passthrough: {input: state}` copies the state; `empty_when: {agent: none}` blanks it.
PT = {"state_key": "input",
      "questions": {"agent": {"type": "choice", "instructions": "Which?",
                              "criteria": {"crm-followup": "a", "none": "b"}}},
      "outputs": {"agent": "agent"},
      "passthrough": {"input": "state"},
      "empty_when": {"agent": "none"}}
payload = {"model": "m", "answers": {"agent": {"type": "choice", "choice": "crm-followup",
                                               "probabilities": {}, "confidence": 0.9}},
           "usage": {"input_tokens": 1, "output_tokens": 1}}
_, t1, _ = capture(R.get_adapter("systemone", decision=PT), payload)
check("passthrough copies the state verbatim", json.loads(t1).get("input") == "I was charged twice.", t1)
payload["answers"]["agent"]["choice"] = "none"
_, t2, _ = capture(R.get_adapter("systemone", decision=PT), payload)
check("empty_when blanks the hand-over for none", json.loads(t2).get("input") == "", t2)

# 7. A missing answer is a TerminationError (nothing to score), never a default.
bad = {"model": "m", "answers": {}, "usage": {}}
try:
    capture(R.get_adapter("systemone", decision=DECISION), bad)
    check("missing answers raise TerminationError", False)
except R.TerminationError:
    check("missing answers raise TerminationError", True)

# 7b. ONE missing answer out of three is also a TerminationError. `answers: {}` alone would
#     stay green under a weakened `if not answers:` guard (reproduced 12 Oct: that guard
#     raises KeyError, not TerminationError, on this payload). except-Exception records FAIL.
partial = {"model": "m", "answers": {k: v for k, v in CANNED["answers"].items() if k != "urgency"}, "usage": {}}
try:
    capture(R.get_adapter("systemone", decision=DECISION), partial)
    check("one missing answer of three raises TerminationError", False, "scored")
except R.TerminationError:
    check("one missing answer of three raises TerminationError", True)
except Exception as e:  # noqa: BLE001
    check("one missing answer of three raises TerminationError", False, f"{type(e).__name__}: {e}")

# 8. runner.adapter_for loads agents/<name>/decision.yaml ONLY for the systemone kind,
#    and every committed decision.yaml names exactly the exam's label vocabulary (a
#    criteria set that drifts from the exam's expected values is a silent 0/N).
for name in ("email-triage", "expense-categorization", "task-intake"):
    spec_path = ROOT / "agents" / name / "decision.yaml"
    check(f"{name}: decision.yaml exists", spec_path.exists())
    if not spec_path.exists():
        continue
    spec = yaml.safe_load(spec_path.read_text())
    cases = json.loads((ROOT / "evals" / name / "cases.json").read_text())["cases"]
    for out_key, q_name in spec["outputs"].items():
        q = spec["questions"][q_name]
        want = {c["expected"][out_key] for c in cases if out_key in c["expected"]}
        if q["type"] == "choice":
            check(f"{name}: every expected {out_key!r} is a criteria key",
                  want <= set(q["criteria"]), str(want - set(q["criteria"])))
        elif q["type"] == "noul":
            check(f"{name}: expected {out_key!r} values are bools", want <= {True, False}, str(want))
    agent = runner.load_agent(name)
    chat = runner.adapter_for(agent)                      # committed provider: unchanged path
    check(f"{name}: committed provider still builds a ChatCompletionsAdapter",
          isinstance(chat, R.ChatCompletionsAdapter))
    dm = runner.adapter_for(agent, provider="systemone")  # the probe path
    check(f"{name}: --provider systemone builds a SystemOneAdapter", isinstance(dm, R.SystemOneAdapter))

# 8a. The default path for EVERY committed agent (not only the three with a decision.yaml):
#     exact type ChatCompletionsAdapter, and load_decision is never called (patched to raise).
_agents = sorted(d.name for d in (ROOT / "agents").iterdir() if (d / "agent.yaml").exists())
check("at least the 8 committed agents are enumerated", len(_agents) >= 8, str(_agents))
_old_load = runner.load_decision


def _never(name):
    raise AssertionError(f"load_decision called on the default path for {name}")


runner.load_decision = _never
try:
    for name in _agents:
        try:
            _ad = runner.adapter_for(runner.load_agent(name))
            check(f"{name}: default path builds exactly ChatCompletionsAdapter without load_decision",
                  type(_ad) is R.ChatCompletionsAdapter, type(_ad).__name__)
        except Exception as e:  # noqa: BLE001
            check(f"{name}: default path builds exactly ChatCompletionsAdapter without load_decision",
                  False, f"{type(e).__name__}: {e}")
finally:
    runner.load_decision = _old_load

# 8b. load_decision's own sys.exit guards. Catch SystemExit SPECIFICALLY: with the guard
#     deleted, a missing file raises FileNotFoundError (message also holds the path), so a
#     catch-any-exception check would stay green. The except-Exception branch records FAIL.
import tempfile  # noqa: E402

try:
    runner.load_decision("recap")                         # recap has no decision.yaml
    check("load_decision: missing spec exits via SystemExit naming the path", False, "returned")
except SystemExit as e:
    check("load_decision: missing spec exits via SystemExit naming the path",
          "agents/recap/decision.yaml" in str(e), str(e))
except Exception as e:  # noqa: BLE001
    check("load_decision: missing spec exits via SystemExit naming the path", False,
          f"{type(e).__name__}: {e}")

_old_root = runner.ROOT
with tempfile.TemporaryDirectory() as tmp:
    (Path(tmp) / "agents" / "recap").mkdir(parents=True)
    (Path(tmp) / "agents" / "recap" / "decision.yaml").write_text("")
    runner.ROOT = Path(tmp)
    try:
        runner.load_decision("recap")
        check("load_decision: empty spec exits via SystemExit 'no questions'", False, "returned")
    except SystemExit as e:
        check("load_decision: empty spec exits via SystemExit 'no questions'",
              "agents/recap/decision.yaml" in str(e) and "no questions" in str(e), str(e))
    except Exception as e:  # noqa: BLE001
        check("load_decision: empty spec exits via SystemExit 'no questions'", False,
              f"{type(e).__name__}: {e}")
    finally:
        runner.ROOT = _old_root

# 9. agent.yaml files are untouched by this lane (byte-identical gate configs).
for name in ("email-triage", "expense-categorization", "task-intake"):
    cfg = yaml.safe_load((ROOT / "agents" / name / "agent.yaml").read_text())
    check(f"{name}: agent.yaml has no decision key", "decision" not in cfg)

print()
if FAILED:
    print(f"FAILED ({len(FAILED)}):")
    for f in FAILED:
        print(f"  - {f}")
    sys.exit(1)
print("all systemone checks passed")
