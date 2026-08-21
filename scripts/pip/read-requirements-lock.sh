#!/usr/bin/env bash
# Print west-topdir-relative pip-compile input paths from requirements-lock.in.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_IN="${SCRIPT_DIR}/requirements-lock.in"

while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "${line}" ]] && continue
    line="${line#-r }"
    printf '%s\n' "${line}"
done < "${LOCK_IN}"
