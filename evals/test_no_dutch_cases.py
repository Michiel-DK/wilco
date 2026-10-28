#!/usr/bin/env python3
"""No new non-English exam case (operator rule since 2026-07-30, repeated 2026-10-28: "never NL").

    python3 evals/test_no_dutch_cases.py

The rule lived in a memory file and the sprint-map; it was broken on 23 Oct (PR #121 added five Dutch
recap cases) and surfaced outward on 28 Oct (a Dutch inbox on the site's hero). This file makes it a
RED test instead of something the operator has to say again.

  (a) every case in every exam (enumerated through runner._all_agents + runner.load_exam, the real
      entry point) that reads as Dutch/French-dominant — as a WHOLE or in ANY CHUNK (an item of an
      inbox, a turn of a thread, a phrase in `expected`; EVERY string in the case is read, not just
      `input`, because the runner sends `turns` to the model) — is in LEGACY below, a FROZEN register
      of the 40 pre-rule cases. Anything else is RED, by (exam, id). The register is pinned at exactly
      40 and every entry must still read non-English: translating or retiring a case means deleting
      its line AND lowering the pin, so a change in either direction is a visible edit to this file.
      Scope (declared, not fixed): a Dutch chunk under 3 stopword hits, or a language outside NL/FR
      (German scores 0/0), is not seen. The rule's purpose is a whole mail, inbox or thread going out
      in Dutch; that is what this catches.
  (b) recap-en is the recap exam translated: same ids, same splits, same expected blocks except
      max_ratio, which is re-chosen so the ABSOLUTE char budget per case is IDENTICAL (int() lands on
      the same number); every must_mention term is present in the English input; every digit token
      survives; zero non-English cases.
  (c) the two graders agree on fixed outputs: the champion's 16 committed held-out recap outputs
      (docs/probes/laptop-examples-2026-10-28, 28 Oct 2026, produced from the DUTCH inputs) scored
      through runner.run_exam on recap-en give the SAME per-case pass/fail and failed_checks as on
      recap. What this pins: drift in the properties.py copy or in the budgets. What it does NOT show:
      that a model behaves the same on English input — that is the snapshot's job.
  (d) A2, seen RED on the defect, through the same enumeration path under a patched runner.ROOT:
      a mail entirely in Dutch; an inbox 23 of 32 items Dutch (a whole-text count alone let 22 of 32
      through — refuter, 28 Oct); a multi-turn case whose `turns` are Dutch behind an English `input`
      label; an `expected` block with Dutch phrases — each flagged by exactly its id; an English
      control is not.
"""
from __future__ import annotations
import contextlib, io, json, re, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
import runner  # noqa: E402

FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


# ---- the detector -------------------------------------------------------------------------------
# Stopword counts, whole words, case-insensitive. Non-English iff >= 3 NL/FR hits AND more NL/FR than
# EN hits. Deliberately crude: it must never be the thing a case is tuned against; its only job is to
# notice a whole mail or transcript written in Dutch (or French — the FR legacy cases trip it too, and
# that is wanted: the rule is English-first, PT/ES by decision, nothing else by accident).
_NONEN = re.compile(r"\b(de|het|een|voor|van|wij|onze|niet|wordt|graag|groeten|bijlage|factuur|facturen|"
                    r"dossier|je|jouw|jullie|geen|nodig|bericht|deze|maand|kan|dag|beste|bedankt|met|"
                    r"vriendelijke|bonjour|merci|nous|vous|votre|notre|pour|avec|cette|est|sont)\b", re.I)
_EN = re.compile(r"\b(the|and|for|please|invoice|regards|attached|meeting|we|our|you|your|is|are|this|"
                 r"that|with|from|can|thanks|hi|dear)\b", re.I)


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)


def case_text(case: dict) -> str:
    """EVERY string in the case (input, turns, expected, ...) — on multi-turn exams the runner sends
    `turns`, not `input`, and a key can carry language too. Joined with blank lines so each string
    is its own chunk below."""
    return "\n\n".join(_strings({k: v for k, v in case.items() if k not in ("id", "split", "note")}))


