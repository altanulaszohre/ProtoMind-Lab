import json
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from protomind.agents import Controller
from protomind.experiments import METRIC_DEFINITIONS, compare, run_one
from protomind.inference import LlamaBackend, MockBackend
from protomind.memory import Memory
from protomind.schema import Decision, Objective, validate_decision
from protomind.replay import replay
from protomind.security import policy
from protomind.simulation import Config, World, distance
from protomind.storage import ROOT, local_path


class InvalidBackend:
    def decide(self, prompt):
        return '{"objective":"FORAGE","duration":999,"target_id":null}', 2
    def close(self): pass


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.config = replace(Config(), seed=42, max_ticks=12)

    def test_bounds_speed_acceleration(self):
        w = World(self.config)
        b = w.prey[0]
        b.x, b.y = .1, .1
        for _ in range(20):
            old_v = (b.vx, b.vy)
            w._move(b, (-100, -100), self.config.prey_speed)
            self.assertTrue(0 <= b.x <= self.config.width and 0 <= b.y <= self.config.height)
            self.assertLessEqual(math.hypot(b.vx, b.vy), self.config.prey_speed + 1e-9)
            self.assertLessEqual(math.hypot(b.vx-old_v[0], b.vy-old_v[1]), self.config.acceleration + 1e-9)

    def test_energy_food(self):
        w = World(replace(self.config, prey_count=1, food_count=1))
        b = w.prey[0]
        w.predator.x = w.predator.y = 99
        food = next(iter(w.food.values()))
        food.x, food.y = b.x, b.y
        old = b.energy
        w.step({b.id: Decision(Objective.REST, 2)})
        self.assertEqual(b.food_eaten, 1)
        self.assertGreater(b.energy, old)
        self.assertEqual(len(w.food), 0)

    def test_predation_and_mortality(self):
        w = World(replace(self.config, prey_count=1, food_count=0))
        b = w.prey[0]
        w.predator.x, w.predator.y = b.x, b.y
        w.step({b.id: Decision(Objective.REST, 2)})
        self.assertFalse(b.alive)
        self.assertEqual(b.death_tick, 1)

    def test_observation_range(self):
        w = World(replace(self.config, prey_count=2, food_count=0, perception=5))
        w.prey[0].x = w.prey[0].y = 0
        w.prey[1].x = w.prey[1].y = 90
        self.assertEqual(w.observe(w.prey[0])["neighbors"], [])
        self.assertIsNone(w.observe(w.prey[0])["predator"])

    def test_replay(self):
        actions = [{f"prey-{i}": Decision(Objective.COHERE, 4) for i in range(8)} for _ in range(8)]
        def run():
            w = World(self.config)
            for a in actions: w.step(a)
            return w.snapshot()
        self.assertEqual(run(), run())


class AgentTests(unittest.TestCase):
    def test_validation_and_fallback(self):
        valid = validate_decision('{"objective":"FLEE","duration":2,"target_id":null}', set())
        self.assertEqual(valid.objective, Objective.FLEE)
        with self.assertRaises(ValueError):
            validate_decision('{"objective":"FORAGE","duration":5,"target_id":"food-0"}', set())
        w = World(Config())
        actions = Controller("B", InvalidBackend()).actions(w)
        self.assertTrue(all(a.objective == Objective.FLEE for a in actions.values()))

    def test_scheduler(self):
        w = World(replace(Config(), food_count=0, decision_interval=10))
        c = Controller("B", MockBackend())
        initial = c.actions(w)
        self.assertEqual(len(initial), 8)
        w.step(initial)
        self.assertEqual(len(c.actions(w)), 0)

    def test_memory_isolation(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as folder:
            m = Memory(Path(folder) / "test.sqlite")
            m.add("prey-0", 1, "threat", {"id":"predator-0"})
            self.assertEqual(m.retrieve("prey-1", 1), [])
            self.assertEqual(len(m.retrieve("prey-0", 1)), 1)
            m.close()

    def test_missing_runtime_and_cleanup(self):
        with patch("protomind.inference.MODEL", ROOT / "models/absent.gguf"):
            with self.assertRaises(FileNotFoundError): LlamaBackend()
        class Process:
            def __init__(self): self.terminated = False
            def poll(self): return None
            def terminate(self): self.terminated = True
            def wait(self, timeout): return 0
        backend = LlamaBackend.__new__(LlamaBackend)
        backend.process = Process()
        backend.close()
        self.assertTrue(backend.process.terminated)


class ResearchTests(unittest.TestCase):
    def test_metrics_and_config(self):
        with self.assertRaises(ValueError): Config(prey_count=0)
        result = run_one(replace(Config(), max_ticks=4, seed=99), "A")
        self.assertEqual(set(result["metrics"]), set(METRIC_DEFINITIONS))
        self.assertTrue(0 <= result["metrics"]["survival_rate"] <= 1)

    def test_recorded_replay(self):
        result = compare(replace(Config(), max_ticks=4, resource_shift_tick=2, stochastic_spawn_probability=.4), [73], MockBackend(), "mock")
        for condition in ("A", "B", "C", "D"):
            self.assertTrue(replay(Path(result["directory"]), condition, 73)["events_match"])

    def test_storage(self):
        with self.assertRaises(ValueError): local_path("../escape")
        self.assertTrue(local_path("models/x").is_relative_to(ROOT))

    def test_publication_policy(self):
        self.assertIn("outside publication allowlist", policy("models/weights.gguf", b"GGUF"))
        self.assertIn("large file", policy("docs/huge.md", b"a" * 1_000_001))
        self.assertIn("private_key", policy("docs/key.md", b"-----BEGIN " + b"PRIVATE KEY-----"))
        self.assertEqual(policy("docs/clean.md", b"ordinary research text"), [])


if __name__ == "__main__": unittest.main()
