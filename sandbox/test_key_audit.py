#!/usr/bin/env python3
"""scripts/key_audit.py — the scans flag what they exist to flag, and nothing next to it.

Scan 2 (required term only inside an address) is pinned on an IN-MEMORY copy of the Devos shape,
not on a blob of the pre-fix cases.json (CLAUDE.md gotcha 19: a public clone has no history).
Scan 1 (all-fail cells) runs through the same loader `main` uses, on two-model fixtures written
to a temp dir with the real `<exam>__<model>-<date>.json` filename shape and REAL case ids, through
all three branches a matrix exercises: labels (email-triage), properties (recap, re-scored by the real
runner.run_properties) and labels + properties (task-intake: run_exam ANDs its properties.py into
`passed` in every mode, so the audit must too). The recap fixture uses train cases with no
address-only row, so the signed Devos/Mertens/Peeters key fixes cannot move it.

The 8 cells N-A7b counted on the 27 Sep matrix are deliberately NOT asserted here: that count
moves the day a key fix merges (gotcha 15's shape). It was the acceptance check of the lane run.

No inference anywhere in this file. Seen RED against two stubs per scan (returns nothing; flags
everything), and tests 7-9 against the two faulty variants the 22 Oct review round named (stored
`passed` in place of the properties re-score; properties skipped outside properties mode); both
recorded in the lane PR. Pass 3 (5c, 5d, 7f, 7g, 8b, 8c): each red on the mutant it targets (a
scored {"error": ...} answer read as dead; the error clauses of _died removed; dead handling in
properties mode only; the labels/fields gate entry not compared; the old TLD list; no email pattern),
and 5a, 8d, 8e + exact tokens after the pass-3 mutation refuter (trajectory verdict, fields gate, dedup).
"""
import contextlib
import importlib.util
import io
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("key_audit", ROOT / "scripts" / "key_audit.py")
KA = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(KA)

FAILED = []


