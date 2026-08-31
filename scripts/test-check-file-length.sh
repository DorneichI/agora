#!/usr/bin/env bash
# Hand-rolled assertions for check-file-length.sh, run against fixture files only.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
check_script="$script_dir/check-file-length.sh"

pass=0
fail=0

assert_true() {
  local desc="$1" condition="$2"
  if [ "$condition" = "true" ]; then
    pass=$((pass + 1))
  else
    fail=$((fail + 1))
    echo "FAIL: $desc"
  fi
}

assert_contains() {
  local desc="$1" haystack="$2" needle="$3"
  case "$haystack" in
    *"$needle"*) pass=$((pass + 1)) ;;
    *)
      fail=$((fail + 1))
      echo "FAIL: $desc (expected output to contain: $needle)"
      ;;
  esac
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

seq 1 100 > "$work/short.py"
seq 1 400 > "$work/exactly_400.py"
seq 1 401 > "$work/over_by_one.py"
seq 1 900 > "$work/way_over.py"

# All files within the limit: pass.
set +e
out1="$(bash "$check_script" 400 "$work/short.py" "$work/exactly_400.py")"
status1=$?
set -e
assert_true "all files within limit exits zero" "$([ "$status1" -eq 0 ] && echo true || echo false)"

# One file one line over the limit: fail, and name the file.
set +e
out2="$(bash "$check_script" 400 "$work/short.py" "$work/over_by_one.py" 2>&1)"
status2=$?
set -e
assert_true "one file over limit exits non-zero" "$([ "$status2" -ne 0 ] && echo true || echo false)"
assert_contains "over-limit output names the file" "$out2" "over_by_one.py"

case "$out2" in
  *short.py*)
    fail=$((fail + 1))
    echo "FAIL: over-limit output should not flag the compliant file"
    ;;
  *) pass=$((pass + 1)) ;;
esac

# Multiple files over the limit: fail, and both are named.
set +e
out3="$(bash "$check_script" 400 "$work/over_by_one.py" "$work/way_over.py" 2>&1)"
status3=$?
set -e
assert_true "multiple files over limit exits non-zero" "$([ "$status3" -ne 0 ] && echo true || echo false)"
assert_contains "multi-violation output names first file" "$out3" "over_by_one.py"
assert_contains "multi-violation output names second file" "$out3" "way_over.py"

# No files passed at all: pass (nothing to check).
set +e
out4="$(bash "$check_script" 400)"
status4=$?
set -e
assert_true "no files passed exits zero" "$([ "$status4" -eq 0 ] && echo true || echo false)"

# A passed path that doesn't exist (e.g. deleted-but-still-listed by a caller): skipped, not an error.
set +e
out5="$(bash "$check_script" 400 "$work/does_not_exist.py")"
status5=$?
set -e
assert_true "missing file is skipped, not a failure" "$([ "$status5" -eq 0 ] && echo true || echo false)"

# Missing max-lines argument entirely: usage error.
set +e
out6="$(bash "$check_script" 2>&1)"
status6=$?
set -e
assert_true "missing max-lines argument exits non-zero" "$([ "$status6" -ne 0 ] && echo true || echo false)"
assert_contains "missing max-lines output shows usage" "$out6" "Usage"

echo ""
echo "Passed: $pass, Failed: $fail"
if [ "$fail" -gt 0 ]; then
  exit 1
fi
