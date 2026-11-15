"""Paired-seed experiments and operational metrics."""
from __future__ import annotations

import csv
import json
import math
import random
import resource
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from .agents import Controller
from .inference import Backend, MODEL_ID, MockBackend
from .memory import Memory, NullMemory
from .simulation import Config, World, distance
from .storage import local_path


METRIC_DEFINITIONS = {
    "survival_rate": "alive prey / initial prey at final tick",
    "mean_survival_time": "mean min(death tick, final tick) over initial prey, in ticks",
    "food_collection": "count of consumed food resources",
    "energy_efficiency": "food collected / total prey distance traveled; zero when distance is zero",
    "group_cohesion": "mean pairwise distance of living prey, averaged over ticks; zero for <2 prey",
    "group_fragmentation": "mean connected components among living prey using perception radius, averaged over ticks",
    "predator_escape_success": "ticks with nearest living prey farther than 4 interaction radii / ticks with living prey",
    "decision_validity": "validated decisions / attempted decisions",
    "inference_latency_ms": "mean wall-clock backend latency per attempted model decision",
    "tokens_per_decision": "reported total tokens / attempted model decisions",
    "total_inference_calls": "number of attempted backend decisions",
    "peak_process_memory_kib": "peak Python RSS plus sampled llama-server RSS, in KiB; A excludes unused server",
    "peak_inference_server_rss_kib": "largest sampled llama-server RSS during the run, in KiB; zero for A",
    "runtime_seconds": "experiment wall-clock duration",
    "group_alignment": "mean velocity polarization of living moving prey over ticks, in [0,1]",
    "predator_encounters": "entries into predator perception radius by living prey",
    "predator_captures": "prey killed by predator",
    "capture_rate": "captures / predator encounters; zero when no encounter",
    "predator_exposure": "prey-ticks inside predator perception radius / all living prey-ticks",
    "final_mean_energy": "mean energy across the initial prey population, dead prey counted as zero",
    "energy_recoveries": "episodes crossing below 20 energy and later reaching at least 30",
    "mean_energy_recovery_ticks": "mean ticks from low energy to recovery; zero when none recover",
}

TIMESERIES_DEFINITIONS = {
    "survival": "living prey / initial prey after each tick",
    "mean_energy": "mean energy over initial prey, dead counted as zero",
    "alignment": "velocity polarization of living moving prey",
    "cohesion": "mean pairwise distance of living prey",
    "fragmentation": "number of connected living prey components",
    "exposure": "number of living prey inside predator perception radius",
    "encounters": "new predator-perception entries this tick",
    "captures": "predator kills this tick",
    "food": "resources consumed this tick",
}


def _cohesion(world: World) -> tuple[float, int]:
    alive = [b for b in world.prey if b.alive]
    if len(alive) < 2: return 0.0, len(alive)
    distances = [distance(a, b) for i, a in enumerate(alive) for b in alive[i + 1:]]
    seen: set[str] = set()
    components = 0
    for b in alive:
        if b.id in seen: continue
        components += 1
        stack = [b]
        while stack:
            current = stack.pop()
            if current.id in seen: continue
            seen.add(current.id)
            stack.extend(other for other in alive if other.id not in seen and distance(current, other) <= world.config.perception)
    return mean(distances), components


def _alignment(world: World) -> float:
    moving = [(b.vx / math.hypot(b.vx, b.vy), b.vy / math.hypot(b.vx, b.vy))
              for b in world.prey if b.alive and math.hypot(b.vx, b.vy) > 1e-9]
    if not moving:
        return 0.0
    return math.hypot(sum(x for x, _ in moving), sum(y for _, y in moving)) / len(moving)


