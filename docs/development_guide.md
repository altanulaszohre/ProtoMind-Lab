# Development guide

Use Python 3.10+ and the wrapper scripts. `setup.sh` creates `.venv` without global package installation or network access; the package has no runtime Python dependencies. The wrappers set `PYTHONPATH` and project-local cache variables. `run_tests.sh` uses the standard library's `unittest`. Python's optional editable-install metadata in `pyproject.toml` is for environments with setuptools available; it is not required for the scripts.

For a new Git checkout, run `setup.sh` to activate `.githooks`. Before a commit or push, run `prepublish_check.sh`. To try real inference, run `setup.sh --runtime` to build or install the pinned runtime, then download the model explicitly. `doctor.sh` checks prerequisites; a missing model or server produces a clear exception and no cloud fallback.

Keep environment mechanics in `simulation.py`, behavior choice in `agents.py`, schema validation in `schema.py`, and metrics in `experiments.py`. Add a test when changing a conservation rule, replay contract, memory namespace, or publication policy. Avoid claiming biological validity from software tests.

## Frontend

Normal users can run the bundled production build without Node.js. Rebuilding requires Node.js 20.19+ or 22.12+ and pnpm 11.25.0. Keep the package-manager store inside the project:

```sh
cd web
pnpm install --frozen-lockfile --ignore-scripts --store-dir ../.cache/pnpm
cd ..
./scripts/build_web.sh
node --import ./web/node_modules/tsx/dist/loader.mjs --test web/tests/*.test.ts
```

The TypeScript sources, production build, and pnpm lockfile are included. Dependency directories and stores are excluded. Platform-specific esbuild binaries are resolved as pinned optional packages; no project package install scripts are required for the verified platform. Do not edit lockfiles merely to bypass installation errors.

## Source archive audits

A source distribution deliberately has no `.git`. Run `scripts/prepublish_check.sh --source-only` for its working files. Once a repository is initialized, omit that option to require Git-aware checks as well. `scripts/verify_distribution.py` verifies the explicit file inventory, content hashes, media formats, relative documentation links, and prohibited-file exclusions without creating Git history.
