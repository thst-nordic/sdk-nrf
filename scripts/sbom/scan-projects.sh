#!/usr/bin/env bash
# Per-west-project Syft scan (Mode B).
# Reads west-projects.csv produced by the workflow and emits SPDX + CycloneDX
# per manifest project under sbom/projects/.
set -euo pipefail

WORKSPACE_ROOT="${1:?usage: scan-projects.sh WORKSPACE_ROOT}"
CSV="${WORKSPACE_ROOT}/sbom/west-projects.csv"
OUT_DIR="${WORKSPACE_ROOT}/sbom/projects"

if [[ ! -f "${CSV}" ]]; then
  echo "error: ${CSV} not found — run west list step first" >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

# Syft exclude patterns shared across per-project scans
SYFT_EXCLUDES=(
  './**/build/**'
  './**/.git/**'
  './**/twister-out/**'
)

scan_project() {
  local name="$1"
  local revision="$2"
  local relpath="$3"
  local target="${WORKSPACE_ROOT}/${relpath}"
  local safe_name

  safe_name="$(echo "${name}" | tr '/:' '_')"

  if [[ ! -d "${target}" ]]; then
    echo "skip ${name}: path ${relpath} not present"
    return 0
  fi

  echo "scan ${name} @ ${revision} (${relpath})"

  local -a exclude_args=()
  for pattern in "${SYFT_EXCLUDES[@]}"; do
    exclude_args+=(--exclude "${pattern}")
  done

  syft "dir:${target}" \
    --source-name "${name}" \
    --source-version "${revision}" \
    -o "spdx-json=${OUT_DIR}/${safe_name}.spdx.json" \
    -o "cyclonedx-json=${OUT_DIR}/${safe_name}.cdx.json" \
    "${exclude_args[@]}"
}

while IFS='|' read -r name revision relpath _url; do
  [[ -z "${name}" || "${name}" == \#* ]] && continue
  scan_project "${name}" "${revision}" "${relpath}"
done < "${CSV}"

echo "per-project SBOMs written to ${OUT_DIR}"
