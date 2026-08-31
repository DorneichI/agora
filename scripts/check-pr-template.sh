#!/usr/bin/env bash
# Validates a PR body against .github/PULL_REQUEST_TEMPLATE.md's required structure.
# See docs/superpowers/specs/2026-08-31-pr-template-design.md's "CI enforcement" section for why.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: check-pr-template.sh <pr-body-file>" >&2
  exit 2
fi

body_file="$1"

if [ ! -f "$body_file" ]; then
  echo "error: PR body file '$body_file' not found" >&2
  exit 2
fi

valid_types="feat fix chore docs refactor test ci build perf style"
fail=0

fail_msg() {
  echo "::error::$1"
  fail=1
}

# Prints the lines of one "## <header>" section (up to the next "## " header or EOF),
# with HTML-comment lines and blank lines stripped.
section_body() {
  local header="$1"
  awk -v header="## $header" '
    $0 == header { in_section=1; next }
    in_section && /^## / { in_section=0 }
    in_section { print }
  ' "$body_file" | grep -v '^<!--' | sed '/^[[:space:]]*$/d'
}

for header in "Summary" "Related issue" "Type of change" "Affected package(s)" "Test plan"; do
  if ! grep -qxF "## $header" "$body_file"; then
    fail_msg "PR body is missing required section header: '## $header'"
  fi
done

if [ "$fail" -eq 1 ]; then
  exit 1
fi

summary_body="$(section_body "Summary")"
if [ -z "$summary_body" ]; then
  fail_msg "Summary section is empty"
fi

related_body="$(section_body "Related issue")"
if ! echo "$related_body" | grep -qE 'Closes #[0-9]+'; then
  fail_msg "Related issue section must contain 'Closes #<issue-number>'"
fi

type_body="$(section_body "Type of change")"
if [ -z "$type_body" ]; then
  fail_msg "Type of change section is empty — list at least one type"
else
  while IFS= read -r line; do
    stripped="${line#- }"
    match=0
    for valid in $valid_types; do
      if [ "$stripped" = "$valid" ]; then
        match=1
        break
      fi
    done
    if [ "$match" -eq 0 ]; then
      fail_msg "Type of change contains an unrecognized entry: '$line'"
    fi
  done <<< "$type_body"
fi

package_body="$(section_body "Affected package(s)")"
if [ -z "$package_body" ]; then
  fail_msg "Affected package(s) section is empty — list at least one package"
else
  while IFS= read -r line; do
    stripped="${line#- }"
    if [ "$stripped" != "backend" ] && [ "$stripped" != "web" ] && [ "$stripped" != "mobile" ] && [ "$stripped" != "repo-wide / tooling" ]; then
      fail_msg "Affected package(s) contains an unrecognized entry: '$line'"
    fi
  done <<< "$package_body"
fi

testplan_body="$(section_body "Test plan")"
non_placeholder="$(echo "$testplan_body" | grep -vxF -- '- [ ]' || true)"
if [ -z "$non_placeholder" ]; then
  fail_msg "Test plan section is still the unmodified empty placeholder — describe how this was verified"
fi

if [ "$fail" -eq 1 ]; then
  exit 1
fi

echo "PR body matches the required template structure."
