# n8n evaluation probe — step 1 RESULTS (cloud trial, run 2026-11-03 17:20–17:21 UTC)

> **EVIDENCE CELL:** one full pass of the 28 email-triage cases through an n8n Cloud workflow (instance
> `rogerwilco`, n8n 2.46.4, trial tier; workflow `VSypJj4BJD4RSqr0`), model **claude-haiku-5-5 via the Anthropic
> Chat Model node, temperature 0**, label extracted by a Code node, written back to the data table and scored by the
> Evaluation node's **Categorization** metric. Per-case labels read from the data table by browser (28 rows, 2 pages) and
> saved as `run1-haiku-labels.csv` here and diffed by `compare.py --csv` against `evals/email-triage/cases.json` and the champion snapshot.
> **Not evidence:** the model is Haiku, not the local champion — this measures n8n's evaluation *mechanics and tiering*,
> not our model. Nothing here changes a champion or a snapshot. Metered: 1 token count (one case), 28 wall times.

## Prediction (registered in STEPS.md before the run) → outcome

| part | predicted | observed | held? |
|---|---|---|---|
| n8n's Categorization metric and our `score_labels` agree on every case given the same output | yes | the one Categorization value inspected (execution 123, `fr-networking-coffee`) = 1 and our grader says pass; every other row's label is a verbatim key label, so exact-match on both sides is the same test | **yes**, on the 1 inspected + 27 by construction (not every metric value was opened) |
| hosted model passes ≥ 23/28 (the 2B champion's score) | ≥ 23 | **27/28** (train 8/8, held-out 19/20) | **yes** |
| metric-based evaluation on the trial is limited to one workflow | limited | **not tested** — one workflow only was built; the Set Metrics node ran on the trial without being greyed out | UNTESTED |

## The per-case table (`compare.py` output, verbatim)

```
champion snapshot: gemma4:e2b-it-qat on ollama 0.40.11  (train 0.875, heldout 0.8)

case                               split   key         n8n         n8n_ok champ agree
client-quote-request               train   reply_now   reply_now   True   True  True
overdue-invoice                    train   reply_now   reply_now   True   True  True
newsletter-substack                train   ignore      ignore      True   True  True
recruiter-linkedin                 train   reply_later reply_later True   True  True
seo-cold-spam                      train   ignore      ignore      True   True  True
friend-dinner                      train   reply_later reply_later True   True  True
production-down                    heldout reply_now   reply_now   True   True  True
gdpr-data-request                  heldout reply_now   reply_now   True   True  True
conference-invite                  heldout reply_later reply_later True   True  True
promo-code                         heldout ignore      ignore      True   True  True
client-question-no-rush            train   reply_now   reply_now   True   False False
agency-whitelabel-offer            train   reply_later reply_later True   True  True
invoice-error-client               heldout reply_now   reply_now   True   True  True
dpa-signature-compliance           heldout reply_now   reply_now   True   True  True
recruiter-fake-urgency             heldout reply_later reply_later True   False False
paid-workshop-invite               heldout reply_later reply_now   False  True  False
intro-no-ask                       heldout reply_later reply_later True   True  True
disk-warning-no-action             heldout ignore      ignore      True   True  True
long-ramble-buried-incident        heldout reply_now   reply_now   True   True  True
newsletter-injection-urgent        heldout ignore      ignore      True   False False
cold-sales-injection-urgent        heldout ignore      ignore      True   False False
nl-client-bug-buried               heldout reply_now   reply_now   True   True  True
fr-tax-authority-documents         heldout reply_now   reply_now   True   True  True
stripe-payout-notice               heldout ignore      ignore      True   True  True
client-domain-newsletter-nl        heldout ignore      ignore      True   True  True
calendar-accept-notice             heldout ignore      ignore      True   False False
proposal-accept-conditional        heldout reply_now   reply_now   True   True  True
fr-networking-coffee               heldout reply_later reply_later True   True  True

n8n run vs key: 27/28 train 8/8  heldout 19/20
verdict agreement with the champion snapshot (same pass/fail per case): 22/28
cases missing from the n8n run: 0
```

Haiku's one miss: `paid-workshop-invite` (key `reply_later`, Haiku `reply_now` — a 1,500 EUR honorarium read as "money
matters"). The 2B champion's five misses (`client-question-no-rush`, `recruiter-fake-urgency`, the two injection cases,
`calendar-accept-notice`) Haiku all gets. ⚠️ Model comparison is incidental here: different model, different serving; the
hosted Haiku row for email-triage in `docs/model-notes.md` / the frontier-direct pass is the place for that, not this probe.

## What n8n's evaluation feature did and did not do (observed, n8n 2.46.4 cloud trial)

1. **Evaluation Trigger + data table works as a dataset loop.** 28 rows → 28 executions, 0.9–1.7 s wall each (Haiku),
   sequential (trial concurrency 1). CSV import kept multi-line `input` cells intact.
