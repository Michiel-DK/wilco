#!/usr/bin/env python3
"""pick.py — the pick rule as a command (later `wilco pick`). No inference, reads committed/produced files only.

    python3 scripts/pick.py <task> [result.json ...] [--prices pricing/prices.json] [--bar-gap N] [--out PATH]

Inputs: one results JSON per candidate, as `runner.py run` / `diff` write them (`results/<task>__<provider>__<model>.json`;
with no files given, every top-level `results/<task>__*.json` is read). A committed `evals/<task>/snapshot.json` is accepted
too (the champion's per-case verdicts; it carries no `metrics_totals`, so only a zero-priced local model gets a cost from it).
Identity is the file's own `provider` + `model` fields, never the filename; the price key is exactly `<provider>/<model>`.

Per candidate: held-out passed/total (counted from the per-case `split` + `passed`, cross-checked against the file's
`heldout` block) and cost per 10k tasks = `metrics_totals` prompt/completion tokens x the list price / cases in the file x 10k.
Tokens come from `metrics_totals` ONLY (CLAUDE.md gotcha 13: every per-case `detail.metrics` repeats them; a walker that
sums every token key counts the run twice). No `metrics_totals` on a priced model -> cost unknown, never a re-sum.

A `metrics_totals` marked `complete: False` (runner.py: some cases were not metered, so the total is a floor) is a
cost floor, not a cost: excluded like an unknown cost. Refusals (exit 2): unreadable JSON, a case without a bool
`passed`; a snapshot whose ids are not in `evals/<task>/cases.json`; the candidates do not cover the same case-id set with the same split per id (the 8 Oct comparable-set
rule: never a silent intersection); two files for one `<provider>/<model>`; a file whose own `heldout` block disagrees with
its cases; a file for another task. Exit 3: no candidate at or above the bar has a known cost (no pick). Exit 0: a pick.
Writes `results/<task>-pick.md` (or --out) with the same table and flags as the terminal."""
import argparse, glob, json, os, sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(REPO, "sandbox"))
from router import PROVIDER_TIER, PROVIDERS, TIER_ORDER  # noqa: E402  (read-only: local providers; tiers for the adopt hint)

# ---- the rule's constant, in one place --------------------------------------------------------------------------
BAR_GAP = 1
"""The bar = the best held-out score any candidate reached, minus BAR_GAP cases. Every candidate at or above the bar is
eligible; the cheapest eligible candidate with a KNOWN cost takes the task (ties: higher held-out, then name). BAR_GAP = 1
is the public rule ("the best score any model reached, or one case from it"): at 10-20 held-out cases a one-case gap is
noise, so a model one case behind the best is not beaten. Unknown-cost candidates still set the bar (they sat the exam);
they are only excluded from the cheapest pick. `--bar-gap N` overrides for one run."""
NOISE_GAP = 1   # a one-case gap between the pick and another candidate is printed as "within noise" (the README's wording)

HOSTED_FLAG = "no stable-case gate: temperature 0 does not reproduce on hosted APIs; same-day rerun only"
LOCAL_TAG = "≈0 local"


class Refusal(Exception):
    """A comparability / consistency failure: exit 2 with the message, never a partial table."""


def is_local(provider):
    """Local = a router provider whose base_url is this machine (ollama, mlx, systemone) or none at all (stub).
    A provider the router does not know is treated as hosted, so it carries the hosted flag rather than escaping it."""
    p = PROVIDERS.get(provider)
    if p is None: return False
    url = p.get("base_url")
    return url is None or url.startswith(("http://localhost", "http://127.0.0.1"))


def exam_ids(task):
    """Case ids of the committed exam, or None when evals/<task>/cases.json does not exist."""
    p = os.path.join(REPO, "evals", task, "cases.json")
    return {c["id"] for c in json.load(open(p))["cases"]} if os.path.exists(p) else None


