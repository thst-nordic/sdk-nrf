#!/usr/bin/env bash
# Verify requirements-fixed.txt pins are installable from Nordic PyPI on each
# supported platform (Linux, Windows, macOS arm64) for Python 3.12.
#
# Default (--fast): PEP 503 simple index scan + HEAD on wheel/sdist URLs.
# Full mode: pip download with --platform overrides (slower, highest fidelity).
#
# Usage (from west workspace root):
#   ./nrf/scripts/pip/validate-requirements-fixed.sh nrf/scripts/requirements-fixed.txt
#   ./nrf/scripts/pip/validate-requirements-fixed.sh --fast nrf/scripts/requirements-fixed.txt
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/validate-requirements-fixed.py" "$@"
