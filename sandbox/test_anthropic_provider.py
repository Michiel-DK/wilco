"""anthropic provider (2026-10-28): the body sent to Anthropic's OpenAI-compatible endpoint
carries NO `temperature` (the endpoint 400s on it); every other provider's body is unchanged
(ollama still sends temperature 0.0); the provider has a tier. check()-style: run with
`python3 sandbox/test_anthropic_provider.py`, rc 1 on any failure (CLAUDE.md gotcha 17)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # insert, never append: a namespace package on PYTHONPATH would shadow this repo's router (refuter, 28 Oct)
from sandbox import router

FAILED = []
def check(label, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + label + ("" if cond else f"  -- {detail}"))
    if not cond: FAILED.append(label)

class _Resp:
    status_code = 200
    def raise_for_status(self): pass
    def json(self):
        return {"choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}

captured = []
def fake_post(url, headers=None, data=None, timeout=None):
    captured.append((url, json.loads(data))); return _Resp()

def main():
    router.requests.post = fake_post
    os.environ["ANTHROPIC_API_KEY"] = "test-not-a-key"
    msgs = [{"role": "user", "content": "x"}]
    check("PROVIDERS has anthropic", "anthropic" in router.PROVIDERS, str(sorted(router.PROVIDERS)))
    check("anthropic tier is frontier", router.PROVIDER_TIER.get("anthropic") == "frontier",
          str(router.PROVIDER_TIER.get("anthropic")))
    router.get_adapter("anthropic").generate(msgs, "claude-opus-5-5")
    router.get_adapter("ollama").generate(msgs, "gemma4:e2b-it-qat")
    url_a, body_a = captured[0]; url_o, body_o = captured[1]
    check("anthropic url is the vendor's chat/completions",
          url_a == "https://api.anthropic.com/v1/chat/completions", url_a)
    check("anthropic body has NO temperature", "temperature" not in body_a, json.dumps(body_a))
    check("anthropic body is EXACTLY model/messages/max_tokens/stream (nothing added, only temperature gone)",
          sorted(body_a) == ["max_tokens", "messages", "model", "stream"], str(sorted(body_a)))
    check("ollama body still carries temperature 0.0 (byte-identical default path)",
          body_o.get("temperature") == 0.0 and sorted(body_o) == ["max_tokens", "messages", "model", "stream", "temperature"],
          str(sorted(body_o)))
    check("default drop_body_keys is empty", router.ChatCompletionsAdapter("http://x").drop_body_keys == ())
    print(f"\n{len(FAILED)} failed"); return 1 if FAILED else 0

if __name__ == "__main__":
    sys.exit(main())