_CHUNK = re.compile(r"\n\s*\n|--- item \d+ ---")


def _dominant(text: str) -> bool:
    a, b = len(_NONEN.findall(text)), len(_EN.findall(text))
    return a >= 3 and a > b


def non_english(text: str) -> bool:
    """Non-English as a WHOLE, or in ANY chunk (an inbox item, a turn, a phrase). A whole-text count
    alone let an inbox with 22 of 32 Dutch items through (refuter, 28 Oct)."""
    return _dominant(text) or any(_dominant(ch) for ch in _CHUNK.split(text))


def non_english_cases() -> set[tuple[str, str]]:
    """Every (exam, id) that reads non-English, through the runner's own enumeration."""
    found = set()
    for exam in runner._all_agents():
        for c in runner.load_exam(exam)["cases"]:
            if non_english(case_text(c)):
                found.add((exam, c["id"]))
    return found


# ---- the frozen register (40 on 2026-10-28). Remove lines; never add one without a review. -------
LEGACY: frozenset[tuple[str, str]] = frozenset({
    ("email-triage", "client-domain-newsletter-nl"),
    ("email-triage", "fr-networking-coffee"),
    ("email-triage", "fr-tax-authority-documents"),
    ("email-triage", "nl-client-bug-buried"),
    ("recap", "amounts-and-dates"),
    ("recap", "amounts-at-length"),
    ("recap", "automated-but-actionable"),
    ("recap", "buried-critical"),
    ("recap", "buried-critical-xl"),
    ("recap", "busy-day-standard"),
    ("recap", "compression-heavy"),
    ("recap", "dependency-delivery-vs-install"),
    ("recap", "long-day-heldout-xl"),
    ("recap", "long-day-train-2"),
    ("recap", "long-day-train-3"),
    ("recap", "long-day-train-xl"),
    ("recap", "long-quiet-day"),
    ("recap", "meeting-moved-date-decoy"),
    ("recap", "near-duplicate-invoices"),
    ("recap", "quiet-day-automated"),
    ("recap", "quiet-day-big-amount-decoy"),
    ("recap", "quiet-day-newsletters"),
    ("recap", "quiet-day-with-receipt"),
    ("recap", "rounding-bait"),
    ("recap", "two-urgent-among-noise"),
    ("recap", "very-long-day"),
    ("reply-draft", "budget-gap-nl"),
    ("reply-draft", "devis-exact-fr"),
    ("reply-draft", "fr-workshop-reschedule"),
    ("reply-draft", "invoice-hours-nl-buried"),
    ("reply-draft", "prijs-exact-nl"),
    ("reply-draft", "refund-angry-nl"),
    ("reply-draft", "suivi-boutique-fr"),
    ("reply-draft", "weekday-call-nl"),
    ("task-intake", "heavy-nl-crm-question"),
    ("task-intake", "reply-fr-reponds"),
    ("task-intake", "reply-instruction-wins-newsletter"),
    ("task-intake", "reply-nl-antwoord"),
    ("task-intake", "triage-sort-accountant"),
    ("task-intake", "triage-urgent-or-not-newsletter"),
})


def test_a_no_new_non_english_case():
    found = non_english_cases()
    offenders = sorted(found - LEGACY)
    check("every non-English case is in the frozen LEGACY register (no new Dutch/French case)",
          not offenders, f"NEW non-English case(s): {offenders}")
    gone = sorted(LEGACY - found)
    check("every LEGACY entry still reads non-English (translated/retired = delete its line AND lower the pin)",
          not gone, f"stale: {gone[:5]}")
    check("the register is pinned at exactly 40 (growth or shrink is a visible edit to this number)",
          len(LEGACY) == 40, str(len(LEGACY)))
    check("the register is not empty and the suite still enumerates (detector not inert)",
          len(found) >= 1 and len(runner._all_agents()) >= 8, f"found={len(found)}")


