# Snapshots that refuse to move: 0 of 282 cases on the 1 Nov re-snapshot

**Headline: on 1 November we re-ran every exam on a new runtime (Ollama 0.40.2 → 0.40.11). Of the 282 cases, none changed
verdict and none was unstable.** The exact count is a little narrower than the headline, so here it is:
259 of the 282 cases had an earlier snapshot to compare against, and 0 of those 259 changed pass/fail. The other 23
(the English recap exam, `recap-en`) were sitting for the first time, so they had no earlier snapshot and could not move.
Instability covers all 282: every case gave the same verdict on all three loads. 0 cases were added or removed.

How it was derived: the script below diffs each committed `evals/<exam>/snapshot.json` in commit `f249005` against the
same file in that commit's parent, matching cases by id. A case counts as "moved" if it was stable on both sides and its
`passed` value changed.

## The rule that makes "did not move" mean something

An exam here is a fixed set of cases with a deterministic grader, split into train (we iterate on it) and held-out
(we only report it). A **snapshot** records the champion model's verdict on each case, and that record is committed to git.
Three rules turn it into a gate:

1. **Three fresh loads at temperature 0.** A snapshot is three separate model loads, each starting from an unloaded
   model. A 6 Sep probe saw one case give a 367-character summary on one load and a 332-character one on the next,
   one passing and one failing (`docs/probes/determinism-2026-09-06/RESULTS.md`). **That did not hold up.** On 7 Sep,
   174 cases × 4 fresh loads gave the same verdict every time, 0 unstable
   (`docs/probes/snapshot-reproducibility-2026-09-07/RESULTS.md`). We kept three loads as a cheap guard anyway.
2. **Stable or exempt.** A case is *stable* only if all three loads agree. Otherwise it is marked unstable and
   kept out of the gate. On 1 Nov no case needed that exemption.
3. **Per case, not per score.** `check` fails if *any* stable case moves, in either direction. Comparing the
   aggregate score is not enough, because the aggregate is blind to flips that cancel out.

## The incident that forced it

After the Ollama 0.33.2 upgrade (31 Aug), **5 of 22** verdicts on the call-summary exam (`transcript-en`) differed from
its 26 Aug snapshot. Two held-out cases went in opposite directions (`renewal-heldout-digits` pass → fail,
`support-heldout-long` fail → pass), so the held-out score did not change. The old gate compared that score, so it
printed `ok` every day for a week. The runtime is the likely cause, not a proven one: the snapshot did not record a
version then, and the other pre-bump snapshots reproduced exactly. The script re-derives the 5 from the 7 Sep
three-load re-take (`ebb8248`) against the 26 Aug file.

## The stamp: what the runtime was when the verdicts were taken