def check(label, ok, extra=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {extra}" if not ok and extra else ""))
    if not ok:
        FAILED.append(label)


DEVOS_INPUT = ("--- item 7 --- From: t.devos@devos-installaties.be Subject: levering\n"
               "De levering van donderdag schuift naar maandag. Sorry voor het ongemak. Tom De Vos")


def _case(must_mention, cid="devos-shape"):
    return {"id": cid, "split": "heldout", "input": DEVOS_INPUT,
            "expected": {"must_mention": must_mention}}


def test_1_scan2_flags_a_term_found_only_in_the_address():
    rows = KA.address_only_terms({"recap": [_case(["Devos"])]})
    check("'Devos' (only in t.devos@devos-installaties.be) is flagged",
          [(r["case"], r["term"]) for r in rows] == [("devos-shape", "Devos")], f"rows={rows}")
    check("the flagged row, every field: exam, case, split, term, whole token, occurrences",
          rows == [{"exam": "recap", "case": "devos-shape", "split": "heldout", "term": "Devos",
                    "token": "t.devos@devos-installaties.be", "occurrences": 2}], f"rows={rows}")


def test_2_scan2_leaves_a_term_the_prose_supports():
    rows = KA.address_only_terms({"recap": [_case(["Vos"])]})
    check("'Vos' (in the signature 'Tom De Vos') is NOT flagged", rows == [], f"rows={rows}")


def test_3_scan2_never_flags_a_term_with_zero_occurrences():
    # all() over zero hits is True: an over-eager scan would flag every absent term.
    rows = KA.address_only_terms({"recap": [_case(["Janssens"])]})
    check("'Janssens' (absent from the input) is NOT flagged", rows == [], f"rows={rows}")


def test_4_scan2_reads_commit_owner_and_must_commit():
    case = {"id": "call", "split": "train",
            "input": "Rep: I'll mail it to sales@acme-tools.com today. Customer: we confirm the pilot.",
            "expected": {"must_commit": ["confirm the pilot"], "commit_owner": {"acme": "rep"}}}
    rows = KA.address_only_terms({"transcript-en": [case]})
    check("commit_owner key 'acme' (only in the address) is flagged; the prose term is not",
          [r["term"] for r in rows] == ["acme"], f"rows={rows}")


def test_5_scan3_lists_three_word_terms_only():
    case = {"id": "lc", "split": "heldout", "input": "x",
            "expected": {"must_commit": ["summary recap email", "updated quote",
                                         "confirm the exact seat count"]}}
    rows = KA.phrasing_tight_terms({"transcript-en": [case]})
    check("3- and 5-word terms listed, 'updated quote' (2) not",
          [r["term"] for r in rows] == ["summary recap email", "confirm the exact seat count"],
          f"rows={rows}")
    check("each tight row carries exam, case, split and its word count",
          [(r["exam"], r["case"], r["split"], r["words"]) for r in rows]
          == [("transcript-en", "lc", "heldout", 3), ("transcript-en", "lc", "heldout", 5)], f"rows={rows}")


def test_5a_a_term_under_two_keys_is_one_row_per_scan():
    case = {"id": "dup", "split": "train",
            "input": "Rep: I will send the signed order form to orders@acme-tools.com tomorrow.",
            "expected": {"must_commit": ["send the signed order form", "acme"],
                         "commit_owner": {"send the signed order form": "rep", "acme": "rep"}}}
    tight = KA.phrasing_tight_terms({"transcript-en": [case]})
    addr = KA.address_only_terms({"transcript-en": [case]})
    check("a term in must_commit AND commit_owner is one tight row", [r["term"] for r in tight]
          == ["send the signed order form"], f"rows={tight}")
    check("... and one address row", [r["term"] for r in addr] == ["acme"], f"rows={addr}")


def test_5b_scan2_flags_a_term_found_only_in_a_url_or_a_bare_domain():
    # Each input isolates ONE address pattern: the term sits in the URL PATH (past the domain token
    # the bare-domain pattern would match), and the bare domain has no @ and no scheme.
    url = {"id": "url", "split": "train", "input": "Offerte staat op https://tuinofferte.org/maes/2026, groeten.",
           "expected": {"must_mention": ["maes"]}}
    dom = {"id": "dom", "split": "train", "input": "Zie kwekerij-verhaeghe.be voor de catalogus. Groeten, Jan",
           "expected": {"must_mention": ["Verhaeghe"]}}
    http = {"id": "http", "split": "train", "input": "Oude link: http://tuinofferte.org/claes/2025 groeten.",
            "expected": {"must_mention": ["claes"]}}
    rows = KA.address_only_terms({"recap": [url, dom, http]})
    check("a term only inside an https:// or http:// URL is flagged, and one only in a bare .be domain",
          [(r["case"], r["term"]) for r in rows] == [("url", "maes"), ("dom", "Verhaeghe"), ("http", "claes")],
          f"rows={rows}")


def test_5e_scan2_prose_next_to_an_address_is_not_flagged():
    # The negative side of the patterns: a missing space after a full stop before a 7-letter word is
    # not a domain ({2,6} upper bound + word boundary), and a name right before an <address> is not
    # inside it (containment, not overlap).
    cases = [{"id": "nospace", "split": "train", "input": "Akkoord voor Sofie Janssens.Vrijdag bellen we.",
              "expected": {"must_mention": ["Janssens"]}},
             {"id": "angle", "split": "train", "input": "From: Tom De Vos<t.devos@devos.be> Subject: levering",
              "expected": {"must_mention": ["De Vos"]}}]
    rows = KA.address_only_terms({"recap": cases})
    check("'Janssens.Vrijdag' and 'De Vos<t.devos@...>' are NOT address-only", rows == [], f"rows={rows}")


def test_5c_scan2_a_bare_domain_matches_any_tld_not_only_a_fixed_list():
    # .org was outside the first TLD list (be|nl|com|pt|es|eu|io): this term was waved through.
    for tld in ("org", "shop", "studio"):   # 3, 4 and 6 letters: the {2,6} bound, both ends that matter
        case = {"id": tld, "split": "train", "input": f"Zie tuincentrum-maes.{tld} voor de catalogus. Groeten, Jan",
                "expected": {"must_mention": ["Maes"]}}
        rows = KA.address_only_terms({"recap": [case]})
        check(f"'Maes' only in the bare domain tuincentrum-maes.{tld} is flagged",
              [r["term"] for r in rows] == ["Maes"], f"rows={rows}")


def test_5d_scan2_the_email_pattern_carries_an_address_the_domain_pattern_misses():
    # Every 2-6 letter TLD email is ALSO a bare-domain token, so only a longer TLD isolates the
    # email pattern (deleting it otherwise stays green).
    case = {"id": "mail", "split": "train", "input": "Stuur de foto's naar studio@maes.photography, groeten. Jan",
            "expected": {"must_mention": ["Maes"]}}
    rows = KA.address_only_terms({"recap": [case]})
    check("'Maes' only in studio@maes.photography is flagged",
          [r["term"] for r in rows] == ["Maes"], f"rows={rows}")


def _write_result(d, model, records, exam="email-triage"):
    (Path(d) / f"{exam}__{model}-2026-09-27.json").write_text(
        json.dumps({"agent": exam, "cases": records}))


def test_6_scan1_lists_a_cell_only_when_every_model_failed_it():
    ex = KA.runner.load_exam("email-triage")
    labels = sorted({c["expected"]["label"] for c in ex["cases"]})
    a, b = ex["cases"][0], ex["cases"][1]

    def rec(case, right):
        want = case["expected"]["label"]
        # A right label in different case: run_exam's _fields_matched lower-cases, so it passes.
        got = f" {want.upper()} " if right else next(lab for lab in labels if lab != want)
        return {"id": case["id"], "split": case["split"], "passed": right, "got": {"label": got}}

    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [rec(a, False), rec(b, False)])
        _write_result(d, "model-two", [rec(a, False), rec(b, True)])
        cells, mismatches = KA.all_fail_cells(d)
    listed = [(c["case"], c["check"], c["n"]) for c in cells]
    check(f"{a['id']} (failed by both) listed with n=2", (a["id"], "label", 2) in listed, f"cells={listed}")
    check(f"{b['id']} (failed by one of two) NOT listed", all(c[0] != b["id"] for c in listed),
          f"cells={listed}")
    check("fixture re-scores to its stored passed", mismatches == [], f"mismatches={mismatches}")