def test_b_recap_en_is_recap_translated():
    nl = {c["id"]: c for c in runner.load_exam("recap")["cases"]}
    en = {c["id"]: c for c in runner.load_exam("recap-en")["cases"]}
    check("recap-en has exactly recap's ids", set(nl) == set(en), f"{sorted(set(nl) ^ set(en))}")
    check("recap-en keeps recap's splits", all(nl[i]["split"] == en[i]["split"] for i in nl))
    same_keys = all({k: v for k, v in nl[i]["expected"].items() if k != "max_ratio"}
                    == {k: v for k, v in en[i]["expected"].items() if k != "max_ratio"} for i in nl)
    check("expected blocks identical except max_ratio", same_keys)
    budget_ok, off = True, []
    for i in nl:
        if "max_ratio" in nl[i]["expected"]:
            b_nl = int(len(nl[i]["input"]) * float(nl[i]["expected"]["max_ratio"]))
            b_en = int(len(en[i]["input"]) * float(en[i]["expected"]["max_ratio"]))
            if b_nl != b_en:
                budget_ok = False; off.append((i, b_nl, b_en))
    check("max_ratio re-chosen so the absolute char budget per case is IDENTICAL (int() lands on the same number)", budget_ok, str(off[:3]))
    miss = [(i, t) for i in en for t in en[i]["expected"].get("must_mention", []) if str(t).lower() not in en[i]["input"].lower()]
    check("every must_mention term is present in the English input", not miss, str(miss[:3]))
    num = re.compile(r"\d[\d.,:/-]*\d|\d")
    diff = [i for i in nl if sorted(num.findall(nl[i]["input"])) != sorted(num.findall(en[i]["input"]))]
    check("every digit token survives translation (check_grounded sees the same figures)", not diff, str(diff[:3]))
    check("recap-en has zero non-English cases", not [i for i in en if non_english(case_text(en[i]))])
    check("recap (Dutch) is entirely in LEGACY — the register names it, nothing else may be added there",
          all(("recap", i) in LEGACY for i in nl if non_english(case_text(nl[i]))))


class _Replay:
    def __init__(self, by_input): self.by_input = by_input
    def generate(self, messages, model, temperature=0.0, max_tokens=512):
        out = self.by_input[messages[-1]["content"]]
        return out, {"prompt_tokens": 10, "completion_tokens": 40, "total_tokens": 50,
                     "content_chars": len(out), "reasoning_chars": 0, "finish_reason": "stop"}


def _score(exam_name: str, outputs: dict) -> dict:
    exam = runner.load_exam(exam_name); agent = runner.load_agent(exam_name)
    cases = {c["id"]: c for c in exam["cases"]}
    sub = {**exam, "cases": [cases[i] for i in outputs]}
    by_input = {cases[i]["input"]: json.dumps(o, ensure_ascii=False) for i, o in outputs.items()}
    saved = runner.adapter_for
    try:
        runner.adapter_for = lambda *a, **k: _Replay(by_input)
        with contextlib.redirect_stdout(io.StringIO()):
            result = runner.run_exam(agent, sub, "ollama", "scripted")
    finally:
        runner.adapter_for = saved
    got = {c["id"]: (c["passed"], sorted(f["check"] for f in (c.get("failed_checks") or []))) for c in result["cases"]}
    if set(got) != set(outputs):
        raise AssertionError(f"run_exam scored {sorted(got)}, expected exactly {sorted(outputs)}")
    return got


def test_c_translation_preserves_every_verdict():
    p = ROOT / "docs/probes/laptop-examples-2026-10-28/results/recap__ollama__gemma4_e4b-it-qat.json"
    stored = {c["id"]: c["got"] for c in json.loads(p.read_text())["cases"]}
    check("the committed 28 Oct held-out recap outputs exist (16)", len(stored) == 16, str(len(stored)))
    a = _score("recap", stored); b = _score("recap-en", stored)
    flips = sorted(i for i in stored if a[i] != b[i])
    check("same per-case verdict + failed_checks on recap and recap-en through run_exam (0 flips)",
          not flips, f"flips: {[(i, a[i], b[i]) for i in flips][:3]}")
    check("the replay is not vacuous: at least one stored output fails on both", any(not a[i][0] for i in a))


