"""Read-only frame adapter around the validated World and Controller."""
from __future__ import annotations
import gzip
import hashlib
import json
import math
import threading
import time
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from .agents import Controller
from .experiments import _alignment, _cohesion
from .memory import Memory, NullMemory
from .models import open_model, validate_backend
from .research import scenario_config
from .simulation import Config, World, distance
from .schema import validate_decision
from .storage import ROOT

LIMITS = {
    'prey_count': (1,100,1), 'food_count': (0,200,1), 'max_ticks': (10,2000,1),
    'seed': (0,2147483647,1), 'food_replenish_interval': (1,100,1),
    'predator_perception': (5,100,1), 'predator_speed': (.5,5,.1),
    'perception': (5,100,1), 'social_strength': (0,3,.1), 'metabolism': (.01,.5,.01),
    'stochastic_spawn_probability': (0,1,.01), 'decision_interval': (1,30,1),
}
INTEGER_FIELDS={'prey_count','food_count','max_ticks','seed','food_replenish_interval','decision_interval'}


def presets():
    out={key:asdict(scenario_config(key)) for key in ('motion','predator','scarcity','change')}
    out['calibrated']=json.loads((ROOT/'configs/calibrated_v1.json').read_text())['config']
    return out


def configuration(payload: dict) -> Config:
    name=payload.get('scenario','predator')
    if name not in presets(): raise ValueError('Unknown scenario')
    edits=payload.get('config',{})
    if not isinstance(edits,dict): raise ValueError('Configuration must be an object')
    if name=='calibrated' and edits: raise ValueError('Calibrated reference is immutable; select a custom scenario')
    for key,value in edits.items():
        if key=='predator_enabled':
            if type(value) is not bool: raise ValueError('Predator population is 0 or 1')
        elif key not in LIMITS: raise ValueError('Unsupported configuration parameter: '+key)
        else:
            lo,hi,_=LIMITS[key]
            if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi: raise ValueError('Out of range: '+key)
            if key in INTEGER_FIELDS and type(value) is not int: raise ValueError('Integer required: '+key)
    base=presets()[name] | edits
    if name=='change': base['resource_shift_tick']=max(1,base['max_ticks']//2)
    if base['prey_count']*base['max_ticks']>100_000: raise ValueError('Use at most 100,000 prey-ticks per interactive episode')
    return Config(**base)


def frame(world: World, controller: Controller, new_records: list, events: list) -> dict:
    c=world.config
    def body(b):
        out={key:getattr(b,key) for key in ('id','x','y','vx','vy','energy','alive','death_tick','food_eaten','target_id')}
        out['objective']=b.objective.value
        if b.id.startswith('prey'):
            out['observation']=world.observe(b) if b.alive else None
            out['memories']=controller.memory.retrieve(b.id,world.tick,limit=4)
        return out
    pred=body(world.predator) if c.predator_enabled else None
    if pred:
        visible=[b for b in world.prey if b.alive and distance(b,world.predator)<=c.predator_perception]
        pred['objective']='CAPTURE' if any(e['type']=='predation' for e in events) else 'PURSUIT' if visible else 'PATROL'
        pred['visible_prey']=[b.id for b in visible]
    cohesion,fragments=_cohesion(world)
    records=controller.records if controller.condition!='A' else []
    metrics={'survival':sum(b.alive for b in world.prey)/c.prey_count,
             'mean_energy':sum(b.energy if b.alive else 0 for b in world.prey)/c.prey_count,
             'alignment':_alignment(world),'cohesion':cohesion,'fragmentation':fragments,
             'food':sum(b.food_eaten for b in world.prey),'encounters':world.encounter_count,'captures':world.capture_count,
             'latency_ms':sum(r.latency_ms for r in records)/len(records) if records else 0,
             'tokens':sum(r.tokens for r in records),'calls':len(records),'invalid':sum(not r.valid for r in records)}
    return {'tick':world.tick,'prey':[body(b) for b in world.prey], 'predator':pred,
            'food':[{'id':b.id,'x':b.x,'y':b.y} for b in world.food.values()],
            'decisions':[asdict(r) for r in new_records], 'events':events, 'metrics':metrics}


def header(config: Config, condition: str, scenario: str, model=None):
    return {'schema':1,'id':uuid.uuid4().hex[:12],'scenario':scenario,'condition':condition,
            'mechanism':'mechanistic' if condition=='A' else 'llama.cpp', 'model':model if condition!='A' else None,
            'config':asdict(config), 'status':'running','frames':[],
            'interpretation':'Engineering simulation, not a biologically validated model. Single episodes do not establish a treatment effect.'}


def record(config: Config, condition='A', backend=None) -> dict:
    world=World(config)
    mem=Memory(':memory:') if condition in ('C','D') else NullMemory()
    control=Controller(condition,backend,mem)
    result=header(config,condition,'predator')
    result['frames'].append(frame(world,control,[],[]))
    try:
        while world.tick<config.max_ticks and any(b.alive for b in world.prey):
            index=len(control.records)
            events=world.step(control.actions(world)); control.record_events(events)
            result['frames'].append(frame(world,control,control.records[index:],events))
        result['status']='complete'
        return result
    finally: mem.close()


def verify_recording(data: dict) -> bool:
    """Reapply every recorded action and verify exact engine positions/events/metrics."""
    config=Config(**data['config']); world=World(config)
    ctrl=Controller('A')
    initial=frame(world,ctrl,[],[])
    if data['frames'][0]!=initial: return False
    for expected in data['frames'][1:]:
        actions={}
        for row in expected['decisions']:
            actor=next(b for b in world.prey if b.id==row['agent'] and b.alive)
            obs=world.observe(actor)
            actions[actor.id]=validate_decision(json.dumps(row['decision']),{i['id'] for i in obs['food']+obs['neighbors']})
        events=world.step(actions)
        actual=frame(world,ctrl,[],events)
        for key in ('tick','prey','predator','food','events','metrics'):
            if actual[key]!=expected[key]: return False
    return True


def save_recording(data: dict, path: Path):
    raw=json.dumps(data,separators=(',',':'),allow_nan=False).encode()
    with path.open('wb') as f:
        with gzip.GzipFile(fileobj=f,mode='wb',mtime=0,filename='') as gz: gz.write(raw)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LiveSession:
    def __init__(self,payload):
        self.config=configuration(payload)
        condition=payload.get('condition','A')
        if condition not in ('A','B','C','D'): raise ValueError('Unknown decision condition')
        mem=payload.get('memory',{})
        if set(mem)-{'max_per_agent','max_age'}: raise ValueError('Unknown memory setting')
        self.max_mem=mem.get('max_per_agent',80); self.max_age=mem.get('max_age',200)
        if type(self.max_mem) is not int or type(self.max_age) is not int or not 8<=self.max_mem<=200 or not 10<=self.max_age<=1000: raise ValueError('Memory bounds: 8–200 records; 10–1000 ticks')
        self.model_settings=payload.get('model',{})
        self.data=header(self.config,condition,payload.get('scenario','predator'),self.model_settings)
        self.data['memory']={'max_per_agent':self.max_mem,'max_age':self.max_age}
        self.lock=threading.Lock(); self.wake=threading.Event(); self.wake.set(); self.stop_event=threading.Event()
        self.backend=None
        self.thread=threading.Thread(target=self.run,name='protomind-experiment',daemon=True)
        self.thread.start()

    def run(self):
        memory=None
        try:
            condition=self.data['condition']
            if condition!='A':
                self.data['status']='loading_model'
                self.backend=open_model(self.model_settings)
                self.data['validation']=validate_backend(self.backend)
            memory=Memory(':memory:',self.max_mem,self.max_age) if condition in ('C','D') else NullMemory()
            world=World(self.config); ctrl=Controller(condition,self.backend,memory)
            with self.lock:
                self.data['frames'].append(frame(world,ctrl,[],[])); self.data['status']='running'
            while world.tick<self.config.max_ticks and any(b.alive for b in world.prey) and not self.stop_event.is_set():
                self.wake.wait(.2)
                if not self.wake.is_set(): continue
                start=time.monotonic(); index=len(ctrl.records)
                actions=ctrl.actions(world)
                if self.stop_event.is_set(): break
                events=world.step(actions); ctrl.record_events(events)
                snapshot=frame(world,ctrl,ctrl.records[index:],events)
                with self.lock: self.data['frames'].append(snapshot)
                self.stop_event.wait(max(0,.125-(time.monotonic()-start)))
            self.data['status']='stopped' if self.stop_event.is_set() else 'complete'
        except Exception as exc:
            self.data['status']='error'
            # Do not leak local paths or raw backend responses into persisted diagnostics.
            self.data['error']='Model or experiment failed: '+type(exc).__name__+'. Check local model compatibility; replay and mechanistic mode remain available.'
        finally:
            if memory: memory.close()
            if self.backend: self.backend.close()
            folder=ROOT/'experiments'/'observatory'; folder.mkdir(parents=True,exist_ok=True)
            save_recording(self.data,folder/(self.data['id']+'.json.gz'))

    def snapshot(self,after=-1):
        with self.lock: return {**self.data,'frames':self.data['frames'][max(0,after+1):]}

    def control(self,action):
        if action=='pause': self.wake.clear(); self.data['status']='paused'
        elif action=='resume': self.wake.set(); self.data['status']='running'
        elif action=='stop': self.stop_event.set(); self.wake.set()
        else: raise ValueError('Unknown transport command')

    def close(self):
        self.stop_event.set(); self.wake.set()
        if self.backend: self.backend.close()
        self.thread.join(timeout=8)
