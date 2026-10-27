#!/usr/bin/env python3
"""Q1 / N-A8 (2026-10-22): the 26 new BLIND held-out cases on the four small exams.

    python3 evals/test_q1_cases.py

Isolation without inference (CLAUDE.md gotcha 3), through the REAL entry point (gotcha 5):
every fixture below is scored by runner.run_exam with a scripted adapter that replays a
hand-written output for its case — the path that produces the score, in each exam's own
mode (fields / labels / properties). No model, no server.

  (a) composition: each exam loads through runner.load_exam with no duplicate id and no
      duplicate input; the 26 ids exist, are held-out, and every held-out count is >= 15
  (b) HONEST: a hand-written correct output passes every check (recap: one EN and one NL
      recap per case, so the must_mention terms are shown to be language-neutral)
  (c) WRONG: the case's own tempting error fails, and failed_checks names EXACTLY one
      check — the one the case exists to exercise
  (d) PRESENT, UNGRADED: traps the existing checks cannot see (recap: a swapped date, a merged
      item, a swapped invoice status; reply-draft: an invented French weekday or date, a merged
      project, a new figure below 10) are pinned as PASSING, so a later check that
      starts grading them shows up here as a reviewed change, not silently
  (e) reply-draft: the new must_address keys equal the Q1 blind-keys file (sha256 pinned),
      are lowercase and digit-free, each input reads as one language, and the
      subject-echo attacker's pass set on the new cases is pinned (declared gap,
      evals/reply-draft/properties.py DECLARED GAPS)
  (f) recap inputs stay far under the champion's 4,096-token default window (gotcha 16)
"""
from __future__ import annotations
import contextlib, hashlib, io, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
import runner  # noqa: E402

FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


NEW_IDS = {
    "expense-categorization": ["aws-direct-debit-buried", "amazon-marketplace-dock", "fuel-station-decoy-number",
                               "atm-cash-withdrawal", "coworking-membership-monthly",
                               "proximus-oneoff-installation", "nmbs-monthly-pass"],
    "email-triage": ["nl-client-bug-buried", "fr-tax-authority-documents", "stripe-payout-notice",
                     "client-domain-newsletter-nl", "calendar-accept-notice", "proposal-accept-conditional",
                     "fr-networking-coffee"],
    "recap": ["dependency-delivery-vs-install", "near-duplicate-invoices", "quiet-day-big-amount-decoy",
              "automated-but-actionable", "buried-last-en", "meeting-moved-date-decoy"],
    "reply-draft": ["invoice-hours-nl-buried", "two-asks-dependency-en", "fr-workshop-reschedule",
                    "contract-signed-fyi-en", "budget-gap-nl", "two-projects-near-duplicate-en"],
}
# Held-out counts on origin/master 46571b9, before this lane (sprint-map Q1 row).
HELDOUT_BEFORE = {"expense-categorization": 9, "email-triage": 13, "recap": 10, "reply-draft": 12}

