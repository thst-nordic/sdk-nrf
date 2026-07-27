#!/usr/bin/env bash
# Upload per-component CycloneDX SBOMs to Dependency-Track as child projects.
# Env: DTRACK_URL, DTRACK_API_KEY, PARENT, VERSION, WORKSPACE_ROOT
set -euo pipefail

: "${DTRACK_URL:?DTRACK_URL required}"
: "${DTRACK_API_KEY:?DTRACK_API_KEY required}"
: "${PARENT:?PARENT required}"
: "${VERSION:?VERSION required}"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-.}"

API="https://${DTRACK_URL}/api/v1"
PROJECTS_DIR="${WORKSPACE_ROOT}/sbom/projects"

auth_header=("X-Api-Key: ${DTRACK_API_KEY}")

api_get() {
  curl -sf -H "${auth_header[@]}" "${API}/$1"
}

api_put_bom() {
  local payload="$1"
  curl -sf -X PUT -H "${auth_header[@]}" \
    -H "Content-Type: application/json" \
    -d "${payload}" \
    "${API}/bom"
}

find_project_uuid() {
  local name="$1"
  local version="$2"
  local enc_name enc_version
  enc_name="$(jq -rn --arg v "${name}" '$v|@uri')"
  enc_version="$(jq -rn --arg v "${version}" '$v|@uri')"
  api_get "project/lookup?name=${enc_name}&version=${enc_version}" \
    | jq -r '.uuid // empty'
}

ensure_project() {
  local name="$1"
  local version="$2"
  local parent_uuid="${3:-}"

  local uuid
  uuid="$(find_project_uuid "${name}" "${version}")"
  if [[ -n "${uuid}" ]]; then
    echo "${uuid}"
    return 0
  fi

  local payload
  if [[ -n "${parent_uuid}" ]]; then
    payload="$(jq -n \
      --arg name "${name}" \
      --arg version "${version}" \
      --arg parent "${parent_uuid}" \
      '{name: $name, version: $version, parent: {uuid: $parent}, active: true, classifier: "APPLICATION"}')"
  else
    payload="$(jq -n \
      --arg name "${name}" \
      --arg version "${version}" \
      '{name: $name, version: $version, active: true, classifier: "APPLICATION"}')"
  fi

  uuid="$(curl -sf -X PUT -H "${auth_header[@]}" \
    -H "Content-Type: application/json" \
    -d "${payload}" \
    "${API}/project" | jq -r '.uuid')"
  echo "${uuid}"
}

echo "ensuring parent project ${PARENT} @ ${VERSION}"
PARENT_UUID="$(ensure_project "${PARENT}" "${VERSION}")"
echo "parent uuid: ${PARENT_UUID}"

if [[ ! -d "${PROJECTS_DIR}" ]]; then
  echo "no per-project SBOMs at ${PROJECTS_DIR} — skipping"
  exit 0
fi

for cdx in "${PROJECTS_DIR}"/*.cdx.json; do
  [[ -f "${cdx}" ]] || continue
  base="$(basename "${cdx}" .cdx.json)"
  echo "upload component ${base} @ ${VERSION}"

  CHILD_UUID="$(ensure_project "${base}" "${VERSION}" "${PARENT_UUID}")"

  bom_b64="$(base64 -w 0 "${cdx}" 2>/dev/null || base64 "${cdx}" | tr -d '\n')"
  payload="$(jq -n \
    --arg project "${CHILD_UUID}" \
    --arg bom "${bom_b64}" \
    '{project: $project, bom: $bom}')"

  api_put_bom "${payload}"
  echo "  uploaded → ${CHILD_UUID}"
done

echo "component upload complete"