Every snapshot now carries a `runtime` block. `check` refuses to compare against a snapshot whose stamp disagrees with
the live server (PR #79 added the version; PR #105 added the cache fields):

- `runtime.version`: the Ollama version (`/api/version`).
- `runtime.kv_cache_type` and `runtime.flash_attention`: server-wide settings that the version endpoint does not
  report. We read them from the listening server process's environment. A probe on 8 Oct showed why the version alone
  is not enough. With the version unchanged, a q4_0 KV cache flipped 2 held-out cases DOWN on each of two exams
  (`docs/probes/m7-kv-cache-2026-10-08/RESULTS.md`). The version stamp could not see that, so `check` would have
  blamed the model.

A changed stamp is a refusal, not a warning: a runtime bump counts as a possible re-roll of every verdict until a fresh
three-load snapshot says otherwise. The 1 Nov run was that snapshot.

## Four re-takes, one script

| date | runtime | cases compared | moved | unstable |
|---|---|---|---|---|
| 7 Sep | pre-stamp → 0.33.2 (5 exams) | 140 | 5 (all `transcript-en`) | 0 |
| 2 Oct | 0.33.2 → 0.35.0 | 220 | 1 (train, `task-intake`: `recap-end-of-day` fail → pass) | 0 |
| 10 Oct | 0.35.0 → 0.40.2, first KV/flash-attention stamp | 230 | 0 | 0 |
| 1 Nov | 0.40.2 → 0.40.11 | 259 (+23 first baseline) | 0 | 0 |

## What did not hold, or is not claimed

- **This does not show the runtime is verdict-neutral.** It shows that these cases on these champions gave the same
  verdicts at the default cache settings. Five moved after the 0.33.2 bump; the next bump gets its own three-load evening.
- **The 2 Oct bump did move one case**: a train case, which the gate ignores, but a real move.
- **The 10 Oct run changed two things at once**: the runtime version and the new stamp fields. Since nothing moved,
  there was nothing to attribute to either one.
- **The 1 Nov run used one cache setting** (`unset`/`unset`), so it says nothing about the KV-cache type as a cause.
- **Energy.** The same run was metered at 0.095 Wh per case-run. ⚠️ not re-derived: the `powermetrics` capture is not
  committed, so the figure is quoted from `docs/probes/energy-resnapshot-2026-11-01/RESULTS.md`.
- **The differ was seen red before it was trusted.** We planted one flipped held-out verdict and one unstable train case
  in the 1 Nov recap snapshot, in memory only, and ran the differ. It reported exactly
  `recap: buried-critical (heldout) PASS -> FAIL`, plus 1 unstable case.

## Re-derive

No API key, GPU or model call. It reads git objects at pinned commits, so it needs this repository's history:

```sh
python3 scripts/writeups/snapshots-that-refuse-to-move.py
```

Output for the 1 Nov block, pasted:

```
== 1 Nov  energy re-snapshot, 0.40.2 -> 0.40.11  (commit f249005 vs f249005^)
exam                         cases compared moved unstable added removed  runtime old -> new
call-fields                32->32         32     0        0     0       0  0.40.2 kv=unset fa=unset -> 0.40.11 kv=unset fa=unset
crm-followup               47->47         47     0        0     0       0  0.40.2 kv=unset fa=unset -> 0.40.11 kv=unset fa=unset
email-triage               28->28         28     0        0     0       0  0.40.2 kv=unset fa=unset -> 0.40.11 kv=unset fa=unset
expense-categorization     22->22         22     0        0     0       0  0.40.2 kv=unset fa=unset -> 0.40.11 kv=unset fa=unset
recap-en                        23        -     -        0     -       -  (first baseline) -> 0.40.11 kv=unset fa=unset
recap                      23->23         23     0        0     0       0  0.40.2 kv=unset fa=unset -> 0.40.11 kv=unset fa=unset
reply-draft                25->25         25     0        0     0       0  0.40.2 kv=unset fa=unset -> 0.40.11 kv=unset fa=unset
task-intake                50->50         50     0        0     0       0  0.40.2 kv=unset fa=unset -> 0.40.11 kv=unset fa=unset
transcript-en              32->32         32     0        0     0       0  0.40.2 kv=unset fa=unset -> 0.40.11 kv=unset fa=unset
TOTAL: 282 cases in the new snapshots; 259 compared, 0 moved; 0 unstable; 23 first-baseline; 0 added, 0 removed
```

The other blocks print the same way: 7 Sep `140 compared, 5 moved`, 2 Oct `220 compared, 1 moved`, 10 Oct `230 compared, 0 moved`.

## Sources

- `evals/*/snapshot.json` at commits `f249005`, `310ef4c`, `f72f1df` and their parents
- `docs/probes/energy-resnapshot-2026-11-01/RESULTS.md`
- `docs/probes/kv-stamp-resnapshot-2026-10-10/RESULTS.md`
- `docs/probes/l0-resnapshot-2026-10-02/RESULTS.md`
- `docs/probes/determinism-2026-09-06/RESULTS.md`
- `docs/probes/snapshot-reproducibility-2026-09-07/RESULTS.md`
- `docs/probes/m7-kv-cache-2026-10-08/RESULTS.md`
- `docs/gotchas.md` (the runtime-bump and KV-cache entries)
- `scripts/writeups/snapshots-that-refuse-to-move.py`
