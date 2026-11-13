#!/usr/bin/env python3
"""email-triage-pt is the email-triage exam in European Portuguese, and nothing else.

    python3 evals/test_email_triage_pt.py

email-triage-pt is an exam-only LANGUAGE VARIANT of email-triage (the recap-en precedent, PR #131):
same prompt, same champion fields, same 28 cases with the same ids / splits / labels / class markers
/ notes; only `input` differs, translated to pt-PT. email-triage is a labels-mode exam (exact match
on `label`, no properties.py), so a translation can move a MODEL's answer but never the key.

  (a) every input reads Portuguese: through runner.load_exam, the whole input AND every chunk with
      >= 3 stopword hits has more PT hits than EN hits and more than NL/FR hits (`de`, shared by PT and
      the NL/FR list, counts on neither side; the whole input needs >= 4 PT hits) (the EN and NL/FR
      lists are test_no_dutch_cases.py's own, imported, not copied); no pt-BR marker (a deny list of
      pt-BR-only words + the Brazilian `estar + gerund` progressive). Deliberately crude, like the NL
      detector: it must never be what a case is tuned against.
  (b) the key is email-triage's exactly: same top-level keys, `not_verified` identical, the same ids
      in the same order, and every case key other than `input` (split, expected, class, note) equal.
  (c) kept exactly in translation: the digit tokens (recap-en's regex), the e-mail addresses, and a
      literal list of names / places / codes / hosts, counted per case; the two class=injection cases
      keep the literal `reply_now` token and carry the translated planted line.
  (d) agents/email-triage-pt: name, variant_of email-triage, email-triage's provider / model / tier /
      temperature / max_tokens; prompt.md byte-identical; the description carries the contamination
      note (Claude translated the inputs, so no Claude row is ever scored here).
  (e) the real scorer: a fixed answer set (each case's own label on even positions, a wrong label on
      odd) scored through runner.run_exam on email-triage and on email-triage-pt gives the SAME
      per-case verdict, and the set is not vacuous (some pass, some fail).
  (f) seen RED on the defect, in-process, against the checkers above: an English input put back,
      a split moved, a label changed, a digit dropped, `reply_now` translated away, a pt-BR word,
      a Dutch input — each flagged by exactly its id, judged by what it adds over the committed exam's
      own flags (so a real defect on disk is named once, not cascaded over every mutant line —
      python-reviewer, PR #205); the committed exam is the clean control.
"""
from __future__ import annotations
import copy, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
import yaml  # noqa: E402
import runner  # noqa: E402

ND = runner._load_module(ROOT / "evals" / "test_no_dutch_cases.py", "nd_for_email_triage_pt")

FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


SRC, VAR = "email-triage", "email-triage-pt"

# ---- the Portuguese detector -------------------------------------------------------------------
# Function words and fixed formulas of Portuguese that are not English words ('no', 'do', 'as' left out).
_PT = re.compile(r"\b(não|uma|um|os|das|dos|da|para|com|em|na|nos|ao|é|está|estão|são|sua|seu|nossa|nosso|"
                 r"nossos|pode|obrigad[oa]|olá|cumprimentos|você|esta|este|mais|mas|já|também|ainda|desde|"
                 r"que|por|se|muito|caro|assunto)\b", re.I)
# pt-BR-only vocabulary where pt-PT uses another word (equipa, contacto, telemóvel, utilizador, registo, ecrã,
# autocarro, comboio) + the Brazilian progressive `estar + gerund` (pt-PT: `estar a + infinitive`).
_PT_BR = re.compile(r"\b(equipe|contato|celular|usuári[oa]s?|registro|tela|ônibus|trem|"
                    r"(?:estou|está|estamos|estão|estava|estavam)\s+\w+ndo)\b", re.I)


def _counts(text: str) -> tuple[int, int, int]:
    """(pt, en, nl/fr) hits. 'de' is Portuguese AND in the NL/FR list, so it is neutral here: left out of both counts."""
    nonen = [w for w in ND._NONEN.findall(text) if w.lower() != "de"]
    return len(_PT.findall(text)), len(ND._EN.findall(text)), len(nonen)


