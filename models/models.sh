#!/usr/bin/env bash
# Build the three 16k-window Ollama models this repo's exams were measured on.
#
#   ./models/models.sh              pull each base tag, build each variant, verify it; skip what is already right
#   ./models/models.sh --dry-run    print the plan and the current state (read-only `ollama show`); pulls/builds nothing
#   ./models/models.sh --rebuild    overwrite a variant that exists with other weights or another window
#   ./models/models.sh --allow-drift  build even when a base tag now resolves to different weights than were measured
#   ./models/models.sh gemma4-e2b-ctx16k ...   only the named variants (default: all three)
#
# Each variant is the SAME weights as its base tag with one change: `PARAMETER num_ctx 16384`. Ollama's
# OpenAI-compatible endpoint ignores a window sent in the request, so the Modelfile is the only lever.
#
# A tag is not a version: `ollama pull gemma4:e4b` today can fetch other weights than the ones measured. Each
# row below records the weight blob (sha256) the committed scores were taken on, read with `ollama show
# <name> --modelfile` on the measuring machine on 2026-10-23. After a pull the script compares the base tag's
# blob to it and refuses to build on a mismatch unless --allow-drift is given; a result on drifted weights
# is a new measurement, not the committed one. Known on 2026-10-23: gemma4:e4b has moved (now 5cd492fc6f08...),
# so gemma4-e4b-ctx16k-plain (a comparison arm, not a champion) cannot be rebuilt as measured from the library
# tag, and a run that includes it pulls that tag (~9.6 GB) and then refuses it. `ollama show --modelfile` prints
# the weights first and, for gemma4, a projector blob second; the first FROM is the one compared.
#
# Exit 0: every selected variant is present at the measured window, on the measured weights unless --allow-drift
# was given and said otherwise (the last line says which). Exit 1: something was refused or
# failed, each one printed. Exit 2: usage, or no `ollama` on PATH (except --dry-run, which still prints the plan).
set -u

cd "$(dirname "$0")/.." || { echo "models.sh: cannot reach repo root"; exit 2; }

dry=0; rebuild=0; drift=0; only=""
for a in "$@"; do
  case "$a" in
    --dry-run) dry=1 ;;
    --rebuild) rebuild=1 ;;
    --allow-drift) drift=1 ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    -*) echo "models.sh: unknown argument: $a"; exit 2 ;;
    *) only="$only $a " ;;
  esac
done

# name | Modelfile | base tag | weight blob the scores were measured on
ROWS='
gemma4-e2b-ctx16k|models/gemma4-e2b-ctx16k.Modelfile|gemma4:e2b-it-qat|3646b4c147cd235a44d91df1546d3b7d8e29b547dbe4e1f80856419aa455e6fd
gemma4-e4b-ctx16k|models/gemma4-e4b-ctx16k.Modelfile|gemma4:e4b-it-qat|e8b6a059ba86947a44ace84d6e5679795bc41862c25c30513142588f0e9dba1d
gemma4-e4b-ctx16k-plain|models/gemma4-e4b-ctx16k-plain.Modelfile|gemma4:e4b|4c27e0f5b5adf02ac956c7322bd2ee7636fe3f45a8512c9aba5385242cb6e09a'

for n in $only; do
  case "$ROWS" in
    *"
$n|"*) ;;
    *) echo "models.sh: unknown model: $n (known: gemma4-e2b-ctx16k gemma4-e4b-ctx16k gemma4-e4b-ctx16k-plain)"; exit 2 ;;
  esac
done

have_ollama=0
command -v ollama >/dev/null 2>&1 && have_ollama=1
if [ "$have_ollama" -eq 0 ] && [ "$dry" -eq 0 ]; then
  echo "models.sh: no 'ollama' on PATH. Install it from https://ollama.com, or run with --dry-run to see the plan."
  exit 2
fi

blob() {   # the weight blob a name resolves to, or empty when the name is not present
  ollama show "$1" --modelfile 2>/dev/null | sed -n 's/^FROM .*sha256-\([0-9a-f]\{64\}\).*/\1/p' | head -1
}
window() {   # num_ctx set on a name, or empty
  ollama show "$1" --parameters 2>/dev/null | awk '$1 == "num_ctx" { print $2; exit }'
}

