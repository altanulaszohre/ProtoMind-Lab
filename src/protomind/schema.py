"""Strict behavioral decisions; physical state is never model-controlled."""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum


class Objective(str, Enum):
    FORAGE = "FORAGE"
    EXPLORE = "EXPLORE"
    COHERE = "COHERE"
    FOLLOW = "FOLLOW"
    FLEE = "FLEE"
    REST = "REST"


@dataclass(frozen=True)
class Decision:
    objective: Objective
    duration: int
    target_id: str | None = None


FALLBACK = Decision(Objective.FLEE, 2)


def validate_decision(raw: str, visible_ids: set[str], predator_visible: bool | None = None) -> Decision:
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) != {"objective", "duration", "target_id"}:
        raise ValueError("decision must have exactly objective, duration, target_id")
    if type(data["duration"]) is not int or not 1 <= data["duration"] <= 12:
        raise ValueError("invalid duration")
    obj = Objective(data["objective"])
    target = data["target_id"]
    if target is not None and (not isinstance(target, str) or target not in visible_ids):
        raise ValueError("target is not visible")
    if obj in (Objective.FOLLOW, Objective.FORAGE) and target is None:
        raise ValueError("objective requires a visible target")
    if obj not in (Objective.FOLLOW, Objective.FORAGE) and target is not None:
        raise ValueError("objective forbids target")
    if obj == Objective.FOLLOW and not target.startswith("prey-"):
        raise ValueError("FOLLOW requires prey")
    if obj == Objective.FORAGE and not target.startswith("food-"):
        raise ValueError("FORAGE requires food")
    if obj == Objective.FLEE and predator_visible is False:
        raise ValueError("FLEE requires a visible predator")
    return Decision(obj, data["duration"], target)
