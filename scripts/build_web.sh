#!/bin/sh
set -eu
. "$(dirname "$0")/env.sh"
cd "$PROJECT_ROOT/web"
if ! command -v node >/dev/null 2>&1; then echo 'Install Node.js 20.19+ or 22.12+ to rebuild. The bundled web build requires only Python to run.' >&2; exit 1; fi
export npm_config_cache="$PROJECT_ROOT/.cache/npm"
if [ ! -d node_modules ]; then
  command -v pnpm >/dev/null 2>&1 || { echo 'Use pnpm 11.25.0 to install the pinned web/pnpm-lock.yaml dependencies, or use the bundled browser build.' >&2; exit 1; }
  pnpm install --frozen-lockfile --ignore-scripts --store-dir "$PROJECT_ROOT/.cache/pnpm"
fi
node node_modules/typescript/bin/tsc --noEmit
node node_modules/vite/bin/vite.js build
