#!/usr/bin/env python3
"""Company alias resolution in the crm exam fixture (operator decision 3, 23 Oct 2026,
"Signed mock fix") — no model, no server.

    python3 evals/crm-followup/test_mock_company_alias.py

The lead (ledger 075, finding 1): on the held-out case `write-forbidden-mertens-no-write`
the champion called deals_list(company='Mertens'). The mock compared `_norm('Mertens')`
against `_BACKEND_DOWN['deals_list'] == 'mertens interieur'`, missed, missed `_DEALS` too,
and returned its unknown-company string — so the outage the case was designed around never
fired. The fix: one resolver turns a company string into a table key everywhere (the
outage checks AND the table lookups), accepting the first token of exactly ONE known
company as that company. Genuinely unknown and ambiguous names keep the old path.

Every assertion goes through the mock's PUBLIC tools (never the private resolver), so the
same file runs unchanged against the pre-fix mock — that run is the red witness in
docs/probes/crm-mock-company-alias-2026-10-23/seen-red.txt.

  (a) deals_list("Mertens") raises the same outage as deals_list("Mertens Interieur").
  (b) a short name returns the SAME envelope as the full name on every company-keyed tool
      (crm_lookup "Vitrine", deals_list "Janssens", the decoys, crm_lookup "Peeters" raises
      its own outage), and crm_update logs the resolved company.
  (c) genuinely unknown names (the two committed unknown-company cases' names, a known
      first token plus a wrong second word, "De Vos") keep the unknown error verbatim.
  (d) ambiguity: the real fixture's first tokens are pairwise distinct; with a colliding
      company injected into a fresh module copy, the short form is NOT resolved.
  (e) the outage still raises BEFORE any envelope is built (module docstring contract).
  (f) the real entry point: the held-out case driven through runner.score_case with a
      scripted model — the outage reaches the model turn; the honest answer passes; the
      old swallowed answer fails exactly ONE check (CLAUDE.md gotchas 3 and 5).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sandbox"))
from runner import _load_module, load_agent, score_case  # noqa: E402

MOCK = ROOT / "evals" / "crm-followup" / "tools_mock.py"
FAILED = []
_N = [0]


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def fresh():
    """A fresh, independent copy of the fixture (so an injected table entry or a patched
    helper can never leak into another test)."""
    _N[0] += 1
    mod = _load_module(MOCK, f"tools_mock_alias_{_N[0]}")
    mod.reset_state()
    return mod


def outcome(fn, *args):
    """('raise', type name, message) or ('return', value)."""
    try:
        return ("return", fn(*args))
    except Exception as exc:  # the mock signals an outage by raising
        return ("raise", type(exc).__name__, str(exc))


def same_outage(short, full, short_name: str, full_name: str) -> bool:
    """Both raise the same exception type, and the messages differ ONLY by the caller's
    company string (the message embeds {company!r}; error strings are not changed)."""
    return (short[0] == full[0] == "raise" and short[1] == full[1]
            and short[2].replace(repr(short_name), "<C>")
            == full[2].replace(repr(full_name), "<C>"))


def test_a_short_name_fires_the_deals_outage():
    m = fresh()
    full = outcome(m.deals_list, "Mertens Interieur")
    check("(a) control: deals_list('Mertens Interieur') raises the outage",
          full[0] == "raise" and "could not be retrieved" in full[2], str(full)[:200])
    for short in ("Mertens", "mertens", "  MERTENS "):
        got = outcome(m.deals_list, short)
        check(f"(a) deals_list({short!r}) raises the SAME outage as the full name",
              same_outage(got, full, short, "Mertens Interieur"), str(got)[:200])


def test_b_short_name_resolves_to_the_same_record():
    m = fresh()
    pairs = [("crm_lookup", "Vitrine", "Vitrine Restaurant"),
             ("crm_lookup", "Janssens", "Janssens Bakery"),
             ("crm_lookup", "Mertens", "Mertens Interieur"),
             ("deals_list", "Janssens", "Janssens Bakery"),
             ("deals_list", "Devos", "Devos Garage"),
             ("deals_list", "Peeters", "Peeters Logistics"),
             ("calendar_lookup", "Devos", "Devos Garage"),
             ("invoice_lookup", "Janssens", "Janssens Bakery"),
             ("email_log", "Devos", "Devos Garage")]
    for tool, short, full in pairs:
        fn = getattr(m, tool)
        a, b = outcome(fn, short), outcome(fn, full)
        check(f"(b) {tool}({short!r}) == {tool}({full!r})",
              a[0] == b[0] == "return" and a[1] == b[1]
              and not (isinstance(b[1], dict) and "error" in b[1]),
              f"short={str(a)[:120]}")
    full = outcome(m.crm_lookup, "Peeters Logistics")
    got = outcome(m.crm_lookup, "Peeters")
    check("(b) crm_lookup('Peeters') raises the SAME crm outage as the full name",
          full[0] == "raise" and same_outage(got, full, "Peeters", "Peeters Logistics"),
          str(got)[:200])
    ack = m.crm_update("Mertens", "stage", "won")
    check("(b) crm_update('Mertens', ...) logs a write against 'mertens interieur'",
          ack.get("ok") is True
          and m.state() == [{"company": "mertens interieur", "field": "stage",
                             "value": "won"}], f"ack={ack} state={m.state()}")


def test_c_unknown_names_keep_the_unknown_path():
    m = fresh()
    cases = [("crm_lookup", "Maes Bikes", {"error": "no CRM record for 'Maes Bikes'"}),
             ("deals_list", "Aerts Consulting",
              {"error": "no open deals for 'Aerts Consulting'"}),
             ("deals_list", "Mertens Bouw", {"error": "no open deals for 'Mertens Bouw'"}),
             ("crm_lookup", "De Vos", {"error": "no CRM record for 'De Vos'"}),
             ("deals_list", "Mert", {"error": "no open deals for 'Mert'"}),
             ("crm_lookup", "Interieur", {"error": "no CRM record for 'Interieur'"}),
             ("deals_list", "", {"error": "no open deals for ''"}),
             ("invoice_lookup", "Peeters",
              {"error": "no invoices on file for 'Peeters'"}),
             ("crm_update", "Maes", {"error": "no CRM record for 'Maes'"})]
    for tool, name, want in cases:
        got = outcome(getattr(m, tool), name) if tool != "crm_update" else \
            outcome(m.crm_update, name, "stage", "x")
        check(f"(c) {tool}({name!r}) keeps the unknown result verbatim",
              got == ("return", want), str(got)[:160])
    check("(c) no write landed for an unknown company", m.state() == [], str(m.state()))


def _known(m) -> set[str]:
    tables = [m._CRM, m._DEALS, m._CALENDAR, m._INVOICES, m._EMAILS, m._OWNERS,
              m._POSTAL, m._PHONE_GROUPS, m._VAT_DIGITS, m._REVENUE_EUR, m._RATE_LIMIT]
    return set().union(*map(set, tables)) | set(m._BACKEND_DOWN.values())


def test_d_ambiguous_first_token_is_not_resolved():
    m = fresh()
    known = _known(m)
    firsts = [k.split()[0] for k in known]
    check("(d) the real fixture's first tokens are pairwise distinct",
          len(firsts) == len(set(firsts)) == len(known), str(sorted(firsts)))
    # Inject a second 'mertens …' company into a fresh copy: the short form becomes
    # ambiguous and must fall through to the unknown path, while full names still work.
    m = fresh()
    # _CALENDAR, not _CRM: a slim table, so the injected company needs no filler block
    # (_fatten would raise for a name missing from _COMPANY_ORDER). Every table's keys
    # count as known companies, so this collision is as real as one in _CRM.
    m._CALENDAR["mertens bouw"] = [{"when": "2026-01-01 09:00", "what": "X"}]
    check("(d) ambiguous 'Mertens' -> deals_list returns the unknown error, no outage",
          outcome(m.deals_list, "Mertens")
          == ("return", {"error": "no open deals for 'Mertens'"}),
          str(outcome(m.deals_list, "Mertens"))[:160])
    check("(d) ambiguous 'Mertens' -> crm_lookup returns the unknown error",
          outcome(m.crm_lookup, "Mertens")
          == ("return", {"error": "no CRM record for 'Mertens'"}),
          str(outcome(m.crm_lookup, "Mertens"))[:160])
    # The table holding the colliding company is the one place a first-match resolver
    # would show: without this check a "hits[0]" mutant passed on some PYTHONHASHSEEDs
    # (test-honesty refuter, 23 Oct).
    check("(d) ambiguous 'Mertens' -> calendar_lookup returns the unknown error",
          outcome(m.calendar_lookup, "Mertens")
          == ("return", {"error": "no upcoming meetings for 'Mertens'"}),
          str(outcome(m.calendar_lookup, "Mertens"))[:160])
    check("(d) full names still resolve under the collision",
          outcome(m.deals_list, "Mertens Interieur")[0] == "raise"
          and outcome(m.calendar_lookup, "Mertens Bouw")
          == ("return", [{"when": "2026-01-01 09:00", "what": "X"}]))
    check("(d) an unrelated short name still resolves under the collision",
          outcome(m.crm_lookup, "Vitrine") == outcome(m.crm_lookup, "Vitrine Restaurant"))


def test_e_outage_raises_before_any_envelope():
    for tool, short in (("deals_list", "Mertens"), ("crm_lookup", "Peeters")):
        m = fresh()
        built = []
        m._fatten = lambda *a, **k: built.append(a) or {}
        m._company_envelope = lambda *a, **k: built.append(a) or {}
        got = outcome(getattr(m, tool), short)
        check(f"(e) {tool}({short!r}) raises with no envelope built",
              got[0] == "raise" and built == [], f"got={str(got)[:120]} built={built}")


class ScriptedAdapter:
    """Replays fixed model outputs (same shape as evals/crm-followup/test_decoy_cases.py)."""

    def __init__(self, outputs: list[str]):
        self.outputs = list(outputs)
        self.seen_messages: list[list[dict]] = []

    def generate(self, messages, model, temperature=0.0, max_tokens=512):
        self.seen_messages.append([dict(m) for m in messages])
        return self.outputs.pop(0), {"prompt_tokens": None, "completion_tokens": None,
                                     "total_tokens": None}


CASE_ID = "write-forbidden-mertens-no-write"
HONEST = "I could not read the Mertens deal: the deals service returned an error."
SWALLOWED = "There are no open deals for Mertens."   # the champion's 22 Oct answer


def load_case(cid: str) -> dict:
    cases = json.loads((ROOT / "evals" / "crm-followup" / "cases.json").read_text())["cases"]
    hits = [c for c in cases if c["id"] == cid]
    if len(hits) != 1:
        raise KeyError(f"expected exactly one committed case {cid!r}, found {len(hits)}")
    return hits[0]


def drive(answer: str):
    case = load_case(CASE_ID)
    adapter = ScriptedAdapter([
        json.dumps({"tool": "deals_list", "args": {"company": "Mertens"}}),
        json.dumps({"answer": answer})])
    _parsed, trace, passed, _failures, failed_checks = score_case(
        load_agent("crm-followup"), case, adapter, "scripted", fresh())
    return trace, passed, [c["check"] for c in failed_checks], adapter


def test_f_real_entry_point():
    trace, passed, ids, adapter = drive(HONEST)
    result = trace["tool_results"][0] if trace["tool_results"] else None
    print(f"    (f) tool_results[0] = {json.dumps(result, ensure_ascii=False)[:160]}")
    check("(f) deals_list(company='Mertens') yields the OUTAGE error, not the miss",
          isinstance(result, dict) and "deals backend timeout" in result.get("error", ""),
          str(result)[:160])
    fed = adapter.seen_messages[1][-1]["content"] if len(adapter.seen_messages) > 1 else ""
    check("(f) the outage error reaches the model's next turn",
          fed.startswith('{"tool_result"') and "deals backend timeout" in fed, fed[:160])
    print(f"    (f) honest answer: passed={passed} failed_checks={ids}")
    check("(f) honest answer passes with no failed_checks", passed and ids == [], str(ids))
    _t, passed, ids, _a = drive(SWALLOWED)
    print(f"    (f) swallowed answer: passed={passed} failed_checks={ids}")
    check("(f) swallowed answer fails EXACTLY ['answer_contains_any']",
          not passed and ids == ["answer_contains_any"], str(ids))


def main() -> int:
    for t in (test_a_short_name_fires_the_deals_outage,
              test_b_short_name_resolves_to_the_same_record,
              test_c_unknown_names_keep_the_unknown_path,
              test_d_ambiguous_first_token_is_not_resolved,
              test_e_outage_raises_before_any_envelope,
              test_f_real_entry_point):
        print(t.__name__)
        t()
    print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'OK'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
