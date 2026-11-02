#!/usr/bin/env python3
"""ASR scoring against the K0 references (docs/probes/k-asr-2026-10-31/): WER + entity error rate.

    python3 sandbox/asr_score.py --manifest M --hyp-dir D --transcriber NAME --transcriber-version V [--out F]

Stdlib only, no model, no network. Hypothesis for call <id> is <hyp-dir>/<id>.txt. The reference text is the
segment texts of refs/ref-<id>.json joined by ONE space in start order.

NORMALISATION (this module's own code; each rule is pinned by its own check in test_asr_score.py):
  1. lowercase
  2. curly quotes -> straight (U+2018/2019 -> ', U+201C/201D -> ")
  3. hyphens and slashes -> a space (so 'Mary-Ann' is two tokens)
  4. every punctuation character removed EXCEPT an apostrophe sitting between two letters
  5. whitespace collapsed
  6. digits kept verbatim (so '1,582' -> '1582': the comma is punctuation under rule 4, nothing more)
  NOT done, declared limitations: no number-word conversion ('five' != '5'), no thousands or decimal
  handling (3.5 -> '35' on both sides), no contraction expansion, no spelling variants.

ALIGNMENT: Levenshtein over normalised tokens with a backtrace; ties prefer diagonal, then deletion, then
insertion. A reordered adjacent pair of DISTINCT words scores 2 errors (no transposition operator).

ENTITY RULE (round 2): a reference token (a raw whitespace-split token of ONE segment) is an entity if
  (a) it contains a digit, OR
  (b) its core (the raw token stripped of surrounding quotes, brackets, tildes and punctuation) starts with an
      uppercase letter AND it is not the first token of its segment AND the previous raw token of the same
      segment does not end with '.', '?' or '!' (a sentence start inside a segment is not an entity) AND the
      raw token does not start with '(' (bracketed fillers such as '(Um)') AND the core is not in
      {I, I'm, I'll, I've, I'd, OK, Okay}.
The previous-token test reads the raw token literally: 'done."' ends with '"', so it does not end a sentence.
Bracketed fillers are NOT transparent to it: in '(um) So you', the previous raw token of 'So' is '(um)', which
does not end with . ? !, so 'So' IS an entity. On the 10 K0 references this flags 6 sentence starts after a
filler (So x2, Yeah x2, And, That's; pinned in test_asr_score.py check 9e). A raw token that normalisation splits (Mary-Ann) gives several
normalised tokens, ALL carrying the raw token's entity flag. entity error = an entity reference position
aligned to sub or del. Insertions have no reference position and never count as entity errors.

Totals: pooled_wer = sum(errors) / sum(n_ref) (the headline); mean_call_wer = mean of per-call ratios (reported
separately, labelled; long calls weigh the same as short ones there).

Failure modes: score_run RAISES (FileNotFoundError for a missing hyp file, ValueError for an empty
transcriber / transcriber_version or an empty reference); the CLI prints the message to stderr and exits 2.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ENTITY_EXCLUDED = frozenset({"I", "I'm", "I'll", "I've", "I'd", "OK", "Okay"})
_QUOTES = {"‘": "'", "’": "'", "“": '"', "”": '"'}


def _straight(s: str) -> str:
    for k, v in _QUOTES.items():
        s = s.replace(k, v)
    return s


def _norm_raw(tok: str) -> list[str]:
    """Normalise ONE whitespace-delimited raw token to zero or more tokens."""
    s = _straight(tok).lower().replace("-", " ").replace("/", " ")
    out = []
    for piece in s.split():
        chars = []
        for i, c in enumerate(piece):
            if c.isalnum():
                chars.append(c)
            elif c == "'" and 0 < i < len(piece) - 1 and piece[i - 1].isalpha() and piece[i + 1].isalpha():
                chars.append(c)
        if chars:
            out.append("".join(chars))
    return out


def normalize(text: str) -> list[str]:
    toks: list[str] = []
    for raw in text.split():
        toks.extend(_norm_raw(raw))
    return toks


def align(ref: list[str], hyp: list[str]) -> list[tuple[str, str | None, str | None]]:
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub = d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1])
            d[i][j] = min(sub, d[i - 1][j] + 1, d[i][j - 1] + 1)
    ops: list[tuple[str, str | None, str | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            ops.append(("ok" if ref[i - 1] == hyp[j - 1] else "sub", ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            ops.append(("del", ref[i - 1], None))
            i -= 1
        else:
            ops.append(("ins", None, hyp[j - 1]))
            j -= 1
    ops.reverse()
    return ops


def _counts(ops) -> dict:
    s = sum(o[0] == "sub" for o in ops)
    dl = sum(o[0] == "del" for o in ops)
    ins = sum(o[0] == "ins" for o in ops)
    n_ref = sum(o[0] != "ins" for o in ops)
    if n_ref == 0:
        raise ValueError("empty reference: WER is undefined (fail loud)")
    return {"substitutions": s, "deletions": dl, "insertions": ins, "n_ref": n_ref,
            "errors": s + dl + ins, "wer": (s + dl + ins) / n_ref}


def wer(ref_text: str, hyp_text: str) -> dict:
    return _counts(align(normalize(ref_text), normalize(hyp_text)))


def _ordered(ref_segments):
    return sorted(ref_segments, key=lambda s: s["start"])  # stable


def ref_text_of(ref_segments) -> str:
    return " ".join(s["text"] for s in _ordered(ref_segments))


def _is_entity(raw: str, prev: str | None) -> bool:
    """prev = the previous raw token of the same segment, None when raw is the segment's first token."""
    if any(c.isdigit() for c in raw):
        return True
    if prev is None or prev.endswith((".", "?", "!")) or raw.startswith("("):
        return False
    core = _straight(raw).strip(".,;:!?\"'()[]{}<>~-/ ")
    return bool(core) and core[0].isupper() and core not in ENTITY_EXCLUDED