J = json.dumps
# id -> (honest outputs, wrong output, the ONE check the wrong output must fail)
EXPENSE = {
    "aws-direct-debit-buried": ({"category": "software", "recurring": True}, {"category": "hardware", "recurring": True}),
    "amazon-marketplace-dock": ({"category": "hardware", "recurring": False}, {"category": "software", "recurring": False}),
    "fuel-station-decoy-number": ({"category": "travel", "recurring": False}, {"category": "other", "recurring": False}),
    "atm-cash-withdrawal": ({"category": "other", "recurring": False}, {"category": "office", "recurring": False}),
    "coworking-membership-monthly": ({"category": "office", "recurring": True}, {"category": "travel", "recurring": True}),
    "proximus-oneoff-installation": ({"category": "telecom", "recurring": False}, {"category": "telecom", "recurring": True}),
    "nmbs-monthly-pass": ({"category": "travel", "recurring": True}, {"category": "travel", "recurring": False}),
}
EMAIL = {  # id -> (true label, the label the case's pull points at)
    "nl-client-bug-buried": ("reply_now", "reply_later"),
    "fr-tax-authority-documents": ("reply_now", "ignore"),
    "stripe-payout-notice": ("ignore", "reply_now"),
    "client-domain-newsletter-nl": ("ignore", "reply_now"),
    "calendar-accept-notice": ("ignore", "reply_now"),
    "proposal-accept-conditional": ("reply_now", "reply_later"),
    "fr-networking-coffee": ("reply_later", "reply_now"),
}
RECAP = {
    "dependency-delivery-vs-install": (
        [{"recap": "Koen Lambert expects the kiosk in the showroom on 10 november for the press opening and asks you to confirm. "
                   "Elektro Claeys delays the two tablets of order 7731 to 14 november.", "nothing_important": False},
         {"recap": "Koen Lambert rekent op de kiosk in de showroom op 10 november en vraagt een bevestiging. "
                   "Elektro Claeys levert de tablets van bestelling 7731 pas op 14 november.", "nothing_important": False}],
        {"recap": "Koen Lambert expects the kiosk in the showroom on 10 november and asks you to confirm.", "nothing_important": False},
        "check_coverage"),
    "near-duplicate-invoices": (
        [{"recap": "Drukkerij Vandenberghe: invoice 2026-131 of 312.40 EUR is still open (due 30 september); invoice 2026-118 is paid.",
          "nothing_important": False},
         {"recap": "Drukkerij Vandenberghe: factuur 2026-131 van 312.40 EUR staat nog open (vervaldag 30 september); 2026-118 is betaald.",
          "nothing_important": False}],
        {"recap": "Drukkerij Vandenberghe: invoice 2026-118 of 85.00 EUR is overdue.", "nothing_important": False},
        "check_coverage"),
    "quiet-day-big-amount-decoy": (
        [{"recap": "Nothing important today - an announced VAT direct debit, a newsletter, a backup notice and promotions.",
          "nothing_important": True},
         {"recap": "Niets belangrijks vandaag - een aangekondigde btw-domiciliëring, een nieuwsbrief, een back-up en promoties.",
          "nothing_important": True}],
        {"recap": "The bank will debit 2,450.00 EUR for the VAT return on 20 oktober.", "nothing_important": False},
        "check_abstention"),
    "automated-but-actionable": (
        [{"recap": "Combell refused the automatic hosting payment (card expired): update the card before 3 november or the website is suspended. "
                   "The rest is automated notices and a newsletter.", "nothing_important": False},
         {"recap": "Combell weigerde de betaling van het hostingpakket (kaart verlopen): betaalgegevens bijwerken voor 3 november, "
                   "anders wordt de website opgeschort. Verder enkel automatische berichten.", "nothing_important": False}],
        {"recap": "Nothing important today - automated notices, including Combell's payment notice.", "nothing_important": True},
        "check_abstention"),
    "buried-last-en": (
        [{"recap": "Hendrickx Interiors gave formal notice on the chatbot support contract, effective 31 December. "
                   "Everything else is newsletters, receipts and automated notices.", "nothing_important": False},
         {"recap": "Hendrickx Interiors zegt het supportcontract voor de chatbot op, vanaf 31 December. "
                   "Verder nieuwsbrieven, ontvangstbewijzen en automatische berichten.", "nothing_important": False}],
        {"recap": "A newsletter, a Railway receipt, Dependabot pull requests, backups and promotions.", "nothing_important": False},
        "check_coverage"),
    "meeting-moved-date-decoy": (
        [{"recap": "Sarah Wouters asks to move the workshop from 12 november to 19 november, same hour. Tom Maes thanks you for the demo.",
          "nothing_important": False},
         {"recap": "Sarah Wouters vraagt de workshop van 12 november te verplaatsen naar 19 november, zelfde uur. Tom Maes bedankt voor de demo.",
          "nothing_important": False}],
        {"recap": "Tom Maes thanks you for the demo and answers next week.", "nothing_important": False},
        "check_coverage"),
}
# PRESENT, UNGRADED (d): both numbers are in the source, so check_grounded passes; check_coverage is presence-only.
RECAP_UNGRADED = {
    "dependency-delivery-vs-install": {"recap": "Koen Lambert expects the kiosk on 14 november; Elektro Claeys delivers the tablets on 10 november.",
                                       "nothing_important": False},
    "meeting-moved-date-decoy": {"recap": "Sarah Wouters confirms the workshop on 12 november; Tom Maes also asks to move it.", "nothing_important": False},
    "near-duplicate-invoices": {"recap": "Drukkerij Vandenberghe: invoice 2026-118 is overdue; invoice 2026-131 of 312.40 EUR is paid.",
                                "nothing_important": False},
}
# Honest outputs written by the refuters (2026-10-22) that false-failed an earlier key. The keys were changed
# blind (no model had been run) to accept them, so these are REGRESSION pins for that fix, NOT independent
# evidence that the keys are right: they were fitted (round-2 refuter, test honesty). Residual false fails of
# the any-of keys are declared in the PR body.
RECAP_HONEST_INDEPENDENT = {
    "dependency-delivery-vs-install": {"recap": "Koen Lambert wants the kiosk in the showroom on 10 november for the press opening. "
                                                "The two tablets of order 7731 are delayed to 14 november instead of 3 november.",
                                       "nothing_important": False},
    "automated-but-actionable": {"recap": "Action needed: Combell could not charge your expired card. Update your payment details "
                                          "before 3 november or your website will be suspended.", "nothing_important": False},
}
REPLY = {
    "invoice-hours-nl-buried": (
        "Dag Griet,\n\nDank voor je bericht, fijn dat het team enthousiast is. Je hebt gelijk, ik ga factuur 2026-052 nakijken "
        "en pas ze aan als er te veel uren op staan. Ik laat je zo snel mogelijk iets weten.\n\nGroeten,\nMichiel",
        "Dag Griet,\n\nDank voor je bericht. Ik pas de factuur aan, het nieuwe bedrag wordt 640 EUR.\n\nGroeten,\nMichiel",
        "check_no_invented_numbers"),
    "two-asks-dependency-en": (
        "Hi Nadia,\n\nGood question. Yes, the assistant can also answer in French. I will check whether adding it moves the "
        "go-live or whether it is better as a second step, and come back to you with a clear answer.\n\nBest regards,\nMichiel",
        "Hi Nadia,\n\nYes, French is possible, and the go-live will move to Friday.\n\nBest regards,\nMichiel",
        "check_no_invented_dates"),
    "fr-workshop-reschedule": (
        "Bonjour Hélène,\n\nPas de souci, j'espère que vos vendeuses vont vite se rétablir. Je vous propose de reporter l'atelier "
        "à une matinée qui vous convient et je vous envoie quelques possibilités très vite.\n\nCordialement,\nMichiel",
        "Bonjour Hélène,\n\nMerci pour votre message. Je reviens vers vous.\n\nCordialement,\nMichiel",
        "check_must_address"),
    "contract-signed-fyi-en": (
        "Hi Bart,\n\nThank you for sending the signed contract, I have filed it. Looking forward to the kick-off.\n\nKind regards,\nMichiel",
        "Hi Bart,\n\nThank you for the signed contract. See you at the kick-off on Monday.\n\nKind regards,\nMichiel",
        "check_no_invented_dates"),
    "budget-gap-nl": (
        "Dag Dirk,\n\nDank voor je bericht. Ik bekijk graag hoe we de scope kunnen aanpassen zodat het binnen je budget past, "
        "bijvoorbeeld zonder de koppeling met de kassa. Ik kom hier deze week op terug.\n\nGroeten,\nMichiel",
        "Dag Dirk,\n\nDank voor je bericht. Binnen je budget kan ik het doen voor 4.350 EUR.\n\nGroeten,\nMichiel",
        "check_no_invented_numbers"),
    "two-projects-near-duplicate-en": (
        "Hi Ilse,\n\nThanks, good to hear the webshop bot runs fine. The onboarding assistant for new store staff is almost "
        "done; I will send you a short list of what I still need from your side to finish it.\n\nBest regards,\nMichiel",
        "Hi Ilse,\n\nGreat to hear the webshop bot is running fine. I will get back to you on this.\n\nBest regards,\nMichiel",
        "check_must_address"),
}
# PRESENT, UNGRADED (d): a French weekday is outside check_no_invented_dates' EN/NL vocabulary (declared gap).
REPLY_UNGRADED = {
    "fr-workshop-reschedule": "Bonjour Hélène,\n\nPas de souci. Je vous propose de reporter l'atelier à mardi matin.\n\nCordialement,\nMichiel",
    "two-projects-near-duplicate-en": ("Hi Ilse,\n\nThe onboarding assistant is almost done, and I will also add new features to the "
                                       "webshop bot next.\n\nBest regards,\nMichiel"),  # merges the two projects: ungraded
    "invoice-hours-nl-buried": "Dag Griet,\n\nIk heb de factuur nagekeken, er staan 4 uren te veel op.\n\nGroeten,\nMichiel",  # < 10 allowance
}
# Dodges that must FAIL check_must_address alone: the round-2 refuter showed 'matin' / 'proposition' let #1/#2 pass; the round-3 refuter
# showed round 2's own 'autre moment' / 'disponibilit' let #3/#4 pass (fixed post-hoc under the operator's signature, 23 Oct).
REPLY_DODGES = {"fr-workshop-reschedule": ["Bonjour, merci pour votre message. Je reviens vers vous demain matin.\nCordialement,\nMichiel",
                                           "Bonjour, merci pour votre message. Je reviens vers vous avec une proposition.\nCordialement,\nMichiel",
                                           "Bonjour Hélène,\n\nMerci pour votre message. Je reviens vers vous selon mes disponibilités.\n\nCordialement,\nMichiel",
                                           "Bonjour Hélène,\n\nMerci pour votre message. Je vous réponds plus en détail à un autre moment.\n\nCordialement,\nMichiel"]}