def run_one(config: Config, condition: str, backend: Backend | None = None,
            output: Path | None = None) -> dict[str, Any]:
    start = time.perf_counter()
    world = World(config)
    memory_path = (output / f"memory-{condition}-{config.seed}.sqlite") if output else ":memory:"
    memory = Memory(memory_path) if condition in ("C", "D") else NullMemory()
    controller = Controller(condition, backend, memory)
    distances = 0.0
    cohesion: list[float] = []
    components: list[int] = []
    alignment: list[float] = []
    recovery_start: dict[str, int] = {b.id: 0 for b in world.prey if b.energy < 20}
    recovery_lengths: list[int] = []
    timeseries: list[dict[str, float | int]] = []
    try:
        for _ in range(config.max_ticks):
            before = {b.id: (b.x, b.y) for b in world.prey}
            actions = controller.actions(world)
            exposure_before = world.exposure_count
            events = world.step(actions)
            controller.record_events(events)
            distances += sum(((b.x - before[b.id][0]) ** 2 + (b.y - before[b.id][1]) ** 2) ** .5 for b in world.prey)
            c, n = _cohesion(world)
            cohesion.append(c)
            components.append(n)
            a = _alignment(world)
            alignment.append(a)
            for b in world.prey:
                if b.alive and b.energy < 20 and b.id not in recovery_start:
                    recovery_start[b.id] = world.tick
                elif b.alive and b.energy >= 30 and b.id in recovery_start:
                    recovery_lengths.append(world.tick - recovery_start.pop(b.id))
                elif not b.alive:
                    recovery_start.pop(b.id, None)
            timeseries.append({"tick": world.tick,
                               "survival": sum(b.alive for b in world.prey) / config.prey_count,
                               "mean_energy": sum(b.energy for b in world.prey) / config.prey_count,
                               "alignment": a, "cohesion": c, "fragmentation": n,
                               "exposure": world.exposure_count - exposure_before,
                               "encounters": sum(e["type"] == "encounter" for e in events),
                               "captures": sum(e["type"] == "predation" for e in events),
                               "food": sum(e["type"] == "food" for e in events)})
            if output:
                with (output / "actions.jsonl").open("a") as stream:
                    for record in controller.records[-len(actions):]:
                        if record.tick == world.tick - 1:
                            stream.write(json.dumps({"condition": condition, "seed": config.seed, **asdict(record)}, separators=(",", ":")) + "\n")
                with (output / "events.jsonl").open("a") as stream:
                    for event in events:
                        stream.write(json.dumps({"condition": condition, "seed": config.seed, **event}, separators=(",", ":")) + "\n")
            if not any(b.alive for b in world.prey): break
        attempts = len(controller.records) if condition != "A" else 0
        food = sum(b.food_eaten for b in world.prey)
        python_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 if sys.platform == "darwin" else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        server_peak = getattr(backend, "peak_rss_kib", 0) if condition != "A" else 0
        metrics = {
            "survival_rate": sum(b.alive for b in world.prey) / config.prey_count,
            "mean_survival_time": mean(b.death_tick or world.tick for b in world.prey),
            "food_collection": food,
            "energy_efficiency": food / distances if distances else 0.0,
            "group_cohesion": mean(cohesion) if cohesion else 0.0,
            "group_fragmentation": mean(components) if components else 0.0,
            "predator_escape_success": world.escape_count / world.tick if world.tick else 0.0,
            "decision_validity": sum(r.valid for r in controller.records) / attempts if attempts else 1.0,
            "inference_latency_ms": mean(r.latency_ms for r in controller.records) if attempts else 0.0,
            "tokens_per_decision": sum(r.tokens for r in controller.records) / attempts if attempts else 0.0,
            "total_inference_calls": attempts,
            "peak_process_memory_kib": python_peak + server_peak,
            "peak_inference_server_rss_kib": server_peak,
            "runtime_seconds": time.perf_counter() - start,
            "group_alignment": mean(alignment) if alignment else 0.0,
            "predator_encounters": world.encounter_count,
            "predator_captures": world.capture_count,
            "capture_rate": world.capture_count / world.encounter_count if world.encounter_count else 0.0,
            "predator_exposure": world.exposure_count / world.prey_tick_count if world.prey_tick_count else 0.0,
            "final_mean_energy": sum(b.energy for b in world.prey) / config.prey_count,
            "energy_recoveries": len(recovery_lengths),
            "mean_energy_recovery_ticks": mean(recovery_lengths) if recovery_lengths else 0.0,
        }
        strategies: dict[str, int] = {}
        for record in controller.records:
            objective = record.decision["objective"]
            strategies[objective] = strategies.get(objective, 0) + 1
        return {"condition": condition, "seed": config.seed, "ticks": world.tick,
                "metrics": metrics, "strategies": strategies, "timeseries": timeseries}
    finally:
        memory.close()