def load_candidate(path, task):
    try:
        d = json.load(open(path))
    except (OSError, ValueError) as e:
        raise Refusal(f"{path}: not readable JSON ({e})")
    cases = d.get("cases") if isinstance(d, dict) else None
    if not isinstance(cases, list) or not cases: raise Refusal(f"{path}: no per-case list — not a run/diff/snapshot file")
    if d.get("agent") not in (None, task): raise Refusal(f"{path}: is a `{d['agent']}` result, not `{task}`")
    if not d.get("provider") or not d.get("model"): raise Refusal(f"{path}: no provider/model field")
    splits = {}
    for c in cases:
        if not isinstance(c, dict) or not all(k in c for k in ("id", "split", "passed")):
            raise Refusal(f"{path}: a case without id/split/passed: {str(c)[:80]}")
        if not isinstance(c["passed"], bool): raise Refusal(f"{path}: case {c['id']!r} has passed={c['passed']!r}, not a bool")
        if c["id"] in splits: raise Refusal(f"{path}: case id {c['id']!r} appears twice")
        splits[c["id"]] = c["split"]
    if "agent" not in d:   # a snapshot names no task: its ids must belong to this task's committed exam
        known = exam_ids(task)
        if known is None: raise Refusal(f"{path}: carries no `agent` field and evals/{task}/cases.json does not exist to check it against")
        stray = sorted(set(splits) - known)
        if stray: raise Refusal(f"{path}: {len(stray)} case ids are not in evals/{task}/cases.json (e.g. {stray[:3]}) — another task's file?")
    held = [c for c in cases if c["split"] == "heldout"]
    passed = sum(1 for c in held if c["passed"])
    hb = d.get("heldout")
    if isinstance(hb, dict) and (hb.get("passed"), hb.get("total")) != (passed, len(held)):
        raise Refusal(f"{path}: heldout block says {hb.get('passed')}/{hb.get('total')}, its cases say {passed}/{len(held)}")
    return dict(path=path, label=f"{d['provider']}/{d['model']}", provider=d["provider"], held=passed, n=len(held),
                cases=len(cases), splits=splits, totals=d.get("metrics_totals"), snapshot="loads" in d)


def check_comparable(cands):
    ref = cands[0]
    seen = {}
    for c in cands:
        if c["label"] in seen: raise Refusal(f"two files for {c['label']}: {seen[c['label']]} and {c['path']} — pass one")
        seen[c["label"]] = c["path"]
    for c in cands[1:]:
        if c["splits"] == ref["splits"]: continue
        only_a = sorted(set(ref["splits"]) - set(c["splits"])); only_b = sorted(set(c["splits"]) - set(ref["splits"]))
        moved = sorted(i for i in set(ref["splits"]) & set(c["splits"]) if ref["splits"][i] != c["splits"][i])
        raise Refusal("candidates did not sit the same exam (comparable-set rule; pick never intersects):\n"
                      f"  {ref['label']} ({ref['cases']} cases) vs {c['label']} ({c['cases']} cases)\n"
                      f"  only in the first: {only_a[:8]}{' …' if len(only_a) > 8 else ''} ({len(only_a)})\n"
                      f"  only in the second: {only_b[:8]}{' …' if len(only_b) > 8 else ''} ({len(only_b)})\n"
                      f"  same id, different split: {moved[:8]} ({len(moved)})\n"
                      "  re-run the candidates on one case set, or pass only the files that share it")


def cost_per_10k(c, prices):
    """(USD per 10k tasks or None, tag). Tokens from metrics_totals ONLY — see the module docstring (gotcha 13)."""
    p = prices["models"].get(c["label"])
    if p is None: return None, "cost unknown (not in prices.json)"
    if p["input"] == 0 and p["output"] == 0 and is_local(c["provider"]):
        return 0.0, LOCAL_TAG   # zero rate x any token count; a snapshot without metrics_totals still prices
    t = c["totals"] or {}
    if not isinstance(t.get("prompt_tokens"), (int, float)) or not isinstance(t.get("completion_tokens"), (int, float)):
        return None, "cost unknown (no metrics_totals in the file)"
    if t.get("complete") is False:   # runner.py marks a total as a FLOOR when some cases burned calls it could not meter
        return None, f"cost floor only ({t.get('unmetered_cases', '?')} of {c['cases']} cases unmetered)"
    if t["prompt_tokens"] + t["completion_tokens"] == 0 and not is_local(c["provider"]):
        return None, "cost unknown (0 tokens metered on a hosted run)"
    usd = (t["prompt_tokens"] * p["input"] + t["completion_tokens"] * p["output"]) / 1e6 / c["cases"] * 1e4
    return usd, f"list price {p.get('as_of', prices['as_of'])}"