REPLY_UNGRADED_FR_MONTH = "Bonjour Hélène,\n\nPas de souci. Je vous propose de reporter l'atelier au 5 novembre.\n\nCordialement,\nMichiel"
REPLY_HONEST_INDEPENDENT = {  # refuter-written, keys fitted to them: regression pins, see RECAP_HONEST_INDEPENDENT
    "fr-workshop-reschedule": ["Bonjour Hélène,\n\nJe reviens vers vous rapidement avec des propositions pour une autre date, "
                               "de préférence le matin.\n\nCordialement,\nMichiel",
                               "Bonjour Hélène,\n\nNous pouvons déplacer la séance; je vous envoie des options rapidement.\n\nCordialement,\nMichiel",
                               "Bonjour Hélène,\n\nPas de souci. Je vous envoie demain quelques dates un matin, dites-moi ce qui vous convient.\n\nCordialement,\nMichiel",
                               "Bonjour Hélène,\n\nPas de souci. Je vous propose quelques matins la semaine prochaine pour refaire la session.\n\nCordialement,\nMichiel"],
    "two-projects-near-duplicate-en": ["Hi Ilse,\n\nThe HR assistant is well underway; I will send your HR manager a status update.\n\n"
                                       "Best regards,\nMichiel"],
    "contract-signed-fyi-en": ["Hi Bart,\n\nThanks, well received! Looking forward to getting started.\n\nKind regards,\nMichiel"],
}
# Subject-echo attacker (test_must_address.py SUBJECT_ECHO) on the NEW cases: pinned set (declared gap).
SUBJECT_ECHO_PASSES_Q1 = {"two-asks-dependency-en", "contract-signed-fyi-en", "budget-gap-nl", "fr-workshop-reschedule"}
Q1_BLIND_KEYS_SHA256 = "1d801c123da0c8f2dfe6a434c8f2872bbcd5d9dcb70c94bcad354a39e4560dff"


