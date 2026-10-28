# wilco

![last commit](https://img.shields.io/github/last-commit/Michiel-DK/wilco)
![python](https://img.shields.io/badge/python-3.10%2B-3776AB)
![eval cases](https://img.shields.io/badge/eval%20cases-282%20%28171%20held--out%29-2b8a7e)
![LLM judge](https://img.shields.io/badge/LLM%20judge-none%2C%20deterministic%20scoring-2b8a7e)
![tests](https://github.com/Michiel-DK/wilco/actions/workflows/tests.yml/badge.svg)

**wilco grades a model on your task's own exam and tells you the day it stops passing.**
Write the cases, let every candidate sit them, `pick` takes the cheapest that clears the bar, `check` re-sits the exam per case. The task the exam guarantees, drafts delivered into your inbox or CRM, is at [roger3000.com/wilco](https://roger3000.com/wilco).

| step | command |
|---|---|
| 1. write the exam | `wilco new <task> --mode labels` · `wilco validate <task>` |
| 2. every candidate sits it | `wilco diff <task> --models ollama/<model>,openrouter/<id> --allow-tier-breach` |
| 3. the cheapest that passes wins | `wilco pick <task>` |
| 3b. adopt the winner | `wilco adopt <task> <provider/model>` (writes `provider:` + `model:` in `agents/<task>/agent.yaml`, then snapshots it: 3 loads at temperature 0); on a `tier: local` exam a hosted winner is refused unless `--allow-tier-breach`, and then gets no snapshot, only the same-day rerun |
| 4. know the day it stops passing | `wilco check <task>` (exit 1 if a stable case moved) |
| then: run it | `wilco live <task> --input "..."` (through `routes.yaml`) |

`wilco <command> --help` lists each command's options; `run`, `diff` and `check` keep their research flags behind `--help-advanced`.

Results for the eight example tasks: [**roger3000.com/wilco**](https://roger3000.com/wilco). No developer, or no time to
write the exam? Send us your task: [**roger3000.com/wilco/pricing**](https://roger3000.com/wilco/pricing).

## Five minutes, from clone to a scored table

```
git clone https://github.com/Michiel-DK/wilco && cd wilco
pip install -e .                                                     # the `wilco` command; requests, PyYAML
wilco list                                                           # the eight example tasks, their champions
wilco run email-triage --provider stub --model stub
```

The exams live in the clone, not in the package, so install it editable from the clone. Without installing anything
but `pip install -r requirements.txt`, every `wilco <command>` is `python3 wilco_cli.py <command>`; the shim runs
`scripts/exam_new.py`, `scripts/exam_validate.py`, `scripts/pick.py` and `sandbox/runner.py` unchanged.

The stub needs no network, no key and no model. It answers `reply_later` to every email, so it fails most cases. What
you get is the shape: one line per case, train and held-out scored apart, a result file under `results/`. Then the
pick rule over the committed 27 Sep files, also offline:

```
wilco pick crm-followup docs/probes/matrix-2026-09-27/results/crm-followup__*.json
```

It prints `pick: openrouter/deepseek/deepseek-v4-pro-0813`. That folder holds the eleven hosted runs only; the local
champion's snapshot covers a larger case set (47 cases against the matrix's 38 today), and `pick` refuses to compare
unequal case sets rather than intersect them. (`pick` over the stub's own result prints `NONE`: the stub has no price,
and an unknown cost is never counted as 0.)

**A hosted model.** Put your key in the environment as `OPENROUTER_API_KEY` (nothing is read from a file) and run the same
command:

```
wilco run email-triage --provider openrouter --model <id> --allow-tier-breach
```

The example exams are `tier: local`, so a hosted provider needs `--allow-tier-breach` (see the tier rule below).

**A local model.** Install [Ollama](https://ollama.com), then build the crm-followup champion's 16k-window variant
and run its exam:

```
./models/models.sh gemma4-e2b-ctx16k   # pulls the base unless on disk with the measured weights; --dry-run: plan
wilco run crm-followup --provider ollama --model gemma4-e2b-ctx16k
```

`models.sh` with no name builds all three in `models/`. It checks each base tag's weights against the ones the scores
were taken on and refuses a tag that has moved: on 23 Oct `gemma4:e4b` had, so the non-champion
`gemma4-e4b-ctx16k-plain` is refused unless you pass `--allow-drift` (and then its scores are a new measurement).

## How it works, in four steps

**1. Name the tasks you already send to a model.** Triage, extraction, drafting, summaries. The only requirement is
that a person can say, case by case, whether the answer was right. If nobody can check it, this suite will not
score it and says so. How to write one: [`docs/write-an-exam.md`](docs/write-an-exam.md).

**2. Write down what a correct answer looks like.** Twenty to fifty cases per task, each with its checks: the label,
the fields, the facts that must appear, the tools that must be called. Part of them is held out (here 171 of 282) and never
tuned on.
Scoring is deterministic. No model grades another model's answer, anywhere.

**3. The cheapest model that passes wins.** Every candidate sits the exam. Models below the bar drop out. The bar is
the best score any model reached, or one case from it. The cheapest model left takes the job, and its score is
committed as the snapshot that every later change is checked against.

| CRM follow-up over tool calls, 18 held-out cases, 27 Sep 2026 | passed | $ per 10k tasks (2 Oct ledger) | runs on |
|---|---|---|---|
| Gemma 4 2B (local champion, 3-load snapshot) | 15 of 18 | ≈0 | your laptop |
| DeepSeek V4 Pro | 15 of 18 | 43 | GPU node |
| Gemma 4 31B | 14 of 18 | 5.41 | one 48 GB card |
| GPT-5.6-Sol | 14 of 18 | 127 | vendor API |

Four of twelve candidates: the local champion and the eleven hosted runs in `docs/probes/matrix-2026-09-27/results/`. The best
held-out score, Grok 4.6's 16 of 18, is not in the table. The dollar column is the 2 Oct ledger; `pick`
prints every row and prices it from `pricing/prices.json`, the 27 Sep list prices, so its figures differ.

**4. Know the day it stops passing.** Every model release, runtime bump or price change re-sits the exam per case, and
the report lists what moved in both directions. On 2 Oct an Ollama upgrade moved 1 of 220 cases, none held-out
(`docs/probes/l0-resnapshot-2026-10-02/RESULTS.md`).

### What the gate can and cannot promise

- **The stable-case gate is for local models.** A snapshot (`run <task> --snapshot`) is three fresh loads at
  temperature 0; a case counts only if all three agree. `check` re-sits the exam and fails on any stable case that moved,
  in either direction. It refuses to compare across a changed runtime version, server settings or case set.
- **Hosted models get no stable-case gate.** Temperature 0 does not reproduce on hosted APIs (finding 2 below). A hosted
  score is one run; compare hosted models only within one day, rerun on the same day, and read the cases that flipped
  between the two result files. `pick` says this on every hosted row.
- **The tier label is enforced.** Every task's `agent.yaml` carries `tier: local | eu | frontier` (where its data may go).
  `run`, `diff` and `live` refuse a provider above it (exit 2, before any request) unless `--allow-tier-breach` is
  passed, and the result file then says `tier_breach: true`.
- **The window is a precondition.** Ollama's OpenAI-compatible endpoint runs a model at its Modelfile window (4096 when
  none is set) and ignores a window sent in the request; past it, the front of the prompt (the system prompt first) is
  cut and the model answers anyway. Before every Ollama call the prompt is estimated (characters / 4) against the
  model's window (`num_ctx` from `ollama show`); an over-window case is refused rather than silently truncated: raise
  the window with `PARAMETER num_ctx 16384` in a Modelfile (`models/` has the three this repo uses), or pass
  `--allow-truncation`. A verdict on a long input is a verdict about the window until the window is stated.

Providers live in `sandbox/router.py` `PROVIDERS`: any OpenAI-compatible endpoint is one line there (a base URL and the
env var holding its key). Hosted providers need their key in the environment; nothing is read from a file.

## Where the model runs

| tier | what it means | examples here |
|---|---|---|
| your laptop | small enough for a 16 GB machine; nothing leaves it; ≈$0 per task | Gemma 4 2B / 4B, Qwen3 8B |
| your own cloud | open weights on a GPU you rent or own; data stays in your account | Gemma 4 26B / 31B, Qwen3 14B, Mistral Small 24B, gpt-oss-20b; Kimi K3, GLM-5.3, DeepSeek V4 on a node |
| vendor API | closed weights, pay per call | GPT-5.6-Sol, GPT-5.4-mini, Grok 4.6 |

The score in a table was taken on the runtime the row names. A build on your own card re-sits the exam before the
row is claimed for it.

## What we measured (October 2026)

1. **A 2B–4B model on a laptop holds every short decision task and loses only long summaries.** Level with the hosted
   flagships on email triage, expense fields, reply drafts, the CRM brief over tool calls and the digest; one case
   behind on CRM field write-back, four behind on long call summaries. Local ≈ $0, open weights hosted $0.23–$5.41,
   the vendor flagship $5–$127 per 10k tasks (metered, 27 Sep matrix, 2 Oct ledger).
2. **Temperature zero is not determinism on hosted APIs.** GLM-5.3: 10/13 call summaries on one run, 6/13 across six
   same-day runs. The local champions give the same verdict on every case across all three loads. Reproduce from the committed files, no model
   needed: `python3 docs/probes/pass3-column-2026-09-28/pass_k.py`.
3. **Fine-tuning the local champion did not ship.** When a small model almost passes, it can be fine-tuned on the
   task's training cases and sit the same exam; if any held-out case that used to pass now fails, the new version is
   refused, even when the total went up. Four CRM fine-tunes were refused, the cause named: an unmasked loss that was
   95% tool payload, then a per-step cut that taught a "call again" reflex. A no-training "thinking off" switch was
   refused too. One request-intake adapter held within a case (−87% output tokens, 4.2× faster, held-out 19 → 18 of
   20, one pass) and was not promoted. Write-ups: `docs/probes/i0-*`, `docs/probes/i2*`. This is a measured finding,
   not a step in the workflow.
4. **Serving choices move verdicts, and the instrument now records them.** Same weights at two 4-bit packagings: the
   post-hoc quant beat the maker's QAT tag 6 up / 0 down on the CRM brief, because the QAT tag writes the right answer as
   prose and never emits the final-answer form (`docs/probes/e31-quantisation-2026-09-09/`). An 8-bit tag at a 16k window
   ran 14× slower per case on a 16 GB laptop and was killed. A quantised K/V cache (`q8_0`) moved three stable verdicts on
   long call summaries, and `q4_0` failed held-out cases on both long exams; the snapshot could not see the server setting,
   so it now stamps cache type and flash attention and refuses a mismatch (`docs/probes/m7-kv-cache-2026-10-08/`). The one
   adapter that held its score did so by removing the thinking channel: −85% output tokens, 4× faster
   (`docs/probes/i0-mlx-lora-2026-09-18/`). GPU cost figures are modelled, never measured, and say so
   (`docs/probes/l3-own-gpu-cost-2026-10-02/`).

The chart for all eight tasks, score against cost per 10k, is on the [results site](https://roger3000.com/wilco). Three
times the instrument itself was wrong, and what fixed it: [`docs/post-mortems/`](docs/post-mortems/).

## Tests

```
./scripts/test.sh       # the gate: every test file, one process each, exit code captured; offline
```

`pytest` is blind to this repo's `check()`-style test files: they record a failure in a list and return it as the
exit code, so pytest reports "passed" by construction (post-mortem 3). CI runs the gate, not pytest.

## Scoreboard

Held-out score of the committed champion per task, from `evals/<agent>/snapshot.json` at the 2026-10-28 repo state;
generated by the snapshot script, never typed.

| agent | exam mode | champion | held-out | snapshot date | note |
|---|---|---|---|---|---|
| task-intake | labels | gemma4:e2b-it-qat | 0.955 (21/22) | 2026-10-10 | seventh agent: routes a typed request to the right specialist, or refuses |
| reply-draft | properties | gemma4:e2b-it-qat | 0.944 (17/18) | 2026-10-23 | saturated, useless for ranking |
| expense-categorization | fields | gemma4:e2b-it-qat | 0.938 (15/16) | 2026-10-22 |  |
| crm-followup | trajectory | gemma4-e2b-ctx16k | 0.880 (22/25) | 2026-10-23 | production-size payloads; 4 multi-turn cases; champion swapped 4B to 2B (PR #60) |
| recap | properties | gemma4:e4b-it-qat | 0.812 (13/16) | 2026-10-22 | the hardest exam, on purpose |
| email-triage | labels | gemma4:e2b-it-qat | 0.800 (16/20) | 2026-10-22 |  |
| call-fields | fields | gemma4-e4b-ctx16k | 0.737 (14/19) | 2026-10-10 |  |
| transcript-en | properties | gemma4-e4b-ctx16k | 0.579 (11/19) | 2026-10-22 | English call transcripts incl. a 10-case long-call band (12k-33k chars); local 4B ties Kimi-K3 2/6 on it |
| recap-en | properties | gemma4:e4b-it-qat | — | pending | the recap exam in English: same 23 cases, keys and char budgets (PR #131); first 3-load snapshot pending |

## Where to look

| folder | what is in it |
|---|---|
| [`evals/`](evals/) | one exam per task: `cases.json` (train / held-out), deterministic checks, the committed 3-load snapshot |
| [`agents/`](agents/) | one folder per task: a prompt, a tool list, one model line, the tier; deliberately boring |
| [`sandbox/`](sandbox/) | `runner.py` (run · check · diff · snapshot · live), the provider router, the tests |
| [`wilco_cli.py`](wilco_cli.py) | the `wilco` command (`pyproject.toml`, PyPI name `wilco-exams`): a shim, every command runs the script named in its `--help` |
| [`scripts/`](scripts/) | `exam_new.py`, `exam_validate.py`, `pick.py`; `pricing/prices.json` holds the dated list prices `pick` reads |
| [`models/`](models/) | the three 16k-window Modelfiles (two champions, one comparison arm) and `models.sh` |
| [`docs/probes/`](docs/probes/) | the experiments behind every number; each `RESULTS.md` opens with the one cell that carries the verdict |
| [`docs/post-mortems/`](docs/post-mortems/) | three times the instrument was wrong: belief, probe, fix |

## Status and limits

**Status (2026-10-28):** 8 tasks (the weekly recap also ships in English as `recap-en`: same cases, same keys; its first snapshot is pending), 282 committed cases (111 train / 171 held-out),
59 test files; judge-free and deterministic. Every snapshot is three fresh loads at temperature 0 with a
runtime stamp, so a runtime bump or a model swap re-sits the exam per case. Limits, stated plainly:

- Held-out sets are 16–25 cases per task, so the suite ranks bad models out but cannot separate two good ones (`pick`
  calls a one-case gap noise).
- Every case input is hand-authored. Getting real inputs in is the active work.
- Train scores sit BELOW held-out on crm-followup and recap, by design, not by selection: the train split carries the
  bait, decoy, outage and long-day cases the checks are iterated against (see the failing ids in `evals/*/snapshot.json`);
  held-out is the realistic distribution and is never tuned on. Read the held-out column; the train column is the forcing set.
- Hosted scores have no stable-case gate (above).
- The window estimate is characters / 4, which runs slightly low, and does not count the generation budget.
- One declared hole: on the four quiet-day recap cases a content-free "nothing important today" passes every check;
  two attempts to key it (hand-written and rule-derived word lists) failed honest recaps and were closed on the record
  (`docs/probes/calif-empty-answer-2026-10-21/RESULTS.md`).

> **Public snapshot (repo state 2026-10-28, published 2026-10-28).** A curated, sanitized cut of a private
> working repo: the tasks, the exams, the runner and the write-ups are the real working tree. Kept private on purpose:
> the per-lane build ledger, the build-harness submodule, the sprint queue, lane briefs, competitor notes, per-probe
> result archives, a task corpus mined from private production repos, and anything naming a client. Some links in the
> older write-up therefore point at files that are not in this snapshot. History: the August write-up that argued
> the case before the October matrix, [`docs/eval-suite-is-the-asset.md`](docs/eval-suite-is-the-asset.md), stays
> for the record; its numbers are from the 3 Sep repo state. A client's exam is never published; the
> exams here are demo exams on synthetic cases, and because their held-out cases are public, no routing decision is
> taken on them alone once a model could have seen them.
