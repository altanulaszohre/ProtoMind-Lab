"""Deterministic headless ecology. One tick is one simulation time unit."""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from typing import Any

from .schema import Decision, Objective


@dataclass(frozen=True)
class Config:
    width: float = 100.0
    height: float = 100.0
    prey_count: int = 8
    food_count: int = 18
    perception: float = 28.0
    interaction: float = 2.5
    prey_speed: float = 2.0
    predator_speed: float = 2.6
    acceleration: float = 0.35
    turn_radians: float = 0.6
    metabolism: float = 0.12
    move_cost: float = 0.07
    food_energy: float = 13.0
    food_replenish_interval: int = 9
    decision_interval: int = 5
    max_ticks: int = 100
    seed: int = 1
    predator_enabled: bool = True
    predator_perception: float = 36.0
    capture_radius: float = 2.5
    social_strength: float = 1.0
    start_energy: float = 50.0
    max_energy: float = 100.0
    resource_shift_tick: int | None = None
    stochastic_spawn_probability: float = 0.0
    decision_cooldown: int = 2

    def __post_init__(self) -> None:
        if min(self.width, self.height) < 10 or not 1 <= self.prey_count <= 100 or not 0 <= self.food_count <= 1000:
            raise ValueError("invalid world dimensions or population")
        if min(self.perception, self.interaction, self.prey_speed, self.predator_speed, self.acceleration,
               self.turn_radians, self.metabolism, self.food_energy, self.predator_perception,
               self.capture_radius, self.start_energy, self.max_energy) <= 0:
            raise ValueError("physical parameters must be positive")
        if self.start_energy > self.max_energy or self.social_strength < 0 or not 0 <= self.stochastic_spawn_probability <= 1:
            raise ValueError("invalid energy, social strength, or spawn probability")
        if self.resource_shift_tick is not None and not 1 <= self.resource_shift_tick <= self.max_ticks:
            raise ValueError("resource shift must occur within the episode")
        if self.move_cost < 0 or self.decision_cooldown < 1 or min(self.food_replenish_interval, self.decision_interval, self.max_ticks) < 1 or self.max_ticks > 10000:
            raise ValueError("invalid interval or cost")


@dataclass
class Body:
    id: str
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    energy: float = 50.0
    alive: bool = True
    death_tick: int | None = None
    food_eaten: int = 0
    objectives: list[str] = field(default_factory=list)
    objective: Objective = Objective.COHERE
    target_id: str | None = None
    decision_until: int = 0
    last_decision_tick: int = -10000


def distance(a: Any, b: Any) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def unit(x: float, y: float) -> tuple[float, float]:
    norm = math.hypot(x, y)
    return (x / norm, y / norm) if norm else (0.0, 0.0)