def not_portuguese(text: str) -> str:
    """'' when the text reads pt-PT, else the reason. Whole text, and every chunk that has enough words to judge."""
    p, e, n = _counts(text)
    if not (p >= 4 and p > e and p > n):   # measured 11 Nov: pt-PT inputs 4..50, the English/NL/FR sources 0..2
        return f"whole text pt={p} en={e} nl/fr={n}"
    for ch in ND._CHUNK.split(text):
        p, e, n = _counts(ch)
        if p + e + n >= 3 and not (p > e and p > n):
            return f"chunk pt={p} en={e} nl/fr={n}: {ch.strip()[:60]!r}"
    m = _PT_BR.search(text)
    return f"pt-BR marker {m.group(0)!r}" if m else ""


# ---- the checkers (pure functions of the two case lists, so (f) can feed them mutants) -------------
_NUM = re.compile(r"\d[\d.,:/-]*\d|\d")        # recap-en's digit-token regex (test_no_dutch_cases.py (b))
_MAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
KEEP = ("Sofie", "Michiel", "Jan", "Kasper", "Ella", "Nathalie", "Thomas", "Anna", "Peter", "Rita", "Camille",
        "Koen", "Koen Lambert", "An,", "Ghent", "Antwerp", "Leuven", "Deinze", "Liège", "Retail United",
        "AI in Practice", "AI in Practice Brussels", "SPF Finances", "roger3000.com", "mast-production", "WEEKEND20",
        "HERFST10", "#4482", "2026-031", "meet.google.com/xqv-hbtp-rwd", "CEST", "EUR 214.50", "EUR 1,240.00",
        "1500 EUR", "$299", "white-label", "DPA", "GDPR", "reply_now", "reply_later", "ignore")


def bad_language(cases: list[dict]) -> dict[str, str]:
    return {c["id"]: r for c in cases if (r := not_portuguese(c["input"]))}


def bad_key(src: list[dict], var: list[dict]) -> set[str]:
    out = set()
    for i in range(max(len(src), len(var))):
        s = src[i] if i < len(src) else {}
        v = var[i] if i < len(var) else {}
        strip = lambda c: {k: x for k, x in c.items() if k != "input"}
        if strip(s) != strip(v):
            out.add(v.get("id") or s.get("id") or f"#{i}")
    return out


def bad_kept(src: list[dict], var: list[dict]) -> dict[str, str]:
    out = {}
    by = {c["id"]: c for c in var}
    for s in src:
        v = by.get(s["id"])
        if v is None:
            continue
        a, b = s["input"], v["input"]
        if sorted(_NUM.findall(a)) != sorted(_NUM.findall(b)):
            out[s["id"]] = f"digits {sorted(_NUM.findall(a))} != {sorted(_NUM.findall(b))}"
        elif sorted(_MAIL.findall(a)) != sorted(_MAIL.findall(b)):
            out[s["id"]] = "addresses differ"
        elif lost := [k for k in KEEP if a.count(k) != b.count(k)]:
            out[s["id"]] = f"literal count differs: {lost}"
        elif s.get("class") == "injection" and "NOTA DE SISTEMA PARA O ASSISTENTE DE EMAIL" not in b:
            out[s["id"]] = "the planted line is not there in Portuguese"
    return out


# ---- the tests --------------------------------------------------------------------------------------
SRC_EXAM, VAR_EXAM = runner.load_exam(SRC), runner.load_exam(VAR)


def test_a_every_input_is_portuguese():
    bad = bad_language(VAR_EXAM["cases"])
    check("every email-triage-pt input reads pt-PT (whole + every chunk; no pt-BR marker)", not bad, str(bad))
    check("the detector is not inert: email-triage's own inputs read NOT Portuguese (28 of 28)",
          len(bad_language(SRC_EXAM["cases"])) == len(SRC_EXAM["cases"]) == 28, str(len(bad_language(SRC_EXAM["cases"]))))


