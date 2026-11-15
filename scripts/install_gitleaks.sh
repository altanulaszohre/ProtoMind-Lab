#!/bin/sh
set -eu
. "$(dirname "$0")/env.sh"
VERSION=v8.21.2
ARCH=$(uname -m)
case "$ARCH" in arm64) ASSET='gitleaks_8.21.2_darwin_arm64.tar.gz';; x86_64) ASSET='gitleaks_8.21.2_darwin_x64.tar.gz';; *) echo 'Unsupported architecture' >&2; exit 1;; esac
if [ -L "$PROJECT_ROOT/runtime/gitleaks" ] || [ -L "$PROJECT_ROOT/tmp/$ASSET" ]; then echo 'Unsafe runtime path' >&2; exit 1; fi
mkdir -p "$PROJECT_ROOT/runtime/gitleaks"
curl --fail --location --output "$PROJECT_ROOT/tmp/$ASSET" "https://github.com/gitleaks/gitleaks/releases/download/$VERSION/$ASSET"
python3 "$PROJECT_ROOT/scripts/extract_gitleaks.py" "$PROJECT_ROOT/tmp/$ASSET"
echo 'Gitleaks installed project-locally.'
