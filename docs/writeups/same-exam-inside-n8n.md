# The same exam inside n8n and in our runner: the grading moves with the exam, the model is a swappable part

**Headline.** We ran our exams, unchanged, inside the n8n workflow tool with Claude Haiku 5.5, and graded what n8n
produced with our own grader (`wilco grade`). Re-graded today from the committed files, it gives the probe's verdict
on **every case of every pass**: 32/32 call-fields and 23/23 recap, three passes each. On the labels exam (email
triage) n8n's Categorization metric is an exact match, the same test as ours; applying that rule beside our grader
gives the same verdict on **28/28** cases (Haiku 27/28). Recap is graded by property checks, which no built-in n8n
metric expresses.

Derivation: the script below feeds n8n's saved answers (3 Nov 2026) through `wilco grade`'s grading function, which
drives the real `run_exam` entry point with a replay adapter, and exits 1 if any figure differs from the probe records.

## Method, in plain words

- **Probe 1 (email triage, labels mode).** One n8n Cloud workflow (trial tier, n8n 2.46.4) took the 28 cases from an
  n8n data table and sent each one to Haiku at temperature 0. A Code node pulled out the label and wrote it back to
  the table, and the Evaluation node scored it with its **Categorization** metric (exact match). We exported the
  labels and graded them with our own key.
- **Probe 2 (call-fields and recap).** We built a second workflow through n8n's MCP server. It fetched each exam's
  `cases.json` and `prompt.md` from the public repo at a pinned commit (byte-identical to the dev tree) and asked
  Haiku. Arm N is n8n. Arm R is the same model through our own runner, in the same evening window. Each arm did
  three passes. A predictions file was committed before the first call.
- **Witness first.** Arm R's own answers, replayed through the grader, give back Arm R's verdicts (32/32, 23/23), and
  one broken answer per exam flips exactly that case (`validate_replay.py`, re-run for this page: `VALID`).

## What we found

```
$ python3 scripts/writeups/same-exam-inside-n8n.py
1. email-triage (labels mode), n8n Cloud, claude-haiku-5-5, 28 cases
   wilco grade on the labels n8n wrote back: 27/28  (train 8/8, held-out 19/20)
   exact-match (n8n Categorization semantics) vs wilco grade, same verdict: 28/28
   misses: ['paid-workshop-invite']

2. same model, two paths: n8n (N) vs our runner (R), held-out, 3 passes
   call-fields: wilco grade reproduces the probe's graded verdicts on n8n's answers: 32/32/32 of 32 per pass
   call-fields: held-out N 16 · 16 · 16 = 48/57   R 14 · 14 · 14 = 42/57   same verdict per case N vs R: 51/57
   recap: wilco grade reproduces the probe's graded verdicts on n8n's answers: 23/23/23 of 23 per pass
   recap: held-out N 7 · 6 · 7 = 20/48   R 4 · 6 · 6 = 16/48   same verdict per case N vs R: 40/48
   recap pass 1, n8n arm, held-out failed checks: {'check_abstention': 2, 'check_compression': 6, 'check_grounded': 1}
   call-fields held-out, 4 passes: A (native API) 16 · 16 · 15 · 14 = 61/76   R 14 · 14 · 14 · 13 = 55/76
   recap held-out pass 1: N vs R differ on 5 cases; unstable over 3 passes: N 7/16, R 6/16

3. local 2B champion, self-hosted n8n, Ollama node at defaults vs our runner (email-triage)
   labels equal: 28/28
   our runner (control): train 7/8, held-out 16/20
   node options matched: labels that differ from the runner: 1 ['paid-workshop-invite']
   node options matched-run2: labels that differ from the runner: 1 ['paid-workshop-invite']
   node options numCtx-only: labels that differ from the runner: 5 ['calendar-accept-notice', 'cold-sales-injection-urgent', 'disk-warning-no-action', 'long-ramble-buried-incident', 'paid-workshop-invite']

all figures match the probe records
```

- **The grading moves with the exam.** Exam files, prompt and key stay put, and the answers can come from anywhere.
  The answers n8n produced grade exactly as the probe graded them.