def test_d_seen_red_on_a_dutch_mutant():
    nl_mail = ("From: info@peeters-transport.be\nSubject: probleem met de facturatiemodule\n"
               "Sinds de update van vorige week worden onze facturen dubbel aangemaakt. Dit moet dringend\n"
               "opgelost worden, we kunnen zo niet verder factureren. Met vriendelijke groet, Els Peeters\n")
    en_mail = ("From: info@peeters-transport.be\nSubject: problem with the invoicing module\n"
               "Since last week's update our invoices are being created twice. This needs to be fixed\n"
               "urgently, we cannot keep invoicing like this. Kind regards, Els Peeters\n")
    # the 28 Oct shape: an inbox MOSTLY Dutch — 23 of 32 items from the Dutch exam, 9 from the English one
    split = lambda s: re.split(r"(?=--- item \d+ ---)", s)
    nl_xl = split(next(c["input"] for c in runner.load_exam("recap")["cases"] if c["id"] == "long-day-heldout-xl"))
    en_xl = split(next(c["input"] for c in runner.load_exam("recap-en")["cases"] if c["id"] == "long-day-heldout-xl"))
    mixed_inbox = "".join(nl_xl[:23] + en_xl[23:])
    turns_nl = ["Hoi, in welke fase zit onze deal met Bakkerij Janssens?",
                "En wie is daar onze contactpersoon, en hoe bereik ik die?",
                "Herinner mij even: wat willen zij precies van ons, en is er een deadline?"]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "agents" / "fx").mkdir(parents=True); (root / "evals" / "fx").mkdir(parents=True)
        (root / "agents" / "fx" / "agent.yaml").write_text("name: fx\nprovider: ollama\nmodel: x\ntier: local\n")
        cases = {"cases": [
            {"id": "mutant-nl", "split": "train", "input": nl_mail, "expected": {}},
            {"id": "mutant-inbox-23-of-32-nl", "split": "train", "input": mixed_inbox, "expected": {}},
            {"id": "mutant-turns-nl", "split": "train", "input": "What stage? | contact? | deadline?", "turns": turns_nl, "expected": {}},
            {"id": "mutant-expected-nl", "split": "train", "input": en_mail,
             "expected": {"must_mention": ["de factuur van deze maand", "betaling voor vrijdag", "met vriendelijke groeten"]}},
            {"id": "control-en", "split": "train", "input": en_mail, "expected": {"must_mention": ["Peeters"]}},
        ]}
        (root / "evals" / "fx" / "cases.json").write_text(json.dumps(cases))
        saved = runner.ROOT
        try:
            runner.ROOT = root
            found = non_english_cases()
        finally:
            runner.ROOT = saved
    want = {("fx", "mutant-nl"), ("fx", "mutant-inbox-23-of-32-nl"), ("fx", "mutant-turns-nl"), ("fx", "mutant-expected-nl")}
    check("RED on the defect: all four Dutch mutants flagged by exactly their ids (whole mail, mostly-Dutch inbox, Dutch turns, Dutch expected)",
          found == want, f"found {sorted(found)} want {sorted(want)}")
    check("the mutants are outside LEGACY, so test (a) would go red on them", bool(found) and found.isdisjoint(LEGACY))
    check("an English control case is not flagged", ("fx", "control-en") not in found)


def main() -> int:
    for t in (test_a_no_new_non_english_case, test_b_recap_en_is_recap_translated,
              test_c_translation_preserves_every_verdict, test_d_seen_red_on_a_dutch_mutant):
        print(t.__name__); t()
    print(f"\n{'FAILED: ' + ', '.join(FAILED) if FAILED else 'all green'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
