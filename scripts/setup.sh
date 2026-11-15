#!/bin/sh
set -eu
. "$(dirname "$0")/env.sh"
if [ ! -x "$PROJECT_ROOT/.venv/bin/python" ]; then
  python3 -m venv "$PROJECT_ROOT/.venv"
fi
# The runtime uses PYTHONPATH from the wrapper scripts, avoiding a networked build backend.
if git -C "$PROJECT_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$PROJECT_ROOT" config --local core.hooksPath .githooks
fi
if [ "${1:-}" = "--runtime" ]; then
  if command -v cmake >/dev/null; then
    if [ -L "$PROJECT_ROOT/runtime/llama.cpp" ]; then echo 'Runtime path is a symlink' >&2; exit 1; fi
    command -v git >/dev/null || { echo 'git is required for --runtime' >&2; exit 1; }
    if [ ! -d "$PROJECT_ROOT/runtime/llama.cpp" ]; then
      git clone --depth 1 --branch b12088 https://github.com/ggml-org/llama.cpp.git "$PROJECT_ROOT/runtime/llama.cpp"
    fi
    if [ "$(uname -s)" = Darwin ]; then METAL=ON; else METAL=OFF; fi
    cmake -S "$PROJECT_ROOT/runtime/llama.cpp" -B "$PROJECT_ROOT/runtime/llama.cpp/build" -DCMAKE_BUILD_TYPE=Release "-DGGML_METAL=$METAL"
    cmake --build "$PROJECT_ROOT/runtime/llama.cpp/build" --config Release --target llama-server -j 4
  else
    "$PROJECT_ROOT/scripts/install_runtime_binary.sh"
  fi
fi
echo 'Local setup complete. Model download is a separate explicit step.'
