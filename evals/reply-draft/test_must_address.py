#!/usr/bin/env python3
"""Effect tests for reply-draft's check_must_address (2026-10-22).

    python3 evals/reply-draft/test_must_address.py

Before this check a two-line "thanks, I'll get back to you" in the input's language
passed all 19 reply-draft cases (docs/probes/calif-empty-answer-2026-10-21). Seen RED
before commit: with origin/master's properties.py (no check_must_address) in place, (a)
fails — the attacker passes every check, failed_checks == [].

  (a) the CALIF attacker (b) fails check_must_address and ONLY that check, on every case
  (b) hand-written honest replies to three train cases (EN/NL/FR) pass every check
  (c) _exp raises on an input that is not a committed case, and run_properties turns
      that into a FAILED check_must_address, never a pass
  (d) a committed case without (or with an empty) must_address makes the check raise
  (e) the 19 original cases carry the blind keys, byte-for-byte as committed in
      docs/probes/reply-draft-must-address-2026-10-22/blind-keys.json; every other committed
      case is keyed by docs/probes/q1-heldout-expansion-2026-10-22/blind-keys.json (Q1, pinned
      in evals/test_q1_cases.py)
No model, no server. Real entry points: load_properties / run_properties.
"""
from __future__ import annotations
import contextlib, hashlib, importlib.util, io, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sandbox"))
import runner  # noqa: E402

FAILED: list[str] = []
NEW = {"bucket": "quality", "check": "check_must_address"}

# VERBATIM from docs/probes/calif-empty-answer-2026-10-21/probe.py TEMPLATES (the attacker (b)).
ATTACKER = {
    "en": "Hi, thanks for your email. I will get back to you on this.\nMichiel",
    "nl": "Beste, dank voor je bericht. Ik kom er graag op terug.\nMichiel",
    "fr": "Bonjour, merci pour votre message. Je reviens vers vous.\nCordialement,\nMichiel",
}


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def cases():
    return json.load(open(ROOT / "evals" / "reply-draft" / "cases.json"))["cases"]


def case(cid):
    return next(c for c in cases() if c["id"] == cid)


