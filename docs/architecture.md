# System architecture

The project contains a Python simulation engine, local model integration, a TypeScript/PixiJS observatory, and a native Cocoa/WebKit launcher. The browser interface is served by the standard-library loopback HTTP server; it does not require a cloud service. The initial cellular prototype preceded this implementation. Its biological claims and visual outputs are not evidence for the present engine.

`server.py` validates HTTP hosts, origins, request headers, and file paths. `observatory.py` manages live episodes and verified recordings. `models.py` inspects local GGUF metadata and runs compatibility probes. `web/src/scene.ts` renders engine frames with a separate interpolation clock; `main.ts` provides setup, inspection, reports, and descriptive analysis. `desktop/main.swift` starts and owns the project-local server.

Modules: `simulation.py` owns positions, movement constraints, food, energy, predation, observations, and deterministic seeded RNG streams. `agents.py` schedules objectives at events or intervals. `schema.py` validates exact JSON fields and visible target IDs. `inference.py` owns one llama.cpp process or an explicit mock backend. `memory.py` stores isolated per-prey SQLite records. `experiments.py` runs paired seeds and writes operational metrics; `research.py` defines scenarios, calibration, and sweeps. `security.py` audits publication candidates. See `scientific_model.md` for the ODD model description.

The decision chain is: environment → range-limited observation → individual state → optional bounded memory retrieval → shared model → strict validation/fallback → mechanistic steering → world update. Model output never changes physical state directly. The predator is a pursuit policy behind the same `Body`/movement mechanics and can later be replaced by another controller.

Four streams derive from the configured seed: initial positions, resources, events, and predator behavior. The latter two are reserved for future stochastic policies; the current pursuit and environment are deterministic. Replay of a validated action sequence requires the same configuration and tick order. LLM sampling and latency are outside that guarantee.

Current simplifications: food is point-like, boundaries are clamped, the predator has no energy or satiation dynamics, and one prey may be taken per tick. There is no hydrodynamics, sensory noise, calibrated fish biomechanics, or empirically fitted predator response. The movement equations are inspired by collective-motion models, not validated against observed fish trajectories.
