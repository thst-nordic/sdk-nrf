#!/bin/bash

BASEDIR=$(dirname "$0")

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --linux) TOOLS_VERSIONS=$BASEDIR/tools-versions-linux.yml; shift ;;
        --windows) TOOLS_VERSIONS=$BASEDIR/tools-versions-win10.yml; shift ;;
        --darwin)  TOOLS_VERSIONS=$BASEDIR/tools-versions-darwin.yml; shift ;;
        "") # Auto-detect platform and add corresponding flag
            case $(uname -s) in
            Linux*) set -- --linux "$@"; shift ;;
            Darwin*) set -- --darwin "$@"; shift ;;
            MINGW*|MSYS*|CYGWIN*) set -- --windows "$@"; shift ;;
            *) echo "Unsupported platform: $(uname -s)"; exit 1 ;;
        esac ;;
        *) exit 1 ;;
    esac
done

REQUIREMENTS=$BASEDIR/requirements-fixed.txt
TOOLCHAIN_VERSION=$(cat $REQUIREMENTS $TOOLS_VERSIONS | tr -d '\r' | sha256sum | head -c 10)

echo "${TOOLCHAIN_VERSION}"
