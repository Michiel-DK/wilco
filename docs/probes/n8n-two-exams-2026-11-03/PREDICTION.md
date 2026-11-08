# n8n two-exam probe — prediction (written 3 Nov 2026, BEFORE the first model call)

**What runs.** Claude Haiku 5.5 sits `call-fields` (32 cases, 19 held-out) and `recap` (23 cases, 16 held-out)
twice, on the same day:

- **Arm N (n8n):** n8n Cloud trial workflow `wVhvSAXixE6oaTyz` (built through the n8n MCP). One webhook call per case.
  The case and `prompt.md` are fetched from public `Michiel-DK/wilco@2ed67b7`. Their bytes match agent-sandbox master
  (`git hash-object`, checked 3 Nov). Basic LLM Chain: system = prompt.md, user = case input. Anthropic Chat Model
  `claude-haiku-5-5`, temperature 0 (the node says it is ignored on newer models), thinking unset (node default
  disabled), max tokens 4096 for call-fields and 2048 for recap (the agent.yaml values). The raw answer text is graded
  offline through **our real entry point**: `run_exam` with a replay adapter keyed by case input, which raises on a miss.
- **Arm R (runner):** `sandbox/runner.py run <exam> --provider anthropic --model claude-haiku-5-5`, same day. The
  OpenAI-compatible endpoint drops `temperature`, and thinking is on there (router.py note, 28 Oct). This is a known
  difference between the arms, stated before the run.

**Prediction (held-out):**
1. Arm R lands near the 28 Oct direct row: call-fields 15/19 ±2, recap 8/16 ±2. The 28 Oct row was a different day
   (gotcha 14), so it is context, not the comparator.
2. Arm N and Arm R differ by at most 2 held-out cases per exam. A bigger gap is attributed to the plumbing
   (thinking on/off, the LangChain wrapper) before the model.
3. n8n's built-in metrics can express call-fields only partly (per-field exact match needs one metric per field or a
   Code node) and cannot express recap's checks (character budgets, groundedness, must-mention / must-not-mention).
   That is written down as "not expressible", not built around. Porting `properties.py` to a Code node would be a new
   grader and is out of scope.

**Cost:** ≈$0.04 per exam per arm ⚠️ modelled on the 28 Oct metered Haiku volumes ($6.72 per 10k call-fields tasks,
$3.85 recap; repo-radar `cost_per_10k.py`, 28 Oct). No GPU.
