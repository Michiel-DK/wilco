"""Spoken-number parser: the numbers a SOURCE text spells in English words.

Used by evals/transcript-en/properties.py::check_grounded to widen the SOURCE side
only. check_grounded is an ABSENCE check ("every number the output writes must exist
in the source"); human call transcripts spell every number ("thirty-four", "two four
one seven") and contain zero digits, so a correct recap that writes digits used to
fail. This module adds the digit strings those words denote to the set of source
numbers. It never touches the output side, never normalises digits, and shares no
helper with sandbox/numnorm.py or runner._norm_digits (CLAUDE.md gotcha 4:
normalisation is directional; widening more than the source over-reaches and waves
fabrications through).

API
---
    word_numbers(text) -> set[str]

Elements are digit STRINGS in the form evals/transcript-en's _NUM_RE produces
('34', '4230.45', '05'), never ints or floats.

Grammar (case-insensitive; words are [a-z]+ tokens)
---------------------------------------------------
  unit      zero one two ... nine          (0-9)
  teen      ten eleven ... nineteen        (10-19)
  tens      twenty thirty ... ninety       (20-90)
  scale     hundred thousand million
  cardinal  tens [unit]                    'thirty-four', 'forty eight'  -> 34, 48
            [chunk] hundred [and] [..]     'three hundred and fifty'     -> 350
            chunk thousand [and] [..]      'four thousand two hundred and thirty' -> 4230
            teen/tens/unit hundred         'fifteen hundred'             -> 1500
            a bare scale word counts as 1x ('hundred' -> 100)
            'and' joins only directly after a scale word and before a number word.
  decimal   cardinal 'point' tail          tail = tens/teen [unit]  ('forty five' -> 45)
                                           or a run of digit words  ('four five' -> 45;
                                           'oh five' -> 05). Appended: '4230.45'.
  run       >= 2 consecutive digit words (unit, zero, oh) concatenated
            'two four one seven' -> 2417; 'double eight three two' -> 8832
            ('double'/'triple' repeat the next digit word). A digit word directly
            followed by a scale word ('two hundred') belongs to the cardinal, not
            the run.
  singles   every unit/teen/tens word's own value is also kept ('thirty-four' ->
            34, 30 and 4). Scale words are NOT kept on their own (only inside a
            composed cardinal), 'oh' counts only inside a run or decimal tail.

Separators
----------
  whitespace and hyphens JOIN tokens ('thirty-four' == 'thirty four').
  AppTek markup: '(um)' '(uh)' style parenthetical tags are SKIPPED (transparent:
  'twenty (um) four' reads as 'twenty four'); '~' (truncated-word marker) and every
  other punctuation mark ('.' ',' ';' ':' '?' '!' quotes, newlines, speaker tags)
  BREAK a sequence. Breaking is the conservative choice for an absence check:
  'five. One. Two two nine.' yields 5, 1, 229 but NOT the concatenated 51229.

Known gaps (parser misses; they only ever cost a false FAIL, never a false pass)
  'thirty forty five' (no 'point'): yields 30 and 45, not 30.45.
  'oh' alone, ordinals ('twenty first'), fractions, 'a hundred', 'couple', 'dozen'.
"""
import re

_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
          "six": 6, "seven": 7, "eight": 8, "nine": 9}
_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
          "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
          "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
         "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1000000}
_MULT = {"double": 2, "triple": 3}

_PAREN_TAG = re.compile(r"\([A-Za-z]*\)")
_TOKEN = re.compile(r"[a-z]+|[^a-z\s-]")  # words, or one break char; ws/hyphen vanish


def _tokens(text: str) -> list:
    """Lowercased tokens: words, plus single-char BREAK markers (any non-word,
    non-space, non-hyphen char; digits count as breaks too)."""
    text = _PAREN_TAG.sub(" ", text.lower())
    return _TOKEN.findall(text)


def _is_digit_word(t: str) -> bool:
    return t in _UNITS or t == "oh"


