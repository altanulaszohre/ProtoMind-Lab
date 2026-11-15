#!/bin/sh
set -eu
. "$(dirname "$0")/env.sh"
if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then PY="$PROJECT_ROOT/.venv/bin/python"; else PY=python3; fi
PYTHONPATH="$PROJECT_ROOT/src" "$PY" -m unittest discover -s "$PROJECT_ROOT/tests" -v