failed=0; drifted=0
while IFS='|' read -r name file base want; do
  [ -n "$name" ] || continue
  if [ -n "$only" ]; then case "$only" in *" $name "*) ;; *) continue ;; esac; fi
  if [ ! -f "$file" ]; then
    echo "FAIL  $name: $file is missing"; failed=1; continue
  fi
  if [ "$dry" -eq 1 ]; then
    echo "plan  $name: ollama pull $base (skipped when already on disk with the measured weights); ollama create $name -f $file; expect weights ${want:0:12} and num_ctx 16384"
    if [ "$have_ollama" -eq 1 ]; then
      nb="$(blob "$name")"; nw="$(window "$name")"; bb="$(blob "$base")"
      if [ -z "$nb" ]; then echo "      now: $name not present"
      elif [ "$nb" = "$want" ] && [ "$nw" = "16384" ]; then echo "      now: $name present, measured weights, num_ctx 16384 (would skip)"
      else echo "      now: $name present with weights ${nb:0:12}, num_ctx ${nw:-unset} (differs; --rebuild would overwrite)"
      fi
      if [ -z "$bb" ]; then echo "      now: base $base not pulled"
      elif [ "$bb" = "$want" ]; then echo "      now: base $base resolves to the measured weights"
      else echo "      now: base $base resolves to ${bb:0:12}, NOT the measured ${want:0:12} (a build would need --allow-drift)"
      fi
    fi
    continue
  fi

  nb="$(blob "$name")"; nw="$(window "$name")"
  if [ -n "$nb" ] && [ "$nb" = "$want" ] && [ "$nw" = "16384" ]; then
    echo "ok    $name: already built on the measured weights at num_ctx 16384; skipped"
    continue
  fi
  if [ -n "$nb" ] && [ "$drift" -eq 1 ] && [ "$nb" = "$(blob "$base")" ] && [ "$nw" = "16384" ]; then
    echo "warn  $name: already built on ${nb:0:12}, NOT the measured ${want:0:12} (--allow-drift); skipped"
    drifted=1; continue
  fi
  if [ -n "$nb" ] && [ "$rebuild" -eq 0 ]; then
    echo "FAIL  $name: exists with weights ${nb:0:12}, num_ctx ${nw:-unset}; not the measured build. Left as is (--rebuild overwrites)."
    failed=1; continue
  fi

  # a base already on disk with the measured weights is used as is: a pull could move the tag to other weights
  bb="$(blob "$base")"
  if [ "$bb" = "$want" ]; then
    echo "have  $base: already on disk with the measured weights; not pulled"
  else
    echo "pull  $base"
    if ! ollama pull "$base"; then echo "FAIL  $name: ollama pull $base failed"; failed=1; continue; fi
    bb="$(blob "$base")"
  fi
  if [ -z "$bb" ]; then
    echo "FAIL  $name: cannot read the weights of $base after the pull (ollama show --modelfile); not built"; failed=1; continue
  fi
  if [ "$bb" != "$want" ]; then
    if [ "$drift" -eq 0 ]; then
      echo "FAIL  $name: $base now resolves to weights ${bb:0:12}, not the measured ${want:0:12}. Not built (--allow-drift builds it anyway)."
      failed=1; continue
    fi
    echo "warn  $name: building on ${bb:0:12}, NOT the measured ${want:0:12}; its scores are a new measurement"
    drifted=1
  fi
  echo "build $name from $file"
  if ! ollama create "$name" -f "$file"; then echo "FAIL  $name: ollama create failed"; failed=1; continue; fi
  nb="$(blob "$name")"; nw="$(window "$name")"
  if [ "$nb" = "$bb" ] && [ "$nw" = "16384" ]; then
    echo "ok    $name: built, weights ${nb:0:12}, num_ctx 16384"
  else
    echo "FAIL  $name: after create, weights ${nb:0:12} num_ctx ${nw:-unset} (expected ${bb:0:12} / 16384)"; failed=1
  fi
done <<EOF
$ROWS
EOF

if [ "$dry" -eq 1 ]; then echo "dry run: nothing pulled or built"; exit "$failed"; fi
if [ "$failed" -eq 0 ] && [ "$drifted" -eq 1 ]; then
  echo "models.sh: every selected variant present at num_ctx 16384, but NOT all on the measured weights (--allow-drift)"
elif [ "$failed" -eq 0 ]; then
  echo "models.sh: every selected variant present on the measured weights at num_ctx 16384"
fi
exit "$failed"