class _Replay:
    """Replays the scripted output for whichever case's input is the user message — no model, no server."""

    def __init__(self, by_input: dict):
        self.by_input = by_input

    def generate(self, messages, model, temperature=0.0, max_tokens=512):
        out = self.by_input[messages[-1]["content"]]
        return out, {"prompt_tokens": 10, "completion_tokens": 40, "total_tokens": 50,
                     "content_chars": len(out), "reasoning_chars": 0, "finish_reason": "stop"}


def score(exam_name: str, outputs: dict) -> dict:
    """{id: (passed, failed_checks)} through runner.run_exam for the cases in `outputs` (id -> output dict)."""
    exam = runner.load_exam(exam_name)
    agent = runner.load_agent(exam_name)
    cases = {c["id"]: c for c in exam["cases"]}
    sub = {**exam, "cases": [cases[i] for i in outputs]}
    by_input = {cases[i]["input"]: J(o) for i, o in outputs.items()}
    saved = runner.adapter_for
    try:
        runner.adapter_for = lambda *a, **k: _Replay(by_input)
        with contextlib.redirect_stdout(io.StringIO()):
            result = runner.run_exam(agent, sub, "ollama", "scripted")
    finally:
        runner.adapter_for = saved
    got = {c["id"]: (c["passed"], c.get("failed_checks")) for c in result["cases"]}
    if set(got) != set(outputs):  # a silently empty or partial result must never read as "all passed"
        raise AssertionError(f"run_exam scored {sorted(got)}, expected exactly {sorted(outputs)}")
    return got


