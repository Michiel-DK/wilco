> **EVIDENCE CELL:** **VERDICT: build.** The blind spot is real, but the recommended instrument is an entity-bound field key, not
> the cross-turn contradiction form (§5–6). Detector v1 (the pre-registered definition) over 178 deduplicated multi-turn crm-followup
> records (33 files, 258 restatement opportunities) gives **6 hits, 2 of them case-isolating**. On reading both turns, **all 6 are
> detector attribution errors: 0 real contradictions, 0 isolating.** The isolation witness that carries the verdict is a
> substituted roundup turn. Two hand-edited variants of a passing stored trace, (A) the Janssens and Devos amounts swapped and
> (B) the two stages swapped, each give **`failed_checks == []`** through `runner._score_one_turn` on all 4 turns, and the
> detector flags each one (2 hits per variant). A formatting-only variant (`€6,500`, `9.000 EUR`, `Proposal Sent`) gives 0 hits. A control (D: Devos `9100`) fails
> `answer_contains@t3` + `grounded_answer@t3`, which proves the substituted turn reaches the scorer.
> The verdict does not depend on the hit adjudication. Even if hits 5–6 were real, they would be case-isolating stored examples,
> and the verdict would still be build.
>
> **Not evidence:**
> - The **v2 sensitivity arm** (2 hits, 0 isolating). It was written after v1 ran, on the same data, to measure how much of v1's
>   noise principled attribution rules remove. It is a diagnostic, not a second result.
> - The **raw-unparsed arm** (0 hits). It reads protocol-break text that `answer_present` already fails.
> - The **34 answer-less files** (e33, e6, i0b, i2, snapshot-reproducibility, train-cases-probe, multiturn-ladder, pass2/pass3). They
>   store verdicts but no turn text, so they cannot be searched. They are listed in `analysis.json`, not dropped.
> - The brief's exclusion for "hosted rows from the older 38-case exam whose turn text differs from today's" matches **no
>   row**. The 10 multi-turn cases' `turns` and `turns_expected` are byte-identical between `e7bd8a6` (the last change to
>   `cases.json` before 27 Sep, 38 cases) and today's 47-case file. That was checked by comparing `git show e7bd8a6:evals/crm-followup/cases.json`
>   with HEAD per case id: 10 of 10 "turns same, exp same". So the 27 Sep matrix rows sit today's multi-turn text and count.

Job `as-eb-contradiction-isolation` (unattended, CPU only, no inference, no hosted call). It builds no check and adds no case.
The question comes from CLAUDE.md gotcha 3: a new check earns its place only if some case passes every other check and fails only
the new one. The design is `docs/experiments.md` E20, "The check that does not exist yet". Sections 1–2 were committed before
computing (`1ca5e6e`).

Files: `contradictions.py` (the detector plus the offline re-scorer) · `analysis.json` / `v1-run.txt` (v1, every hit with both turns'
text) · `analysis-v2.json` / `v2-run.txt` (v2 diagnostic) · `selftest-v1.txt` (the witnesses). Reproduce:
`SANDBOX_OFFLINE_PROBES=1 python3 docs/probes/contradiction-isolation-2026-11-10/contradictions.py [--v2] [--selftest]`.

## 1. The check, defined before any output was read for hits

**Unit.** One multi-turn crm-followup case record (`detail.turns`). Text = each turn's graded final answer `turns[k].got.answer`.
Answer-less turns (protocol break, `got == {}`) are scanned in a separate **diagnostic** arm from the last `raw_steps` string. That
arm is flagged, because `answer_present` already fails those turns.

**Fields** (CRM facts that are fixed in `evals/crm-followup/tools_mock.py`; none of the 10 multi-turn cases writes to the CRM):
- `amount`: an open-deal amount. A number counts only next to `EUR`/`€`/`amount`/`worth`/`deal`/`value`, or if it equals a
  `_DEALS` amount. It is normalised with `sandbox/numnorm.strip_thousands` only, never `_norm_digits` (gotcha 4). Numbers in an
  invoice/paid sentence go to a separate field, `invoice_amount`. Phone numbers, years, dates, VAT and employee counts are not amounts.
- `stage`: a stage word from the fixture vocabulary (`proposal sent`, `discovery`, `negotiation`, plus `closed-won`/`closed won`).
- `status`: a CRM status word (`prospect`, `active client`, `churned`).
- `contact`: a person name from the fixture (the `_CRM` contacts plus the `_OWNERS` reps).