def test_6b_scan1_labels_reports_a_stored_passed_its_got_contradicts():
    a = KA.runner.load_exam("email-triage")["cases"][0]
    rec = {"id": a["id"], "split": a["split"], "passed": False, "got": {"label": a["expected"]["label"]},
           "failed_checks": [{"bucket": "quality", "check": "labels"}]}
    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [rec])
        _, mismatches = KA.all_fail_cells(d)
    check("labels mode: right label stored as failed is exactly one mismatch",
          mismatches == [("email-triage", "model-one", a["id"], True, False)], f"mismatches={mismatches}")


# Recap train cases with no address-only row (gotcha 15's shape: a signed key fix must not move this).
RECAP_GOOD = {
    "busy-day-standard": "Sofie Janssens aanvaardt het voorstel van 6500 EUR, wil in september starten en "
                         "vraagt een startdatum. Tom De Vos vraagt om het overleg van donderdag een week te "
                         "verplaatsen, op hetzelfde uur.",
    "compression-heavy": "Els Peeters van Peeters Transport meldt dat sinds de update van vorige week facturen "
                         "dubbel worden aangemaakt; intussen moesten ze er 14 annuleren en kunnen ze niet "
                         "verder factureren.",
}
# The same recaps with the one must_mention term removed: fails check_coverage, nothing else.
RECAP_NO_TERM = {
    "busy-day-standard": RECAP_GOOD["busy-day-standard"].replace("Sofie Janssens", "De klant"),
    "compression-heavy": RECAP_GOOD["compression-heavy"].replace("Els Peeters van Peeters Transport",
                                                                 "Een transportklant"),
}


def _recap_rec(cid, text, got=None):
    """A record in run_exam's shape, scored by the real checks: failed_checks stored only when non-empty."""
    case = RECAP_CASES[cid]
    got = got if got is not None else {"recap": text, "nothing_important": False}
    ok, _, failed = KA.runner.run_properties(RECAP_PROPS, case["input"], got)
    return {"id": cid, "split": case["split"], "passed": ok, "got": got,
            **({"failed_checks": failed} if failed else {})}


def _dead_rec(cid):
    """run_exam's TerminationError record (runner.py case loop): got {}, no check ran."""
    return {"id": cid, "split": RECAP_CASES[cid]["split"], "passed": False, "got": {},
            "detail": {"termination": {"cause": "no_answer"}},
            "failed_checks": [{"bucket": "termination", "check": "termination"}]}


RECAP_CASES = {c["id"]: c for c in KA.runner.load_exam("recap")["cases"]}
RECAP_PROPS = KA.runner.load_properties("recap")


def test_7a_recap_fixture_preconditions():
    # A got that crashes a check also "fails" it (run_properties turns the exception into a failure);
    # pin that the fixture fails for the reason it claims, through the real checks.
    for cid in RECAP_GOOD:
        inp = RECAP_CASES[cid]["input"]
        _, _, good = KA.runner.run_properties(RECAP_PROPS, inp, {"recap": RECAP_GOOD[cid],
                                                                  "nothing_important": False})
        _, _, bad = KA.runner.run_properties(RECAP_PROPS, inp, {"recap": RECAP_NO_TERM[cid],
                                                                 "nothing_important": False})
        check(f"{cid}: the good recap passes every recap check", good == [], f"failed={good}")
        check(f"{cid}: the term-less recap fails check_coverage only",
              [x["check"] for x in bad] == ["check_coverage"], f"failed={bad}")


def test_7b_scan1_properties_lists_the_failed_check_and_not_the_passed_ones():
    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [_recap_rec("busy-day-standard", RECAP_NO_TERM["busy-day-standard"]),
                                       _recap_rec("compression-heavy", RECAP_NO_TERM["compression-heavy"])],
                      exam="recap")
        _write_result(d, "model-two", [_recap_rec("busy-day-standard", RECAP_NO_TERM["busy-day-standard"]),
                                       _recap_rec("compression-heavy", RECAP_GOOD["compression-heavy"])],
                      exam="recap")
        cells, mismatches = KA.all_fail_cells(d)
    listed = [(c["exam"], c["case"], c["check"], c["n"]) for c in cells]
    # Exact list: busy-day-standard failed by both, but ONLY on check_coverage. The 4 checks both models
    # passed on that failed case must stay out (the stored-`passed` variant lists all 5: the 8 -> 43 shape);
    # compression-heavy, failed by one of two, must stay out entirely.
    check("exactly one cell: recap busy-day-standard check_coverage n=2",
          listed == [("recap", "busy-day-standard", "check_coverage", 2)], f"cells={listed}")
    check("the cell carries the case's split and both model names",
          [(c["split"], c["models"]) for c in cells]
          == [(RECAP_CASES["busy-day-standard"]["split"], ["model-one", "model-two"])], f"cells={cells}")
    check("fixture re-scores to its stored passed", mismatches == [], f"mismatches={mismatches}")


