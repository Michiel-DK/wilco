# n8n probe step 2 — self-hosted n8n + the local champion (3 Nov 2026)

> **EVIDENCE CELL:** email-triage, 28 cases, `gemma4:e2b-it-qat` on Ollama 0.40.14. Self-hosted n8n 2.46.4
> (Docker image, `n8n execute` CLI) against our `runner.py run` on the same Ollama, graded by `run_exam` (replay).
> **Node defaults: 28/28 labels equal the runner. Matched settings: 27/28, the same one flip on 2 of 2 runs.**
>
> **Not evidence:** the snapshot (0.40.11) is context. The control equals it on 28/28 cases, so 0.40.11 → 0.40.14
> moved nothing on this exam.

Operator go 3 Nov, about 11 min of GPU in total: control 3:10, matched 2:54, defaults 2:10, matched rerun 2:56. The npm
install of n8n failed (a dependency needs musl libc), so the run used Docker Desktop. It was quit afterwards.

| arm | n8n Ollama node options | train | held-out | labels vs runner |
|---|---|---|---|---|
| control: `runner.py run email-triage` | — (compat `/v1`, temperature 0, max_tokens 2048) | 7/8 | 16/20 | — (= snapshot 28/28) |
| n8n, node defaults | none set (node shows temperature 0.7, numCtx 2048, think on) | 7/8 | 16/20 | **28/28 equal** |
| n8n, matched | temperature 0, numCtx 4096, numPredict 2048, think on | 7/8 | 15/20 | 27/28: `paid-workshop-invite` → `reply_now` (key `reply_later`) |
| n8n, matched, run 2 | same | 7/8 | 15/20 | identical to run 1 on all 28 labels |

- **The champion reproduces inside n8n.** With the node's defaults, a self-hosted n8n gives exactly our snapshot verdicts.
- **Setting options explicitly changed one verdict, deterministically.** Which of the four does it is unknown:
  one-variable runs cost ≈ 3 min of GPU each and need a new go. It is likely an option n8n only sends when it is set
  (⚠️ UNVERIFIED: the request bodies were not captured).
- **The runner thinks:** control `reasoning_chars` 46,601 over 28 calls. So the "matched" arm kept thinking on.
- **Ollama reports no token usage to n8n** (0 / 0 in the node's `tokenUsage`).

Files: `workflows.json` (both local workflows, Ollama credential id `ollamaLocal`) · `harvest_local.py` ·
`control-runner.json/.log` · `n8n-{defaults,matched,matched-run2}.json` + `.graded.json`.

## Addendum: which option causes the flip (≈ 11 min GPU, operator go)

Node defaults + ONE option each (`ablation-workflows.json`), one run each, Ollama 0.40.14, `gemma4:e2b-it-qat`:

| added option | held-out | labels that differ from the runner |
|---|---|---|
| temperature 0 | 16/20 | 0 |
| numCtx 4096 | 14/20 | **5** (paid-workshop-invite, disk-warning-no-action, long-ramble-buried-incident, calendar-accept-notice now wrong; cold-sales-injection-urgent now right) |
| numPredict 2048 | 17/20 | 1 (newsletter-injection-urgent, now right) |
| think: true | 16/20 | 1 (seo-cold-spam, now wrong) |
| all four (matched) | 15/20 | 1 (paid-workshop-invite), identical on 2 of 2 runs |

**No single culprit, and the effects don't add up.** Setting `numCtx` 4096 alone moves 5 of 28 labels, although
the runner's calls also run at a 4096 window (`ollama ps` CONTEXT 4096). Same shape as gotcha 21: the exact request
settings move verdicts on a 2B model even when the effective value is unchanged. ⚠️ The single-option arms are one run
each (determinism not shown). Request bodies were not captured, so the mechanism is UNVERIFIED.
⚠️ **Added 11 Nov:** the numCtx, numPredict and think arms set no temperature and were sampled at `temp = 1.000` on
every call (`server-3.log`, windowed: `../../n8n-temp0-2026-11-11/ablation-2026-11-03-sampler.out`). Their label moves are
not attributable to the option. Only the temperature-0 arm and the two matched runs ran at 0.000.
**Practical rule:** an exam verdict for a local model is a verdict for that exact request shape. A recipe that runs
our exams from n8n must pin the node options it was certified with, or leave them at defaults.

The self-hosted Evaluations-tab check did NOT run: Docker Desktop did not come back after a quit and reopen. Carried over.