**Entity attribution, deterministic.** A value goes to company C if C's name, or its unique first token, appears in the same line
or sentence. Otherwise it goes to the company most recently named earlier in the same answer (this covers roundup headers like
`**1. Janssens Bakery**`). Otherwise it goes to the turn's subject company: the single company its tool calls targeted, or, with no
tool call, the company named in the turn text.

**Established.** A triple (company C, field F, value V) is established at turn i when the model's own turn-i answer states V for
F of C **and** V is grounded: it appears in a tool result returned in turns 0..i of the same case. An ungrounded statement is a
fabrication, which E10 rung A / `grounded_answer` already covers. It does not establish anything.

**Contradicts.** A later turn j > i states a value V' ≠ V for the same (C, F). The exception: some tool result returned in turns
i+1..j carries F = V' for C, i.e. a new tool result changed it. One established value and one later different value is one hit.
Several values in one turn for the same (C, F) are not cross-turn and are not counted.

**Isolating.** A hit is **case-isolating** when the case's stored `failed_checks` is empty (every existing check passed on every
turn). It is **turn-isolating** when turn j's own `failed_checks` is empty but another turn failed. Gotcha 3 asks for
case-isolating. Verdicts come from the stored `failed_checks`, cross-checked by re-scoring each turn offline through
`runner._score_one_turn` with the scoring trace rebuilt the way `_run_turns` builds it.

**Denominator.** A restatement opportunity is a (case, i < j, C, F) such that F of C is established at i and turn j states any
value for (C, F). Hits are reported over opportunities, so that zero hits reads as "0 of N chances".

## 2. Predictions (committed before computing, `1ca5e6e`)

- P1: **0 to 3 hits** across all searchable records. Restatement opportunities exist almost only in the two recap/roundup turns
  (`portfolio-recap-multiturn-fb2` t3, `long-thread-recap-with-outage-train` t3). Hosted models restate grounded values faithfully.
- P2: **0 case-isolating hits** in stored outputs. In a roundup, a wrong amount almost always drops the right one and fails
  `answer_contains`. The exception would be an amount *swap* between companies, where all three numbers are present.