def entity_positions(ref_segments) -> set[int]:
    pos, out = 0, set()
    for seg in _ordered(ref_segments):
        raws = seg["text"].split()
        for k, raw in enumerate(raws):
            norm = _norm_raw(raw)
            if _is_entity(raw, raws[k - 1] if k else None):
                out.update(range(pos, pos + len(norm)))
            pos += len(norm)
    return out


def score_call(ref_segments, hyp_text: str) -> dict:
    ref_tokens = normalize(ref_text_of(ref_segments))
    ops = align(ref_tokens, normalize(hyp_text))
    row = _counts(ops)
    ents = entity_positions(ref_segments)
    ref_i, bad = 0, 0
    for op, _, _ in ops:
        if op == "ins":
            continue
        if ref_i in ents and op in ("sub", "del"):
            bad += 1
        ref_i += 1
    row["entity_errors"] = bad
    row["entity_n"] = len(ents)
    return row


def score_run(manifest_path, hyp_dir, transcriber: str, transcriber_version: str) -> dict:
    if not isinstance(transcriber, str) or not transcriber.strip():
        raise ValueError("transcriber is required and must be non-empty")
    if not isinstance(transcriber_version, str) or not transcriber_version.strip():
        raise ValueError("transcriber_version is required and must be non-empty")
    mpath, hdir = Path(manifest_path), Path(hyp_dir)
    manifest = json.loads(mpath.read_text())
    rows = []
    for call in manifest["calls"]:
        hyp_file = hdir / f"{call['id']}.txt"
        if not hyp_file.is_file():
            raise FileNotFoundError(f"missing hypothesis file: {hyp_file}")
        segs = json.loads((mpath.parent / call["ref_file"]).read_text())["segments"]
        row = score_call(segs, hyp_file.read_text())
        row["id"] = call["id"]
        rows.append(row)
    if not rows:
        raise ValueError("manifest lists no calls")
    errs, n = sum(r["errors"] for r in rows), sum(r["n_ref"] for r in rows)
    ee, en = sum(r["entity_errors"] for r in rows), sum(r["entity_n"] for r in rows)
    return {
        "transcriber": transcriber, "transcriber_version": transcriber_version,
        "n_calls": len(rows), "calls": rows,
        "totals": {
            "errors": errs, "n_ref": n, "pooled_wer": errs / n,
            "mean_call_wer": sum(r["wer"] for r in rows) / len(rows),
            "entity_errors": ee, "entity_n": en, "entity_error_rate": (ee / en) if en else None,
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="WER + entity error rate against the K0 references")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--hyp-dir", required=True)
    ap.add_argument("--transcriber", required=True)
    ap.add_argument("--transcriber-version", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        res = score_run(a.manifest, a.hyp_dir, a.transcriber, a.transcriber_version)
    except (ValueError, FileNotFoundError, KeyError, OSError) as e:
        print(f"asr_score: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    text = json.dumps(res, indent=1)
    if a.out:
        Path(a.out).write_text(text + "\n")
    t = res["totals"]
    print(f"{res['transcriber']} {res['transcriber_version']}: pooled_wer={t['pooled_wer']:.4f} "
          f"(mean_call_wer={t['mean_call_wer']:.4f}) entity_errors={t['entity_errors']}/{t['entity_n']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