2. **Set Outputs wrote the model label back to the table** per row (`n8n_label` column, `updatedAt` stamped per row).
3. **Set Metrics ran on the trial tier, not greyed out.** Output per execution: `Categorization: 1`. So the docs' "self-hosted:
   Enterprise / Starter: single workflow" line did not block a cloud-trial run of one workflow.
4. **The run never appeared as a test run.** The workflow's *Evaluations* tab (top bar) shows a "Get started" onboarding
   screen ("automated tests that assess agent workflow outputs using model-graded checks") and no run list. The executions
   were started from the editor's **Execute** button, which iterates the dataset but registers as 28 ordinary executions,
   not as an evaluation test run; the Set Metrics node's own help text says metrics "will be displayed in the 'evaluations'
   tab, not on the Google Sheet or Data table". Net: **the per-case metric exists only inside each execution; no aggregate,
   no delta-vs-previous-run, no run page** was produced this way. Whether the "Get started" flow or a "Run test" button
   (not found on this version's tab) would have produced the classic run page is UNTESTED. This also means the public-API
   `/test-runs` route had nothing to return, so `compare.py` used the CSV route (labels read from the table).
5. **Token count is visible per execution in the Logs panel** (execution 123, `fr-networking-coffee`: 405 tokens), not
   per case in any evaluation view. Cost is not shown for the Anthropic node. No energy anywhere (as the docs read said).
6. **Two UI foot-guns cost ~30 min:** the System message field had been filled with the file *name* `system-prompt.txt`
   instead of its contents (Haiku then answered the email); and a stray `.` after `{{ $json.n8n_label }}` in Set Outputs
   wrote `reply_now.` to every row, which exact-match then scored 0. Both are operator errors, not n8n's — but they are the
   kind of thing our committed `prompt.md` + `cases.json` + `check` make impossible by construction.
7. **A second "Evaluations" panel** (right-hand side, per-node "when Basic LLM Chain receives input, check output",
   "To be similar") is a different, newer light-test feature. It was not used.
8. Minor: in the Set Metrics node the Expected/Actual fields were mapped swapped (`expected = n8n_label`, `actual =
   expected_label`). Harmless for exact match; would matter for an asymmetric metric.

## Step 2 still has to show
- the same workflow in **self-hosted Docker** with the **Ollama node pointed at the local champion** (`gemma4:e2b-it-qat`,
  ollama 0.40.11): prediction = 23/28 reproduces per case (the snapshot's exact pass/fail set), i.e. the n8n path is a
  faithful transport of our champion. Needs the GPU go (one 2B exam, < 15 min).
- launching as a real evaluation test run (find "Run test" on this version, or the API `createTestRun`) to see whether the
  aggregate page and `/test-runs` endpoint appear on the free/registered tier.
- a Claude Haiku run of email-triage through **our** runner (`--provider anthropic`) so the 27/28 above gets a same-model
  counterpart under our grader; today it has none on disk.

## Cost / time
- Anthropic: 28 Haiku calls, ≈ 400 tokens each by the one inspected case (≈ 11k tokens total, ⚠️ estimated from n=1);
  dollar figure not computed (rule: dollars only from `cost_per_10k.py`).
- Wall: 28 executions in ≈ 48 s (17:20:33 → 17:21:11 per the table's `updatedAt` stamps). Operator UI time ≈ 45 min
  including the two foot-guns.

## Item 3, 3 Nov evening: launch as a real evaluation test run — NOT AVAILABLE on the trial UI

On workflow `VSypJj4BJD4RSqr0` (dataset trigger on `email triage cases` + Set Outputs + Set Metrics categorization), the
workflow-level **Evaluations** tab (top centre, next to Editor/Executions) shows only the "Get started" onboarding screen.
There is no Run test button (operator, screenshot 19:07). The n8n MCP cannot start a dataset-row trigger either
("Only Schedule, Webhook, Form, and Chat triggers can be executed directly through MCP"). So **prediction part 3 (an
aggregate page + `/test-runs` API on the trial tier) cannot be tested here.** That is recorded as "no test run reachable
on n8n Cloud trial 2.46.4", not as "the feature does not exist". ⚠️ Whether a paid tier or self-hosted unlocks it is UNVERIFIED.

Two side observations, same screenshot:
- 2.46.4 has a second, **node-level** evaluation panel in the editor's right sidebar. It holds test cases per node ("When
  Basic LLM Chain receives input, check output"), checks like "To be similar", and "Create case" / "Run all". It is
  separate from the data-table evaluation and not in the private competition note yet.
- The plan bar reads **0/1000 executions** after ≈ 180 manual/MCP executions today. Manual executions apparently do not
  count against the trial limit. ⚠️ Inferred from the counter only.
