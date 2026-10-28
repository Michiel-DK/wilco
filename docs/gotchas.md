# Gotchas — each one cost a build

> Mirror of the numbered gotchas section of this repo's private operating file (`CLAUDE.md`, not in the public cut).
> Test docstrings cite them as "CLAUDE.md gotcha N"; the numbers below are those numbers. Byte-identical to the source
> section by `sandbox/test_gotchas_mirror.py`, so this file cannot drift from it. Some items name private PRs, lanes or a
> ledger entry: those are the receipts, kept as written.

## Gotchas — each one cost a build

1. **Presence is not effect.** A thing can be present and inert while every check passes:
   `num_ctx` accepted-and-ignored by the compat endpoint, `judges.py` imported and dormant, a
   `sensitivePaths` block no lane passes, `test_ratchet.sh` counting 7 of 428 assertions here
   because it greps for bare `assert`. Test the *effect*, through the real entry point.
2. **A green guard proves nothing until seen RED.** Build the attacker's input by hand and run
   it. Two adversarial tests here looked green while asserting nothing. A count floor only
   catches a *net* decrease — delete a real test, add a stub, and the count holds.
3. **A new check earns its place only if some case isolates it.** Name a case that passes every
   other check and fails only the new one, and verify `failed_checks` has exactly one entry.
   Shipped unfalsifiable checks three times, each disguised by a score moving the right way.
4. **Normalization is directional.** Presence checks and absence checks must never share a
   helper — over-normalizing waves a fabrication through. `sandbox/numnorm.py` is the single
   implementation of *thousands-stripping* and exports only `strip_thousands`; the indiscriminate
   helper is `_norm_digits` in `sandbox/runner.py` (~line 931; grep it, the number drifts) (`_norm_digits('65,00') == '6500'` — a
   European sixty-five matching six thousand five hundred). Never swap one for the other.
   ⚠️ Neither converts a decimal comma: `strip_thousands('1.234,56') == '1234,56'`, which does
   **not** equal `1234.56` — verified 2026-08-25. Money grading across locales is unbuilt work.
5. **An ad-hoc probe is not a witness for the tool.** Reproduce through the real entry point —
   a hand-quoted census script hid an `imaplib` quoting bug the tool actually had.
6. **Enumerate with `find`, never a glob.** Four test files sit directly in `evals/`; the glob
   finds 12 of 17. Exclude `.claude/` — `.claude/worktrees/` holds other branches' copies.
   `./scripts/test.sh` does all of this; when a count here disagrees with `find`, this file is wrong.
7. **The shell lies, six ways.** `$?` is clobbered by any intervening command *including a
   substitution in the same argument list*; zsh uses 1-indexed `$pipestatus`, aborts a whole
   line on an unmatched glob, and does not word-split unquoted vars (`for t in $files` runs
   once). Capture `rc=$?` immediately; iterate with `while IFS= read -r`.
8. **`check-all` gets killed on long runs** and buffered stdout hides how far it got. Run
   per-exam with `python3 -u`. It is never the gate for a build lane.
9. **`git add -A` is banned here** — ~4 sessions run in parallel and the tree is shared mutable
   state. Stage explicit paths; run `git status --short` first and leave what you did not touch.
10. **Fixing an exam can destroy it.** Correcting reply-draft's rubric saturated it at 1.0.
    After any instrument fix, re-check headroom, not just correctness.
11. **A refutation is a lead, not a verdict** — 3 of 8 were right in observation and wrong in
    conclusion. Reproduce before acting; merging against a round-trip on verified evidence is legitimate.
12. **`drift_check.sh` reads `harness` + slash + word anywhere in `CLAUDE.md` or `docs/**.md` as
    a file reference** and fails the audit if it does not resolve. Write it with a hyphen. Prose
    is a code path here. (Softened at pin 291f0f8: a left word-boundary means `exoharness/exo`
    no longer trips it — but bare `harness/<word>` still does.)
13. **Pool tokens from `metrics_totals` ONLY.** Every results JSON carries per-case metrics AND
    a top-level `metrics_totals` aggregate; a recursive walker that sums every
    `prompt_tokens`/`completion_tokens` key counts everything twice. Cost: a committed pricing
    doc carried 2× figures for three hours on 2026-08-31, caught only because someone else's
    independently-derived numbers disagreed.
14. **Hosted comparisons are same-day or they are not comparisons.** Measured 2026-08-31: the
    same two hosted models on the same exams dropped 5–6 heldout cases across a two-day gap,
    while identical same-day reruns flip at most 0–4 of 17 verdicts. Run every arm of a hosted
    A/B in one window; treat cross-day deltas as provider drift until proven otherwise.
