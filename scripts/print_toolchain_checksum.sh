#!/bin/bash

# Parse command line arguments
OS_OVERRIDE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            echo "Usage: $0 [--os OS_TYPE] [--help|-h]"
            echo ""
            echo "Print the toolchain checksum for the specified or detected platform."
            echo ""
            echo "The checksum is computed from requirements-fixed.txt and the appropriate"
            echo "tools-versions-*.yml file based on the operating system."
            echo ""
            echo "Options:"
            echo "  --os OS_TYPE    Override OS detection. Supported values:"
            echo "                  'Linux', 'MINGW', 'Darwin'"
            echo "                  Default: auto-detect using 'uname -s'"
            echo "  --help, -h      Show this help message"
            echo ""
            echo "Note: print_docker_image.sh must use Linux checksum (--os Linux)"
            echo "      because Docker containers run on Linux regardless of host OS."
            exit 0
            ;;
        --os)
            OS_OVERRIDE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Use --help for usage information" >&2
            exit 1
            ;;
    esac
done

BASEDIR=$(dirname "$0")
REQUIREMENTS=$BASEDIR/requirements-fixed.txt

# Detect OS and set tools version file + hash command
# Use override if provided, otherwise auto-detect
OS_TYPE="${OS_OVERRIDE:-$(uname -s)}"
case "$OS_TYPE" in
    MINGW*)   TOOLS_VERSIONS="$BASEDIR/tools-versions-win10.yml" ; HASH_CMD="sha256sum" ;;
    Linux*)   TOOLS_VERSIONS="$BASEDIR/tools-versions-linux.yml" ; HASH_CMD="sha256sum" ;;
    Darwin*)  TOOLS_VERSIONS="$BASEDIR/tools-versions-darwin.yml" ; HASH_CMD="shasum -a 256" ;;
    *) echo "Unsupported OS"; exit 1 ;;
esac

# Compute SHA256 and take first 10 characters
TOOLCHAIN_VERSION=$(cat "$REQUIREMENTS" "$TOOLS_VERSIONS" \
    | sed 's/\r$//' \
    | $HASH_CMD \
    | cut -c1-10)

echo "${TOOLCHAIN_VERSION}"