def compare(config: Config, seeds: list[int], backend: Backend | None, backend_name: str,
            output_root: Path | None = None, conditions: tuple[str, ...] = ("A", "B", "C", "D")) -> dict[str, Any]:
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be nonempty and unique")
    if backend_name not in ("mechanistic", "mock", "llama"):
        raise ValueError("explicit mechanistic, mock, or llama backend required")
    if not conditions or len(set(conditions)) != len(conditions) or any(c not in "ABCD" for c in conditions):
        raise ValueError("conditions must be unique members of A,B,C,D")
    if len(seeds) > 50:
        raise ValueError("at most 50 seeds per experiment")
    output_root = output_root or local_path("experiments")
    if not output_root.resolve().is_relative_to(local_path(".")):
        raise ValueError("experiment output must stay inside project root")
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + f"-{seeds[0]}"
    folder = output_root / run_id
    folder.mkdir(exist_ok=False)
    config_record = {"config": asdict(config), "seeds": seeds, "backend": backend_name,
                     "model": MODEL_ID if backend_name == "llama" else "MOCK: no LFM3 inference" if backend_name == "mock" else "MECHANISTIC: no model",
                     "quantization": "Q4_K_M" if backend_name == "llama" else None,
                     "runtime": "llama.cpp b12088" if backend_name == "llama" else backend_name,
                     "model_revision": "cd0c74c" if backend_name == "llama" else None,
                     "started_utc": datetime.now(timezone.utc).isoformat(),
                     "metric_definitions": METRIC_DEFINITIONS,
                     "timeseries_definitions": TIMESERIES_DEFINITIONS,
                     "conditions": conditions}
    (folder / "config.json").write_text(json.dumps(config_record, indent=2))
    rows = []
    for seed in seeds:
        for condition in conditions:
            rows.append(run_one(replace(config, seed=seed), condition, backend, folder))
    summary = {condition: {name: mean(row["metrics"][name] for row in rows if row["condition"] == condition)
                           for name in METRIC_DEFINITIONS} for condition in conditions}
    summary_intervals: dict[str, Any] = {}
    if len(seeds) >= 5:
        for condition in conditions:
            summary_intervals[condition] = {}
            for metric in ("survival_rate", "mean_survival_time", "predator_encounters", "predator_captures", "food_collection", "group_alignment"):
                values = [row["metrics"][metric] for row in rows if row["condition"] == condition]
                rng = random.Random(619)
                draws = sorted(mean(rng.choice(values) for _ in values) for _ in range(1000))
                summary_intervals[condition][metric] = [draws[25], draws[974]]
    paired = paired_comparisons(rows, conditions)
    result = {"runs": rows, "summary": summary, "completed_utc": datetime.now(timezone.utc).isoformat(),
              "backend": backend_name, "paired_comparisons": paired, "summary_intervals": summary_intervals}
    (folder / "results.json").write_text(json.dumps(result, indent=2))
    with (folder / "metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["condition", "seed", "ticks", *METRIC_DEFINITIONS])
        writer.writeheader()
        for row in rows:
            writer.writerow({"condition": row["condition"], "seed": row["seed"], "ticks": row["ticks"], **row["metrics"]})
    result["artifact_bytes"] = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
    (folder / "results.json").write_text(json.dumps(result, indent=2))
    return {"directory": str(folder), "summary": summary, "summary_intervals": summary_intervals, "paired_comparisons": paired,
            "artifact_bytes": result["artifact_bytes"], "backend": backend_name}


def paired_comparisons(rows: list[dict[str, Any]], conditions: tuple[str, ...]) -> dict[str, Any]:
    by_key = {(row["seed"], row["condition"]): row for row in rows}
    seeds = sorted({row["seed"] for row in rows})
    output: dict[str, Any] = {}
    for left, right in (("B", "A"), ("C", "B"), ("D", "B"), ("D", "C")):
        if left not in conditions or right not in conditions:
            continue
        metrics = {}
        for metric in ("survival_rate", "mean_survival_time", "food_collection", "group_alignment", "predator_exposure"):
            differences = [by_key[(seed, left)]["metrics"][metric] - by_key[(seed, right)]["metrics"][metric] for seed in seeds]
            interval = None
            if len(differences) >= 5:
                rng = random.Random(781)
                boot = sorted(mean(rng.choice(differences) for _ in differences) for _ in range(1000))
                interval = [boot[25], boot[974]]
            metrics[metric] = {"paired_mean_difference": mean(differences), "observed_range": [min(differences), max(differences)],
                               "bootstrap_95_interval": interval, "n_pairs": len(differences)}
        output[f"{left}-{right}"] = metrics
    return output
