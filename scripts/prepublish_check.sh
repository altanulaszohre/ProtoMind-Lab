#!/bin/sh
set -eu
. "$(dirname "$0")/env.sh"
if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then PY="$PROJECT_ROOT/.venv/bin/python"; else PY=python3; fi
PYTHONPATH="$PROJECT_ROOT/src" "$PY" -m protomind.security --scope all "$@"
if [ -x "$PROJECT_ROOT/runtime/gitleaks/gitleaks" ]; then
  "$PROJECT_ROOT/runtime/gitleaks/gitleaks" dir --redact --no-banner --report-format json --report-path "$PROJECT_ROOT/tmp/gitleaks-source.json" "$PROJECT_ROOT"
  if git -C "$PROJECT_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  "$PROJECT_ROOT/runtime/gitleaks/gitleaks" git --staged --redact --no-banner --report-format json --report-path "$PROJECT_ROOT/tmp/gitleaks-staged.json" "$PROJECT_ROOT"
  if git -C "$PROJECT_ROOT" rev-parse HEAD >/dev/null 2>&1; then
    "$PROJECT_ROOT/runtime/gitleaks/gitleaks" git --redact --no-banner --report-format json --report-path "$PROJECT_ROOT/tmp/gitleaks-history.json" "$PROJECT_ROOT"
  fi
  fi
else
  echo 'Gitleaks not installed; supplemental scan skipped.'
fi
