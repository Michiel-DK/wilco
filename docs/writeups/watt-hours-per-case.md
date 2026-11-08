# Watt-hours per case: what a small local model draws to sit an exam

**0.031 to 0.169 Wh per case, 80.8 Wh for 846 case-runs (0.0955 Wh per case-run).**

That is metered package power (CPU + GPU + Neural Engine) on one laptop, an M1 Pro MacBook Pro, with the idle draw
subtracted. Nine exams were sat three times each, one after another, during the 1 November re-snapshot. Each figure
is the energy the chip drew while the model answered the exam's cases, divided by the number of cases. The cheapest
task is expense categorisation on a 2B model. The dearest is a meeting recap on a 4B model. The gap is 5.5×.

## Method, in plain words

1. The operator started macOS `powermetrics` under sudo, sampling CPU, GPU and ANE power every 2 seconds, then left
   the laptop alone while the scheduler re-took every exam's snapshot. A snapshot is three fresh model loads at
   temperature 0 over every case in the exam.
2. Each load already records when it started and how long it ran (`load_resources.wall_s` in the snapshot). For
   each load, `scripts/energy_report.py` integrates the power samples that overlap that window. A sample that only
   partly overlaps counts in proportion. A window with less than 90% sample coverage is refused. The worst window
   here had 99.4%.
3. Idle draw was measured separately: a median of 72 mW over a quiet hour with nothing running. It is subtracted
   for the length of each window. Against 24–30 W under load that removes about 0.3%, so gross and net barely differ.
4. Per exam, the median of the three loads is reported, with the min–max beside it.

| exam | model | cases | Wh per case (min–max of 3 loads) | J per 1k output tokens | avg package W |
|---|---|---|---|---|---|
| expense-categorization | Gemma 4 E2B (QAT) | 22 | 0.031 (0.031–0.031) | 409 | 29.4 |
| email-triage | Gemma 4 E2B (QAT) | 28 | 0.047 (0.046–0.047) | 411 | 30.3 |
| task-intake | Gemma 4 E2B (QAT) | 50 | 0.050 (0.050–0.050) | 409 | 29.4 |
| reply-draft | Gemma 4 E2B (QAT) | 25 | 0.068 (0.068–0.069) | 402 | 30.1 |
| crm-followup | Gemma 4 E2B, 16k window | 47 | 0.085 (0.085–0.085) | 535 | 26.9 |
| call-fields | Gemma 4 E4B, 16k window | 32 | 0.131 (0.131–0.131) | 749 | 23.5 |
| recap-en | Gemma 4 E4B (QAT) | 23 | 0.153 (0.153–0.154) | 625 | 24.2 |
| transcript-en | Gemma 4 E4B, 16k window | 32 | 0.161 (0.160–0.161) | 712 | 23.5 |
| recap | Gemma 4 E4B (QAT) | 23 | 0.169 (0.168–0.170) | 731 | 24.2 |

## What the numbers say

- **It repeats.** Load-to-load spread is at most 0.002 Wh per case on every exam.
- **Model size sets the cost per token, and input length sets the cost per case.** The 2B models run hotter (about
  30 W) but finish sooner: 402–535 J per 1k output tokens. The 4B models draw less (about 24 W) and take longer per
  token: 625–749 J per 1k. The three long-input exams (call-fields, transcript-en, recap) cost the most per case,
  0.13–0.17 Wh.
- **For scale:** 10,000 tasks in this mix comes to about 0.96 kWh of package energy. That figure is *modelled on this
  run's mix*. A real workload has a different mix and will land somewhere else.

## What this is not

- **Not wall-socket energy.** Package power leaves out the display, DRAM, SSD and charger losses. These figures are a
  floor on what a wall meter would read.
- **Hosted models: not metered.** We cannot meter someone else's data centre, and no provider publishes per-request
  energy for API calls or for these tasks. The figures that do exist cover something else. Google reports a median
  Gemini Apps text prompt at 0.24 Wh, measured across the full stack: accelerators, host CPU and DRAM, idle capacity
  and data-centre overhead (arXiv 2508.15734). OpenAI's figure is about 0.34 Wh per average ChatGPT query, given in a
  blog post with no method. Those are consumer prompts under a wider scope than ours. Dividing one by the other would
  give a ratio between two different measurements, so this page does not report one.
- **One night, one laptop, serial.** Nothing here covers concurrency, another chip, or a server GPU.
- **The later windows were dropped.** After about 18:50 that evening, coding agents shared the laptop with other GPU
  jobs, so those windows are upper bounds and are not reported. That rules out the transcript-asr exam's snapshot,
  taken at 20:45. Its exclusion follows from its timestamp. The probe does not name it.
- ⚠️ **Not re-derived from the repo: the per-exam Wh, the J per 1k output tokens, the window coverage and the 72 mW
  idle draw.** All four come from the raw `powermetrics` capture and the per-load results files, and neither is
  committed. The script reads them from the probe's rows but does not recompute them. What the repo can re-derive is
  everything after the integration step, plus one independent check described below.
- **The last digit differs from the probe.** The probe sums 27 unrounded loads and gets 0.095 Wh per case-run and
  0.95 kWh per 10k. The script below sums the rounded medians and gets 0.0955 and 0.96. This page quotes the script.

## Re-derive

```sh
python3 scripts/writeups/watt-hours-per-case.py
```

It reads the committed per-exam rows and each exam's `snapshot.json`. It checks that the case counts match, recomputes
the range and totals, and does one independent check: Wh per case × cases × 3600 ÷ the snapshot's median wall time
should give back each row's average watts. If the energy rows had been integrated over the wrong window, this check
would show it. No model, GPU or key is needed. Output on 6 November 2026:

```
exam                       n  Wh/case  table W  snap W
expense-categorization    22    0.031     29.4    29.3
email-triage              28    0.047     30.3    30.5
task-intake               50    0.050     29.4    29.3
reply-draft               25    0.068     30.1    30.0
crm-followup              47    0.085     26.9    27.0
call-fields               32    0.131     23.5    23.5
recap-en                  23    0.153     24.2    24.2
transcript-en             32    0.161     23.5    23.6
recap                     23    0.169     24.2    24.1

exams: 9 · cases: 282 · case-runs: 846
excluded: transcript-asr (snapshot taken after 18:50 on 1 Nov, when coding agents shared the laptop)
range: 0.031 Wh/case (expense-categorization) to 0.169 Wh/case (recap), 5.5x
max load-to-load spread: 0.002 Wh/case
total: 80.8 Wh over 846 case-runs = 0.0955 Wh per case-run
10,000 tasks of this mix: 0.96 kWh (modelled on this mix)
avg-W cross-check vs snapshot wall times: worst row off by 0.7%
from the rows, not recomputed: min window coverage 0.994
from the rows, not recomputed: e2b J per 1k output tokens 402–535
from the rows, not recomputed: e4b J per 1k output tokens 625–749
```

## Sources

- `docs/probes/energy-resnapshot-2026-11-01/RESULTS.md`: the probe, its evidence cell and per-exam rows
- `scripts/energy_report.py`: the integration (capture × window → Wh, idle subtraction, coverage gate)
- `evals/*/snapshot.json`: case counts and per-load wall times of the 1 November re-snapshot
- `scripts/writeups/watt-hours-per-case.py`: the re-derive script above