15. **An aggregate gate is blind to cancelling flips, and a runtime bump is a silent
    re-roll.** Ollama 0.33.2 (31 Aug) moved 5 of 22 transcript-en verdicts in opposite
    directions; `check` compared the heldout score and printed `ok` for a week. Now per
    case + `runtime.version` in every snapshot (PR #79). A test that pins "the old code"
    as `git show master:` is right until the day it merges — pin a blob (PR #80).
16. **The window is a precondition, not a tuning — and the default silently truncates.**
    Ollama's compat endpoint runs every model at a 4,096-token window and IGNORES `num_ctx`
    in the request (`router.py`, measured 2026-07-29). Past ~3k prompt tokens the FRONT of
    the prompt is cut — system prompt first — and the model answers confidently on what is
    left, or dies with `finish_reason=length` and 0 content. Three measurements read that as
    model capability before anyone checked: crm multi-turn 0/4 (2 of 4 were the window,
    ladder 3 Sep), transcript-en dead on every real-length call (a 19.6k-char call is 5,317
    tokens, 6 Sep), qwen3:8b "dead" on the whole long band (run at its 4k default). The only
    lever is a Modelfile (`PARAMETER num_ctx 16384` → `<model>-ctx16k`, crm precedent PR #70;
    ~+85% wall). **Every verdict on an input over ~3k tokens is a verdict about the window
    until the window is stated.** The window is a champion field: operator-signed.
17. **pytest is blind to this repo's `check()`-style test files.** Most test files (31 on
    2026-09-18; grep `^def check(`) record a failure by appending to a `FAILED` list and
    return the verdict as the exit code of `main()`; no `assert` sits inside any test
    (`sandbox/test_bakeoff.py`: 24 collected, 0 assert statements). `python3 -m pytest -q`
    collects every `def test_*`, sees no exception, and prints "N passed" by construction —
    a red `check()` is invisible to it (reproduced 2026-09-18: `check("1 == 2", False)` →
    pytest "1 passed", `python3 <file>` → rc 1). Cost: PR #85 named pytest as its gate, a
    gate that cannot go red (ledger 044, criterion halt 2). The gate is `./scripts/test.sh`
    (`python3 <file>`, one process per file, `rc=$?` captured at once). pytest is only the
    public clone's CI, and its green carries the same blind spot.
18. **A bake-off strategy receives the answer key.** `cmd_bakeoff` (`sandbox/runner.py`,
    ~line 2982; grep it) calls `fn(ctx, case)` with the full case dict, so
    `case["expected"]` (`must_commit`, `commit_owner`, `must_not_commit`, ...) is
    live-readable inside every function in `sandbox/strategies.py`. Nothing in the
    instrument stops a "defensive top-up" from the key, and the score would move the right
    way while measuring nothing. Only per-strategy sentinel tests pin it
    (`test_G_answer_key_never_leaks…`, `test_N_…` in `sandbox/test_bakeoff.py`). Cost:
    ledger 044, criterion halt 3 (PR #85). **Closed 18 Oct by PR #109 (ledger 067):** `cmd_bakeoff`
    now hands every strategy the case WITHOUT `expected`; a strategy that reads the key raises
    `KeyError` (`sandbox/test_q6_bakeoff_strips_expected.py`, seen red on the old code). The
    sentinel tests stay as the second lock.

19. **The public clone's pytest is not CI's pytest.** The 21 Sep refresh passed 494 tests locally and went
    red on GitHub in 14 s: `test_mlx_provider.py` imported mlx-lm, which is Apple-only and not in
    `requirements.txt`, and this Mac has it. A test that touches a platform-only package must branch on
    its presence with an EFFECT check on both sides (installed → proceeds; absent → the runner refuses
    loudly, positively identified — a bare `"mlx"` substring also matched the env-var refusal), never a
    skip. And a test that pins a master blob cannot ship in a clone without history — exclude it in
    `scripts/publish-public-snapshot.sh`, with the reason. Ledger 052–053, PR #95.

20. **A modelled figure travels as a measurement the moment it sits in a table.** The one-pager's "$791 per 10k
    tasks, 93% saved" was footnoted honestly on day one (the local 4B's token volumes × OpenAI's August direct
    rate); three weeks later it was a headline on two pages, the marketplace rate had halved, and on a flagship's
    measured volumes the figure is ≈$53 — the "saving" against the routed hosted $48 is unmeasured. Same shape twice
    in one session: a "$25" run estimate scaled from that $791 (measured volumes on disk said $5), a "~1%" loss
    share stated as fact (measured 5%). **Rule:** every outward number carries one of `metered` / `modelled on <inputs>`
    / `estimated`; dollar figures come ONLY from repo-radar `scripts/cost_per_10k.py` (ledger × measured volumes,
    tag included), never retyped; a number in prose traces to a tool call this session or carries ⚠️. The daily price
    monitor (repo-radar `scripts/price_sweep.py`) is the change alarm; the frontier run is what turns "modelled" into
    "metered" for the premium tier. 22 Sep, see the private strategy note.

21. **The runtime stamp sees the version, not the server's settings.** Ollama's `OLLAMA_KV_CACHE_TYPE` is server-wide, invisible
    to `/api/version`, and moves verdicts: measured 8 Oct (`docs/probes/m7-kv-cache-2026-10-08`), q8_0 flipped 4 stable cases of 70
    (none held-out down), q4_0 flipped 2 held-out cases DOWN on each of two exams — with `runtime.version` 0.35.0 on every arm, so
    `check` would run and call it a model regression. **Closed 10 Oct by PR #105 (ledger 062):** the stamp now carries
    `runtime.kv_cache_type` and `runtime.flash_attention`, read from the listening server process's environment (`lsof` → `ps -E`),
    re-read after the last load; `snapshot_preflight` refuses a mismatch and a pre-stamp snapshot. All 8 snapshots re-taken that night
    carry `unset`/`unset` (0 of 230 moved). A second instance for any experiment still runs on its own port (`OLLAMA_HOST=127.0.0.1:11435`).
