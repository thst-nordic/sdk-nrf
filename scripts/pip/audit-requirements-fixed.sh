#!/usr/bin/env bash
# Run pip-audit on requirements-fixed.txt with Jenkins-equivalent whitelist handling.
#
# Reads scripts/pip-audit-whitelist.yml and passes each listed ID as --ignore-vuln,
# matching ncs-toolchain-bundler Jenkinsfile.bundle getPipAuditWhiteListCmd().
#
# Usage (from west workspace root):
#   ./nrf/scripts/pip/audit-requirements-fixed.sh [whitelist.yml] [requirements-fixed.txt]
#
set -euo pipefail

WHITELIST="${1:-nrf/scripts/pip-audit-whitelist.yml}"
REQUIREMENTS="${2:-nrf/scripts/requirements-fixed.txt}"
NORDIC_PYPI_INDEX="${NORDIC_PYPI_INDEX:-https://files.nordicsemi.com/artifactory/api/pypi/nordic-pypi/simple}"

log() {
    printf '[audit-requirements-fixed] %s\n' "$*"
}

if [[ ! -f "${WHITELIST}" ]]; then
    echo "error: whitelist not found: ${WHITELIST}" >&2
    exit 2
fi

if [[ ! -f "${REQUIREMENTS}" ]]; then
    echo "error: requirements file not found: ${REQUIREMENTS}" >&2
    exit 2
fi

ignore_args=()
whitelist_count=0
while IFS= read -r line; do
    id="${line#  - }"
    ignore_args+=(--ignore-vuln "${id}")
    whitelist_count=$((whitelist_count + 1))
done < <(grep '^  - ' "${WHITELIST}")

log "Auditing ${REQUIREMENTS} (${whitelist_count} whitelisted CVEs)"

export PIP_CONFIG_FILE=/dev/null
python3 -m pip install -q pip-audit
exec python3 -m pip_audit -r "${REQUIREMENTS}" \
    --index-url "${NORDIC_PYPI_INDEX}" \
    "${ignore_args[@]}"
