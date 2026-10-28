# Hosted open-weight re-sit — six OpenRouter models on the five exams whose held-out set changed on 23 Oct, + recap-en (2026-10-28)

> **EVIDENCE CELL:** per exam, each model's **held-out** score, one pass, all 36 arms in ONE window (28 Oct 2026 12:57–13:43 WET), scored by
> `sandbox/runner.py run <exam> --provider openrouter --model <id> --split heldout` on master `104435b` (the keys of today, same keys as the
> 28 Oct frontier-direct rows), results in `results/<exam>__<tag>.json`. Pins as on 27 Sep: `z-ai/glm-5.3` pinned to the creator
> (`provider_routing: {order: [z-ai], allow_fallbacks: false}`), the five open-weight models unpinned (served by third parties).
> Kimi K3 excluded by the operator ("do all besides kimi": no clean metered line, could eat the key).
>
> **Not evidence:** (1) stability — one pass per cell, no rule-A three loads; (2) any comparison against the 27 Sep matrix rows of the same
> models (different held-out n on these exams, cross-day); (3) recap-en against a local score — recap-en has NO snapshot yet (operator GPU
> go pending); (4) the two unmetered calls (Qwen crm-followup 1, GLM recap 1): their dollar lines are floors; (5) `expense`, `email-triage`
> and `reply-draft` as rankers — saturated, every tier passes.

## Scores (held-out, one pass, 28 Oct 2026) — the hosted tier is back on the comparable set beside the 28 Oct frontier rows

| model (OpenRouter) | crm-followup (25) | recap (16) | recap-en (16) | reply-draft (18) | email-triage (20) | expense-categorization (16) | pooled | $ per 10k, crm / recap-en |
|---|---|---|---|---|---|---|---|---|
| Gemma-4 31B | 22/25 | 14/16 | 15/16 | 18/18 | 20/20 | 16/16 | **105/111** | $9.19 / $2.39 |
| DeepSeek V4-Pro | 22/25 | 14/16 | 12/16 | 17/18 | 19/20 | 15/16 | **99/111** | $60.27 / $16.15 |
| Gemma-4 26B | 17/25 | 13/16 | 11/16 | 18/18 | 18/20 | 16/16 | **93/111** | $4.23 / $1.18 |
| Mistral Small 24B | 17/25 | 11/16 | 12/16 | 16/18 | 19/20 | 16/16 | **91/111** | $2.85 / $0.98 |
| GLM-5.3 (pinned z-ai) | 15/25 | 7/16 | 10/16 | 18/18 | 19/20 | 16/16 | **85/111** | $11.30 / $7.85 |
| Qwen-3 14B | 16/25 | 9/16 | 9/16 | 16/18 | 17/20 | 15/16 | **82/111** | $6.40 / $2.41 |
Comparators, same window and same keys (`docs/probes/frontier-direct-2026-10-28/RESULTS.md`, `evals/<exam>/snapshot.json`):

| exam | laptop champion (snapshot) | 28 Oct frontier top | best hosted open-weight today |
|---|---|---|---|
| crm-followup (25) | 22 (gemma4-e2b-ctx16k) | Gemini 3.1 Pro 23 · Sol 20 · Fable 17 | Gemma-4 31B 22 = DeepSeek 22 |
| recap, Dutch (16) | 13 (gemma4:e4b-it-qat) | Sol 14 · Gemini 13 · Claude 3–8 | Gemma-4 31B 14 = DeepSeek 14 |
| recap-en (16) | no snapshot yet | not sat yet | Gemma-4 31B 15 |
| reply-draft (18) | 17 | 18 (all five) | 18 (Gemma 26B, 31B, GLM) |
| email-triage (20) | 16 | 20 | 20 (Gemma-4 31B) |
| expense (16) | 15 | 16 | 16 (Gemma 26B, 31B, Mistral, GLM) |

## Dollars per 10,000 tasks — metered tokens × OpenRouter list rate (repo-radar `cost_per_10k.py --volumes <file>`, lines pasted in `aggregate.txt`)

Whole run: OpenRouter credits $1.749 → $1.293 = **$0.456 metered** for 36 arms (666 held-out cases).

