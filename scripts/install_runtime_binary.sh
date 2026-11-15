#!/bin/sh
set -eu
. "$(dirname "$0")/env.sh"
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
  echo 'Prebuilt runtime installer supports macOS Apple Silicon only; use setup.sh --runtime with CMake elsewhere' >&2
  exit 1
fi
ARCHIVE="$PROJECT_ROOT/tmp/llama-b12088-bin-macos-arm64.tar.gz"
if [ -L "$ARCHIVE" ]; then echo 'Runtime archive path is a symlink' >&2; exit 1; fi
if [ ! -s "$ARCHIVE" ]; then
  curl --fail --location --retry 3 --continue-at - --output "$ARCHIVE" 'https://github.com/ggml-org/llama.cpp/releases/download/b12088/llama-b12088-bin-macos-arm64.tar.gz'
fi
python3 "$PROJECT_ROOT/scripts/safe_runtime_extract.py" "$ARCHIVE"
echo 'Pinned llama.cpp runtime installed inside runtime/llama-b12088.'