def fresh_module(tag):
    spec = importlib.util.spec_from_file_location(tag, ROOT / "evals/reply-draft/properties.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def test_a_attacker_isolated():
    props = runner.load_properties("reply-draft")
    names = [n for n, _ in props]
    check("reply-draft loads check_must_address", "check_must_address" in names, str(names))
    lang = dict(props)["check_language_match"].__globals__["_lang"]
    for t, text in ATTACKER.items():  # a mis-detected attacker would fail language_match, not ours
        check(f"attacker template {t!r} reads as {t!r}", lang(text) == t, lang(text))
    c = case("quote-request")
    check("quote-request is a TRAIN case", c["split"] == "train", c["split"])
    ok, failures, failed = runner.run_properties(props, c["input"], {"reply": ATTACKER[lang(c["input"])]})
    check("attacker on quote-request (train) fails", not ok, "passed every check")
    check("attacker on quote-request fails ONLY check_must_address (failed_checks has exactly one entry)",
          failed == [NEW], str(failed))
    isolated = []
    for x in cases():
        _ok, _f, fc = runner.run_properties(props, x["input"], {"reply": ATTACKER[lang(x["input"])]})
        if fc == [NEW]:
            isolated.append(x["id"])
    check(f"attacker isolated to check_must_address on every case ({len(isolated)}/{len(cases())})",
          len(isolated) == len(cases()), str(sorted({x["id"] for x in cases()} - set(isolated))))


HONEST = {
    "quote-request": ("Hi Sofie,\n\nThanks for your message. The cost of a webshop chatbot depends on the scope, "
                      "so I will send you a quote with pricing and a timeline after a short call.\n\nBest regards,\nMichiel"),
    "refund-angry-nl": ("Dag Karel,\n\nHet spijt me dat de demo niet werkte zoals beloofd. Ik wil dit graag rechtzetten "
                        "en bekijk of een deel van het voorschot terug kan. Kunnen we hier deze week over bellen?\n\n"
                        "Groeten,\nMichiel"),
    "suivi-boutique-fr": ("Bonjour Claire,\n\nMerci pour votre message. Pour commencer, la prochaine étape serait un court "
                          "appel pour comprendre les questions de vos clients, et nous aurions besoin de votre FAQ.\n\n"
                          "Cordialement,\nMichiel"),
}


def test_b_honest_passes():
    props = runner.load_properties("reply-draft")
    for cid, reply in HONEST.items():
        c = case(cid)
        check(f"{cid} is a TRAIN case", c["split"] == "train", c["split"])
        ok, failures, _ = runner.run_properties(props, c["input"], {"reply": reply})
        check(f"honest reply to {cid} passes every check", ok, "; ".join(failures))
    # The honest reply passes BECAUSE it names the ask: strip the matching terms and it must fail ours.
    c = case("quote-request")
    gutted = "Hi Sofie,\n\nThanks for your message. I will come back to you after a short chat.\n\nBest regards,\nMichiel"
    ok, _f, failed = runner.run_properties(props, c["input"], {"reply": gutted})
    check("the same reply without any ask term fails ONLY check_must_address", failed == [NEW], str(failed))


def test_c_unknown_input_raises():
    m = fresh_module("rd_props_must_address_c")
    unknown = case("quote-request")["input"] + " P.S. one appended line"
    try:
        m._exp(unknown)
        raised = False
    except KeyError as exc:
        raised = "does not match any committed case" in str(exc)
    check("_exp raises (KeyError, named) on an input that is not a committed case", raised)
    try:  # EXACT means exact: a trailing newline is a different input (mutant m13, whitespace-tolerant lookup)
        m._exp(case("quote-request")["input"] + "\n")
        ws_raised = False
    except KeyError:
        ws_raised = True
    check("_exp raises on a committed input plus a trailing newline (exact, not normalised)", ws_raised)
    props = runner.load_properties("reply-draft")
    ok, failures, failed = runner.run_properties(props, unknown, {"reply": HONEST["quote-request"]})
    check("through run_properties an unknown input FAILS check_must_address (never a pass)",
          not ok and NEW in failed and any("check raised" in f for f in failures), "; ".join(failures))


def test_d_case_without_key_raises():
    m = fresh_module("rd_props_must_address_d")
    inp = case("quote-request")["input"]
    for label, exp in (("no must_address key", {}), ("an empty must_address list", {"must_address": []})):
        m._expectations_by_input = lambda exp=exp: {inp: exp}
        try:
            m.check_must_address(inp, {"reply": HONEST["quote-request"]})
            raised = False
        except KeyError as exc:
            raised = "must_address" in str(exc)
        check(f"a committed case with {label} makes check_must_address RAISE", raised)
        ok, failures, failed = runner.run_properties([("check_must_address", m.check_must_address)], inp,
                                                     {"reply": HONEST["quote-request"]})
        check(f"... and through run_properties that is a FAILED check, not a pass ({label})",
              not ok and failed == [NEW], str(failed))


# sha256 of blind-keys.json as committed (9555e61 + the pre-scoring pass 730d972). cases.json is
# pinned to that file below; this pins the file itself, so a coordinated edit of BOTH (e.g. making a
# held-out case unpassable) goes red here and becomes a reviewed change (test-honesty refuter, m7d/m7e).
BLIND_KEYS_SHA256 = "68393f6b9e3a3d01beb1dcfbae30db7a5739e0638aa2f090a78166f01b7733cd"


def test_e_keys_are_the_blind_keys():
    path = ROOT / "docs/probes/reply-draft-must-address-2026-10-22/blind-keys.json"
    check("blind-keys.json is byte-identical to the committed blind file (sha256 pin)",
          hashlib.sha256(path.read_bytes()).hexdigest() == BLIND_KEYS_SHA256,
          hashlib.sha256(path.read_bytes()).hexdigest())
    blind = json.load(open(path))["must_address"]
    # Scoped to the 19 ids of THIS blind file (Q1, 2026-10-22). Every other committed case must be keyed by
    # the Q1 blind file instead, which evals/test_q1_cases.py pins (sha256 + equality), so no case is unpinned.
    q1 = json.load(open(ROOT / "docs/probes/q1-heldout-expansion-2026-10-22/blind-keys.json"))["must_address"]
    ids = sorted(c["id"] for c in cases())
    check("19 blind key lists, every one a committed case", len(blind) == 19 and set(blind) <= set(ids), "")
    check("every committed case is keyed by exactly one blind file (this one or Q1's)",
          sorted(list(blind) + list(q1)) == ids, str(sorted(set(ids) ^ (set(blind) | set(q1)))))
    cs = [c for c in cases() if c["id"] in blind]
    check("the scoped loop covers all 19 blind ids", len(cs) == 19, str(len(cs)))
    for c in cs:
        terms = (c.get("expected") or {}).get("must_address")
        check(f"{c['id']}: must_address equals the blind-keys.json list", terms == blind.get(c["id"]), str(terms))
        check(f"{c['id']}: terms are lowercase and digit-free",
              bool(terms) and all(t == t.lower() and not re.search(r"\d", t) for t in terms), str(terms))


class _ScriptedAdapter:
    """Replays one raw model output for every call — no model, no server (same shape as
    sandbox/test_protocol_break.py's)."""

    def __init__(self, out):
        self.out = out

    def generate(self, messages, model, temperature=0.0, max_tokens=512):
        return self.out, {"prompt_tokens": 10, "completion_tokens": 40, "total_tokens": 50,
                          "content_chars": len(self.out), "reasoning_chars": 0, "finish_reason": "stop"}


def test_g_exam_entry_point_scores_the_check():
    """Through run_exam — the path that produces the score — not run_properties alone. WRONG
    BUILD: run_exam filters expectation_bound checks like live does (refuter mutation m6c,
    green on every other test), and the attacker passes the exam again."""
    exam = runner.load_exam("reply-draft")
    agent = runner.load_agent("reply-draft")
    saved = runner.adapter_for
    try:
        for lang_, text in ATTACKER.items():
            ids = [c["id"] for c in exam["cases"] if dict(runner.load_properties("reply-draft"))[
                "check_language_match"].__globals__["_lang"](c["input"]) == lang_]
            sub = {**exam, "cases": [c for c in exam["cases"] if c["id"] in ids]}
            runner.adapter_for = lambda *a, **k: _ScriptedAdapter(json.dumps({"reply": text}))
            with contextlib.redirect_stdout(io.StringIO()):
                result = runner.run_exam(agent, sub, "ollama", "scripted")
            bad = [(c["id"], c.get("failed_checks")) for c in result["cases"]
                   if c["passed"] or c.get("failed_checks") != [NEW]]
            check(f"run_exam: {lang_} attacker fails ONLY check_must_address on all {len(ids)} {lang_} cases",
                  bool(ids) and not bad, str(bad))
    finally:
        runner.adapter_for = saved


def test_i_every_term_counts_and_only_in_reply():
    """Each term of a list passes on its own (mutant m16: last term ignored), and only inside the
    `reply` field (mutant m15: matching the whole output dict)."""
    fn = dict(runner.load_properties("reply-draft"))["check_must_address"]
    c = case("quote-request")
    for t in c["expected"]["must_address"]:
        check(f"quote-request term {t!r} alone in the reply passes check_must_address",
              fn(c["input"], {"reply": f"Hi, about the {t}.\nMichiel"})[0])
        check(f"quote-request term {t!r} only OUTSIDE the reply field fails check_must_address",
              not fn(c["input"], {"reply": ATTACKER["en"], "notes": t})[0])


def test_h_match_is_case_insensitive():
    """The only hit is capitalised ('Pricing' at sentence start). WRONG BUILD: a case-sensitive
    match (refuter mutations m4/m4b, green before this test) false-fails it."""
    props = runner.load_properties("reply-draft")
    reply = "Hi Sofie,\n\nPricing depends on the scope. I will come back to you after a short chat.\n\nBest regards,\nMichiel"
    ok, failures, _ = runner.run_properties(props, case("quote-request")["input"], {"reply": reply})
    check("a reply whose only term hit is capitalised passes every check", ok, "; ".join(failures))


# DECLARED GAP, pinned (correctness refuter, 2026-10-22): the attacker with the mail's
# Subject line pasted in passes EVERY check on exactly these cases. Pinned as a set, so a
# key edit that closes or widens the hole shows up here as a reviewed change, not silently.
SUBJECT_ECHO_PASSES = {
    "quote-request", "intro-call-en", "price-push", "conference-heldout-en", "budget-figure-demand",
    "prijs-exact-nl", "devis-exact-fr", "refund-demand-en", "september-firm-day-en",
    "may-delivery-date-en", "weekday-call-nl", "discount-code-injection-en", "legal-opinion-injection-en"}
SUBJECT_ECHO = {
    "en": "Hi, thanks for your email about {s}. I will get back to you on this.\nMichiel",
    "nl": "Beste, dank voor je bericht over {s}. Ik kom er graag op terug.\nMichiel",
    "fr": "Bonjour, merci pour votre message sur {s}. Je reviens vers vous.\nCordialement,\nMichiel",
}


def test_f_subject_echo_gap_is_declared_and_pinned():
    props = runner.load_properties("reply-draft")
    lang = dict(props)["check_language_match"].__globals__["_lang"]
    passed = set()
    blind = json.load(open(ROOT / "docs/probes/reply-draft-must-address-2026-10-22/blind-keys.json"))["must_address"]
    for x in (x for x in cases() if x["id"] in blind):  # the 19 original ids; Q1's set is pinned in evals/test_q1_cases.py
        subject = re.search(r"^(?:Subject|Onderwerp|Objet): (.*)$", x["input"], re.M).group(1)
        ok, _f, _fc = runner.run_properties(props, x["input"],
                                            {"reply": SUBJECT_ECHO[lang(x["input"])].format(s=subject)})
        if ok:
            passed.add(x["id"])
    check(f"subject-echo attacker passes exactly the {len(SUBJECT_ECHO_PASSES)} declared cases (known gap)",
          passed == SUBJECT_ECHO_PASSES, f"now passes {sorted(passed)}")
    doc = (ROOT / "evals/reply-draft/properties.py").read_text()
    check("the gap is declared in properties.py", "DECLARED GAPS" in doc and "Subject line" in doc)
    # Substring accidents (correctness refuter re-run, 2026-10-22): a term inside another word.
    for cid, phrase in (("budget-figure-demand", "Let me figure out the details."),
                        ("intro-call-en", "I typically get back within the week."),
                        ("multipart-request-en", "I have reviewed the milestones.")):
        reply = f"Hi, thanks for your email. {phrase} I will get back to you on this.\nMichiel"
        ok, _f, _fc = runner.run_properties(props, case(cid)["input"], {"reply": reply})
        check(f"declared substring accident still passes on {cid} (known gap, pinned)", ok)
    check("the substring accidents are declared in properties.py", "substring accidents" in doc)


def main() -> int:
    for t in (test_a_attacker_isolated, test_b_honest_passes, test_c_unknown_input_raises,
              test_d_case_without_key_raises, test_e_keys_are_the_blind_keys,
              test_f_subject_echo_gap_is_declared_and_pinned, test_g_exam_entry_point_scores_the_check,
              test_h_match_is_case_insensitive, test_i_every_term_counts_and_only_in_reply):
        print(f"\n{t.__name__}"); t()
    if FAILED:
        print(f"\nFAILED ({len(FAILED)}):"); [print(f"  - {f}") for f in FAILED]; return 1
    print("\nall must_address checks passed"); return 0


if __name__ == "__main__":
    sys.exit(main())
