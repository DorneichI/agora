#!/usr/bin/env bash
# Ratchet check: fails if current coverage % dropped vs. the baseline saved from main,
# beyond a small tolerance. See root CLAUDE.md's "Coverage ratchet" section for why this
# exists instead of a fixed threshold or an external service like Codecov.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: check-coverage-ratchet.sh <label> <current_pct> <baseline_file>" >&2
  exit 2
fi

label="$1"
current="$2"
baseline_file="$3"
tolerance="0.5"

if [ ! -f "$baseline_file" ]; then
  echo "No coverage baseline found for $label yet (first run since the ratchet was introduced, or the cached baseline expired) - skipping ratchet check."
  exit 0
fi

baseline="$(cat "$baseline_file")"
echo "$label coverage: current ${current}%, baseline ${baseline}% (tolerance ${tolerance}pp)"

if awk -v cur="$current" -v base="$baseline" -v tol="$tolerance" 'BEGIN { exit !(cur + tol >= base) }'; then
  echo "$label coverage OK (no drop beyond tolerance)."
  exit 0
fi

echo "::error::$label coverage dropped from ${baseline}% to ${current}% (tolerance ${tolerance}pp)"
exit 1