def test_7c_scan1_properties_reports_a_stored_passed_its_got_contradicts():
    good = _recap_rec("busy-day-standard", RECAP_GOOD["busy-day-standard"])
    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [{**good, "passed": False}], exam="recap")
        _write_result(d, "model-two", [good], exam="recap")
        cells, mismatches = KA.all_fail_cells(d)
    check("the contradicting record, and only it, is a mismatch",
          mismatches == [("recap", "model-one", "busy-day-standard", True, False)],
          f"mismatches={mismatches}")
    check("a got that passes every check lists no cell", cells == [], f"cells={cells}")


def test_7d_scan1_a_dead_run_never_hides_an_all_fail_cell():
    # Copying the input as the recap fails check_compression only; an EMPTY got passes it. A
    # terminated run (got {}) re-scored as if it answered would credit that pass and erase the cell.
    cid = "busy-day-standard"
    copy = RECAP_CASES[cid]["input"]
    pre = _recap_rec(cid, copy)
    check("precondition: the input-as-recap fails check_compression only",
          [x["check"] for x in pre.get("failed_checks", [])] == ["check_compression"], f"rec={pre}")
    _, _, empty = KA.runner.run_properties(RECAP_PROPS, RECAP_CASES[cid]["input"], {})
    check("precondition: an empty got passes check_compression",
          "check_compression" not in {x["check"] for x in empty}, f"failed={empty}")
    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [_recap_rec(cid, copy)], exam="recap")
        _write_result(d, "model-two", [_recap_rec(cid, copy)], exam="recap")
        _write_result(d, "model-dead", [_dead_rec(cid)], exam="recap")
        cells, mismatches = KA.all_fail_cells(d)
    listed = [(c["case"], c["check"], c["n"]) for c in cells]
    check("check_compression stays listed with the dead run counted as a fail (n=3)",
          (cid, "check_compression", 3) in listed, f"cells={listed}")
    check("no mismatch from the dead record", mismatches == [], f"mismatches={mismatches}")


def _error_rec(cid, legacy=False):
    """run_exam's ValueError/TypeError record (runner.py case loop): got {"error": ...}, no check ran.
    legacy=True: the same record written before run_exam stored failed_checks."""
    return {"id": cid, "split": RECAP_CASES[cid]["split"], "passed": False,
            "got": {"error": "Expecting value: line 1 column 1 (char 0)"},
            **({} if legacy else {"failed_checks": [{"bucket": "quality", "check": "error"}]})}


def test_7f_scan1_a_parse_error_record_never_hides_an_all_fail_cell():
    # 7d's twin for the OTHER death: a parse error stores got {"error": ...}, which also passes
    # check_compression when re-scored as an answer.
    cid = "busy-day-standard"
    copy = RECAP_CASES[cid]["input"]
    _, _, err = KA.runner.run_properties(RECAP_PROPS, RECAP_CASES[cid]["input"], _error_rec(cid)["got"])
    check("precondition: a got of {'error': ...} passes check_compression",
          "check_compression" not in {x["check"] for x in err}, f"failed={err}")
    for legacy in (False, True):
        with tempfile.TemporaryDirectory() as d:
            _write_result(d, "model-one", [_recap_rec(cid, copy)], exam="recap")
            _write_result(d, "model-two", [_recap_rec(cid, copy)], exam="recap")
            _write_result(d, "model-dead", [_error_rec(cid, legacy)], exam="recap")
            cells, mismatches = KA.all_fail_cells(d)
        listed = [(c["case"], c["check"], c["n"]) for c in cells]
        tag = "pre-failed_checks record" if legacy else "failed_checks [error]"
        check(f"parse-error record ({tag}): check_compression stays listed with n=3",
              (cid, "check_compression", 3) in listed, f"cells={listed}")
        check(f"parse-error record ({tag}): no mismatch", mismatches == [], f"mismatches={mismatches}")


