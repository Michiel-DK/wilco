"""Q6(b) — CLAUDE.md gotcha 18: a bake-off strategy must never receive the answer key.

Why: `cmd_bakeoff` called `fn(ctx, case)` with the full committed case dict, so
`case["expected"]` was live-readable inside every function in sandbox/strategies.py and
nothing in the instrument stopped a "defensive top-up" from the key. The fix hands the
strategy a COPY of the case without "expected"; the scorer and the limit column keep using
the original case.

Drives the REAL `runner.cmd_bakeoff` (gotcha 5: no hand-copied loop) with the agent/exam/
properties/adapter loaders monkeypatched and runner.ROOT pointed at a temp dir (the command
writes results/bakeoff__*.json). No inference, no network. cmd_bakeoff catches every
per-case Exception and records checks=['error:<Type>'], so nothing raises out of it: the
strip is witnessed by (i) a sentinel list written by the strategy and (ii) the printed
rows carrying error:KeyError.

[W] = RED on the unfixed runner.py, [C] = green on both sides (control).
"""
import argparse
import contextlib
import io
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sandbox"))
import runner  # noqa: E402
import strategies  # noqa: E402

FAILED = []


def check(label, ok, extra=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {extra}" if not ok and extra else ""))
    if not ok:
        FAILED.append(label)


@contextlib.contextmanager
def patched(mod, **attrs):
    saved = {k: getattr(mod, k) for k in attrs}
    try:
        for k, v in attrs.items():
            setattr(mod, k, v)
        yield
    finally:
        for k, v in saved.items():
            setattr(mod, k, v)


CASES = [
    {"id": "c1", "split": "train", "input": "x" * 100, "expected": {"max_ratio": 0.5}},
    {"id": "c2", "split": "heldout", "input": "y" * 40, "expected": {"max_ratio": 0.25}},
    {"id": "c3", "split": "heldout", "input": "z" * 10, "expected": {}},
]
N = len(CASES)


def _prop(input_text, output):
    return (output or {}).get("recap") == "fixed", "recap must be 'fixed'"


_prop.bucket = "quality"
PROPS = [("check_fixed", _prop)]

SEEN = []          # one bool per strategy call: was "expected" in the case it received?


def _reader(ctx, case):
    SEEN.append("expected" in case)
    must = case["expected"]            # KeyError once the key is stripped
    return {"recap": "fixed" if must is not None else "no"}, []


def _blind(ctx, case):
    return {"recap": "fixed"}, [{"total_tokens": 1}]


def _run(strategy_name):
    """Run the real cmd_bakeoff for one registered strategy; return (rc, stdout, rows)."""
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        over = dict(load_agent=lambda n: {"name": n, "model": "m", "provider": "stub"},
                    load_exam=lambda n: {"cases": [dict(c) for c in CASES]},
                    load_properties=lambda n: PROPS,
                    adapter_for=lambda agent, provider=None, timeout=None: object(),
                    ROOT=pathlib.Path(tmp))
        args = argparse.Namespace(agent="fx", model=None, timeout=1, strategies=strategy_name,
                                  filter_agent=None, long_min=50)
        with patched(runner, **over), contextlib.redirect_stdout(out):
            rc = runner.cmd_bakeoff(args)
    text = out.getvalue()
    rows = [ln for ln in text.splitlines() if re.match(r"\s+\[(PASS|FAIL)\] c\d", ln)]
    return rc, text, rows


strategies.STRATEGIES["q6-reader"] = _reader
strategies.STRATEGIES["q6-blind"] = _blind
try:
    print("\n(1) a strategy that reads case['expected'] no longer can")
    SEEN.clear()
    rc, text, rows = _run("q6-reader")
    check("[C] cmd_bakeoff ran to completion (rc 0)", rc == 0, f"rc={rc}")
    check("[C] the strategy was called once per case", len(SEEN) == N, str(SEEN))
    check("[W] the strategy never saw 'expected' (sentinel list all False)",
          len(SEEN) == N and not any(SEEN), str(SEEN))
    check("[W] every case row records error:KeyError for the reader strategy",
          len(rows) == N and all("error:KeyError" in r for r in rows), "\n".join(rows))

    check("[W] an erroring case reports out=0 (no UnboundLocalError / stale output carried over)",
          len(rows) == N and all("out=   0" in r for r in rows), "\n".join(rows))

    print("\n(2) a strategy that never reads the key scores exactly as before")
    rc, text, rows = _run("q6-blind")
    # Pinned on origin/master (same fake): the strategy returns recap 'fixed' for every
    # case, so all pass; `limit` is derived from the ORIGINAL case's expected.max_ratio.
    want_rows = [
        "  [PASS] c1                     train    in=  100 out=   5 limit=  50  ",
        "  [PASS] c2                     heldout  in=   40 out=   5 limit=  10  ",
        "  [PASS] c3                     heldout  in=   10 out=   5 limit=   -  ",
    ]
    check("[C] per-case verdict rows identical to the origin/master measurement "
          "(scorer and limit column still see 'expected')", rows == want_rows,
          "\n".join(rows))
    check("[C] totals line: train 1/1, heldout 2/2",
          re.search(r"q6-blind\s+1/1\s+2/2", text) is not None, text[-400:])
finally:
    strategies.STRATEGIES.pop("q6-reader", None)
    strategies.STRATEGIES.pop("q6-blind", None)

check("[C] throwaway strategies removed from the registry",
      "q6-reader" not in strategies.STRATEGIES and "q6-blind" not in strategies.STRATEGIES)


def main() -> int:
    print(f"\n{'FAILED: ' + ', '.join(FAILED) if FAILED else 'all green'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
