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
   Leave the node's options empty, see below.
4. Run the workflow. Export the result:
   - self-hosted: `n8n execute --id <workflow id> --rawOutput > run.json` (log lines before the JSON are fine), or
   - download the execution from the UI / read it through the n8n API or MCP (`get_workflow_execution`).
5. Grade: `wilco grade email-triage run.json` (exit 0 = the grade ran; the line `email-triage: train p/t · heldout p/t` is the result).
   The per-case lines are the runner's own. The result file lands in `results/external/<task>__external__<label>.json`.

`wilco grade` also reads a JSON object `{case_id: text}`, a JSON list of `{case_id, text}`, and a CSV with the header
`case_id,text`, so answers from any other tool grade the same way. `--node NAME` names the n8n node to read (default `Result`).
It refuses (exit 2, one line) an unknown case id, a case with no answer, an unrecognised format, a missing node, and any
exam that is multi-turn, tool-using or judge-graded: those cannot be graded from a list of answers.

A case whose answer does not parse fails: the runner re-asks, and a recorded answer is the same text again.

## Leave the model node at its defaults, or pin what you certified

The template's Ollama node has no options set on purpose. Evidence (probe `docs/probes/n8n-two-exams-2026-11-03/step2/RESULTS.md`
in the private working repo; n8n 2.46.4 self-hosted in Docker, Ollama 0.40.14, `gemma4:e2b-it-qat`, email-triage, 3 Nov 2026):

- With the node's defaults, n8n gave exactly the verdicts the committed snapshot holds: 28 of 28 labels equal to `wilco run`.
- Setting node options changed verdicts. `numCtx` 4096 alone moved 5 of 28 labels in one run (single-option arms were run once
  each, so their determinism is not shown). All four options set together (temperature 0, numCtx 4096, numPredict 2048,
  think on) moved 1 of 28, identically on 2 of 2 runs. The mechanism is not established: request bodies were not captured.

So a verdict holds for the exact request settings it was graded with. After changing any node option, the model, or the
Ollama version, run the exam again and re-grade.

## What n8n's own evaluation cannot do here

n8n's built-in evaluation metrics (categorization, string similarity, LLM-judged correctness and helpfulness, tools used,
custom expressions; same probe folder, `RESULTS.md`) cover a label match well. They do not express most of this repo's
checks (for example recap's compression ratio, abstention and grounded-number checks); those only exist as the exam's own
grader, which is why the grading happens in `wilco grade`.

## Not verified

The template is generalised from the two workflows the probe ran (`step2/workflows.json`). The `Exam` Set node, the two
URLs built from it and the `model` expression on the Ollama node were not run end to end after the generalisation:
import it, run it once, and check that `wilco grade` reports 28 answers for `email-triage` before trusting a number from it.
