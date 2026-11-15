"""Local command-line entry points."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import replace

from .storage import configure_local_environment

configure_local_environment()  # before importing inference or any optional dependency

from .experiments import compare
from .inference import LlamaBackend, MODEL, MockBackend, SERVER
from .research import calibrate, estimate_inference, scenario_config, sweep
from .simulation import Config
from .replay import replay
from .storage import ROOT, external_paths, owned_bytes


def doctor() -> dict[str, object]:
    usage = shutil.disk_usage(ROOT)
    return {"project_root": str(ROOT), "model_present": MODEL.is_file(), "runtime_present": SERVER.is_file(),
            "venv_present": (ROOT / ".venv/pyvenv.cfg").is_file(), "python": sys.executable,
            "free_bytes": usage.free, "project_bytes": owned_bytes(),
            "estimated_model_ram_bytes": 2_200_000_000,
            "external_cache_variables": external_paths(),
            "note": "OS swap, system caches and process metadata cannot be guaranteed inside project"}


def main() -> None:
    parser = argparse.ArgumentParser(prog="protomind")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    repeat = commands.add_parser("replay")
    repeat.add_argument("folder")
    repeat.add_argument("--condition", choices=["A", "B", "C", "D"], required=True)
    commands.add_parser("calibrate")
    repeat.add_argument("--seed", type=int, required=True)
    run = commands.add_parser("run")
    run.add_argument("--backend", choices=["mock", "llama"], default="mock")
    run.add_argument("--scenario", choices=["motion", "predator", "scarcity", "change"], default="predator")
    run.add_argument("--conditions", default="A,B,C,D")
    run.add_argument("--seeds", default="1001,1002")
    run.add_argument("--ticks", type=int)
    run.add_argument("--food", type=int)
    run.add_argument("--estimate-only", action="store_true")
    run.add_argument("--allow-long-run", action="store_true")
    scan = commands.add_parser("sweep")
    scan.add_argument("--scenario", choices=["motion", "predator", "scarcity", "change"], default="predator")
    scan.add_argument("--parameter", required=True)
    scan.add_argument("--values", required=True)
    scan.add_argument("--seeds", default="101,102,103,104")
    scan.add_argument("--ticks", type=int)
    scan.add_argument("--backend", choices=["mock", "llama"], default="mock")
    scan.add_argument("--allow-long-run", action="store_true")
    args = parser.parse_args()
    if args.command == "doctor":
        print(json.dumps(doctor(), indent=2))
        return
    if args.command == "replay":
        from pathlib import Path
        result = replay(Path(args.folder), args.condition, args.seed)
        print(json.dumps(result, indent=2))
        if not result["events_match"]:
            raise SystemExit(1)
        return
    if args.command == "calibrate":
        record = calibrate()
        print(json.dumps({"seeds": record["seeds"], "grid": [{k: v for k, v in row.items() if k != "per_seed"} for row in record["grid"]]}, indent=2))
        return
    seeds = [int(x) for x in args.seeds.split(",")]
    config = scenario_config(args.scenario, args.ticks)
    if args.command == "sweep":
        values = tuple(x.strip() for x in args.values.split(","))
        memory_sweep = args.parameter == "memory"
        conditions = tuple({"none": "B", "individual": "C", "scrambled": "D"}.get(x, "A") for x in values) if memory_sweep else ("A",)
        estimate = estimate_inference(config, len(seeds) * len(values) if memory_sweep else 0, conditions[:1])
        if memory_sweep and args.backend == "llama" and estimate["empirical_event_adjusted_calls"] > 200 and not args.allow_long_run:
            parser.exit(2, f"Estimated {estimate['empirical_event_adjusted_calls']} model calls; pass --allow-long-run to execute.\n")
        if not memory_sweep:
            print(json.dumps(sweep(config, tuple(seeds), args.parameter, values), indent=2))
        elif args.backend == "llama":
            with LlamaBackend() as backend:
                print(json.dumps(sweep(config, tuple(seeds), args.parameter, values, backend, "llama"), indent=2))
        else:
            print(json.dumps(sweep(config, tuple(seeds), args.parameter, values, MockBackend(), "mock"), indent=2))
        return
    conditions = tuple(x.strip().upper() for x in args.conditions.split(","))
    if args.food is not None:
        config = replace(config, food_count=args.food)
    estimate = estimate_inference(config, len(seeds), conditions)
    if args.estimate_only:
        print(json.dumps(estimate, indent=2))
        return
    if args.backend == "llama" and estimate["empirical_event_adjusted_calls"] > 200 and not args.allow_long_run:
        parser.exit(2, f"Estimated {estimate['empirical_event_adjusted_calls']} model calls (about {estimate['estimated_runtime_minutes_at_1_2s_per_call']} minutes); pass --allow-long-run to execute.\n")
    try:
        if conditions == ("A",):
            result = compare(config, seeds, None, "mechanistic", conditions=conditions)
        elif args.backend == "llama":
            with LlamaBackend() as backend:
                result = compare(config, seeds, backend, "llama", conditions=conditions)
        else:
            result = compare(config, seeds, MockBackend(), "mock", conditions=conditions)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"protomind: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
