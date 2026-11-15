#!/bin/sh
set -eu
. "$(dirname "$0")/env.sh"
PY="$PROJECT_ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then echo 'Run scripts/setup.sh first' >&2; exit 1; fi
case "${1:-}" in --*|"") set -- run "$@";; esac
PYTHONPATH="$PROJECT_ROOT/src" "$PY" -m protomind.cli "$@"
