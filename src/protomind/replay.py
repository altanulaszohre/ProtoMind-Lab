"""Replay logged, validated actions without model inference."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from .schema import validate_decision
from .simulation import Config, World
from .storage import ROOT


def replay(folder: Path, condition: str, seed: int) -> dict[str, Any]:
    folder = folder.resolve()
    if not folder.is_relative_to((ROOT / "experiments").resolve()):
        raise ValueError("replay folder must be under project experiments")
    metadata = json.loads((folder / "config.json").read_text())
    result = json.loads((folder / "results.json").read_text())
    match = next((r for r in result["runs"] if r["condition"] == condition and r["seed"] == seed), None)
    if match is None:
        raise ValueError("condition and seed not found in run")
    config = replace(Config(**metadata["config"]), seed=seed)
    world = World(config)
    actions_by_tick: dict[int, list[dict[str, Any]]] = {}
    with (folder / "actions.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            if row["condition"] == condition and row["seed"] == seed:
                actions_by_tick.setdefault(row["tick"], []).append(row)
    for tick in range(match["ticks"]):
        actions = {}
        for row in actions_by_tick.get(tick, []):
            actor = next((b for b in world.prey if b.id == row["agent"] and b.alive), None)
            if actor is None:
                raise ValueError("replay action references absent agent")
            obs = world.observe(actor)
            visible = {item["id"] for item in obs["food"] + obs["neighbors"]}
            # Recorded safe fallbacks are allowed even when no predator is visible.
            actions[actor.id] = validate_decision(json.dumps(row["decision"]), visible)
        world.step(actions)
    expected = [dict(row) for row in (json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines())
                if row["condition"] == condition and row["seed"] == seed]
    actual = [{"condition": condition, "seed": seed, **event} for event in world.events]
    return {"condition": condition, "seed": seed, "ticks": world.tick,
            "events_match": actual == expected, "event_count": len(actual)}