def apply_rule(cands, bar_gap=BAR_GAP):
    """Fills cost-independent verdicts and returns (best, bar, pick or None). See BAR_GAP for the rule."""
    if bar_gap < 0: raise Refusal("--bar-gap must be >= 0")
    # W7: clamped at 0 — a best of 0 printed "bar -1/n". Same eligible set: held is never < 0.
    best = max(c["held"] for c in cands); bar = max(best - bar_gap, 0)
    ok = [c for c in cands if c["held"] >= bar and c["usd"] is not None]
    pick = min(ok, key=lambda c: (c["usd"], -c["held"], c["label"])) if ok else None
    for c in cands:
        if c is pick: v = "PICK"
        elif c["held"] < bar: v = "below"
        elif c["usd"] is None: v = "at bar, cost unknown — excluded"
        elif c["held"] == best: v = "best"
        else: v = "at bar"
        c["verdict"] = v
        c["noise"] = bool(pick) and c is not pick and abs(c["held"] - pick["held"]) == NOISE_GAP
    return best, bar, pick


def fmt_usd(x):
    return "—" if x is None else ("≈0" if x == 0 else (f"{x:,.2f}" if x < 10 else f"{x:,.0f}"))


def build(task, paths, prices, bar_gap=BAR_GAP):
    cands = [load_candidate(p, task) for p in paths]
    if not cands: raise Refusal(f"no result files for `{task}`")
    check_comparable(cands)
    for c in cands: c["usd"], c["tag"] = cost_per_10k(c, prices)
    best, bar, pick = apply_rule(cands, bar_gap)
    cands.sort(key=lambda c: (-c["held"], float("inf") if c["usd"] is None else c["usd"], c["label"]))
    flags = []
    for c in cands:
        if c["usd"] is None: flags.append(f"{c['label']}: {c['tag']} — EXCLUDED from the cheapest pick, never counted as 0")
    hosted = [c["label"] for c in cands if not is_local(c["provider"])]
    if hosted: flags.append(f"hosted ({', '.join(hosted)}): {HOSTED_FLAG}")
    for c in cands:
        if c["noise"]:
            flags.append(f"{c['label']} {c['held']}/{c['n']} vs the pick {pick['held']}/{pick['n']}: a one-case gap, within noise")
    return dict(task=task, cands=cands, best=best, bar=bar, bar_gap=bar_gap, pick=pick, flags=flags, n=cands[0]["n"],
                prices_as_of=prices["as_of"], prices_source=prices.get("source", "?"), current=current_label(task),
                tier=current_tier(task))


def above_tier(provider, tier):
    """'<provider> is <p>-tier, the task is <t>-tier' when the provider ranks above the task's tier, else None (also when
    either is unknown: the runner's own guard is the authority, this is only a heads-up)."""
    p = PROVIDER_TIER.get(provider)
    if tier not in TIER_ORDER or p not in TIER_ORDER or TIER_ORDER.index(p) <= TIER_ORDER.index(tier):
        return None
    return f"{provider} is {p}-tier, the task is {tier}-tier"


def _agent_yaml(task):
    try:
        import yaml  # noqa: PLC0415  (requirements.txt; imported here so the rule above stays import-light)
        d = yaml.safe_load(open(os.path.join(REPO, "agents", task, "agent.yaml"))) or {}
    except Exception:  # noqa: BLE001 — no file / unreadable YAML: nothing to say about the current model or tier
        return None
    return d if isinstance(d, dict) else None


def current_tier(task):
    d = _agent_yaml(task)
    return d.get("tier", TIER_ORDER[0]) if d is not None else None   # no key = the strictest tier, as the runner reads it