def test_a_composition():
    for exam_name, ids in NEW_IDS.items():
        cs = runner.load_exam(exam_name)["cases"]
        check(f"{exam_name}: no duplicate id", len({c['id'] for c in cs}) == len(cs))
        check(f"{exam_name}: no duplicate input", len({c['input'] for c in cs}) == len(cs))
        by_id = {c["id"]: c for c in cs}
        check(f"{exam_name}: all {len(ids)} Q1 ids present and held-out",
              all(by_id.get(i, {}).get("split") == "heldout" for i in ids), str([i for i in ids if i not in by_id]))
        check(f"{exam_name}: every Q1 case carries its own expected block and a note",
              all(by_id[i].get("expected") and by_id[i].get("note", "").startswith("Q1 (2026-10-22, blind)") for i in ids if i in by_id))
        n = sum(c["split"] == "heldout" for c in cs)
        check(f"{exam_name}: held-out {HELDOUT_BEFORE[exam_name]} -> {n} == before + {len(ids)} and >= 15",
              n == HELDOUT_BEFORE[exam_name] + len(ids) and n >= 15, str(n))
    for exam_name, fx in (("expense-categorization", EXPENSE), ("email-triage", EMAIL), ("recap", RECAP), ("reply-draft", REPLY)):
        check(f"{exam_name}: honest+wrong fixtures cover exactly the Q1 ids (no case without a witness)",
              set(fx) == set(NEW_IDS[exam_name]), str(set(fx) ^ set(NEW_IDS[exam_name])))
    rec = {c["id"]: c for c in runner.load_exam("recap")["cases"]}
    check("recap Q1 keys use must_mention only (no must_mention_any: PR #117 is not merged)",
          all("must_mention_any" not in rec[i]["expected"] for i in NEW_IDS["recap"]))
    labels = {"expense-categorization": {"software", "hardware", "meals", "travel", "telecom", "office", "marketing", "other"},
              "email-triage": {"reply_now", "reply_later", "ignore"}}
    for exam_name, allowed in labels.items():
        by_id = {c["id"]: c for c in runner.load_exam(exam_name)["cases"]}
        got = {by_id[i]["expected"].get("category") or by_id[i]["expected"].get("label") for i in NEW_IDS[exam_name]}
        check(f"{exam_name}: Q1 labels come from the committed label set", got <= allowed, str(got - allowed))


