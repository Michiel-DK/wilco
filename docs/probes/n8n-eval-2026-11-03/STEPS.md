# n8n evaluation probe — step 1 (cloud trial): our email-triage exam as THEIR evaluation

> **EVIDENCE CELL:** one n8n evaluation run of the 28 email-triage cases, per-case exact-match on `label`,
> diffed by `compare.py` against the answer key and the champion snapshot (gemma4:e2b-it-qat, ollama 0.40.11, 23/28).
> **Not evidence:** the model used on the cloud is a hosted Gemma 4, not the local champion — step 1 measures
> *their evaluation mechanics and tiering*, not our model. Step 2 (self-hosted Docker + local Ollama) is the model proof.

**Prediction, registered 2026-11-03 before any run:** the n8n Categorization metric and our `score_labels`
agree on every case (same pass/fail given the same output); the hosted 26B model passes ≥ 23/28 (the 2B
champion's score); metric-based evaluation on the trial tier is limited to one workflow (docs say "Starter …
single workflow"). Properties-mode exams (recap, reply-draft) will NOT map to a single scalar metric; not attempted here.

**Why the cloud is allowed for this exam:** all 28 cases, held-out included, are already public in
`Michiel-DK/wilco` `evals/email-triage/cases.json` (checked 2026-11-03 against the local clone). Nothing
leaves the laptop that is not on GitHub. Do NOT reuse this reasoning for an exam whose held-out is not in the public cut.

## Files here
- `email-triage-cases.csv` — 28 rows: `case_id, split, input, expected_label` (from `evals/email-triage/cases.json`).
- `system-prompt.txt` — the exam prompt, verbatim copy of `agents/email-triage/prompt.md`.
- `compare.py` — reads the run (API or CSV) and prints the per-case diff. No model calls.

## In the n8n cloud UI (≈30 min)

1. **Data table.** Left nav → *Data tables* → *Create* → import `email-triage-cases.csv`. Keep the column names.
   Add one empty text column `n8n_label` (the run writes the model's label back here).
2. **Credential — pick ONE of three, write down which:**
   - **Anthropic (simplest):** *Credentials* → *Anthropic* type → key = `ANTHROPIC_API_KEY` from this repo's `.env`.
     Chain node = *Anthropic Chat Model*, model `claude-haiku-5-5` (28 short cases ≈ a few cents). This repo already has an
     `anthropic` provider (PR #130), so step 2 can later re-run the same exam through our runner with the same model and
     compare per case — the cleanest "their grader vs ours, same model" test. No Claude email-triage results exist on disk today.
   - **OpenRouter:** *OpenAI* type → base URL `https://openrouter.ai/api/v1`, key = `OPENROUTER_API_KEY`; model
     `google/gemma-4-26b-a4b-it` (no 2B/4B Gemma 4 on OpenRouter; 26B-A4B is the smallest, $0.10/M prompt ≈ a cent).
   - **No key:** n8n's own Gateway credits (trial tiers only), any model it offers; note which one.
   Temperature 0 in every case. The model is NOT the thing under test in step 1.
3. **Workflow, four nodes:**
   1. *Evaluation Trigger* → source = the data table. (One trigger per workflow; this is the limit the docs name.)
   2. *Basic LLM Chain* with the chat-model sub-node from step 2 attached → system message = contents of `system-prompt.txt`;
      user message = `{{ $json.input }}`; temperature 0; max tokens 64.
   3. *Code* node (JavaScript), one line of logic that mirrors our grader's leniency — first JSON object, key `label`,
      trimmed and lower-cased:
      ```js
      const t = $input.first().json.text ?? $input.first().json.output ?? '';
      const m = String(t).match(/\{[\s\S]*?\}/);
      let label = null; try { label = JSON.parse(m[0]).label; } catch (e) {}
      return [{ json: { ...$('Evaluation Trigger').first().json, n8n_label: (label ?? '').trim().toLowerCase() } }];
      ```
   4. *Evaluation* node, operation **Set Outputs** → write `n8n_label` back to the table row; then a second
      *Evaluation* node, operation **Set Metrics** → metric **Categorization** with actual = `{{ $json.n8n_label }}`,
      expected = `{{ $json.expected_label }}`.
      If the Set Metrics step is greyed out on the trial tier, record that (it is a finding) and continue with Set Outputs only.
4. **Run** from the *Evaluations* tab → *Run test*. Wait for 28/28.
5. **Screenshot** the run detail page (per-case rows + the Categorization card). That is the application artefact.
6. **Export** either way:
   - API: *Settings → n8n API → create key*; then from the repo root
     `N8N_HOST=https://<sub>.app.n8n.cloud N8N_API_KEY=... python3 docs/probes/n8n-eval-2026-11-03/compare.py --workflow <workflowId>`
     (workflow id = the hex in the editor URL). If the API returns 403 on `/test-runs`, the key lacks the `testRun` scope
     or the tier lacks the endpoint — note it, use the CSV route.
   - CSV: data table → export → `python3 docs/probes/n8n-eval-2026-11-03/compare.py --csv <file>`.

## What to write in RESULTS.md afterwards (not before)
- the per-case table from `compare.py`, verbatim;
- whether Set Metrics was available on the trial tier, and what the Evaluations tab said about limits;
- which model answered (OpenRouter id or gateway model), tokens if the run page shows them, wall time;
- did the prediction hold (three parts, each yes/no);
- what step 2 (self-hosted, local champion, all cases) still has to show.
