#!/usr/bin/env bash
# Post-process per-project CycloneDX SBOMs with west manifest revisions.
# Expects to run from the west workspace root (ncs/) with sbom/ present.
set -euo pipefail

SBOM_DIR="${SBOM_DIR:-sbom/projects}"
CSV="${SBOM_DIR%/projects}/west-projects.csv"

if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq is required" >&2
  exit 1
fi

if [[ ! -d "${SBOM_DIR}" ]]; then
  echo "error: ${SBOM_DIR} not found" >&2
  exit 1
fi

declare -A REVISIONS=()
if [[ -f "${CSV}" ]]; then
  while IFS='|' read -r name revision _path _url; do
    [[ -z "${name}" || "${name}" == \#* ]] && continue
    safe_name="$(echo "${name}" | tr '/:' '_')"
    REVISIONS["${safe_name}"]="${revision}"
  done < "${CSV}"
fi

for cdx in "${SBOM_DIR}"/*.cdx.json; do
  [[ -f "${cdx}" ]] || continue
  base="$(basename "${cdx}" .cdx.json)"
  revision="${REVISIONS[${base}]:-unknown}"

  echo "annotate ${base} → revision ${revision}"

  tmp="$(mktemp)"
  jq --arg rev "${revision}" --arg name "${base}" '
    .metadata.component.version = $rev |
    .metadata.component.name = (.metadata.component.name // $name) |
    .metadata.properties = (
      (.metadata.properties // []) |
      map(select(.name != "west:revision")) +
      [{"name": "west:revision", "value": $rev}]
    )
  ' "${cdx}" > "${tmp}"
  mv "${tmp}" "${cdx}"
done

echo "annotation complete"