def current_label(task):
    """`<provider>/<model>` from agents/<task>/agent.yaml, or None (no file, unreadable). W7: the adopt line is only
    printed when the pick is NOT already the task's model — adopting the champion again is a refusal, not a step."""
    d = _agent_yaml(task)
    return f"{d.get('provider')}/{d.get('model')}" if d is not None else None


def rows(r):
    return [(c["label"] + (" (snapshot)" if c["snapshot"] else ""), f"{c['held']}/{c['n']}", fmt_usd(c["usd"]), c["tag"],
             c["verdict"] + (" · within noise of the pick" if c["noise"] else "")) for c in r["cands"]]


HEAD = ("candidate", "held-out", "$/10k", "tag", "verdict")


def terminal(r):
    rs = [HEAD] + rows(r); w = [max(len(x[i]) for x in rs) for i in range(5)]
    out = [f"pick — {r['task']}: best {r['best']}/{r['n']}, bar {r['bar']}/{r['n']} (best − {r['bar_gap']})"]
    out += ["  ".join(x[i].ljust(w[i]) for i in range(5)).rstrip() for x in rs]
    out.append(f"pick: {r['pick']['label']}" if r["pick"] else "pick: NONE — no candidate at the bar has a known cost")
    if r["pick"] and r["pick"]["label"] == r.get("current"):   # W7: already the champion — nothing to adopt
        out.append(f"already the task's model (agents/{r['task']}/agent.yaml): nothing to adopt")
    elif r["pick"]:   # W7: the next command, exact (README step 3b)
        out.append(f"adopt it: wilco adopt {r['task']} {r['pick']['label']}")
        above = above_tier(r["pick"].get("provider"), r.get("tier"))
        if above:   # say it here, not only when adopt refuses
            out.append(f"  ({above}: adopt refuses it unless --allow-tier-breach, and then takes no snapshot)")
    out += [f"! {f}" for f in r["flags"]]
    out.append(f"prices: LIST price as of {r['prices_as_of']} ({r['prices_source']}), not metered")
    return "\n".join(out)


def markdown(r):
    out = [f"# pick — `{r['task']}`", "",
           f"Best held-out {r['best']}/{r['n']}; bar {r['bar']}/{r['n']} (best − {r['bar_gap']}). The cheapest candidate at or "
           "above the bar with a known cost takes the task.", "",
           "| " + " | ".join(HEAD) + " |", "|" + "---|" * 5]
    out += ["| " + " | ".join(x) + " |" for x in rows(r)]
    out += ["", f"**Pick: {r['pick']['label']}**" if r["pick"] else "**No pick** — no candidate at the bar has a known cost.", ""]
    out += [f"- {f}" for f in r["flags"]]
    out += [f"- $/10k = `metrics_totals` tokens × LIST price as of {r['prices_as_of']} ({r['prices_source']}) / cases × 10k; "
            "modelled on list price, not metered."]
    return "\n".join(out) + "\n"


def main(argv=None):
    # W7: `wilco pick` in the usage line under the shim (WILCO_PROG)
    ap = argparse.ArgumentParser(prog=f"{os.environ['WILCO_PROG']} pick" if os.environ.get("WILCO_PROG") else None,
                                 description="the pick rule over one task's result files")
    ap.add_argument("task"); ap.add_argument("files", nargs="*")
    ap.add_argument("--prices", default=os.path.join(REPO, "pricing", "prices.json"))
    ap.add_argument("--bar-gap", type=int, default=BAR_GAP)
    ap.add_argument("--out", default=None, help="markdown path (default results/<task>-pick.md)")
    a = ap.parse_args(argv)
    paths = a.files or sorted(glob.glob(os.path.join(REPO, "results", f"{a.task}__*.json")))   # top level only
    try:
        r = build(a.task, paths, json.load(open(a.prices)), a.bar_gap)
    except Refusal as e:
        print(f"pick: REFUSED — {e}", file=sys.stderr); return 2
    print(terminal(r))
    out = a.out or os.path.join(REPO, "results", f"{a.task}-pick.md")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, "w").write(markdown(r)); print(f"wrote {out}")
    return 0 if r["pick"] else 3


if __name__ == "__main__":
    sys.exit(main())
