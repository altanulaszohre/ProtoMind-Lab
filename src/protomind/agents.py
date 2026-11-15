"""Event-triggered objectives and mechanistic baseline."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from .inference import Backend
from .memory import Memory, NullMemory
from .schema import Decision, FALLBACK, Objective, validate_decision
from .simulation import Body, World


@dataclass
class DecisionRecord:
    tick: int
    agent: str
    raw: str
    decision: dict[str, Any]
    valid: bool
    latency_ms: float
    tokens: int
    trigger: str


class Controller:
    def __init__(self, condition: str, backend: Backend | None = None, memory: Memory | NullMemory | None = None):
        if condition not in ("A", "B", "C", "D"):
            raise ValueError("condition must be A, B, C, or D")
        if condition != "A" and backend is None:
            raise ValueError("LLM condition requires explicit backend")
        self.condition, self.backend, self.memory = condition, backend, memory or NullMemory()
        self.previous: dict[str, tuple[bool, bool, bool, bool]] = {}
        self.records: list[DecisionRecord] = []

    def _trigger(self, world: World, b: Body, obs: dict[str, Any]) -> str | None:
        state = (obs["predator"] is not None, bool(obs["food"]), len(obs["neighbors"]) == 0, b.energy < 20)
        previous = self.previous.get(b.id)
        self.previous[b.id] = state
        if previous is None:
            return "initial"
        if state[0] and not previous[0]: return "threat"
        if world.tick - b.last_decision_tick < world.config.decision_cooldown:
            return None
        if not state[1] and previous[1]: return "food_depleted"
        if state[2] and not previous[2]: return "separated"
        if state[3] and not previous[3]: return "critical_energy"
        if state[1] and not previous[1]: return "resource_discovered"
        if world.tick >= b.decision_until or world.tick % world.config.decision_interval == 0:
            return "interval"
        return None

    @staticmethod
    def _scramble(value: Any) -> Any:
        """Preserve record shape but erase content for the D negative control."""
        if isinstance(value, dict):
            return {key: Controller._scramble(item) for key, item in value.items()}
        if isinstance(value, list):
            return [Controller._scramble(item) for item in value]
        if isinstance(value, str):
            return "x" * len(value)
        if isinstance(value, (int, float)):
            return 0
        return value

    @staticmethod
    def baseline(obs: dict[str, Any]) -> Decision:
        if obs["predator"] is not None:
            return Decision(Objective.FLEE, 3)
        if obs["food"] and obs["energy"] < 85:
            return Decision(Objective.FORAGE, 5, obs["food"][0]["id"])
        if not obs["neighbors"]:
            return Decision(Objective.EXPLORE, 5)
        return Decision(Objective.COHERE, 5)

    def actions(self, world: World) -> dict[str, Decision]:
        actions: dict[str, Decision] = {}
        for b in world.prey:
            if not b.alive: continue
            obs = world.observe(b)
            trigger = self._trigger(world, b, obs)
            if trigger is None: continue
            if self.condition == "A":
                decision = self.baseline(obs)
                raw, tokens, latency, valid = "", 0, 0.0, True
            else:
                memories = self.memory.retrieve(b.id, world.tick, ("threat", "food", "outcome"), 4) if self.condition in ("C", "D") else []
                if self.condition == "D":
                    memories = self._scramble(memories)
                prompt = json.dumps({"observation": obs, "memory": memories}, separators=(",", ":"))
                start = time.perf_counter()
                raw, tokens = "", 0
                try:
                    assert self.backend is not None
                    raw, tokens = self.backend.decide(prompt)
                    visible = {item["id"] for item in obs["food"] + obs["neighbors"]}
                    decision = validate_decision(raw, visible, obs["predator"] is not None)
                    valid = True
                except (ValueError, KeyError, TypeError, TimeoutError, OSError, RuntimeError, AssertionError):
                    raw, decision, valid = raw or "[unavailable]", FALLBACK, False
                latency = (time.perf_counter() - start) * 1000
            actions[b.id] = decision
            record = DecisionRecord(world.tick, b.id, raw, {"objective": decision.objective.value,
                                     "duration": decision.duration, "target_id": decision.target_id},
                                    valid, latency, tokens, trigger)
            self.records.append(record)
            if self.condition in ("C", "D"):
                self.memory.add(b.id, world.tick, "observation", obs)
                self.memory.add(b.id, world.tick, "decision", record.decision)
                if obs["predator"]: self.memory.add(b.id, world.tick, "threat", obs["predator"])
                if obs["food"]: self.memory.add(b.id, world.tick, "food", obs["food"][0])
        return actions

    def record_events(self, events: list[dict[str, Any]]) -> None:
        if self.condition in ("C", "D"):
            for event in events:
                if event.get("agent") is not None:
                    self.memory.add(event["agent"], event["tick"], "outcome", event)