def test_7g_scan1_a_model_that_answers_error_is_scored_not_dead():
    # A model's OWN answer {"error": ...} is scored by run_exam: it passes check_compression and the
    # record stores the checks it failed. Treating it as dead would list check_compression although
    # the instrument passed it for both models.
    cid = "busy-day-standard"
    got = {"error": "ik kan hier geen samenvatting van maken"}
    recs = [_recap_rec(cid, None, got=dict(got)) for _ in range(2)]
    stored = sorted(x["check"] for x in recs[0].get("failed_checks", []))
    check("precondition: the answer is scored, fails some checks, passes check_compression",
          bool(stored) and "check_compression" not in stored and not recs[0]["passed"], f"stored={stored}")
    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [recs[0]], exam="recap")
        _write_result(d, "model-two", [recs[1]], exam="recap")
        cells, mismatches = KA.all_fail_cells(d)
    listed = sorted(c["check"] for c in cells if c["case"] == cid)
    check("exactly the checks the instrument failed are listed (check_compression is not)",
          listed == stored, f"listed={listed} stored={stored}")
    check("the scored error answer re-scores to its stored record", mismatches == [], f"mismatches={mismatches}")


def test_7e_scan1_per_check_disagreement_with_stored_failed_checks_is_a_mismatch():
    # Same overall verdict (failed), different failed check: the overall-only comparison misses it.
    cid = "busy-day-standard"
    rec = _recap_rec(cid, RECAP_NO_TERM[cid])
    rec = {**rec, "failed_checks": [{"bucket": "quality", "check": "check_compression"}]}
    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [rec], exam="recap")
        _, mismatches = KA.all_fail_cells(d)
    check("stored failed_checks [check_compression] vs re-scored [check_coverage] is a mismatch",
          mismatches == [("recap", "model-one", cid, ["check_coverage"], ["check_compression"])],
          f"mismatches={mismatches}")


def test_8_scan1_labels_exam_with_properties_lists_the_property_cell():
    ex = {c["id"]: c for c in KA.runner.load_exam("task-intake")["cases"]}
    a = ex["crm-devos-stage"]
    b = next(c for c in ex.values() if c["id"] != a["id"] and c["expected"]["agent"] != "none")
    wrong = "recap" if a["expected"]["agent"] != "recap" else "email-triage"

    props = KA.runner.load_properties("task-intake")

    def rec(case, agent, passed):
        got = {"agent": agent, "input": ""}
        label = [] if agent == case["expected"]["agent"] else [{"bucket": "quality", "check": "labels"}]
        fc = label + KA.runner.run_properties(props, case["input"], got)[2]
        return {"id": case["id"], "split": case["split"], "passed": passed, "got": got,
                **({"failed_checks": fc} if fc else {})}

    with tempfile.TemporaryDirectory() as d:
        # a: label wrong AND hand-over empty, both models. b: label right, hand-over empty: run_exam
        # stored passed=False (check_none_hands_over_nothing), so a labels-only re-score disagrees.
        for m in ("model-one", "model-two"):
            _write_result(d, m, [rec(a, wrong, False), rec(b, b["expected"]["agent"], False)],
                          exam="task-intake")
        cells, mismatches = KA.all_fail_cells(d)
    listed = {(c["case"], c["check"]) for c in cells}
    check(f"{a['id']}: the property cell check_none_hands_over_nothing is listed",
          (a["id"], "check_none_hands_over_nothing") in listed, f"cells={sorted(listed)}")
    check(f"{b['id']}: check_none_hands_over_nothing listed although the label is right",
          (b["id"], "check_none_hands_over_nothing") in listed, f"cells={sorted(listed)}")
    check(f"{a['id']}: the label cell 'agent' is listed too (failed by both)",
          (a["id"], "agent") in listed, f"cells={sorted(listed)}")
    check(f"{a['id']}: check_agent_in_roster (passed by both) is NOT listed",
          (a["id"], "check_agent_in_roster") not in listed, f"cells={sorted(listed)}")
    check("label right + hand-over empty re-scores to the stored passed=False", mismatches == [],
          f"mismatches={mismatches}")

    # Label WRONG, hand-over the whole request (every property passes), stored passed=True: the
    # label must still carry the verdict, so this is exactly one mismatch.
    good = {"agent": wrong, "input": a["input"]}
    check("precondition: the whole-request hand-over passes every task-intake property",
          KA.runner.run_properties(props, a["input"], good)[0])
    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [{"id": a["id"], "split": a["split"], "passed": True, "got": good}],
                      exam="task-intake")
        _, mismatches = KA.all_fail_cells(d)
    check("labels + properties: a wrong label stored as passed is exactly one mismatch",
          mismatches == [("task-intake", "model-one", a["id"], False, True)], f"mismatches={mismatches}")


TI_CASES = {c["id"]: c for c in KA.runner.load_exam("task-intake")["cases"]}
TI_PROPS = KA.runner.load_properties("task-intake")
TI_A = TI_CASES["crm-devos-stage"]
TI_WRONG = "recap" if TI_A["expected"]["agent"] != "recap" else "email-triage"


def _ti_rec(agent, handover, stored_checks, passed=False):
    got = {"agent": agent, "input": handover}
    return {"id": TI_A["id"], "split": TI_A["split"], "passed": passed, "got": got,
            **({"failed_checks": [{"bucket": "quality", "check": c} for c in stored_checks]}
               if stored_checks else {})}


