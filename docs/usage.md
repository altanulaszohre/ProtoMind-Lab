# Observatory and experiment guide

## Replay

The application initially opens the bundled mechanistic recording. The first displayed frame is tick 22; rewind to inspect initialization. Time is expressed in simulation ticks, not biological seconds. At 1× display speed, playback advances eight ticks per wall-clock second.

Use play/pause, speed selection, single-tick stepping, and the timeline. Event log entries seek to an actual recorded event. Captures occur only at engine capture frames. An agent that died remains available in the inspector with its recorded state; it is no longer rendered as living. Its stored velocity and energy are the last recorded body values, not evidence of continuing movement.

Select an entity directly or use the inspector selector. Observations, memory records, and validated objectives come from engine/controller state. Condition A has no episodic memory; condition B also omits persistent memory. Conditions C and D show their stored individual records. D supplies scrubbed content to the policy according to the existing negative-control implementation. No chain-of-thought is displayed.

Trails use at most fourteen preceding recorded ticks. Sensing fields and neighbor links are visualization settings and do not alter an experiment. All world axes use the same display scale.

## Live mode

Choose a scenario, condition, seed, population, and duration. Expand perception/pursuit, environment/policy, or memory settings for advanced parameters. Resource regeneration is an interval in ticks: a lower interval means more frequent regeneration attempts. The calibrated preset cannot be edited. Choose a derived scenario for a custom configuration.

A running experiment owns an immutable configuration. Pause takes effect between engine operations; a model decision already in progress may finish first. Stop saves the partial episode. The timeline and rewind controls inspect recorded frames rather than resetting the scientific experiment. Start a new episode after stopping the current one.

Model conditions validate model loading and structured decisions before stepping the engine. Failures are explicit. During inference delays, the renderer waits at the last available frame; it does not predict future trajectories. Invalid individual model responses are recorded as invalid with the existing safe fallback. Inspect invalid-decision counts before interpreting results.

## Analysis, datasets, and reports

Datasets contains the bundled public replay and locally saved observatory recordings. Analysis shows actual measurements through the selected tick. Local-recording comparisons use final available frames, report completion state, and warn about unmatched configurations or seeds. They are descriptive comparisons, not significance tests.

Reports saves `report.json`, `metrics.csv`, and the selected recording prefix in `experiments/reports/`. A prefix is not a final episode outcome. No report is uploaded to an external service.

## CLI research workflows

Use the CLI help for the complete supported argument set:

```sh
./scripts/run.sh --help
./scripts/run.sh calibrate --help
./scripts/run.sh replay --help
```

The existing CLI supports paired seed schedules, calibration, replay, and bounded sweeps. Its explicit mock backend exists for software tests; label mock outputs accurately. Use `--backend llama` for real inference after installing the model/runtime. See the experimental protocol for paired comparisons and appropriate uncertainty reporting.