class World:
    def __init__(self, config: Config):
        self.config = config
        self.rng_init = random.Random(config.seed)
        self.rng_resources = random.Random(config.seed + 100003)
        self.rng_events = random.Random(config.seed + 200003)
        self.rng_predator = random.Random(config.seed + 300003)
        self.prey = [Body(f"prey-{i}", self.rng_init.uniform(config.width * .2, config.width * .8),
                          self.rng_init.uniform(config.height * .2, config.height * .8), energy=config.start_energy) for i in range(config.prey_count)]
        self.predator = Body("predator-0", config.width * .5, config.height * .1, energy=100)
        self.predator_heading = self.rng_predator.uniform(-math.pi, math.pi)
        self.predator_visible_previous: set[str] = set()
        self.food: dict[str, Body] = {}
        self.next_food = 0
        for _ in range(config.food_count):
            self._spawn_food()
        self.tick = 0
        self.events: list[dict[str, Any]] = []
        self.escape_count = 0
        self.exposure_count = 0
        self.prey_tick_count = 0
        self.encounter_count = 0
        self.capture_count = 0

    def _spawn_food(self) -> None:
        if len(self.food) >= self.config.food_count:
            return
        key = f"food-{self.next_food}"
        self.next_food += 1
        self.food[key] = Body(key, self.rng_resources.uniform(1, self.config.width - 1),
                              self.rng_resources.uniform(1, self.config.height - 1), energy=self.config.food_energy)

    def observe(self, actor: Body) -> dict[str, Any]:
        r = self.config.perception
        neighbors = [b for b in self.prey if b.id != actor.id and b.alive and distance(actor, b) <= r]
        resources = [b for b in self.food.values() if distance(actor, b) <= r]
        threat = self.predator if self.config.predator_enabled and distance(actor, self.predator) <= r else None
        def item(b: Body) -> dict[str, float | str]:
            return {"id": b.id, "dx": round(b.x - actor.x, 3), "dy": round(b.y - actor.y, 3)}
        return {"tick": self.tick, "id": actor.id, "energy": round(actor.energy, 3),
                "neighbors": [item(b) for b in neighbors], "food": [item(b) for b in resources],
                "predator": item(threat) if threat else None}

    def _move(self, body: Body, desired: tuple[float, float], max_speed: float) -> None:
        c = self.config
        dx, dy = unit(*desired)
        target_vx, target_vy = dx * max_speed, dy * max_speed
        ax, ay = target_vx - body.vx, target_vy - body.vy
        amag = math.hypot(ax, ay)
        if amag > c.acceleration:
            ax, ay = ax * c.acceleration / amag, ay * c.acceleration / amag
        nvx, nvy = body.vx + ax, body.vy + ay
        old_angle = math.atan2(body.vy, body.vx) if math.hypot(body.vx, body.vy) > 1e-8 else None
        if old_angle is not None and math.hypot(nvx, nvy) > 1e-8:
            new_angle = math.atan2(nvy, nvx)
            delta = (new_angle - old_angle + math.pi) % (2 * math.pi) - math.pi
            angle = old_angle + max(-c.turn_radians, min(c.turn_radians, delta))
            speed = min(max_speed, math.hypot(nvx, nvy))
            nvx, nvy = math.cos(angle) * speed, math.sin(angle) * speed
        speed = math.hypot(nvx, nvy)
        if speed > max_speed:
            nvx, nvy = nvx * max_speed / speed, nvy * max_speed / speed
        body.x = max(0.0, min(c.width, body.x + nvx))
        body.y = max(0.0, min(c.height, body.y + nvy))
        body.vx = 0.0 if body.x in (0.0, c.width) else nvx
        body.vy = 0.0 if body.y in (0.0, c.height) else nvy

    def _steer(self, b: Body) -> tuple[float, float]:
        c = self.config
        neighbors = [n for n in self.prey if n.alive and n.id != b.id and distance(n, b) <= c.perception]
        sx = sy = ax = ay = cx = cy = 0.0
        for n in neighbors:
            d = max(distance(n, b), .01)
            if d < c.interaction * 3:
                sx += (b.x - n.x) / (d * d)
                sy += (b.y - n.y) / (d * d)
            ax += n.vx
            ay += n.vy
            cx += n.x - b.x
            cy += n.y - b.y
        k = max(1, len(neighbors))
        social = c.social_strength * (2.0 if b.objective == Objective.COHERE else .45 if b.objective in (Objective.FORAGE, Objective.EXPLORE, Objective.FLEE) else 1.0)
        x, y = social * (sx * 5 + ax / k * .3 + cx / k * .03), social * (sy * 5 + ay / k * .3 + cy / k * .03)
        pred_d = distance(b, self.predator)
        if c.predator_enabled and pred_d < c.perception and (b.objective == Objective.FLEE or pred_d < c.capture_radius * 5):
            x += (b.x - self.predator.x) * 5
            y += (b.y - self.predator.y) * 5
        if b.objective == Objective.FORAGE and b.target_id in self.food:
            f = self.food[b.target_id]
            x += (f.x - b.x) * 2
            y += (f.y - b.y) * 2
        elif b.objective == Objective.FOLLOW:
            target = next((n for n in neighbors if n.id == b.target_id), None)
            if target:
                x += (target.x - b.x) * 2
                y += (target.y - b.y) * 2
        elif b.objective == Objective.EXPLORE:
            x += (c.width / 2 - b.x) * .1 + 3
            y += (c.height / 2 - b.y) * .1 + 2
        elif b.objective == Objective.REST:
            x, y = 0, 0
        if b.x < 5: x += 20
        if b.x > c.width - 5: x -= 20
        if b.y < 5: y += 20
        if b.y > c.height - 5: y -= 20
        return x, y

    def step(self, actions: dict[str, Decision] | None = None) -> list[dict[str, Any]]:
        self.tick += 1
        actions = actions or {}
        events: list[dict[str, Any]] = []
        for b in self.prey:
            if not b.alive:
                continue
            if b.id in actions:
                decision = actions[b.id]
                b.objective, b.target_id = decision.objective, decision.target_id
                b.decision_until = self.tick + decision.duration
                b.last_decision_tick = self.tick
                b.objectives.append(decision.objective.value)
            self._move(b, self._steer(b), self.config.prey_speed)
            b.energy -= self.config.metabolism + self.config.move_cost * math.hypot(b.vx, b.vy)
            for key, f in list(self.food.items()):
                if distance(b, f) <= self.config.interaction:
                    b.energy = min(self.config.max_energy, b.energy + f.energy)
                    b.food_eaten += 1
                    del self.food[key]
                    events.append({"tick": self.tick, "type": "food", "agent": b.id, "resource": key})
                    break
            if b.energy <= 0:
                b.energy, b.alive, b.death_tick = 0.0, False, self.tick
                events.append({"tick": self.tick, "type": "starvation", "agent": b.id})
        targets = [b for b in self.prey if b.alive]
        if self.config.predator_enabled and targets:
            visible = [b for b in targets if distance(b, self.predator) <= self.config.predator_perception]
            if visible:
                nearest = min(visible, key=lambda b: (distance(b, self.predator), b.id))
                desired = (nearest.x - self.predator.x, nearest.y - self.predator.y)
            else:
                if self.tick % 8 == 0:
                    self.predator_heading = self.rng_predator.uniform(-math.pi, math.pi)
                desired = (math.cos(self.predator_heading), math.sin(self.predator_heading))
            self._move(self.predator, desired, self.config.predator_speed)
            currently_visible = {b.id for b in targets if distance(b, self.predator) <= self.config.predator_perception}
            self.prey_tick_count += len(targets)
            self.exposure_count += len(currently_visible)
            for agent_id in sorted(currently_visible - self.predator_visible_previous):
                self.encounter_count += 1
                events.append({"tick": self.tick, "type": "encounter", "agent": agent_id})
            self.predator_visible_previous = currently_visible
            for b in targets:
                if distance(b, self.predator) <= self.config.capture_radius:
                    b.alive, b.death_tick = False, self.tick
                    self.capture_count += 1
                    events.append({"tick": self.tick, "type": "predation", "agent": b.id})
                    break
            if all(distance(b, self.predator) > self.config.capture_radius * 4 for b in targets):
                self.escape_count += 1
        if self.tick % self.config.food_replenish_interval == 0:
            self._spawn_food()
        if self.rng_events.random() < self.config.stochastic_spawn_probability:
            self._spawn_food()
        if self.config.resource_shift_tick == self.tick:
            for food in self.food.values():
                food.x = self.rng_events.uniform(self.config.width * .65, self.config.width * .95)
                food.y = self.rng_events.uniform(self.config.height * .05, self.config.height * .95)
            events.append({"tick": self.tick, "type": "resource_shift", "agent": None})
        self.events.extend(events)
        return events

    def snapshot(self) -> dict[str, Any]:
        return {"tick": self.tick, "prey": [asdict(b) for b in self.prey],
                "predator": asdict(self.predator), "food": [asdict(f) for f in self.food.values()],
                "events": self.events}
