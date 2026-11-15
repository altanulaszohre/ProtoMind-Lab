"""Frozen scenarios, mechanistic calibration, and bounded parameter sweeps."""
from __future__ import annotations

import json
import random
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from .experiments import METRIC_DEFINITIONS, run_one
from .inference import Backend
from .simulation import Config
from .storage import ROOT, local_path

CALIBRATION_SEEDS = tuple(range(101, 113))
EVALUATION_SEEDS = tuple(range(1001, 1009))
SWEEP_PARAMETERS = {
    "predator_speed": float, "predator_perception": float, "perception": float,
    "food_count": int, "prey_count": int, "decision_interval": int,
    "social_strength": float,
}


def scenario_config(name: str, ticks: int | None = None) -> Config:
    if name not in ("motion", "predator", "scarcity", "change"):
        raise ValueError("scenario must be motion, predator, scarcity, or change")
    frozen = json.loads((ROOT / "configs/calibrated_v1.json").read_text())
    base = Config(**frozen["config"])
    if ticks is not None:
        base = replace(base, max_ticks=ticks)
    if name == "motion":
        return replace(base, predator_enabled=False)
    if name == "scarcity":
        return replace(base, food_count=7, food_replenish_interval=20, metabolism=.26)
    if name == "change":
        return replace(base, food_count=10, resource_shift_tick=max(1, base.max_ticks // 2))
    return base


def estimate_inference(config: Config, seed_count: int, conditions: tuple[str, ...]) -> dict[str, float | int]:
    modeled = sum(c != "A" for c in conditions)
    scheduled = config.prey_count * ((config.max_ticks + config.decision_interval - 1) // config.decision_interval) * modeled * seed_count
    expected = round(scheduled * 1.6)
    upper = config.prey_count * config.max_ticks * modeled * seed_count
    return {"scheduled_call_estimate": scheduled, "empirical_event_adjusted_calls": expected,
            "event_trigger_upper_bound": upper,
            "estimated_runtime_minutes_at_1_2s_per_call": round(expected * 1.2 / 60, 1),
            "note": "Empirical 1.6x event multiplier from short local runs; hardware and future policies can change duration"}


def calibrate(seeds: tuple[int, ...] = CALIBRATION_SEEDS) -> dict[str, Any]:
    if not seeds or set(seeds) & set(EVALUATION_SEEDS):
        raise ValueError("calibration seeds must be nonempty and disjoint from evaluation seeds")
    results = []
    for ticks in (100, 140, 180):
        for speed in (2.3, 2.6, 2.9):
            config = Config(max_ticks=ticks, predator_speed=speed)
            runs = [run_one(replace(config, seed=seed), "A") for seed in seeds]
            results.append({"max_ticks": ticks, "predator_speed": speed,
                            "mean_survival": mean(r["metrics"]["survival_rate"] for r in runs),
                            "mean_survival_time": mean(r["metrics"]["mean_survival_time"] for r in runs),
                            "mean_encounters": mean(r["metrics"]["predator_encounters"] for r in runs),
                            "mean_captures": mean(r["metrics"]["predator_captures"] for r in runs),
                            "per_seed": [{"seed": r["seed"], "survival": r["metrics"]["survival_rate"],
                                          "encounters": r["metrics"]["predator_encounters"],
                                          "captures": r["metrics"]["predator_captures"]} for r in runs]})
    record = {"kind": "mechanistic_calibration", "seeds": seeds, "evaluated_utc": datetime.now(timezone.utc).isoformat(),
              "grid": results, "selection": "Configuration is frozen separately; this command does not optimize toward a chosen mortality rate"}
    folder = local_path("experiments/calibration")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "grid_v1.json").write_text(json.dumps(record, indent=2))
    return record


def sweep(config: Config, seeds: tuple[int, ...], parameter: str, values: tuple[str, ...],
          backend: Backend | None = None, backend_name: str = "mechanistic") -> dict[str, Any]:
    if not seeds or len(set(seeds)) != len(seeds) or len(seeds) > 50 or not values or len(values) > 12:
        raise ValueError("invalid sweep seeds or values")
    if parameter != "memory" and parameter not in SWEEP_PARAMETERS:
        raise ValueError("unsupported sweep parameter")
    if parameter == "memory" and backend is None:
        raise ValueError("memory sweep requires an explicit backend")
    if parameter == "memory" and any(value not in ("none", "individual", "scrambled") for value in values):
        raise ValueError("memory values: none, individual, scrambled")
    root = local_path("experiments/sweeps")
    root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = root / run_id
    folder.mkdir()
    variants = []
    for index, value in enumerate(values):
        if parameter == "memory":
            condition = {"none": "B", "individual": "C", "scrambled": "D"}.get(value)
            if condition is None: raise ValueError("memory values: none, individual, scrambled")
            trial = config
        else:
            convert = SWEEP_PARAMETERS[parameter]
            trial = replace(config, **{parameter: convert(value)})
            condition = "A"
        variant_folder = folder / f"variant-{index}"
        variant_folder.mkdir()
        rows = [run_one(replace(trial, seed=seed), condition, backend, variant_folder) for seed in seeds]
        entry = {"value": value, "condition": condition, "config": asdict(trial), "runs": rows,
                 "summary": {key: mean(row["metrics"][key] for row in rows) for key in METRIC_DEFINITIONS}}
        (variant_folder / "results.json").write_text(json.dumps(entry, indent=2))
        variants.append(entry)
    result = {"parameter": parameter, "seeds": seeds, "backend": backend_name,
              "variants": variants, "completed_utc": datetime.now(timezone.utc).isoformat()}
    paired: dict[str, Any] = {}
    for variant in variants[1:]:
        comparison = {}
        for metric in ("survival_rate", "mean_survival_time", "predator_encounters", "food_collection", "group_alignment"):
            differences = [next(r for r in variant["runs"] if r["seed"] == seed)["metrics"][metric]
                           - next(r for r in variants[0]["runs"] if r["seed"] == seed)["metrics"][metric] for seed in seeds]
            interval = None
            if len(differences) >= 5:
                rng = random.Random(991)
                draws = sorted(mean(rng.choice(differences) for _ in differences) for _ in range(1000))
                interval = [draws[25], draws[974]]
            comparison[metric] = {"mean_difference": mean(differences), "observed_range": [min(differences), max(differences)],
                                  "bootstrap_95_interval": interval, "n_pairs": len(differences)}
        paired[f"{variant['value']}-vs-{variants[0]['value']}"] = comparison
    result["paired_comparisons"] = paired
    (folder / "sweep.json").write_text(json.dumps(result, indent=2))
    return {"directory": str(folder), "parameter": parameter,
            "paired_comparisons": paired,
            "summary": [{"value": v["value"], "condition": v["condition"], "survival": v["summary"]["survival_rate"],
                         "encounters": v["summary"]["predator_encounters"]} for v in variants]}