- P3: on paper, **at least one constructible case passes every existing check and is still a contradiction**. Roundup stage
  is unpinned (fb2's own R8 note), and `answer_contains` is substring presence with no entity binding, so a stage or amount swap
  between companies passes. If P3 holds, the brief's rule makes the verdict **build** even if P2 holds.
- P4: the offline re-scorer reproduces the stored `failed_checks` on every searchable file. Any mismatch is reported, not smoothed.

## 3. What ran and what came out

**Corpus** (from `contradictions.py`, `v1-run.txt` lines 1–5). 81 committed probe JSONs carry multi-turn crm records:
- **33 searchable** after dedupe. That is 178 case records, and 125 of them have empty `failed_checks`.
- **14 dropped as duplicates**: same per-turn answers, hashed. These are the 11 `rescored-2026-10-23/matrix` copies, which are
  copied unchanged for crm per that README, plus `rescored/frontier-trio`, one `rescored/claude-inline` pair, and `i2v3` = `i2v2`.
- **34 unsearchable**, with no turn text.

The searchable records come from the 27 Sep matrix (11 hosted models × 10 cases), the 28 Oct re-sits, frontier-direct and laptop
examples (held-out only, 2 cases each), the claude-inline rescored set, and the i2v2/i2v4 local runs.

**P4: HELD.** Re-scoring all 178 records through `runner._score_one_turn` reproduces the stored `failed_checks` exactly:
`re-score mismatches vs stored failed_checks: 0`. The stored verdicts are therefore today's scorer's verdicts on these outputs.

**Detector v1 (pre-registered):**
```
restatement opportunities 258 by field {'contact': 39, 'amount': 108, 'stage': 111}
HITS graded-answer arm: 6; case-isolating 2; turn-isolating 2
HITS raw-unparsed diagnostic arm: 0
```
Each hit, adjudicated by reading both turns (full text in `v1-run.txt`):

| # | file · case | detector says | what the text says | verdict |
|---|---|---|---|---|
| 1–2 | claude-haiku-5-5 (frontier-direct) · mid-thread-switch | Devos contact: t1 `Marieke Claes` → t3 `Jan De Vos` / `Tom Verhaeghe` | t1 is about Janssens. A caveat bullet mentions "Devos Garage's address", and the next line, "Check these with Marieke Claes", carried over to Devos. Claes is Janssens' owner. | detector error (carry-over) |
| 3–4 | same | Devos contact: t0 `Jan De Vos` / `Tom Verhaeghe` → t1 `Marieke Claes` | same carry-over. v1 also files owners under `contact`, so "contact: Jan De Vos, owner: Tom Verhaeghe" reads as two contacts | detector error |
| 5 | kimi-k3 (matrix) · mid-thread-switch | Devos stage: t2 `proposal sent` → t3 `discovery` | t2: "past discovery (Devos Garage) and proposal sent (Janssens Bakery)". The value comes before its company in a parenthesis, and v1 binds it to the nearest company before it | detector error (binding); **case-isolating** only because the case is fully green |
| 6 | same | Janssens contact: t1 `Marieke Claes` → t2 `Bram Wouters` | t2 is about Peeters. "The account is owned by Bram Wouters" carried over from the parenthesis that named Janssens last | detector error (carry-over); **case-isolating** for the same reason |

**Real contradictions in stored outputs: 0 of 258 opportunities. Case-isolating: 0.**
- **P1** (0–3 hits): HELD for real contradictions. The raw detector gave 6, above the range, and all 6 are noise.
- **P2** (0 case-isolating): HELD.
- The P1 premise was **wrong**: opportunities are not "almost only" in the roundups. The hosted models restate stage and amount
  of earlier companies in passing, in comparisons like "one stage further along than the Devos deal", so the mid-thread-switch
  turns carry many opportunities too.

**Detector v2 (diagnostic, written after v1).** It adds four rules: owners as a separate `owner` field; a value followed by
"(Company)" binds to that company; carry-over only from a segment naming exactly one company; name + alias count as one mention.
Result: 252 opportunities, 2 hits, 0 case-isolating. Both remaining hits are #1–4's carry-over (`v2-run.txt`).
- **The witnesses still fire under v2**: swap A gives 2 hits, swap B gives 2, formatting gives 0.
- **Finding for any build:** deterministic attribution over free prose produced **6 false hits in 258** (v1) and **2 in 252** (v2)
  on real hosted answers, and **0 true ones**. A built check that grades free text this way would fail correct answers more
  often than it catches drift. Its precision is the first risk, ahead of its recall.

## 4. The isolation witness (P3), run, not just argued

`--selftest` (`selftest-v1.txt`) uses `google/gemma-4-31b-it`'s stored `portfolio-recap-multiturn-fb2` trace from hosted-resit
28 Oct. It passes the case: stored `failed_checks: []`, re-scored `[]`. Turns 0–2 state Janssens 6500 / proposal sent,
Devos 9000 / discovery, and Peeters 4200 / negotiation, each grounded. Only turn 3's answer was replaced. The tool results and the
earlier turns are unchanged, and the whole case was scored through the real `_score_one_turn`:

| variant (turn 3 answer) | existing checks, all 4 turns | contradiction hits |
|---|---|---|
| A: Janssens **9000**, Devos **6500**, Peeters 4200 (stages right) | `failed_checks=[]` | 2 (Janssens amount, Devos amount) |
| B: Janssens stage **discovery**, Devos stage **proposal sent** (amounts right) | `failed_checks=[]` | 2 (Janssens stage, Devos stage) |
| C: same facts as turns 0–2, reformatted (`€6,500`, `9.000 EUR`, `Proposal Sent`) | `failed_checks=[]` | 0 |
| D (control): Devos **9100**, rest right | `answer_contains@t3`, `grounded_answer@t3` (**red**: the substitution is scored) | 1 |

**P3: HELD.** Two reasons the existing checks pass A and B:
- `answer_contains` checks needle presence with **no entity binding**. `_needle_matches` is number-token or case-insensitive
  substring, with no proximity form; read 11 Nov, `sandbox/runner.py:1244`.
- Roundup stage is **unpinned** (fb2's R8 note).

`grounded_answer` passes as well, because 9000 and 6500 are both in the corpus. Variants A and B are byte-for-byte what an
attribution-drift failure looks like. No stored output shows one yet.

**At most 3 constructible cases** (described, not added):
1. **Roundup swap.** fb2 / long-thread-recap shape. The final roundup restates every company's amount and stage. A swap keeps
   every needle present. This is witnessed above.
2. **Judgement that depends on an earlier value.** For example, after turns that fetched the three deals: "Which deal is furthest
   along, and which is biggest?" The right answer (Peeters furthest, Devos biggest) follows from earlier-turn facts. A drifted
   answer ("Janssens is furthest along, in negotiation") contradicts turn 1's stage. No `answer_contains` set can pin it: "Peeters"
   and "Devos" also appear in any answer that lists all three.
3. **Referential callback that re-states a field.** "Going back to the first company: is its deal still at the stage you told me?"
   The answer must restate turn 0's stage for turn 0's company. A model that binds "first" to the wrong company, or restates the
   wrong stage, can still mention every needle.

## 5. What this does not show

- **No drift was observed in stored data.** The case for building rests on a constructed failure (gotcha 3 asks only that a case
  isolate it), not on a measured rate. The denominator is 258 opportunities across 33 runs. Each case has 14 records (the 2 held-out cases have 33),
  and most are hosted models. The local 2B champion contributes only `laptop-examples` (2 held-out cases) and the i2v2/i2v4 local runs.
- **Labelling.** All adjudication in section 3 is one reader (this job, a Claude session) reading both turns. There are **no human
  labels**.
- The 34 answer-less files may hold contradictions that cannot be seen. Those are mostly 2B runs from 2–20 Sep.
- **A key edit is the competing design.** In this fixture, every established value equals the fixture truth, because nothing writes.
  So a per-company field key ("Devos → 9000, discovery") graded against the answer catches A and B without any cross-turn logic.
  A contradiction check differs only where turn i itself was wrong-but-grounded. There it would also fail a turn j that
  *corrected* the error. The draft brief below names both.

## 6. Draft lane brief (NOT queued, NOT authorised)

```text
LANE: entity-bound field check for multi-turn crm roundups (E20's "self-consistency across turns", cheapest isolating form)

WHY: docs/probes/contradiction-isolation-2026-11-10/RESULTS.md — a swapped-attribution roundup (amounts or stages traded
between companies) passes every existing check (failed_checks == [], runner._score_one_turn); answer_contains has no entity
binding. 0 instances in 258 stored opportunities: this closes a blind spot, it does not fix a measured rate.

DECIDE FIRST (operator):
  (a) KEY form: a new expected key, e.g. `fields_by_entity: {"devos garage": {"amount": "9000", "stage": "discovery"}, ...}`,
      graded against the committed truth; or
  (b) CONTRADICTION form: graded against the model's own earlier grounded statements (what E20 wrote). Fails a self-correction;
      needs the established-set machinery in contradictions.py.
  Recommendation: (a). It isolates the same witnesses, needs no cross-turn state, and cannot punish a correction.

BUILD:
  - score-defining: touches sandbox/runner.py (score_trajectory / _score_one_turn) and possibly evals/crm-followup/properties.py →
    sensitivePaths FULL tier; pass the CLAUDE.md Lane args explicitly to single-lane-build.
  - attribution must be high-precision: the v1 prose attributor here made 6 false hits / 258 on real hosted answers (v2: 2 / 252).
    Bind a value only when the company and the value share one line/sentence with no other company in it; otherwise "unbound",
    which FAILS CLOSED for a key field (stated nowhere bound ⇒ missing), never passes vacuously.
  - normalisation: numnorm.strip_thousands only (gotcha 4); stage/status case-folded; no _norm_digits.
  - isolation test (gotcha 3), seen RED on the old code: substituted-roundup variants A and B from contradictions.py --selftest
    each fail ONLY the new check (failed_checks has exactly one entry kind); variant C passes; control D still fails answer_contains; every stored passing fb2 /
    long-thread-recap trace in the 33 searchable files still passes (precision guard over real prose).

CASES AND SNAPSHOT:
  - arming the check on existing cases = editing their expected blocks; any NEW case (constructible cases 2 and 3 in RESULTS §4) =
    a NEW committed entry with its own turns_expected. Either changes the crm-followup case set / keys, so `check` refuses until
    a re-snapshot (3 loads, rule A). The re-snapshot is operator-authorised, and on a held-out case (fb2 is held-out) the key edit
    is an operator-signed decision. No split moves.
  - after the instrument change, re-check headroom (gotcha 10): the champion already fails fb2 t3, so the new check must not be
    the only thing between it and a pass it does not deserve, nor saturate the train twin.

GATE: ./scripts/test.sh (never check-all, never pytest — gotcha 17). No inference in the build; the re-snapshot is a separate go.
```