def test_8b_scan1_a_dead_task_intake_record_is_a_fail_on_every_check():
    # model-one: label wrong, whole request handed over (every property passes). model-dead: a parse
    # error. The label cell is listed with n=2 and no property cell is (model-one passed them all).
    # Re-scoring the dead {"error": ...} as an answer fails the properties too, against its stored
    # failed_checks [error]: a mismatch, and property cells that one model did pass stay out anyway.
    ok, _, _ = KA.runner.run_properties(TI_PROPS, TI_A["input"], {"agent": TI_WRONG, "input": TI_A["input"]})
    check("precondition: the whole-request hand-over passes every task-intake property", ok)
    dead = {"id": TI_A["id"], "split": TI_A["split"], "passed": False, "got": {"error": "Extra data: line 1"},
            "failed_checks": [{"bucket": "quality", "check": "error"}]}
    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [_ti_rec(TI_WRONG, TI_A["input"], ["labels"])], exam="task-intake")
        _write_result(d, "model-dead", [dead], exam="task-intake")
        cells, mismatches = KA.all_fail_cells(d)
    listed = [(c["case"], c["check"], c["n"]) for c in cells]
    check("exactly one cell: crm-devos-stage agent n=2 (the dead run counted as a fail)",
          listed == [(TI_A["id"], "agent", 2)], f"cells={listed}")
    check("no mismatch from the dead task-intake record", mismatches == [], f"mismatches={mismatches}")
    # Same, but model-one also fails check_none_hands_over_nothing (empty hand-over): the dead run
    # adds its fail to that PROPERTY cell too, n=2.
    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [_ti_rec(TI_WRONG, "", ["labels", "check_none_hands_over_nothing"])],
                      exam="task-intake")
        _write_result(d, "model-dead", [dead], exam="task-intake")
        cells, mismatches = KA.all_fail_cells(d)
    listed = {(c["check"], c["n"]) for c in cells}
    check("the property cell counts the dead run too: check_none_hands_over_nothing n=2",
          ("check_none_hands_over_nothing", 2) in listed and ("agent", 2) in listed, f"cells={sorted(listed)}")
    check("... with no mismatch", mismatches == [], f"mismatches={mismatches}")


def test_8c_scan1_task_intake_per_check_disagreement_is_a_mismatch():
    # Same overall verdict (failed) both times; only the per-check comparison, gate entry included, sees it.
    right = TI_A["expected"]["agent"]
    cases = [
        # label right, hand-over empty; the record ALSO claims the labels gate failed
        (_ti_rec(right, "", ["labels", "check_none_hands_over_nothing"]),
         (["check_none_hands_over_nothing"], ["check_none_hands_over_nothing", "labels"])),
        # label wrong, hand-over empty; the record stores only the gate: stored is a strict SUBSET
        (_ti_rec(TI_WRONG, "", ["labels"]),
         (["check_none_hands_over_nothing", "labels"], ["labels"])),
        # label wrong, every property passes; the record blames a property instead of the gate
        (_ti_rec(TI_WRONG, TI_A["input"], ["check_none_hands_over_nothing"]),
         (["labels"], ["check_none_hands_over_nothing"])),
    ]
    for rec, (rescored, stored) in cases:
        with tempfile.TemporaryDirectory() as d:
            _write_result(d, "model-one", [rec], exam="task-intake")
            _, mismatches = KA.all_fail_cells(d)
        check(f"task-intake: re-scored {rescored} vs stored {stored} is exactly one mismatch",
              mismatches == [("task-intake", "model-one", TI_A["id"], rescored, stored)],
              f"mismatches={mismatches}")


def test_8d_scan1_fields_mode_judges_each_key_and_compares_the_fields_gate():
    # Two-key fields case: model-one misses `category`, model-two misses `recurring`. Both fail the
    # case (the fields gate), but no KEY is missed by both, so no cell; and both records agree with
    # their stored failed_checks [fields]. A third, right on both keys, passes with no failed_checks.
    case = {c["id"]: c for c in KA.runner.load_exam("expense-categorization")["cases"]}["railway-subscription"]
    exp = case["expected"]
    check("precondition: a two-key expected block", sorted(exp) == ["category", "recurring"], f"exp={exp}")
    wrong_cat = {**exp, "category": "travel" if exp["category"] != "travel" else "software"}
    wrong_rec = {**exp, "recurring": not exp["recurring"]}

    def rec(got, passed):
        return {"id": case["id"], "split": case["split"], "passed": passed, "got": got,
                **({} if passed else {"failed_checks": [{"bucket": "quality", "check": "fields"}]})}

    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [rec(wrong_cat, False)], exam="expense-categorization")
        _write_result(d, "model-two", [rec(wrong_rec, False)], exam="expense-categorization")
        _write_result(d, "model-three", [rec(dict(exp), True)], exam="expense-categorization")
        cells, mismatches = KA.all_fail_cells(d)
    check("fields: no key failed by every model -> no cell", cells == [], f"cells={cells}")
    check("fields: one-key misses agree with stored failed_checks [fields]", mismatches == [],
          f"mismatches={mismatches}")
    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [rec(wrong_cat, False)], exam="expense-categorization")
        _write_result(d, "model-two", [rec(wrong_cat, False)], exam="expense-categorization")
        cells, _ = KA.all_fail_cells(d)
    check("fields: the key both models missed is the one cell, named by the key",
          [(c["case"], c["check"], c["n"]) for c in cells] == [(case["id"], "category", 2)], f"cells={cells}")