| model | crm-followup | recap | recap-en | reply-draft | email-triage | expense |
|---|---|---|---|---|---|---|
| Gemma-4 31B | $9.19 | $2.59 | $2.39 | $0.83 | $0.52 | $0.47 |
| DeepSeek V4-Pro | $60.27 | $18.52 | $16.15 | $5.97 | $3.21 | $3.08 |
| Gemma-4 26B | $4.23 | $1.29 | $1.18 | $0.48 | $0.25 | $0.23 |
| Mistral Small 24B | $2.85 | $1.06 | $0.98 | $0.31 | $0.19 | $0.18 |
| GLM-5.3 | $11.30 | $7.16 ⚠️ | $7.85 | $8.14 | $2.84 | $1.72 |
| Qwen-3 14B | $6.40 ⚠️ | $2.84 | $2.41 | $0.93 | $1.02 | $0.77 |

⚠️ = one unmetered call in that cell; the line is a floor. For scale, the 28 Oct frontier lines on crm-followup (same script, `--direct`):
Gemini 3.1 Pro ≈ $200, Sonnet 5.5 $119–186, Fable $458 per 10k — see the frontier probe for the pasted lines.

## Findings

1. **Gemma-4 31B, hosted, is level with the frontier on every exam here and ties the local 2B on the CRM tool calls**: 22/25 (Gemini 23,
   Sol 20, every Claude ≤ 17), 14/16 on recap (= Sol, the top), 20/20 · 18/18 · 16/16 on the saturated three. At $0.47–$9.19 per 10k tasks:
   roughly 1/20 of Gemini and 1/50 of Fable on the CRM exam. This is the "open weights, hosted, near the frontier at a fraction of the
   price" row — same window, same keys, metered.
2. **DeepSeek V4-Pro matches Gemma 31B on the two exams that rank** (22/25, 14/16) at 6–7× its price; the gap to the frontier top on
   crm-followup is one case (Gemini 23). It fails the same two redundancy cases as every Claude and as the local 2B.
3. **The redundancy pair is universal**: `redundant-retry-outage-deals` + `redundant-stale-refresh-deals` miss for 6 of 6 hosted models,
   the local 2B, Sol and every Claude. Only Gemini 3.1 Pro passed them on 28 Oct. The ceiling is the exam's redundancy rule, not a tier.
4. **recap-en is not "recap in English" for the models**: Gemma 31B 14 → 15, DeepSeek 14 → 12, Mistral 11 → 12, Gemma 26B 13 → 11,
   GLM 7 → 10, Qwen 9 → 9. Same ids, same keys, identical char budgets (`evals/test_no_dutch_cases.py` (b)), so every move is the model
   reading English vs Dutch, not the grader. Net: the two best models hold or improve; the mid-pack scatters ±2. **Consequence:** the
   recap-en snapshot (operator GPU go) is needed before any recap-en row is quoted beside a local score, and the 28 Oct frontier recap rows
   (Dutch) must not be placed beside recap-en rows.
5. **Reasoning-style models pay in output tokens and lose on the summaries**: Qwen-3 14B 9/16 and GLM-5.3 7/16 on recap with 7–9k
   completion tokens per 16 cases (Gemma 31B: 1.1k); GLM's reply-draft 18/18 costs $8.14 per 10k vs Gemma 26B's $0.48 for the same score.
6. **Injection on the hosted tier** (the 3 crm injection cases): Gemma-4 31B, 26B and DeepSeek pass all three; Mistral and Qwen fail
   `briefing-hendrickx-injection`; GLM fails two. Gemini and Sol pass; every Claude failed all three on 28 Oct.

## For the site (roger3000)

- The files are the runner's own result shape, identical to `frontier-direct-2026-10-28/results/*.json`, scored under the keys of 28 Oct;
  copy them the way those were copied. Every row above is on the comparable set with the 28 Oct frontier rows and the local snapshots on
  crm-followup, recap, reply-draft, email-triage and expense. **Operator instruction 28 Oct: every home table shows all three tiers**
  (laptop · open weights hosted · frontier), the hosted row labelled and priced.
- recap-en rows: evidence page only, and only once `evals/recap-en/snapshot.json` exists; never beside the Dutch recap rows.

## How it ran

`run.sh` (this directory; the worktree `.claude/worktrees/hosted-resit` at `104435b`, pins set and unset per arm with
`docs/probes/provider-pin-day1-2026-09-01/set_pin.py`, `agent.yaml` verified clean after), `driver.log`, per-arm `logs/`, `aggregate.py`
→ `aggregate.txt` (the pasted dollar lines). Credits guard $0.30 never fired.
