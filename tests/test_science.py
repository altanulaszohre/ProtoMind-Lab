"""Mechanistic ecology, controls, and research protocol tests."""
import json
import math
import unittest
from dataclasses import replace

from protomind.agents import Controller
from protomind.experiments import paired_comparisons, run_one
from protomind.memory import Memory
from protomind.research import CALIBRATION_SEEDS, EVALUATION_SEEDS, scenario_config, sweep
from protomind.schema import Decision, Objective
from protomind.simulation import Config, World, distance


class CaptureBackend:
    def __init__(self): self.prompts = []
    def decide(self, prompt):
        self.prompts.append(json.loads(prompt))
        return '{"objective":"COHERE","duration":4,"target_id":null}', 10
    def close(self): pass


class EcologyTests(unittest.TestCase):
    def test_calibration_and_evaluation_seeds_disjoint(self):
        self.assertFalse(set(CALIBRATION_SEEDS) & set(EVALUATION_SEEDS))
        self.assertEqual(scenario_config("motion").predator_enabled, False)
        self.assertEqual(scenario_config("change", 20).resource_shift_tick, 10)

    def test_capture_starvation_escape_recovery(self):
        starvation = World(Config(prey_count=1, food_count=0, predator_enabled=False, start_energy=1, metabolism=1, move_cost=0))
        starvation.step({"prey-0": Decision(Objective.REST, 2)})
        self.assertFalse(starvation.prey[0].alive)
        self.assertEqual(starvation.events[-1]["type"], "starvation")
        recovered = World(Config(prey_count=1, food_count=1, predator_enabled=False, start_energy=10, food_energy=25))
        fish = recovered.prey[0]
        food = next(iter(recovered.food.values()))
        food.x, food.y = fish.x, fish.y
        recovered.step({fish.id: Decision(Objective.REST, 2)})
        self.assertGreaterEqual(fish.energy, 30)
        escaped = World(Config(prey_count=1, food_count=0, predator_speed=.5, capture_radius=1, predator_perception=30))
        fish = escaped.prey[0]
        escaped.predator.x, escaped.predator.y = fish.x + 5, fish.y
        for _ in range(15): escaped.step({fish.id: Decision(Objective.FLEE, 2)})
        self.assertTrue(fish.alive)
        self.assertGreater(escaped.escape_count, 0)

    def test_turning_predator_sensing_and_replenishment(self):
        world = World(Config(prey_count=1, food_count=1, predator_perception=1,
                             turn_radians=.2, acceleration=1, food_replenish_interval=1))
        fish = world.prey[0]
        fish.vx, fish.vy = 1, 0
        world._move(fish, (-10, 10), world.config.prey_speed)
        self.assertLessEqual(abs(math.atan2(fish.vy, fish.vx)), .2 + 1e-9)
        world.predator.x, world.predator.y = 0, 0
        world.predator_heading = 0
        food = next(iter(world.food.values()))
        food.x, food.y = fish.x, fish.y
        world.step({fish.id: Decision(Objective.REST, 2)})
        self.assertEqual(world.predator.y, 0)
        self.assertEqual(len(world.food), 1)

    def test_social_ablation_and_stochastic_replay(self):
        base = Config(prey_count=2, food_count=0, predator_enabled=False, stochastic_spawn_probability=.5)
        a, b = World(base), World(replace(base, social_strength=0))
        for world in (a, b):
            world.prey[0].x = world.prey[0].y = 50
            world.prey[1].x, world.prey[1].y = 70, 50
        self.assertNotEqual(a._steer(a.prey[0]), b._steer(b.prey[0]))
        def trial():
            world = World(base)
            for _ in range(20): world.step()
            return world.snapshot()
        self.assertEqual(trial(), trial())

    def test_resource_shift_is_event_not_hidden_observation(self):
        world = World(Config(prey_count=1, food_count=2, predator_enabled=False, resource_shift_tick=1))
        self.assertNotIn("resource_shift", world.observe(world.prey[0]))
        events = world.step()
        self.assertIn("resource_shift", [event["type"] for event in events])

    def test_memory_negative_control_scrubs_information(self):
        world = World(Config(food_count=0))
        memory = Memory(":memory:")
        memory.add("prey-0", 0, "food", {"id": "food-9", "dx": 13.5})
        backend = CaptureBackend()
        controller = Controller("D", backend, memory)
        controller.actions(world)
        record = backend.prompts[0]["memory"][0]
        self.assertEqual(record["payload"]["id"], "x" * 6)
        self.assertEqual(record["payload"]["dx"], 0)
        memory.close()

    def test_new_metrics_and_paired_interval(self):
        result = run_one(replace(scenario_config("predator"), max_ticks=5), "A")
        self.assertEqual(len(result["timeseries"]), 5)
        self.assertIn("group_alignment", result["metrics"])
        self.assertIn("predator_encounters", result["metrics"])
        rows = [{"seed": seed, "condition": condition, "metrics": {"survival_rate": value,
                 "mean_survival_time": value, "food_collection": value,
                 "group_alignment": value, "predator_exposure": value}}
                for seed in range(5) for condition, value in (("A", 0.5), ("B", 0.6))]
        comparison = paired_comparisons(rows, ("A", "B"))["B-A"]["survival_rate"]
        self.assertIsNotNone(comparison["bootstrap_95_interval"])
        self.assertEqual(comparison["n_pairs"], 5)


if __name__ == "__main__": unittest.main()
