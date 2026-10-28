#!/bin/bash
# The deterministic test gate for this repo: `./scripts/test.sh` from the repo root (moved here from
# .cline/test.sh on 2026-10-28; a private shim at that old path still execs this file, because the
# lane tooling resolves its test command as $CLINE_TEST_CMD > ./.cline/test.sh > detect(pytest|npm
# test|make test) and REFUSES to ship when it finds none — before this file existed the detect step
# found nothing here, so every lane aborted fail-closed). This is what makes a lane shippable.
#
# WHY NOT pytest. Every test file in this repo is a module-level script that ends in
# sys.exit(1) — `sandbox/test_router_knobs.py` has zero `def test_` functions. pytest
# would collect nothing from it and report success. The correct invocation is
# `python3 <file>`, one process per file.
#
# WHY NOT check-all. That runs local inference, takes ~10 min, and has been KILLED
# mid-run four times (CLAUDE.md). It is the wrong gate for a build lane. This suite is
# deterministic, needs no model, and finishes in seconds.
# The gate is inference-free unless `SANDBOX_E2E=1` (test_shadow_gmail's one real call is opt-in).
#
# EVERY LINE BELOW ENCODES A ZSH GOTCHA THIS REPO HAS ALREADY PAID FOR:
#   - bash, not zsh          — zsh `nomatch` aborts a whole command line on an empty glob
#   - `find`, not a glob     — FOUR test files sit directly in evals/, one level above
#                              where `evals/*/test_*.py` looks (test_e10_ladder,
#                              test_e13_recap, test_pr2_hardcases, test_recap_adversarial).
#                              Measured 2026-08-05: the glob finds 12 of 16, the find 16.
#                              CLAUDE.md still says "three" — it predates Lane A2.
#   - `while IFS= read -r`   — zsh does not word-split an unquoted var, so `for t in $files`
#                              runs the loop ONCE with all paths as a single argument
#   - `rc=$?` immediately    — any intervening command clobbers $?, including a command
#                              substitution inside the same argument list
#   - no bare globs anywhere — see the `rm -f gate_*.log` incident
set -u

cd "$(dirname "$0")/.." || { echo "test.sh: cannot reach repo root"; exit 2; }

LIST="$(mktemp)"
trap 'rm -f "$LIST"' EXIT

# `.claude/` is excluded because `.claude/worktrees/` holds full repo copies during a
# single-lane-build. Without this, the gate sweeps ANOTHER BRANCH's test files, runs
# them, and reports the result as this branch's — and the inflated count would also mask
# a deletion from the floor below. Empty when this was written; the exclusion is the
# point, not the current contents.
find . -name 'test_*.py' \
  -not -path './.git/*' -not -path './harness/*' -not -path './.claude/*' \
  | sort > "$LIST"
n=$(wc -l < "$LIST" | tr -d ' ')

# Fail-closed floor. This is a FLOOR, not an exact count: adding test files needs no
# edit here, removing one fails loudly. The count has gone stale in CLAUDE.md four
# times (11 -> 14 -> 15 -> 16) precisely because it was written as an exact figure.
# On its own this floor only catches a NET decrease — see the assertion floor below,
# which is what actually catches a deleted test swapped for a placeholder.
MIN_TEST_FILES="${MIN_TEST_FILES:-20}"
if [ "$n" -lt "$MIN_TEST_FILES" ]; then
  echo "test.sh: found $n test files, floor is $MIN_TEST_FILES — refusing to run."
  echo "         A shrinking suite is a green that was not earned. If files were"
  echo "         legitimately removed, lower MIN_TEST_FILES in the same commit."
  exit 2
fi

# ASSERTION FLOOR. The file floor above only notices a NET decrease: delete one real
# test file, add a no-op test_zz.py, and the count is unchanged — which is the modal
# cheap-model failure, not a paranoid one (a model that cannot make a test pass replaces
# it with a placeholder). So count the assertions too.
#
# We count `check(` because that is what this repo actually uses. The harness ratchet
# counts bare `assert` and therefore sees 7 lines here against 421 check() calls — about
# 1.6% of the suite. This is the ratchet the harness cannot give us.
MIN_CHECKS="${MIN_CHECKS:-505}"
c=0
while IFS= read -r t; do
  k=$(grep -cE '\bcheck\(|\b_check\(|\bok\(' "$t" || true)
  c=$((c + k))
done < "$LIST"
if [ "$c" -lt "$MIN_CHECKS" ]; then
  echo "test.sh: found $c check() assertions, floor is $MIN_CHECKS — refusing to run."
  echo "         Test files can stay at $n while their contents are gutted. If checks"
  echo "         were legitimately removed, lower MIN_CHECKS in the same commit and say"
  echo "         which ones in the message."
  exit 2
fi

echo "test.sh: running $n test files, $c check() assertions"
failed=0
failing_files=""

while IFS= read -r t; do
  out="$(python3 "$t" 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "── FAIL rc=$rc  $t"
    echo "$out" | tail -25
    echo
    failed=$((failed + 1))
    failing_files="$failing_files $t"
  fi
done < "$LIST"

echo
if [ "$failed" -ne 0 ]; then
  echo "test.sh: ✗ $failed of $n test files FAILED:$failing_files"
  exit 1
fi
echo "test.sh: ✓ all $n test files passed"
exit 0