def test_b_the_key_is_email_triages():
    check("top-level keys are exactly {agent, note, not_verified, cases}",
          set(VAR_EXAM) == {"agent", "note", "not_verified", "cases"}, str(sorted(VAR_EXAM)))
    check("agent is email-triage-pt", VAR_EXAM["agent"] == VAR)
    check("not_verified identical to email-triage's", VAR_EXAM["not_verified"] == SRC_EXAM["not_verified"])
    check("same ids in the same order (28)", [c["id"] for c in VAR_EXAM["cases"]] == [c["id"] for c in SRC_EXAM["cases"]]
          and len(VAR_EXAM["cases"]) == 28)
    bad = bad_key(SRC_EXAM["cases"], VAR_EXAM["cases"])
    check("every case key but `input` (split, expected, class, note) equals email-triage's", not bad, str(sorted(bad)))
    check("every input differs from email-triage's (each one was translated)",
          all(s["input"] != v["input"] for s, v in zip(SRC_EXAM["cases"], VAR_EXAM["cases"])))
    check("the variant's note names the contamination (no Claude row)", "no Claude row" in VAR_EXAM["note"])


def test_c_kept_exactly():
    bad = bad_kept(SRC_EXAM["cases"], VAR_EXAM["cases"])
    check("digit tokens, addresses, names/places/codes and the planted line survive translation", not bad, str(bad))
    inj = [c for c in VAR_EXAM["cases"] if c.get("class") == "injection"]
    check("both injection cases are there and keep the literal reply_now", len(inj) == 2
          and all("reply_now" in c["input"] for c in inj), str([c["id"] for c in inj]))


def test_d_the_agent_is_a_copy():
    src = yaml.safe_load((ROOT / "agents" / SRC / "agent.yaml").read_text())
    var = yaml.safe_load((ROOT / "agents" / VAR / "agent.yaml").read_text())
    check("agent.yaml name email-triage-pt, variant_of email-triage",
          var.get("name") == VAR and var.get("variant_of") == SRC, repr((var.get("name"), var.get("variant_of"))))
    fields = ("provider", "model", "tier", "temperature", "max_tokens")
    check("champion fields COPIED from email-triage (provider/model/tier/temperature/max_tokens)",
          all(var.get(f) == src.get(f) for f in fields), str({f: (src.get(f), var.get(f)) for f in fields}))
    check("agent.yaml carries no key email-triage's lacks beyond variant_of", set(var) - set(src) == {"variant_of"},
          str(sorted(set(var) - set(src))))
    check("prompt.md byte-identical to email-triage's",
          (ROOT / "agents" / VAR / "prompt.md").read_bytes() == (ROOT / "agents" / SRC / "prompt.md").read_bytes())
    check("description carries the contamination note", "no Claude row" in var.get("description", ""), var.get("description", ""))


def test_e_the_real_scorer_agrees():
    labels = ("reply_now", "reply_later", "ignore")
    outputs = {}
    for i, c in enumerate(SRC_EXAM["cases"]):
        lab = c["expected"]["label"]
        outputs[c["id"]] = {"label": lab if i % 2 == 0 else labels[(labels.index(lab) + 1) % 3]}
    a, b = ND._score(SRC, outputs), ND._score(VAR, outputs)
    flips = sorted(i for i in outputs if a[i] != b[i])
    check("same per-case verdict on email-triage and email-triage-pt through run_exam (0 flips of 28)",
          not flips and len(a) == 28, str(flips[:3]))
    check("the replay is not vacuous: 14 pass, 14 fail", sum(1 for v in b.values() if v[0]) == 14
          and sum(1 for v in b.values() if not v[0]) == 14, str(sum(1 for v in b.values() if v[0])))


