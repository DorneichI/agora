#!/usr/bin/env bash
# Regenerates an env file from an example file: keeps existing values,
# adds new keys from the example as placeholders, and drops keys the
# example no longer declares. See docs/superpowers/specs (design) and
# CLAUDE.md's Secrets section.
set -euo pipefail

example_file="${1:-.env.example}"
env_file="${2:-.env}"

if [ ! -f "$example_file" ]; then
  echo "Error: example file '$example_file' not found." >&2
  exit 1
fi

key_regex='^[A-Za-z_][A-Za-z0-9_]*='

env_exists=0
if [ -f "$env_file" ]; then
  env_exists=1
fi

tmp_out="$(mktemp)"
trap 'rm -f "$tmp_out"' EXIT

carried=()
added=()
removed=()

while IFS= read -r line || [ -n "$line" ]; do
  if [[ "$line" =~ $key_regex ]]; then
    key="${line%%=*}"
    example_value="${line#*=}"
    if [ "$env_exists" -eq 1 ] && grep -q "^${key}=" "$env_file"; then
      existing_value="$(grep "^${key}=" "$env_file" | tail -n1)"
      existing_value="${existing_value#*=}"
      echo "${key}=${existing_value}" >> "$tmp_out"
      carried+=("$key")
    else
      echo "${key}=${example_value}" >> "$tmp_out"
      added+=("$key")
    fi
  else
    echo "$line" >> "$tmp_out"
  fi
done < "$example_file"

if [ "$env_exists" -eq 1 ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ "$line" =~ $key_regex ]]; then
      key="${line%%=*}"
      if ! grep -q "^${key}=" "$example_file"; then
        removed+=("${key}")
      fi
    fi
  done < "$env_file"

  cp "$env_file" "${env_file}.bak"
fi

cp "$tmp_out" "$env_file"

if [ "${#added[@]}" -gt 0 ]; then
  echo "Added (placeholder values from ${example_file} -- fill these in):"
  printf '  %s\n' "${added[@]}"
fi

if [ "${#removed[@]}" -gt 0 ]; then
  echo "Warning: dropped keys not present in ${example_file} (values discarded, not shown -- check ${env_file}.bak if you need the old value):"
  printf '  %s\n' "${removed[@]}"
fi

if [ "${#carried[@]}" -gt 0 ]; then
  echo "Carried over unchanged: ${#carried[@]} key(s)"
fi

if [ "$env_exists" -eq 1 ]; then
  echo "Done. Wrote ${env_file} (backup: ${env_file}.bak)"
else
  echo "Done. Wrote ${env_file}"
fi
