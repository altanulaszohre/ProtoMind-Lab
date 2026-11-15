#!/bin/sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
export PROJECT_ROOT
export HF_HOME="$PROJECT_ROOT/.cache/huggingface"
export HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
export XDG_CACHE_HOME="$PROJECT_ROOT/.cache/xdg"
export PIP_CACHE_DIR="$PROJECT_ROOT/.cache/pip"
export PYTHONPYCACHEPREFIX="$PROJECT_ROOT/.cache/pycache"
export TMPDIR="$PROJECT_ROOT/tmp"
export TEMP="$TMPDIR"
export TMP="$TMPDIR"
export HF_HUB_DISABLE_TELEMETRY=1
for d in "$PROJECT_ROOT/models" "$PROJECT_ROOT/runtime" "$PROJECT_ROOT/data" "$PROJECT_ROOT/experiments" "$PROJECT_ROOT/logs" "$PROJECT_ROOT/tmp" "$PROJECT_ROOT/.cache" "$PROJECT_ROOT/.cache/huggingface" "$PROJECT_ROOT/.cache/xdg" "$PROJECT_ROOT/.cache/pip" "$PROJECT_ROOT/.cache/pycache"; do
  if [ -L "$d" ]; then echo "Managed directory is a symlink: $d" >&2; exit 1; fi
done
mkdir -p "$HF_HOME" "$HUGGINGFACE_HUB_CACHE" "$XDG_CACHE_HOME" "$PIP_CACHE_DIR" "$PYTHONPYCACHEPREFIX" "$TMPDIR" "$PROJECT_ROOT/models" "$PROJECT_ROOT/runtime" "$PROJECT_ROOT/data" "$PROJECT_ROOT/experiments" "$PROJECT_ROOT/logs"
