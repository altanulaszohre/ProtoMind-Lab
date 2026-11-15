"""Bounded GGUF metadata inspection and real structured-decision compatibility probes."""
from __future__ import annotations
import json
import struct
import shutil
import subprocess
from pathlib import Path
from .inference import LlamaBackend, SERVER
from .schema import validate_decision
from .storage import ROOT


def model_path(name: str) -> Path:
    if not isinstance(name, str) or Path(name).name != name or not name.lower().endswith('.gguf'):
        raise ValueError('Select a GGUF filename from the project model library')
    path = ROOT / 'models' / name
    if path.is_symlink() or not path.resolve().is_relative_to((ROOT / 'models').resolve()):
        raise ValueError('Model must be a regular project-local file')
    return path


def metadata(path: Path) -> dict:
    """Read metadata without loading tensor weights; bounded lengths reject corrupt files."""
    with path.open('rb') as f:
        def read(n):
            data = f.read(n)
            if len(data) != n: raise ValueError('Truncated GGUF metadata')
            return data
        def number(fmt): return struct.unpack('<' + fmt, read(struct.calcsize(fmt)))[0]
        def string(keep=True):
            n = number('Q')
            if n > 8_000_000: raise ValueError('GGUF metadata string exceeds limit')
            if keep: return read(n).decode('utf-8', errors='replace')
            f.seek(n, 1)
        def value(kind, keep=True, depth=0):
            formats = {0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}
            if kind in formats: return number(formats[kind])
            if kind == 8: return string(keep)
            if kind == 9 and depth == 0:
                inner, count = number('I'), number('Q')
                if count > 2_000_000: raise ValueError('GGUF array exceeds limit')
                if inner in formats: f.seek(struct.calcsize(formats[inner]) * count, 1)
                else:
                    for _ in range(count): value(inner, False, depth+1)
                return None
            raise ValueError('Unsupported GGUF metadata type')
        if read(4) != b'GGUF': raise ValueError('Not a GGUF model')
        version, tensors, count = number('I'), number('Q'), number('Q')
        if version not in (2,3) or count > 10000: raise ValueError('Unsupported GGUF version or metadata count')
        result = {'file':path.name, 'bytes':path.stat().st_size, 'version':version, 'tensors':tensors}
        for _ in range(count):
            key = string()
            keep = key in ('general.name','general.architecture','general.file_type','tokenizer.chat_template') or key.endswith('.context_length')
            val = value(number('I'), keep)
            if keep: result[key] = val
        if f.tell() > path.stat().st_size: raise ValueError('Truncated GGUF file')
        template = result.pop('tokenizer.chat_template', '')
        result['has_chat_template'] = isinstance(template, str) and bool(template.strip())
        result['estimated_memory_gib'] = round((result['bytes'] * 1.3 + 512 * 1024**2) / 1024**3, 2)
        result['memory_note'] = 'Planning estimate, not a measured requirement; context and architecture affect memory.'
        return result


def library() -> dict:
    items=[]
    for path in sorted((ROOT/'models').glob('*.gguf')):
        try: items.append(metadata(model_path(path.name)))
        except (ValueError, OSError) as exc: items.append({'file':path.name,'error':str(exc)})
    try:
        physical=int(subprocess.run(['sysctl','-n','hw.memsize'],capture_output=True,text=True,check=True).stdout)
    except (OSError, ValueError, subprocess.SubprocessError): physical=None
    return {'models':items,'runtime_available':SERVER.is_file(),'runtime':'llama.cpp b12088',
            'disk_free_bytes':shutil.disk_usage(ROOT).free,'physical_memory_bytes':physical}


def validate_backend(backend: LlamaBackend) -> dict:
    probes = [
        {'tick':0,'id':'prey-0','energy':80,'neighbors':[],'food':[],'predator':None},
        {'tick':1,'id':'prey-0','energy':20,'neighbors':[],'food':[{'id':'food-0','dx':1,'dy':1}],'predator':None},
        {'tick':2,'id':'prey-0','energy':40,'neighbors':[{'id':'prey-1','dx':3,'dy':0}], 'food':[], 'predator':{'id':'predator-0','dx':2,'dy':2}},
    ]
    records=[]
    for obs in probes:
        raw, tokens=backend.decide(json.dumps({'observation':obs,'memory':[]}))
        d=validate_decision(raw,{i['id'] for i in obs['neighbors']+obs['food']},obs['predator'] is not None)
        records.append({'objective':d.objective.value,'tokens':tokens})
    return {'compatible':True,'probes':records,'scope':'Model load, chat template, and three observation-constrained JSON probes; not universal compatibility.'}


def open_model(settings: dict) -> LlamaBackend:
    allowed={'file','context','max_tokens','temperature'}
    if set(settings)-allowed: raise ValueError('Unknown model setting')
    path=model_path(settings.get('file','LFM3-1.7B-Q4_K_M.gguf'))
    info=metadata(path)
    if not info['has_chat_template']: raise ValueError('GGUF has no embedded chat template. Import a supported instruction model with a chat template.')
    return LlamaBackend(model=path,context=settings.get('context',2048),max_tokens=settings.get('max_tokens',96),temperature=settings.get('temperature',0))
