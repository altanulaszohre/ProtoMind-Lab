"""Opt-in real-model integration test: PROTOMIND_REAL_TEST=1 ./scripts/run_tests.sh."""
import json
import os
import unittest

from protomind.inference import LlamaBackend, MODEL, SERVER
from protomind.schema import validate_decision


@unittest.skipUnless(os.environ.get("PROTOMIND_REAL_TEST") == "1", "set PROTOMIND_REAL_TEST=1 for real model test")
class RealModelTests(unittest.TestCase):
    def test_two_independent_observations_and_shutdown(self):
        self.assertTrue(MODEL.is_file())
        self.assertTrue(SERVER.is_file())
        observations = [
            {"tick": 0, "id": "prey-0", "energy": 90, "neighbors": [], "food": [], "predator": None},
            {"tick": 0, "id": "prey-1", "energy": 18, "neighbors": [], "food": [], "predator": None},
        ]
        self.assertNotEqual(observations[0], observations[1])
        with LlamaBackend() as backend:
            for observation in observations:
                raw, tokens = backend.decide(json.dumps({"observation": observation, "memory": []}))
                decision = validate_decision(raw, set(), False)
                self.assertTrue(decision.duration >= 1)
                self.assertGreater(tokens, 0)
        self.assertIsNotNone(backend.process.poll())

@unittest.skipUnless(os.environ.get("PROTOMIND_REAL_TEST") == "1", "set PROTOMIND_REAL_TEST=1 for real model test")
class SelectedModelTests(unittest.TestCase):
    def test_selected_gguf_compatibility_conditions_and_single_model_lock(self):
        from protomind.models import open_model, validate_backend, metadata
        from protomind.observatory import record
        from protomind.simulation import Config
        self.assertTrue(metadata(MODEL)['has_chat_template'])
        with open_model({'file':MODEL.name,'context':2048,'max_tokens':96,'temperature':0}) as backend:
            result=validate_backend(backend)
            self.assertTrue(result['compatible'])
            self.assertTrue(all(p['tokens']>0 for p in result['probes']))
            with self.assertRaises(RuntimeError):
                LlamaBackend(model=MODEL)
            for condition in ('B','C','D'):
                data=record(Config(prey_count=1,max_ticks=10,predator_enabled=False,food_count=2),condition,backend)
                self.assertEqual(data['mechanism'],'llama.cpp')
                self.assertGreater(data['frames'][-1]['metrics']['tokens'],0)
                self.assertEqual(data['frames'][-1]['metrics']['invalid'],0)
                memories=[m for f in data['frames'] for b in f['prey'] for m in b.get('memories',[])]
                self.assertEqual(bool(memories),condition in ('C','D'))
        self.assertIsNotNone(backend.process.poll())
