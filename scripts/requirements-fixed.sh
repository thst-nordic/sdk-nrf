#!/usr/bin/env bash
# Regenerate nrf/scripts/requirements-fixed.txt in Docker (linux/amd64, Python
# 3.12.4), matching nrf/scripts/tools-versions-linux.yml.
# Do not enable nounset when sourced (CI uses virtualenvwrapper in the same shell).
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  set -euo pipefail
fi

BASEDIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REQUIREMENTS_EXCLUDE="${REQUIREMENTS_EXCLUDE:-nrf/scripts/requirements-exclude.txt}"
REQUIREMENTS_FIXED_IN="${REQUIREMENTS_FIXED_IN:-nrf/scripts/requirements-fixed.in}"

declare -A FLATTEN_VISITED=()
declare -a EXCLUDED=()

load_excludes() {
  local line
  EXCLUDED=()
  [[ -f "$NCS_TOP/$REQUIREMENTS_EXCLUDE" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line// /}"
    [[ -z "$line" ]] && continue
    EXCLUDED+=("$(echo "$line" | tr '[:upper:]' '[:lower:]')")
  done <"$NCS_TOP/$REQUIREMENTS_EXCLUDE"
}

is_excluded() {
  local pkg=$1 lower ex
  pkg="${pkg%%[[:space:][]*}"
  lower=$(echo "$pkg" | tr '[:upper:]' '[:lower:]')
  for ex in "${EXCLUDED[@]}"; do
    [[ "$lower" == "$ex" ]] && return 0
  done
  return 1
}

resolve_under_top() {
  local base_dir=$1 ref=$2
  ref="${ref%%#*}"
  ref=$(echo "$ref" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  if [[ "$ref" = /* ]]; then
    echo "$ref"
  else
    echo "$(cd "$base_dir" && cd "$(dirname "$ref")" && pwd)/$(basename "$ref")"
  fi
}

# Remove excluded package lines from one requirements file (-r includes visited first).
apply_excludes_to_file() {
  local src_abs=$1
  [[ -n "${FLATTEN_VISITED[$src_abs]+x}" ]] && return 0
  [[ -f "$src_abs" ]] || { echo "requirements file not found: $src_abs" >&2; return 1; }
  FLATTEN_VISITED[$src_abs]=1

  local base_dir line pkg ref ref_abs tmp
  base_dir=$(dirname "$src_abs")
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^[[:space:]]*-r[[:space:]]+ ]]; then
      ref=${line#*-r}
      ref=$(echo "$ref" | sed 's/^[[:space:]]*//')
      ref_abs=$(resolve_under_top "$base_dir" "$ref")
      apply_excludes_to_file "$ref_abs"
    fi
  done <"$src_abs"

  tmp=$(mktemp)
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^[[:space:]]*# ]] || [[ -z "${line//[[:space:]]/}" ]]; then
      echo "$line"
      continue
    fi
    if [[ "$line" =~ ^[[:space:]]*-r[[:space:]]+ ]]; then
      echo "$line"
      continue
    fi
    pkg=$(echo "$line" | awk '{print $1}')
    if is_excluded "$pkg"; then
      continue
    fi
    echo "$line"
  done <"$src_abs" >"$tmp"
  mv "$tmp" "$src_abs"
}

# Always run before pip-compile: requirements-fixed.in tree + requirements-exclude.txt.
apply_requirements_excludes() {
  local input
  FLATTEN_VISITED=()
  load_excludes
  while IFS= read -r input || [[ -n "$input" ]]; do
    [[ "$input" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${input//[[:space:]]/}" ]] && continue
    apply_excludes_to_file "$NCS_TOP/$input"
  done <"$NCS_TOP/$REQUIREMENTS_FIXED_IN"
}

read_compile_inputs() {
  local input
  COMPILE_INPUTS=()
  while IFS= read -r input || [[ -n "$input" ]]; do
    [[ "$input" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${input//[[:space:]]/}" ]] && continue
    COMPILE_INPUTS+=("$input")
  done <"$NCS_TOP/$REQUIREMENTS_FIXED_IN"
}

usage() {
  cat <<'EOF'
Usage: requirements-fixed.sh [-h|--help] [--check-index]

  Default: apply requirements-exclude.txt, then pip-compile-cross-platform.

  --check-index: HTTP wheel check via validate_requirements_fixed_pins.py (Nordic
  simple index); marker-aware cp312 wheels for linux / windows / mac_arm.

  Source this script and call apply_requirements_excludes with NCS_TOP set (CI).

  Example: CONTAINER_CMD=podman ./requirements-fixed.sh

  Environment: OUT_FILE, INDEX_URL, PYTHON_VERSION, CONTAINER_CMD,
               REQUIREMENTS_FIXED_IN, REQUIREMENTS_EXCLUDE, NCS_TOP,
               PIP_CACHE_DIR (host path mounted for pip wheel/metadata cache),
               PIP_COMPILE_VERBOSE=1 (stream Poetry resolve / HTTP debug),
               PIP_COMPILE_CONTAINER_IMAGE (or PIP_COMPILE_DOCKER_IMAGE),
               CONTAINER_PLATFORM (or DOCKER_PLATFORM)
EOF
}

init_workspace() {
  NCS_TOP=${NCS_TOP:-$(cd "$BASEDIR/../.." && pwd)}
  NCS_TOP=$(cd "$NCS_TOP" && pwd)
  OUT_FILE="${OUT_FILE:-nrf/scripts/requirements-fixed.txt}"
  INDEX_URL="${INDEX_URL:-https://files.nordicsemi.com/artifactory/api/pypi/nordic-pypi/simple}"
  PYTHON_VERSION="${PYTHON_VERSION:-3.12.4}"
  IMAGE="${PIP_COMPILE_CONTAINER_IMAGE:-${PIP_COMPILE_DOCKER_IMAGE:-python:${PYTHON_VERSION}}}"
  CONTAINER_PLATFORM="${CONTAINER_PLATFORM:-${DOCKER_PLATFORM:-linux/amd64}}"
  CONTAINER_CMD="${CONTAINER_CMD:-docker}"
  CONTAINER_PIP_CACHE="/root/.cache/pip"
}

# container_run [-v host:path ...] [-e KEY=VAL ...] -- 'bash -lc script'
container_run() {
  local extra_volumes=() extra_env=() script=""
  local arg mount_spec env_spec remainder
  while [[ $# -gt 0 ]]; do
    arg=$1
    case "$arg" in
      -v)
        mount_spec=$2
        extra_volumes+=(-v "$mount_spec")
        shift 2
        ;;
      -e)
        env_spec=$2
        extra_env+=(-e "$env_spec")
        shift 2
        ;;
      --)
        shift
        remainder=$1
        script=$remainder
        break
        ;;
      *)
        echo "container_run: unknown argument: $arg" >&2
        exit 1
        ;;
    esac
  done
  [[ -n "$script" ]] || {
    echo "container_run: missing script after --" >&2
    exit 1
  }

  "$CONTAINER_CMD" run \
    --rm \
    --platform "$CONTAINER_PLATFORM" \
    --entrypoint /bin/bash \
    -v "$NCS_TOP:/ncs" \
    "${extra_volumes[@]}" \
    -w /ncs \
    "${extra_env[@]}" \
    -e OUT_FILE="$OUT_FILE" \
    -e INDEX_URL="$INDEX_URL" \
    "$IMAGE" \
    -lc "$script"
}

run_regen() {
  init_workspace

  if [[ ! -f "$NCS_TOP/$REQUIREMENTS_FIXED_IN" ]]; then
    echo "compile input list not found: $NCS_TOP/$REQUIREMENTS_FIXED_IN" >&2
    exit 1
  fi

  apply_requirements_excludes
  read_compile_inputs
  compile_inputs_env=$(printf '%s\n' "${COMPILE_INPUTS[@]}")

  local host_pip_cache
  host_pip_cache="${PIP_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/ncs-pip-compile}"
  mkdir -p "$host_pip_cache"

  echo "NCS workspace: $NCS_TOP"
  echo "Container:     $CONTAINER_CMD"
  echo "Image:         $IMAGE (platform: $CONTAINER_PLATFORM)"
  echo "Output file:   $OUT_FILE"
  echo "Compile list:  $REQUIREMENTS_FIXED_IN"
  echo "Exclude file:  $REQUIREMENTS_EXCLUDE"
  echo "Pip cache:     $host_pip_cache"
  echo "Verbose:       ${PIP_COMPILE_VERBOSE:-0}"

  container_run \
    -v "$host_pip_cache:$CONTAINER_PIP_CACHE" \
    -e "COMPILE_INPUTS=$compile_inputs_env" \
    -e "PIP_CACHE_DIR=$CONTAINER_PIP_CACHE" \
    -e "PIP_COMPILE_VERBOSE=${PIP_COMPILE_VERBOSE:-}" \
    -- "$(cat <<'REGEN_CONTAINER'
set -euo pipefail
echo "Python: $(python --version) ($(which python))"

python -m pip install -U pip setuptools wheel
pip install --index-url "$INDEX_URL" \
  "pip-compile-cross-platform==1.4.2+nordic.3" --upgrade

if [[ "${PIP_COMPILE_VERBOSE:-}" == 1 ]]; then
  export PYTHONUNBUFFERED=1
  export POETRY_HTTP_DEBUG=1
  python <<'PY'
import pathlib, sys
import pip_compile_cross_platform as pc

path = pathlib.Path(pc.__file__).with_name("__init__.py")
text = path.read_text()
old_run = """def _run_poetry(work_dir: Path, *args):
    env = os.environ.copy()
    env["POETRY_WARNINGS_EXPORT"] = "false"

    result = subprocess.run(
        [sys.executable, "-m", "poetry", *args],"""
new_run = """def _run_poetry(work_dir: Path, *args):
    env = os.environ.copy()
    env["POETRY_WARNINGS_EXPORT"] = "false"

    poetry_args = list(args)
    if os.environ.get("PIP_COMPILE_VERBOSE") == "1" and "export" not in poetry_args:
        poetry_args = ["-vvv", *poetry_args]

    result = subprocess.run(
        [sys.executable, "-m", "poetry", *poetry_args],"""
if old_run not in text:
    sys.exit("pip-compile-cross-platform verbose patch failed")
text = text.replace(old_run, new_run)
needle = (
    "    if result.returncode:\n"
    "        print(result.stdout, file=sys.stderr)\n"
    '        raise Exception("Poetry encountered an error")\n'
    "\n"
    "    return result"
)
insert = (
    '    if os.environ.get("PIP_COMPILE_VERBOSE") == "1" and result.stdout:\n'
    "        print(result.stdout, file=sys.stderr, flush=True)\n"
    + needle
)
if needle not in text:
    sys.exit("pip-compile-cross-platform verbose patch failed (needle)")
path.write_text(text.replace(needle, insert))
PY
  echo "Verbose: Poetry -vvv (not export) and POETRY_HTTP_DEBUG enabled"
fi

mapfile -t compile_inputs <<< "$COMPILE_INPUTS"
pip-compile-cross-platform \
  "${compile_inputs[@]}" \
  --output-file "$OUT_FILE" \
  --min-python-version 3.12 \
  --index-url "$INDEX_URL"
echo "SUCCESS: pip-compile wrote $OUT_FILE"
REGEN_CONTAINER
)"
}

run_check_index() {
  init_workspace
  [[ -f "$NCS_TOP/$OUT_FILE" ]] || { echo "FAIL: missing $OUT_FILE" >&2; exit 1; }

  echo "NCS workspace: $NCS_TOP"
  echo "Container:     $CONTAINER_CMD"
  echo "Image:         $IMAGE (platform: $CONTAINER_PLATFORM)"
  echo "Output file:   $OUT_FILE"
  echo "Index:         $INDEX_URL"
  echo "Pip cache:     (none — check-index)"
  local py_mm="${PYTHON_VERSION:-3.12.4}"
  py_mm="${py_mm%.*}"
  local check_py_tag="cp${py_mm//./}"
  echo "Wheel tags:    ${check_py_tag} on linux / windows / mac_arm"

  container_run \
    -e "CHECK_INDEX_PYTHON_TAG=${check_py_tag}" \
    -e "VALIDATE_PINS_SCRIPT=nrf/scripts/validate_requirements_fixed_pins.py" \
    -- "$(cat <<'CHECK_INDEX'
set -euo pipefail
python3 /ncs/"$VALIDATE_PINS_SCRIPT" \
  --requirements "/ncs/$OUT_FILE" \
  --index nordic \
  --index-url "$INDEX_URL" \
  --python-tag "${CHECK_INDEX_PYTHON_TAG:-cp312}" \
  --workers 24
CHECK_INDEX
)"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  mode=regen
  while [[ $# -gt 0 ]]; do
    option=$1
    case "$option" in
      -h | --help)
        usage
        exit 0
        ;;
      --check-index)
        mode=check-index
        shift
        ;;
      *)
        echo "Unknown option: $option" >&2
        usage >&2
        exit 1
        ;;
    esac
  done
  case "$mode" in
    check-index)
      run_check_index
      ;;
    *)
      run_regen
      ;;
  esac
fi