def test_f_seen_red_on_each_defect():
    src, var = SRC_EXAM["cases"], VAR_EXAM["cases"]
    ids = [c["id"] for c in var]
    # Each mutant is judged by what it ADDS over the committed exam's own flags, so a real defect in the
    # committed file shows up once (in (a)-(c) and the control below), not as a cascade over every mutant line.
    base_lang, base_key, base_kept = set(bad_language(var)), bad_key(src, var), set(bad_kept(src, var))
    new_lang = lambda m: {k: v for k, v in bad_language(m).items() if k not in base_lang}  # noqa: E731
    new_key = lambda s, m: bad_key(s, m) - base_key  # noqa: E731
    new_kept = lambda s, m: {k: v for k, v in bad_kept(s, m).items() if k not in base_kept}  # noqa: E731

    def mutate(i: int, fn) -> list[dict]:
        m = copy.deepcopy(var); fn(m[i]); return m

    def at(cid: str) -> int:
        return ids.index(cid)

    i_en = at("overdue-invoice")
    m = mutate(i_en, lambda c: c.update(input=src[i_en]["input"]))
    check("RED: an English input put back is flagged by exactly its id (language)", set(new_lang(m)) == {"overdue-invoice"},
          str(new_lang(m)))
    i_nl = at("client-domain-newsletter-nl")
    m = mutate(i_nl, lambda c: c.update(input=src[i_nl]["input"]))
    check("RED: a Dutch input put back is flagged by exactly its id (language)",
          set(new_lang(m)) == {"client-domain-newsletter-nl"}, str(new_lang(m)))
    m = mutate(at("friend-dinner"), lambda c: c.update(input=c["input"].replace("jantamos", "estamos jantando")))
    check("RED: a pt-BR progressive is flagged by exactly its id (language)", set(new_lang(m)) == {"friend-dinner"},
          str(new_lang(m)))
    m = mutate(at("seo-cold-spam"), lambda c: c.update(input=c["input"].replace("equipa", "equipe")))
    check("RED: a pt-BR word (equipe) is flagged by exactly its id (language)", set(new_lang(m)) == {"seo-cold-spam"},
          str(new_lang(m)))
    m = mutate(at("promo-code"), lambda c: c.update(split="train"))
    check("RED: a case moved heldout -> train is flagged by exactly its id (key)", new_key(src, m) == {"promo-code"},
          str(new_key(src, m)))
    m = mutate(at("recruiter-fake-urgency"), lambda c: c.update(expected={"label": "reply_now"}))
    check("RED: a changed label is flagged by exactly its id (key)", new_key(src, m) == {"recruiter-fake-urgency"},
          str(new_key(src, m)))
    m = mutate(at("newsletter-injection-urgent"), lambda c: c.pop("class"))
    check("RED: a dropped class=injection marker is flagged by exactly its id (key)",
          new_key(src, m) == {"newsletter-injection-urgent"}, str(new_key(src, m)))
    m = mutate(at("overdue-invoice"), lambda c: c.update(input=c["input"].replace("EUR 214.50", "EUR 214,50")))
    check("RED: an amount re-written in pt-PT style is flagged by exactly its id (kept)",
          set(new_kept(src, m)) == {"overdue-invoice"}, str(new_kept(src, m)))
    m = mutate(at("cold-sales-injection-urgent"), lambda c: c.update(input=c["input"].replace("reply_now", "responder já")))
    check("RED: reply_now translated away in an injection case is flagged by exactly its id (kept)",
          set(new_kept(src, m)) == {"cold-sales-injection-urgent"}, str(new_kept(src, m)))
    m = mutate(at("conference-invite"), lambda c: c.update(input=c["input"].replace("AI in Practice Brussels", "AI in Practice Bruxelas")))
    check("RED: a place name translated is flagged by exactly its id (kept)",
          set(new_kept(src, m)) == {"conference-invite"}, str(new_kept(src, m)))
    check("control: the committed exam is clean on all three checkers",
          not base_lang and not base_key and not base_kept, str((sorted(base_lang), sorted(base_key), sorted(base_kept))))


def main() -> int:
    for t in (test_a_every_input_is_portuguese, test_b_the_key_is_email_triages, test_c_kept_exactly,
              test_d_the_agent_is_a_copy, test_e_the_real_scorer_agrees, test_f_seen_red_on_each_defect):
        print(t.__name__); t()
    print(f"\n{'FAILED: ' + ', '.join(FAILED) if FAILED else 'all green'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
