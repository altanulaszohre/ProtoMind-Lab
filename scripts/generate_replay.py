"""Reproducibly generate and independently verify the bundled engine recording."""
import json
from dataclasses import replace
from protomind.observatory import record, verify_recording, save_recording
from protomind.research import scenario_config
from protomind.storage import ROOT

config=replace(scenario_config('predator'),seed=1001)
data=record(config)
data['id']='bundled'; data['verification']='Engine actions reapplied; all positions, events and metrics match.'
assert verify_recording(data), 'Recording failed deterministic verification'
path=ROOT/'recordings/predator-pressure.json.gz'
checksum=save_recording(data,path)
(ROOT/'recordings/manifest.json').write_text(json.dumps({'file':path.name,'sha256':checksum,'condition':'A','mechanism':'mechanistic; no LLM inference','seed':1001,'ticks':len(data['frames'])-1,'bytes':path.stat().st_size,'verified':True,'generator':'scripts/generate_replay.py'},indent=2)+'\n')
print(json.dumps({'bytes':path.stat().st_size,'frames':len(data['frames']),'verified':True}))
