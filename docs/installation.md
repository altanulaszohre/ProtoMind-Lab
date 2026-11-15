# Installation and desktop packaging

## Model-free use

Install Python 3.10+ using a trusted operating-system package manager or the Python project. No global Python package installation is needed. Run `scripts/setup.sh` from this source directory, then `scripts/observatory.sh --open`. The bundled `web/dist/` build and compressed replay are sufficient. The Python backend uses the standard library.

All wrapper scripts resolve their own project root. Spaces in the project path are supported. A relocated installation should recreate `.venv` with `scripts/setup.sh` if that virtual environment was made on a different machine or its original Python executable is unavailable. Python itself is a system prerequisite and is not bundled.

## Native macOS launcher

Run `scripts/build_macos.sh` with Apple's Command Line Tools installed. It builds `ProtoMind Lab.app` in the current project using Cocoa and WebKit. This lightweight wrapper avoids bundling a second browser engine or a second model copy. The icon is generated from the existing original SVG master and supplied ICNS asset.

Keep the app at the project root. On launch it resolves the adjacent Python wrapper, starts a loopback server on an available port, waits for a readiness record under `tmp/`, and opens the observatory. Its WebKit data store is nonpersistent. Closing the final window terminates the owned server; the server closes its owned inference process. A heartbeat watchdog stops an abandoned desktop server. Browser mode remains independent and must be stopped explicitly.

The app is ad-hoc signed. It is not notarized, universal, or a self-contained Python distribution. A build targets the architecture of its build machine. Signing with an appropriate Developer ID and notarization are separate release-maintainer tasks. A locally tested build is not proof of Gatekeeper acceptance on other machines.

A separate launcher ZIP, when supplied, contains only the app and installation notes. Extract the app into this project after basic setup. It is unsuitable for installation by itself in a system Applications directory. Source builds remain the portable option.

## Optional local inference

Use `scripts/setup.sh --runtime`, then explicitly run `scripts/download_model.sh`. The runtime installer is pinned to llama.cpp b12088. The prebuilt installation path targets supported macOS architectures; other Unix systems require the source-build toolchain. The default model is LiquidAI/LFM3-1.7B Q4_K_M, approximately 1.1 GB.

Other GGUF files may be imported through Models. Select an instruction model with an embedded chat template and run the compatibility probe. Passing three probes establishes limited operational compatibility, not scientific equivalence or universal GGUF support. Memory estimates are planning estimates; actual usage varies with architecture and context.

## Troubleshooting

- **Address in use:** select another port with `--port`.
- **Missing production build:** run `scripts/build_web.sh` using the documented frontend prerequisites.
- **Missing model/runtime:** use Replay or condition A, or explicitly install the required local files.
- **Compatibility failure:** inspect the model's architecture and chat template; use a model supported by the pinned runtime.
- **Native startup failure:** inspect `logs/desktop.log` locally. Do not publish logs without reviewing them.
- **Offline use:** model and runtime downloads require connectivity once; ordinary replay, mechanistic execution, and installed-model inference use loopback communication only.
