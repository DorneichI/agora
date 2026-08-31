#!/usr/bin/env bash
# Fails if any given file exceeds max_lines. Deliberately generic (no language-specific
# logic, no built-in exclusions) -- the caller (lefthook command / CI step) decides which
# files to pass in, e.g. excluding tests/ or *.test.ts(x). See root CLAUDE.md's file-length
# enforcement section for why tests are exempt.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: check-file-length.sh <max-lines> [file...]" >&2
  exit 2
fi

max_lines="$1"
shift

violations=0
for file in "$@"; do
  [ -f "$file" ] || continue
  lines=$(wc -l < "$file" | tr -d ' ')
  if [ "$lines" -gt "$max_lines" ]; then
    echo "$file: $lines lines (max $max_lines)" >&2
    violations=$((violations + 1))
  fi
done

if [ "$violations" -gt 0 ]; then
  echo "" >&2
  echo "$violations file(s) exceed the $max_lines-line limit." >&2
  exit 1
fi
