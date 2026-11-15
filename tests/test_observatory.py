import gzip
import hashlib
import json
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from protomind.observatory import configuration, presets, record, verify_recording, LiveSession, frame
from protomind.simulation import Config, World
from protomind.agents import Controller
from protomind.models import metadata, model_path
from protomind.storage import ROOT

class ObservatoryTests(unittest.TestCase):
    def test_bundled_recording_reconstructs_exactly(self):
        path=ROOT/'recordings/predator-pressure.json.gz'
        manifest=json.loads((ROOT/'recordings/manifest.json').read_text())
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),manifest['sha256'])
        data=json.loads(gzip.decompress(path.read_bytes()))
        self.assertEqual(data['mechanism'],'mechanistic')
        self.assertTrue(verify_recording(data))
        self.assertTrue(any(e['type']=='predation' for f in data['frames'] for e in f['events']))
        self.assertLess(path.stat().st_size,200000)

    def test_reference_immutable_and_parameter_bounds(self):
        before=(ROOT/'configs/calibrated_v1.json').read_bytes()
        self.assertEqual(configuration({'scenario':'calibrated'}),Config(**presets()['calibrated']))
        for edit in ({'prey_count':101},{'prey_count':2.5},{'predator_enabled':2},{'width':1},{'perception':float('nan')},{'max_ticks':0}):
            with self.assertRaises(ValueError): configuration({'config':edit})
        with self.assertRaises(ValueError): configuration({'scenario':'calibrated','config':{'seed':7}})
        config=configuration({'scenario':'change','config':{'prey_count':24,'max_ticks':30,'predator_enabled':False}})
        self.assertEqual(config.resource_shift_tick,15)
        self.assertEqual((ROOT/'configs/calibrated_v1.json').read_bytes(),before)

    def test_population_resources_metrics_and_capture_markers(self):
        data=record(replace(Config(),prey_count=30,max_ticks=50,seed=4))
        count=30; prev_survival=1
        for f in data['frames']:
            self.assertEqual(len(f['prey']),count)
            alive=sum(b['alive'] for b in f['prey'])
            self.assertEqual(f['metrics']['survival'],alive/count)
            self.assertLessEqual(f['metrics']['survival'],prev_survival);prev_survival=f['metrics']['survival']
            self.assertEqual(f['metrics']['mean_energy'],sum(b['energy'] if b['alive'] else 0 for b in f['prey'])/count)
            self.assertEqual(f['predator']['objective']=='CAPTURE',any(e['type']=='predation' for e in f['events']))
            self.assertEqual(f['metrics']['tokens'],0)
        self.assertTrue(verify_recording(data))

    def test_no_predator_is_not_rendered(self):
        data=record(Config(predator_enabled=False,max_ticks=10))
        self.assertTrue(all(f['predator'] is None for f in data['frames']))

    def test_replay_tampering_detected(self):
        data=record(Config(max_ticks=10))
        data['frames'][3]['prey'][0]['x']+=.01
        self.assertFalse(verify_recording(data))

    def test_live_pause_resume_stop_and_saved_record(self):
        session=LiveSession({'scenario':'motion','config':{'prey_count':3,'max_ticks':30}})
        deadline=time.monotonic()+3
        while len(session.data['frames'])<3 and time.monotonic()<deadline: time.sleep(.02)
        session.control('pause');time.sleep(.2);n=len(session.data['frames']);time.sleep(.2)
        self.assertEqual(len(session.data['frames']),n)
        session.control('resume');time.sleep(.3)
        self.assertGreater(len(session.data['frames']),n)
        session.close()
        self.assertFalse(session.thread.is_alive())
        self.assertEqual(session.data['status'],'stopped')
        saved=ROOT/'experiments/observatory'/(session.data['id']+'.json.gz')
        self.assertTrue(saved.is_file())
        self.assertTrue(verify_recording(json.loads(gzip.decompress(saved.read_bytes()))))

    def test_missing_llm_never_becomes_mechanistic(self):
        session=LiveSession({'scenario':'motion','condition':'C','model':{'file':'missing-test-model.gguf'},'config':{'max_ticks':10}})
        session.thread.join(3)
        self.assertEqual(session.data['status'],'error')
        self.assertEqual(session.data['mechanism'],'llama.cpp')
        self.assertEqual(session.data['frames'],[])

    def test_model_path_and_corrupt_metadata(self):
        for name in ('../model.gguf','/external.gguf','model.bin'):
            with self.assertRaises(ValueError): model_path(name)
        with tempfile.NamedTemporaryFile(dir=ROOT/'tmp',suffix='.gguf') as f:
            f.write(b'GGUF'+b'\xff'*28);f.flush()
            with self.assertRaises(ValueError): metadata(Path(f.name))