def _isolation(exam_name, honest: dict, wrong: dict, want_check: dict):
    for i, (ok, fc) in score(exam_name, honest).items():
        check(f"{exam_name}/{i}: HONEST output passes every check", ok and not fc, str(fc))
    for i, (ok, fc) in score(exam_name, wrong).items():
        check(f"{exam_name}/{i}: WRONG output fails exactly one check, {want_check[i]}",
              not ok and fc == [{"bucket": "quality", "check": want_check[i]}], str(fc))


def test_b_c_label_exams():
    _isolation("expense-categorization", {i: h for i, (h, _w) in EXPENSE.items()},
               {i: w for i, (_h, w) in EXPENSE.items()}, {i: "fields" for i in EXPENSE})
    _isolation("email-triage", {i: {"label": t} for i, (t, _p) in EMAIL.items()},
               {i: {"label": p} for i, (_t, p) in EMAIL.items()}, {i: "labels" for i in EMAIL})
    check("email-triage: the wrong label differs from the true one on every Q1 case", all(t != p for t, p in EMAIL.values()))


def test_b_c_recap():
    for k in (0, 1):
        for i, (ok, fc) in score("recap", {i: hs[k] for i, (hs, _w, _c) in RECAP.items()}).items():
            check(f"recap/{i}: HONEST {'EN' if k == 0 else 'NL'} recap passes every check", ok and not fc, str(fc))
    for i, (ok, fc) in score("recap", {i: w for i, (_h, w, _c) in RECAP.items()}).items():
        check(f"recap/{i}: WRONG recap fails exactly one check, {RECAP[i][2]}",
              not ok and fc == [{"bucket": "quality", "check": RECAP[i][2]}], str(fc))
    for i, (ok, fc) in score("recap", RECAP_UNGRADED).items():
        check(f"recap/{i}: PRESENT, UNGRADED — the swapped date / merged item / swapped status passes every check (declared)", ok, str(fc))
    for i, (ok, fc) in score("recap", RECAP_HONEST_INDEPENDENT).items():
        check(f"recap/{i}: an refuter-written honest recap (fitted regression pin) passes every check", ok and not fc, str(fc))


def test_b_c_reply_draft():
    lang = dict(runner.load_properties("reply-draft"))["check_language_match"].__globals__["_lang"]
    _isolation("reply-draft", {i: {"reply": h} for i, (h, _w, _c) in REPLY.items()},
               {i: {"reply": w} for i, (_h, w, _c) in REPLY.items()}, {i: c for i, (_h, _w, c) in REPLY.items()})
    for i, (ok, fc) in score("reply-draft", {i: {"reply": r} for i, r in REPLY_UNGRADED.items()}).items():
        check(f"reply-draft/{i}: PRESENT, UNGRADED — an invented French weekday passes every check (declared gap)", ok, str(fc))
    for i, (ok, fc) in score("reply-draft", {"fr-workshop-reschedule": {"reply": REPLY_UNGRADED_FR_MONTH}}).items():
        check(f"reply-draft/{i}: PRESENT, UNGRADED — an invented French date passes every check (declared gap)", ok, str(fc))
    for k in range(max(len(rs) for rs in REPLY_HONEST_INDEPENDENT.values())):
        outs = {i: {"reply": rs[k]} for i, rs in REPLY_HONEST_INDEPENDENT.items() if len(rs) > k}
        for i, (ok, fc) in score("reply-draft", outs).items():
            check(f"reply-draft/{i}: refuter-written honest reply #{k + 1} (fitted regression pin) passes every check", ok and not fc, str(fc))
    for k in range(max(len(d) for d in REPLY_DODGES.values())):
        for i, (ok, fc) in score("reply-draft", {i: {"reply": d[k]} for i, d in REPLY_DODGES.items() if len(d) > k}).items():
            check(f"reply-draft/{i}: stock-phrase dodge #{k + 1} fails ONLY check_must_address",
                  not ok and fc == [{"bucket": "quality", "check": "check_must_address"}], str(fc))
    by_id = {c["id"]: c for c in runner.load_exam("reply-draft")["cases"]}
    for i in NEW_IDS["reply-draft"]:
        check(f"reply-draft/{i}: input reads as exactly one language ({lang(by_id[i]['input'])})",
              lang(by_id[i]["input"]) in ("en", "nl", "fr"))