def _digit_run(toks: list, i: int):
    """Maximal run of digit words (with double/triple) starting at i.
    Returns (digit_string, n_digit_words_counted, next_i)."""
    out = []
    n = 0
    j = i
    while j < len(toks):
        t = toks[j]
        mult = 1
        k = j
        if t in _MULT and k + 1 < len(toks) and _is_digit_word(toks[k + 1]):
            mult = _MULT[t]
            k += 1
            t = toks[k]
        if not _is_digit_word(t):
            break
        # 'two hundred' etc. belongs to a cardinal, not to the run
        if k + 1 < len(toks) and toks[k + 1] in _SCALES and mult == 1 and n > 0:
            break
        out.append(str(_UNITS.get(t, 0)) * mult)
        n += 1
        j = k + 1
    return "".join(out), n, j


def _small(toks: list, i: int):
    """tens [unit] | teen | unit at i -> (value, next_i) or None."""
    if i >= len(toks):
        return None
    t = toks[i]
    if t in _TENS:
        v = _TENS[t]
        if i + 1 < len(toks) and toks[i + 1] in _UNITS and _UNITS[toks[i + 1]] > 0:
            return v + _UNITS[toks[i + 1]], i + 2
        return v, i + 1
    if t in _TEENS:
        return _TEENS[t], i + 1
    if t in _UNITS:
        return _UNITS[t], i + 1
    return None


def _cardinal(toks: list, i: int):
    """Greedy cardinal at i -> (int, next_i) or None. The caller has already ruled
    out a digit run. States: 'none' | 'small' | 'hundred' | 'scale'; a small number
    may only start the number or follow hundred/scale, never another small."""
    total = 0
    chunk = 0
    last = "none"
    j = i
    while j < len(toks):
        t = toks[j]
        if t in _SCALES:
            sc = _SCALES[t]
            if sc == 100:
                if last == "small" and 0 < chunk < 100:
                    chunk *= 100
                elif last == "none":
                    chunk = 100
                else:
                    break
                last = "hundred"
                j += 1
            else:
                if last in ("small", "hundred"):
                    total += chunk * sc
                elif last == "none":
                    total += sc
                else:
                    break
                chunk = 0
                last = "scale"
                j += 1
            # optional 'and' right before another number word
            if (j + 1 < len(toks) and toks[j] == "and"
                    and _small(toks, j + 1) is not None):
                j += 1
            continue
        if last == "small":
            break
        s = _small(toks, j)
        if s is None:
            break
        chunk += s[0]
        last = "small"
        j = s[1]
    if last == "none":
        return None
    return total + chunk, j


def _singles(toks: list, i: int, j: int, out: set) -> None:
    for t in toks[i:j]:
        if t in _UNITS:
            out.add(str(_UNITS[t]))
        elif t in _TEENS:
            out.add(str(_TEENS[t]))
        elif t in _TENS:
            out.add(str(_TENS[t]))


def word_numbers(text: str) -> set:
    """Digit strings denoted by the English number words in `text` (see module
    docstring for the grammar). Pure; returns an empty set when there are none."""
    toks = _tokens(text)
    out = set()
    i = 0
    n = len(toks)
    while i < n:
        t = toks[i]
        startable = (t in _UNITS or t in _TEENS or t in _TENS or t in _SCALES
                     or t in _MULT or t == "oh")
        if not startable:
            i += 1
            continue
        # 1) digit run (>= 2 digit words, or a double/triple)
        if _is_digit_word(t) or t in _MULT:
            run, cnt, j = _digit_run(toks, i)
            if cnt >= 2 or (cnt == 1 and t in _MULT):
                out.add(run)
                _singles(toks, i, j, out)
                i = j
                continue
        # 2) cardinal, optionally with a decimal tail
        if t == "oh" or t in _MULT:
            i += 1
            continue
        card = _cardinal(toks, i)
        if card is None:
            i += 1
            continue
        val, j = card
        _singles(toks, i, j, out)
        text_val = str(val)
        if j < n and toks[j] == "point":
            tail = None
            k = j + 1
            if k < n and (toks[k] in _TENS or toks[k] in _TEENS):
                s = _small(toks, k)
                if s:
                    tail, k = str(s[0]), s[1]
            elif k < n and _is_digit_word(toks[k]):
                run, cnt, k2 = _digit_run(toks, k)
                if cnt >= 1:
                    tail, k = run, k2
            if tail is not None:
                _singles(toks, j + 1, k, out)
                text_val = f"{val}.{tail}"
                j = k
        out.add(text_val)
        i = j
    return out
