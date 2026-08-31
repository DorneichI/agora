#!/usr/bin/env bash
# Hand-rolled assertions for check-pr-template.sh, run against fixture PR-body files only.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
checker="$script_dir/check-pr-template.sh"

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

valid_body() {
  cat <<'EOF'
## Summary
Adds a widget.

## Related issue
Closes #42

## Type of change
- feat

## Affected package(s)
- web

## Test plan
- [x] Ran `npm test` locally.
EOF
}

# A fully valid body: pass.
valid_body > "$work/valid.md"
set +e
out1="$(bash "$checker" "$work/valid.md")"
status1=$?
set -e
assert_true "valid body exits zero" "$([ "$status1" -eq 0 ] && echo true || echo false)"
assert_contains "valid body output confirms match" "$out1" "matches the required template structure"

# Missing a required header: fail.
valid_body | grep -v '^## Related issue$' > "$work/missing_header.md"
set +e
out2="$(bash "$checker" "$work/missing_header.md" 2>&1)"
status2=$?
set -e
assert_true "missing header exits non-zero" "$([ "$status2" -ne 0 ] && echo true || echo false)"
assert_contains "missing header output flags it" "$out2" "missing required section header"

# Related issue left as the unfilled placeholder: fail.
valid_body | sed 's/^Closes #42$/Closes #/' > "$work/unfilled_issue.md"
set +e
out3="$(bash "$checker" "$work/unfilled_issue.md" 2>&1)"
status3=$?
set -e
assert_true "unfilled Closes # exits non-zero" "$([ "$status3" -ne 0 ] && echo true || echo false)"
assert_contains "unfilled Closes # output flags it" "$out3" "Related issue section must contain"

# Type of change fully deleted (section empty): fail.
valid_body | grep -v '^- feat$' > "$work/empty_type.md"
set +e
out4="$(bash "$checker" "$work/empty_type.md" 2>&1)"
status4=$?
set -e
assert_true "empty Type of change exits non-zero" "$([ "$status4" -ne 0 ] && echo true || echo false)"
assert_contains "empty Type of change output flags it" "$out4" "Type of change section is empty"

# Type of change has an unrecognized entry (typo): fail.
valid_body | sed 's/^- feat$/- feet/' > "$work/typo_type.md"
set +e
out5="$(bash "$checker" "$work/typo_type.md" 2>&1)"
status5=$?
set -e
assert_true "typo'd type exits non-zero" "$([ "$status5" -ne 0 ] && echo true || echo false)"
assert_contains "typo'd type output flags it" "$out5" "unrecognized entry"

# Affected package(s) has an unrecognized entry: fail.
valid_body | sed 's/^- web$/- frontend/' > "$work/typo_package.md"
set +e
out6="$(bash "$checker" "$work/typo_package.md" 2>&1)"
status6=$?
set -e
assert_true "typo'd package exits non-zero" "$([ "$status6" -ne 0 ] && echo true || echo false)"
assert_contains "typo'd package output flags it" "$out6" "unrecognized entry"

# Test plan left as the bare unmodified placeholder: fail.
valid_body | sed 's/^- \[x\] Ran `npm test` locally\.$/- [ ]/' > "$work/empty_testplan.md"
set +e
out7="$(bash "$checker" "$work/empty_testplan.md" 2>&1)"
status7=$?
set -e
assert_true "unmodified Test plan exits non-zero" "$([ "$status7" -ne 0 ] && echo true || echo false)"
assert_contains "unmodified Test plan output flags it" "$out7" "unmodified empty placeholder"

# Summary section truly empty: zero lines (not even a blank one) between its header and the
# next header. Built via a direct heredoc (not by deleting a line from valid_body) so no stray
# blank line is left behind — this is what previously made section_body's pipeline exit non-zero
# under `set -euo pipefail` and kill the whole script silently, with no ::error:: message at all.
cat <<'EOF' > "$work/truly_empty_summary.md"
## Summary
## Related issue
Closes #42

## Type of change
- feat

## Affected package(s)
- web

## Test plan
- [x] Ran `npm test` locally.
EOF
set +e
out9="$(bash "$checker" "$work/truly_empty_summary.md" 2>&1)"
status9=$?
set -e
assert_true "truly empty Summary exits non-zero" "$([ "$status9" -ne 0 ] && echo true || echo false)"
assert_contains "truly empty Summary output is not silent" "$out9" "Summary section is empty"

# Multiple valid types/packages listed: pass.
cat <<'EOF' > "$work/multi_valid.md"
## Summary
Adds a widget.

## Related issue
Closes #42

## Type of change
- feat
- fix

## Affected package(s)
- web
- backend

## Test plan
- [x] Ran `npm test` locally.
EOF
set +e
out8="$(bash "$checker" "$work/multi_valid.md")"
status8=$?
set -e
assert_true "multiple valid types/packages exits zero" "$([ "$status8" -eq 0 ] && echo true || echo false)"

echo ""
echo "Passed: $pass, Failed: $fail"
if [ "$fail" -gt 0 ]; then
  exit 1
fi
