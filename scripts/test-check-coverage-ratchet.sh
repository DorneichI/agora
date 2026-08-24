#!/usr/bin/env bash
# Hand-rolled assertions for check-coverage-ratchet.sh, run against fixture baseline
# files only.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ratchet_script="$script_dir/check-coverage-ratchet.sh"

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

# Coverage went up: pass.
echo "80.00" > "$work/baseline1"
set +e
out1="$(bash "$ratchet_script" backend 85.00 "$work/baseline1")"
status1=$?
set -e
assert_true "coverage increase exits zero" "$([ "$status1" -eq 0 ] && echo true || echo false)"
assert_contains "coverage increase output says OK" "$out1" "OK"

# Coverage dropped, but within the 0.5pp tolerance: pass.
echo "80.00" > "$work/baseline2"
set +e
out2="$(bash "$ratchet_script" backend 79.60 "$work/baseline2")"
status2=$?
set -e
assert_true "small drop within tolerance exits zero" "$([ "$status2" -eq 0 ] && echo true || echo false)"
assert_contains "small drop within tolerance output says OK" "$out2" "OK"

# Coverage dropped beyond the tolerance: fail.
echo "80.00" > "$work/baseline3"
set +e
out3="$(bash "$ratchet_script" backend 79.00 "$work/baseline3")"
status3=$?
set -e
assert_true "drop beyond tolerance exits non-zero" "$([ "$status3" -ne 0 ] && echo true || echo false)"
assert_contains "drop beyond tolerance output flags it" "$out3" "dropped"

# Coverage exactly equal to baseline: pass.
echo "80.00" > "$work/baseline4"
set +e
out4="$(bash "$ratchet_script" backend 80.00 "$work/baseline4")"
status4=$?
set -e
assert_true "equal coverage exits zero" "$([ "$status4" -eq 0 ] && echo true || echo false)"

# No baseline file yet: pass without blocking (bootstrap case).
rm -f "$work/baseline5"
set +e
out5="$(bash "$ratchet_script" backend 42.00 "$work/baseline5")"
status5=$?
set -e
assert_true "missing baseline exits zero" "$([ "$status5" -eq 0 ] && echo true || echo false)"
assert_contains "missing baseline output explains bootstrap" "$out5" "No coverage baseline"

echo ""
echo "Passed: $pass, Failed: $fail"
if [ "$fail" -gt 0 ]; then
  exit 1
fi