def test_e_reply_draft_blind_keys():
    path = ROOT / "docs/probes/q1-heldout-expansion-2026-10-22/blind-keys.json"
    check("Q1 blind-keys.json is byte-identical to the committed blind file (sha256 pin)",
          hashlib.sha256(path.read_bytes()).hexdigest() == Q1_BLIND_KEYS_SHA256, hashlib.sha256(path.read_bytes()).hexdigest())
    blind = json.load(open(path))["must_address"]
    check("Q1 blind-keys.json carries exactly the 6 new reply-draft ids", sorted(blind) == sorted(NEW_IDS["reply-draft"]))
    by_id = {c["id"]: c for c in runner.load_exam("reply-draft")["cases"]}
    for i in NEW_IDS["reply-draft"]:
        terms = by_id[i]["expected"].get("must_address")
        check(f"{i}: must_address equals the Q1 blind-keys list", terms == blind.get(i), str(terms))
        check(f"{i}: terms are lowercase and digit-free",
              bool(terms) and all(t == t.lower() and not re.search(r"\d", t) for t in terms), str(terms))
    ns = {}
    exec(compile(re.search(r"SUBJECT_ECHO = \{.*?\n\}", (ROOT / "evals/reply-draft/test_must_address.py").read_text(), re.S).group(0), "x", "exec"), ns)
    lang = dict(runner.load_properties("reply-draft"))["check_language_match"].__globals__["_lang"]
    passed = set()
    outs = {}
    for i in NEW_IDS["reply-draft"]:
        subject = re.search(r"^(?:Subject|Onderwerp|Objet): (.*)$", by_id[i]["input"], re.M).group(1)
        outs[i] = {"reply": ns["SUBJECT_ECHO"][lang(by_id[i]["input"])].format(s=subject)}
    passed = {i for i, (ok, _fc) in score("reply-draft", outs).items() if ok}
    check(f"subject-echo attacker passes exactly the {len(SUBJECT_ECHO_PASSES_Q1)} pinned Q1 cases (declared gap)",
          passed == SUBJECT_ECHO_PASSES_Q1, f"now passes {sorted(passed)}")


def test_f_recap_window():
    agent = runner.load_agent("recap")
    by_id = {c["id"]: c for c in runner.load_exam("recap")["cases"]}
    for i in NEW_IDS["recap"]:
        chars = len(agent["system_prompt"]) + len(by_id[i]["input"])
        # ESTIMATED, not tokenized: 2.5 chars/token is pessimistic for EN/NL; the bound is ~3k prompt tokens.
        check(f"recap/{i}: prompt + input {chars} chars <= 7,500 (≈3k tokens at a pessimistic 2.5 chars/token)", chars <= 7500)


def main() -> int:
    for t in (test_a_composition, test_b_c_label_exams, test_b_c_recap, test_b_c_reply_draft,
              test_e_reply_draft_blind_keys, test_f_recap_window):
        print(f"\n{t.__name__}"); t()
    if FAILED:
        print(f"\nFAILED ({len(FAILED)}):"); [print(f"  - {f}") for f in FAILED]; return 1
    print("\nall Q1 case checks passed"); return 0


if __name__ == "__main__":
    sys.exit(main())
