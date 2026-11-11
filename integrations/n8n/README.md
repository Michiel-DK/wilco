# Sit a wilco exam in n8n, grade it with wilco

n8n runs the model calls. wilco does the grading: `wilco grade` feeds the answers n8n produced through the same
`run_exam` entry point `wilco run` uses, with the same checks and the same train / held-out split. It makes no model
call and no network call.

## Recipe

1. Import `wilco-exam-ollama.json` into n8n (Workflows, Import from File).
2. In the **Exam** node set `exam` (a single-turn exam folder under `evals/`, e.g. `email-triage`), `wilco_commit`
   (pin the commit of this repo whose `cases.json` and `prompt.md` you mean; the template ships the commit the probe
   used) and `model` (the Ollama model tag, e.g. the exam's champion in `agents/<exam>/agent.yaml`; n8n cannot read it from there).
3. In the **Ollama Chat Model** node pick your Ollama credential (the template names one, `Ollama local`, and holds no secret).
   Leave its options at the template's `temperature: 0`, see below.
4. Run the workflow. Export the result:
   - self-hosted: `n8n execute --id <workflow id> --rawOutput > run.json` (log lines before the JSON are fine), or
   - download the execution from the UI / read it through the n8n API or MCP (`get_workflow_execution`).
5. Grade: `wilco grade email-triage run.json` (exit 0 = the grade ran; the line `email-triage: train p/t · heldout p/t (95% CI lo–hi)` is the result).
   The per-case lines are the runner's own. The result file lands in `results/external/<task>__external__<label>.json`.

`wilco grade` also reads a JSON object `{case_id: text}`, a JSON list of `{case_id, text}`, and a CSV with the header
`case_id,text`, so answers from any other tool grade the same way. `--node NAME` names the n8n node to read (default `Result`).
It refuses (exit 2, one line) an unknown case id, a case with no answer, an unrecognised format, a missing node, and any
exam that is multi-turn, tool-using or judge-graded: those cannot be graded from a list of answers.

A case whose answer does not parse fails: the runner re-asks, and a recorded answer is the same text again.

## Pin temperature 0 on the model node

The template's Ollama node sets one option, `temperature: 0`, and nothing else. Evidence (probes in the private working
repo; n8n 2.46.4 self-hosted in Docker, `gemma4:e2b-it-qat`, email-triage, 28 cases):

- **Node defaults sample.** With the node's options empty, n8n sends no temperature and Ollama uses the model's own
  default: its server log shows `temp = 1.000` on every call. On 3 Nov (Ollama 0.40.14,
  `docs/probes/n8n-two-exams-2026-11-03/step2/RESULTS.md`) that draw gave exactly the verdicts the committed snapshot holds,
  28 of 28 labels equal to `wilco run`. It was one sampled draw: on 7 Nov (Ollama 0.40.15,
  `docs/probes/n8n-e2e-2026-11-07/RESULTS.md`) the same template moved 5 of 28 verdicts against the snapshot.
- **Temperature 0 alone reproduces.** On 11 Nov (Ollama 0.40.15, `docs/probes/n8n-temp0-2026-11-11/RESULTS.md`) the
  template with only `temperature: 0` set ran twice: both runs graded `train 7/8 · heldout 16/20`, 0 of 28 verdicts moved
  against the snapshot, the two runs gave byte-identical answer texts, and every call (56 of 56) ran at `temp = 0.000`.
  A same-day `wilco run` moved 0 of 28 stable cases, so the runtime version did not move verdicts either.
- The earlier one-option arms (3 Nov: `numCtx` 4096 alone moved 5 of 28 labels; `numPredict`, `think` 1 each) did not
  set a temperature and were sampled at `temp = 1.000` (server log), so their moves are not attributable to the option.
  The four options set together (temperature 0, numCtx 4096, numPredict 2048, think on) moved 1 of 28 identically on
  2 of 2 runs; which of the three non-temperature options does it is not established.

So a verdict holds for the exact request settings it was graded with. Keep `temperature: 0`. After changing any node
option, the model or the Ollama version, run the exam again and re-grade.

## What n8n's own evaluation cannot do here

n8n's built-in evaluation metrics (categorization, string similarity, LLM-judged correctness and helpfulness, tools used,
custom expressions; same probe folder, `RESULTS.md`) cover a label match well. They do not express most of this repo's
checks (for example recap's compression ratio, abstention and grounded-number checks); those only exist as the exam's own
grader, which is why the grading happens in `wilco grade`.

## Verified, and what is not

The template ran end to end on 7 Nov (as shipped then, options empty) and twice on 11 Nov (with `temperature: 0`):
`wilco grade` reported 28 answers for `email-triage` each time, with no refusal. It was run on one exam, one model and
one laptop only. For another exam or model, run it once and check that `wilco grade` reports every case before trusting
a number from it.
