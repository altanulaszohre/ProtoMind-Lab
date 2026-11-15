# Experimental protocol

## Separation of calibration and evaluation

Calibration uses mechanistic A only, seeds 101–112. Run `./scripts/run.sh calibrate` to reproduce the 3 × 3 grid in `experiments/calibration/grid_v1.json`. The selected 140-tick, speed-2.6 parameter set is frozen in `configs/calibrated_v1.json`. Evaluation seeds 1001–1008 are disjoint. Sensitivity and social ablation examples use seeds 301–306 and do not change the frozen file.

## Controlled conditions

A is mechanistic. B uses real LFM3 with current observation only. C uses the same foundation model plus the prey's bounded individual memory. D uses the same model and memory recording schedule, but retrieved values are scrambled before prompting. Conditions share seed, physics, population, resources, predator, observation radius, and episode duration. All use the same event/interval scheduling and cooldown. B/C/D share one model process and its inference settings. Model calls run sequentially. D approximates a prompt-shape control, not an exact token-matched placebo.

Run `./scripts/run.sh --scenario predator --conditions A,B,C,D --backend llama --seeds 1001,1002 --ticks 10` for a bounded real-model pilot. Use `--estimate-only` first for longer runs. The CLI requires `--allow-long-run` when its event-adjusted planning estimate exceeds 200 model calls; the estimate uses a conservative 1.6× planning multiplier and is not a hard runtime bound. A full 140-tick, eight-seed A/B/C/D evaluation is intentionally not launched as a routine test. Mechanistic evaluation needs no model: `./scripts/run.sh --scenario predator --conditions A --seeds 1001,1002,1003,1004,1005,1006,1007,1008`.

## Scenarios and ablations

- `motion`: predator disabled; tests collective motion without attack.
- `predator`: frozen calibrated predator pressure.
- `scarcity`: fewer resources, slower replenishment, higher metabolism.
- `change`: food relocated in the second half; event is logged but not revealed as global knowledge to agents.

Mechanistic parameter sweeps use `./scripts/run.sh sweep --parameter predator_perception --values 24,48 --seeds 301,302,303,304,305,306 --ticks 140`. Supported parameters are predator speed/perception, prey perception, food count, prey count, decision interval, and social strength. `--parameter memory --values none,individual,scrambled` runs B/C/D with the chosen explicit backend and a cost guard for real LFM3. Sweeps write ignored local structured results under `experiments/sweeps/`.

## Recording and analysis

Each run stores configuration, model/runtime identifier, action and event JSONL, per-seed metrics and per-tick trajectories, behavior counts, and paired comparisons. Replay validates recorded decisions and compares events without loading the model. Metric definitions are embedded in configuration JSON; zero denominators are assigned zero except baseline decision validity, which is one by convention. Disk footprint is recorded for the experiment folder. Inspect invalid decisions and fallback use before interpreting behavior. For at least five pairs, bootstrap intervals use 1,000 deterministic paired resamples. Treat these as exploratory intervals; do not claim biological validation or causal memory benefit from short runs.
