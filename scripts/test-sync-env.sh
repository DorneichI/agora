#!/usr/bin/env bash
# Hand-rolled assertions for sync-env.sh, run against fixture files only
# (never the real .env/.env.example).
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sync_script="$script_dir/sync-env.sh"

pass=0
fail=0

assert_eq() {
  local desc="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    pass=$((pass + 1))
  else
    fail=$((fail + 1))
    echo "FAIL: $desc"
    echo "  expected: $expected"
    echo "  actual:   $actual"
  fi
}

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

# New key gets added with placeholder; existing key's value is preserved.
cat > "$work/example1" <<'EOF'
# a comment
FOO=example-foo
BAR=example-bar
EOF
cat > "$work/env1" <<'EOF'
FOO=custom-foo
EOF
out1="$("$sync_script" "$work/example1" "$work/env1")"
assert_eq "existing value preserved" "custom-foo" "$(grep '^FOO=' "$work/env1" | cut -d= -f2-)"
assert_eq "new key gets example placeholder" "example-bar" "$(grep '^BAR=' "$work/env1" | cut -d= -f2-)"
assert_contains "output flags newly added key" "$out1" "BAR"
assert_eq "comment preserved" "# a comment" "$(head -n1 "$work/env1")"

# Stale key (not in example) is dropped and warned about.
cat > "$work/example2" <<'EOF'
FOO=example-foo
EOF
cat > "$work/env2" <<'EOF'
FOO=custom-foo
STALE=old-value
EOF
out2="$("$sync_script" "$work/example2" "$work/env2")"
if grep -q '^STALE=' "$work/env2"; then
  fail=$((fail + 1))
  echo "FAIL: stale key should have been removed"
else
  pass=$((pass + 1))
fi
assert_contains "output warns about stale key" "$out2" "STALE"

# First run (no existing env file) copies the example through as-is.
cat > "$work/example3" <<'EOF'
# header
FOO=example-foo
EOF
rm -f "$work/env3"
"$sync_script" "$work/example3" "$work/env3" > /dev/null
assert_eq "first run copies example through" "$(cat "$work/example3")" "$(cat "$work/env3")"
assert_true "no backup file on first run" "$([ ! -f "$work/env3.bak" ] && echo true || echo false)"

# Missing example file: non-zero exit, no env file written.
rm -f "$work/env4"
set +e
"$sync_script" "$work/does-not-exist" "$work/env4" > /dev/null 2>&1
status4=$?
set -e
assert_true "missing example file exits non-zero" "$([ "$status4" -ne 0 ] && echo true || echo false)"
assert_true "no env file written when example is missing" "$([ ! -f "$work/env4" ] && echo true || echo false)"

# Backup file holds the pre-merge contents.
cat > "$work/example5" <<'EOF'
FOO=example-foo
EOF
cat > "$work/env5" <<'EOF'
FOO=custom-foo
EOF
cp "$work/env5" "$work/env5.orig"
"$sync_script" "$work/example5" "$work/env5" > /dev/null
assert_eq "backup matches pre-merge contents" "$(cat "$work/env5.orig")" "$(cat "$work/env5.bak")"

echo ""
echo "Passed: $pass, Failed: $fail"
if [ "$fail" -gt 0 ]; then
  exit 1
fi
