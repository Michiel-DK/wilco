#!/usr/bin/env python3
"""sandbox/numwords.py — parser rows (S-NUMWORDS-GROUNDED, criterion 2).

One row per source phrase the lane pinned, plus negative rows: the parser must NOT
emit the over-reaching values a fabrication would hide behind. Elements are digit
STRINGS ('4230.45'), never ints/floats. No I/O, no network, no inference.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from numwords import word_numbers as W  # noqa: E402

FAILED = []


def check(label, ok, extra=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {extra}" if not ok and extra else ""))
    if not ok:
        FAILED.append(label)


def has(phrase, value):
    got = W(phrase)
    check(f"{phrase!r} -> {value}", value in got, f"got {sorted(got)}")


def lacks(phrase, value):
    got = W(phrase)
    check(f"{phrase!r} does NOT yield {value}", value not in got, f"got {sorted(got)}")


def main():
    # criterion 2: the ten pinned phrases
    has("thirty-four", "34")
    has("forty eight", "48")
    has("three hundred and fifty", "350")
    has("four thousand two hundred and thirty point forty five", "4230.45")
    has("fifteen hundred", "1500")
    has("six thousand", "6000")
    has("two four one seven", "2417")
    has("five one two two nine", "51229")
    has("eight eight three two", "8832")
    has("twenty-two", "22")

    # grammar variants documented in the module docstring
    has("four thousand two hundred and thirty point four five", "4230.45")
    has("double eight three two", "8832")
    has("Thirty-Four Charlie", "34")                  # case-insensitive
    has("twenty (um) four to forty (uh) eight hours", "24")   # markup skipped
    has("twenty (um) four to forty (uh) eight hours", "48")
    has("it will be twenty dollars", "20")             # single word value
    has("thirty-four", "4")                            # every word's own value kept
    has("thirty-four", "30")
    has("oh five", "05")                               # 'oh' inside a run
    has("savings two four one seven.", "2417")

    # sensible breaks (conservative for an absence check)
    lacks("Five. One. Two two nine.", "51229")         # sentence punctuation breaks a run
    has("Five. One. Two two nine.", "229")
    lacks("twenty, four", "24")                        # a comma breaks
    lacks("twenty ~ four", "24")                       # '~' breaks
    lacks("oh, okay", "0")                             # lone 'oh' is not a digit

    # over-reach guards: values a fabrication would hide behind must NOT appear
    lacks("five hundred", "5000")
    lacks("five hundred", "50")
    lacks("fifteen hundred", "15000")
    lacks("fifteen hundred", "150")
    lacks("twenty dollars", "200")
    lacks("six thousand", "60000")
    lacks("two four one seven", "24170")
    lacks("thirty forty five cents", "30.45")          # known gap: no 'point'
    lacks("no numbers in this sentence at all", "7")
    check("no number words -> empty set", W("hello there, how are you today?") == set())
    check("digits are not parsed here", W("call 4217 now") == set())
    check("returns set of str", all(isinstance(x, str) for x in W("fifteen hundred and two")))

    print(f"\n{len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