def test_8e_scan1_trajectory_mode_reads_the_stored_verdict():
    ex = KA.runner.load_exam("crm-followup")
    check("precondition: crm-followup is a trajectory exam without a properties.py",
          ex.get("mode") == "trajectory" and KA.runner.load_properties("crm-followup") == [])
    a, b = ex["cases"][0], ex["cases"][1]

    def rec(case, passed):
        return {"id": case["id"], "split": case["split"], "passed": passed, "got": {"answer": "x"}}

    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [rec(a, False), rec(b, False)], exam="crm-followup")
        _write_result(d, "model-two", [rec(a, False), rec(b, True)], exam="crm-followup")
        cells, mismatches = KA.all_fail_cells(d)
    check("trajectory: the case failed by both is listed as <case> n=2, the one-of-two case is not",
          [(c["case"], c["check"], c["n"]) for c in cells] == [(a["id"], "<case>", 2)], f"cells={cells}")
    check("trajectory: no re-score, no mismatch", mismatches == [], f"mismatches={mismatches}")


_KEY_READ = re.compile(r"""(?:\b_exp\([^)]*\)|\bexp(?:ected)?)\s*(?:\.get\(\s*|\[\s*)["']([a-z_]+)["']""")


def test_9a_every_expected_key_a_properties_file_reads_is_classified():
    found = {}
    for path in sorted((ROOT / "evals").glob("*/properties.py")):
        for key in _KEY_READ.findall(path.read_text()):
            found.setdefault(key, set()).add(path.parent.name)
    classified = set(KA.REQUIRED_KEYS) | set(KA.REQUIRED_DICT_KEYS) | set(KA.NOT_REQUIRED_TERMS)
    check("the grep finds reads at all (the regex is not dead)", len(found) >= 5, f"found={found}")
    check("keys read by evals/*/properties.py == REQUIRED_KEYS | REQUIRED_DICT_KEYS | NOT_REQUIRED_TERMS",
          set(found) == classified,
          f"unclassified={sorted(set(found) - classified)} stale={sorted(classified - set(found))}")
    check("must_not_commit stays out of the required terms (an absence key)",
          "must_not_commit" not in set(KA.REQUIRED_KEYS) | set(KA.REQUIRED_DICT_KEYS))


def _main_exit(argv):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
        try:
            KA.main(argv)
        except SystemExit as e:
            return e.code, err.getvalue()
    return 0, err.getvalue()


def test_9b_bad_arguments_exit_2_with_a_message():
    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [])
        code, err = _main_exit([d, "--exam", "no-such-exam"])
        check("unknown --exam -> exit 2 from the --exam guard",
              code == 2 and "unknown --exam 'no-such-exam'" in err, f"{code} {err!r}")
        code, err = _main_exit([d, "--exam", "recap"])
        check("no result file for --exam -> exit 2", code == 2 and "no <exam>__" in err, f"{code} {err!r}")
    with tempfile.TemporaryDirectory() as d:
        code, err = _main_exit([d])
        check("empty results dir -> exit 2", code == 2 and "no <exam>__" in err, f"{code} {err!r}")
        code, err = _main_exit([str(Path(d) / "missing")])
        check("missing results dir -> exit 2", code == 2 and "no <exam>__" in err, f"{code} {err!r}")