- **The model is a part you can swap.** Line 3 is the cheap local champion (a 2B model) in a self-hosted n8n,
  Ollama node left at its defaults. It gave the same label as our runner on all 28 email cases.
- **Labels map, properties do not.** n8n's metric list (read from the Evaluation node's definition: correctness and
  helpfulness, both model-judged, string similarity, categorization, tools used, custom expressions) covers a label
  match exactly. Call-fields could be covered with one categorization per field. Recap cannot. Its compression
  budget, quiet-day cap, grounded numbers and must-mention lists fit no built-in metric. Running them inside n8n
  would mean porting the checks to JavaScript, which makes a second grader that would need its own seen-red tests.
  We did not build it.

## What did not hold, or is not evidence

- **n8n's Evaluations tab never showed a run.** The workflow ran from the editor's Execute button and registered as
  28 ordinary executions: no run page, no aggregate, no comparison with a previous run. The tab showed only an
  onboarding screen, with no "Run test" button on the trial. The test-run API had nothing to return. So "the
  evaluation tab agrees case by case" is **not shown**. What is shown is that n8n's per-case Categorization metric is
  the same exact-match test. Only **one** metric value was opened (it read 1, our grader says pass). The other 27
  agree by construction, and ⚠️ n8n's own metric values are not re-derived: they are not on disk.
- **The labels on disk are already extracted.** n8n's Code node pulled the label out of Haiku's reply, and the script
  wraps it back as `{"label": ...}` before grading. Haiku's raw text for probe 1 was not kept.
- **The N-vs-R score gap is about the pipe the call travels, not the grading.** call-fields showed a steady 2-case
  gap (16 vs 14), almost all on one date field's wording (⚠️ the per-field reading is from the probe record, not re-derived). Recap's gap is within noise: 7 and 6 of 16 cases are
  unstable across passes. A third arm that called Anthropic's native API directly landed near n8n on call-fields (61/76
  over four passes vs the runner's 55/76). This is **suggestive, not settled**: that arm itself drifted from 16 to
  14 in one evening. A first reading, that the runner arm was hiding extra reasoning, was **retracted**: both arms
  spend the same tokens.
- **Missed predictions.** The runner was predicted within ±2 of an earlier recap score (8/16, ⚠️ a 28 Oct row, not re-derived here) and scored 4. The arms
  were predicted to differ by ≤ 2 held-out cases per exam, and recap's pass 1 differed by 3 net, 5 flips. The earlier
  row was from a different day and is context only. Hosted comparisons hold only within one window.
- **Haiku is not the champion.** Probes 1–2 measure n8n's mechanics, not our shipped model. Haiku's 27/28 and the
  champion's 23/28 (7/8 + 16/20, section 3) are different models on different serving.
- **Node options move verdicts.** In the champion run, setting the Ollama node's options to match our runner's moved
  1 of 28 labels (2 of 2 runs). `numCtx` 4096 set on its own moved 5, though the runner also runs at 4096 (section 3).
  That was one run per option, and request bodies were not captured, so the mechanism is unknown. A verdict holds for the exact
  request settings it was graded with.

## Re-derive

```
python3 scripts/writeups/same-exam-inside-n8n.py
```

With `requirements.txt` installed: the repo's own `scripts/exam_grade.py` and `sandbox/runner.py`. No API key, no GPU, no network.
It exits 1 if a recomputed figure disagrees with the probe records. That guard was seen red by editing one recorded
figure.

## Sources

- `docs/probes/n8n-eval-2026-11-03/RESULTS.md`, `STEPS.md`, `run1-haiku-labels.csv`, `compare.py`
- `docs/probes/n8n-two-exams-2026-11-03/PREDICTION.md`, `RESULTS.md`, `armN/`, `armR/`, `armA/`, `validate_replay.py`
- `docs/probes/n8n-two-exams-2026-11-03/step2/RESULTS.md`, `n8n-defaults.json`, `control-runner.json`
- `evals/email-triage/`, `evals/call-fields/`, `evals/recap/` (cases and keys) · `scripts/exam_grade.py`
- `integrations/n8n/README.md`