def test_9d_committed_cases_loads_every_exam_and_honours_the_filter():
    import subprocess
    # Relative to ROOT: a worktree's own absolute path contains /.claude/ (gotcha 6's exclusion).
    out = subprocess.run(["find", "evals", "-name", "cases.json", "-not", "-path", "*/.claude/*"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split()
    on_disk = {Path(x).parent.name for x in out}
    check("precondition: find sees the exams", len(on_disk) >= 8, f"{sorted(on_disk)}")
    allc = KA.committed_cases()
    check("committed_cases() keys == every evals/<exam>/cases.json find sees", set(allc) == on_disk,
          f"{sorted(allc)} vs {sorted(on_disk)}")
    check("... each with cases", all(len(v) > 0 for v in allc.values()), f"{ {k: len(v) for k, v in allc.items()} }")
    check("committed_cases('recap') is recap only", set(KA.committed_cases("recap")) == {"recap"})


def _main_json(argv):
    with tempfile.TemporaryDirectory() as jd:
        jp = Path(jd) / "ka.json"
        code, err = _main_exit(argv + ["--json", str(jp)])
        return code, (json.loads(jp.read_text()) if jp.exists() else None), err


# Scans 2+3 inputs for 9e: a FIXTURE in place of the committed cases. The committed address-only and
# tight rows are exactly the keys signed fixes remove (gotcha 15's shape); 9d pins the real loader.
FIXTURE_CASES = {
    "recap": [_case(["Devos"]),
              {"id": "tight-recap", "split": "train", "input": "x",
               "expected": {"must_mention": ["start in september please"]}}],
    "transcript-en": [{"id": "tight-call", "split": "heldout", "input": "y",
                       "expected": {"must_commit": ["confirm the exact seat count"]}}],
}


def _fixture_committed_cases(exam_filter=None):
    return {k: v for k, v in FIXTURE_CASES.items() if not exam_filter or k == exam_filter}


def test_9e_main_reports_what_the_scan_functions_return_with_and_without_exam():
    # main end to end: every scan wired into the JSON, and --exam filtering every scan. main looks
    # committed_cases up as a module global, so the fixture loader replaces it for this test only.
    a = KA.runner.load_exam("email-triage")["cases"][0]
    contra = {"id": a["id"], "split": a["split"], "passed": False, "got": {"label": a["expected"]["label"]},
              "failed_checks": [{"bucket": "quality", "check": "labels"}]}
    rt = lambda x: json.loads(json.dumps(x))   # tuples -> lists, as the JSON stores them
    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [contra])
        for m in ("model-one", "model-two"):
            _write_result(d, m, [_recap_rec("busy-day-standard", RECAP_NO_TERM["busy-day-standard"])], exam="recap")
        cells, mism = KA.all_fail_cells(d)
        rcells, rmism = KA.all_fail_cells(d, "recap")
        real = KA.committed_cases
        KA.committed_cases = _fixture_committed_cases
        try:
            code, rep_all, err = _main_json([d])
            rcode, rep_recap, rerr = _main_json([d, "--exam", "recap"])
        finally:
            KA.committed_cases = real
    allc, recc = _fixture_committed_cases(), _fixture_committed_cases("recap")
    check("precondition: the fixture gives an address row and tight rows in two exams",
          len(KA.address_only_terms(allc)) == 1 and len(KA.phrasing_tight_terms(allc)) == 2
          and len(KA.phrasing_tight_terms(recc)) == 1)
    check("main exits 0 and writes the JSON", code == 0 and rep_all is not None, f"{code} {err!r}")
    if rep_all is None:
        return
    check("precondition: the fixture has cells AND a mismatch", bool(cells) and bool(mism), f"{cells} {mism}")
    check("JSON all_fail_cells == all_fail_cells()", rep_all["all_fail_cells"] == rt(cells))
    check("JSON rescore_mismatches == all_fail_cells() mismatches (non-empty)",
          rep_all["rescore_mismatches"] == rt(mism), f"{rep_all['rescore_mismatches']}")
    check("JSON address_only_terms == the scan on every exam's cases (non-empty)",
          rep_all["address_only_terms"] == rt(KA.address_only_terms(allc)) and rep_all["address_only_terms"])
    check("JSON phrasing_tight_terms == the scan on every exam's cases (non-empty)",
          rep_all["phrasing_tight_terms"] == rt(KA.phrasing_tight_terms(allc)) and rep_all["phrasing_tight_terms"])
    check("--exam recap exits 0", rcode == 0 and rep_recap is not None, f"{rcode} {rerr!r}")
    if rep_recap is None:
        return
    check("--exam recap: scan 1 is recap only (the email-triage mismatch and cells drop out)",
          rep_recap["all_fail_cells"] == rt(rcells) and rep_recap["rescore_mismatches"] == rt(rmism) == []
          and {c["exam"] for c in rep_recap["all_fail_cells"]} == {"recap"}, f"{rep_recap['all_fail_cells']}")
    check("--exam recap: scans 2 and 3 are recap only",
          rep_recap["address_only_terms"] == rt(KA.address_only_terms(recc))
          and rep_recap["phrasing_tight_terms"] == rt(KA.phrasing_tight_terms(recc))
          and rep_recap["phrasing_tight_terms"] != rep_all["phrasing_tight_terms"])


def test_9c_unknown_case_id_exits_1():
    with tempfile.TemporaryDirectory() as d:
        _write_result(d, "model-one", [{"id": "no-such-case", "split": "train", "passed": False, "got": {}}])
        code, _ = _main_exit([d])
    check("a result naming a case not in cases.json -> exit 1 (SystemExit with a message)",
          code not in (0, 2, None) and "no-such-case" in str(code), f"code={code!r}")


def main() -> int:
    for fn in sorted((v for k, v in globals().items()
                      if k.startswith("test_") and callable(v)), key=lambda f: f.__name__):
        print(f"\n{fn.__name__}")
        fn()
    print(f"\n{'FAILED: ' + ', '.join(FAILED) if FAILED else 'all green'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
