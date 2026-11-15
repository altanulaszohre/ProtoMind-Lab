"""Loopback-only observatory API and static host. No remote assets or services."""
from __future__ import annotations
import argparse
import csv
import io
import gzip
import hashlib
import json
import mimetypes
import os
import re
import signal
import shutil
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from .models import library, metadata, model_path, open_model, validate_backend
from .observatory import LIMITS, LiveSession, presets
from .storage import ROOT, configure_local_environment

class ObservatoryServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address):
        self.session=None
        self.validation_backend=None
        super().__init__(address,Handler)
        self.operation_lock=threading.Lock()
        self.last_heartbeat=time.monotonic()
        self.desktop=False
        self.validation_backend=None

    def server_close(self):
        if self.session: self.session.close()
        if self.validation_backend: self.validation_backend.close()
        super().server_close()

class Handler(BaseHTTPRequestHandler):
    server: ObservatoryServer
    def log_message(self,*_): pass

    def send(self,status,data,kind='application/json'):
        raw=json.dumps(data,allow_nan=False).encode() if kind=='application/json' else data
        self.send_response(status)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        try: self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError): pass

    def trusted(self,write=False):
        host=self.headers.get('Host','')
        allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        if host not in allowed: raise PermissionError('Invalid local host')
        origin=self.headers.get('Origin')
        if origin and origin not in {'http://'+h for h in allowed}: raise PermissionError('Cross-origin request denied')
        if write and self.headers.get('X-ProtoMind')!='observatory': raise PermissionError('Local application header required')

    def do_GET(self):
        try:
            self.trusted()
            parsed=urlparse(self.path); path=parsed.path; query=parse_qs(parsed.query)
            if path=='/api/health': return self.send(200,{'ok':True,'desktop':self.server.desktop})
            if path=='/api/presets': return self.send(200,{'presets':presets(),'limits':LIMITS})
            if path=='/api/models': return self.send(200,library())
            if path=='/api/live':
                if not self.server.session: return self.send(200,{'status':'idle','frames':[]})
                return self.send(200,self.server.session.snapshot(int(query.get('after',['-1'])[0])))
            if path=='/api/datasets':
                items=[{'id':'bundled','name':'Predator Pressure · verified mechanistic recording','bundled':True}]
                for p in sorted((ROOT/'experiments/observatory').glob('*.json.gz'),reverse=True)[:50]:
                    if re.fullmatch(r'[0-9a-f]{12}\.json\.gz',p.name): items.append({'id':p.name[:-8],'name':'Local experiment '+p.name[:-8],'bundled':False})
                return self.send(200,items)
            if path.startswith('/api/recordings/'):
                ident=path.rsplit('/',1)[1]
                if ident=='bundled':
                    file=ROOT/'recordings/predator-pressure.json.gz'
                    manifest=json.loads((ROOT/'recordings/manifest.json').read_text())
                    if hashlib.sha256(file.read_bytes()).hexdigest()!=manifest['sha256']: raise ValueError('Bundled recording integrity check failed')
                elif re.fullmatch('[0-9a-f]{12}',ident): file=ROOT/'experiments/observatory'/(ident+'.json.gz')
                else: raise ValueError('Unknown recording')
                if file.is_symlink(): raise ValueError('Recording symlinks are not supported')
                return self.send(200,json.loads(gzip.decompress(file.read_bytes())))
            if path.startswith('/assets/'):
                root=ROOT/'assets'; rel=path[len('/assets/'):]
                if not (root/rel).is_file(): root=ROOT/'web/dist/assets'
            else:
                root=ROOT/'web/dist'; rel='index.html' if path=='/' else path.lstrip('/')
            file=(root/rel).resolve()
            if not file.is_relative_to(root.resolve()) or not file.is_file(): return self.send(404,{'error':'Not found'})
            return self.send(200,file.read_bytes(),mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        except PermissionError as exc: self.send(403,{'error':str(exc)})
        except (ValueError,OSError,KeyError) as exc: self.send(400,{'error':str(exc) if not isinstance(exc,OSError) else 'Local file unavailable'})

    def do_POST(self):
        try:
            self.trusted(True)
            parsed=urlparse(self.path); path=parsed.path
            length=int(self.headers.get('Content-Length','0'))
            if path=='/api/models/import': return self.import_model(length,parse_qs(parsed.query))
            if not 0<=length<=65536: raise ValueError('Request exceeds limit')
            data=json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(data,dict): raise ValueError('Expected JSON object')
            if path=='/api/heartbeat':
                self.server.last_heartbeat=time.monotonic(); return self.send(200,{'ok':True})
            if path=='/api/live':
                if not self.server.operation_lock.acquire(blocking=False): raise ValueError('Wait for the current model operation to finish')
                try:
                    if self.server.session and self.server.session.thread.is_alive(): raise ValueError('Stop the current experiment before starting another')
                    self.server.session=LiveSession(data)
                finally: self.server.operation_lock.release()
                return self.send(201,{'id':self.server.session.data['id']})
            if path=='/api/control':
                if not self.server.session or not self.server.session.thread.is_alive(): raise ValueError('No active experiment')
                self.server.session.control(data.get('action'))
                return self.send(200,{'status':self.server.session.data['status']})
            if path=='/api/models/test':
                if not self.server.operation_lock.acquire(blocking=False): raise ValueError('Model operation already in progress')
                try:
                    if self.server.session and self.server.session.thread.is_alive(): raise ValueError('Stop the experiment before testing a model')
                    with open_model(data) as backend:
                        self.server.validation_backend=backend
                        result=validate_backend(backend)
                    return self.send(200,result)
                finally:
                    self.server.validation_backend=None; self.server.operation_lock.release()
            if path=='/api/export':
                ident=data.get('id','')
                if self.server.session and self.server.session.data['id']==ident:
                    recording=self.server.session.snapshot()
                elif ident=='bundled': recording=json.loads(gzip.decompress((ROOT/'recordings/predator-pressure.json.gz').read_bytes()))
                elif re.fullmatch('[0-9a-f]{12}',ident):
                    recording=json.loads(gzip.decompress((ROOT/'experiments/observatory'/(ident+'.json.gz')).read_bytes()))
                else: raise ValueError('Recording not found')
                tick=data.get('tick',0)
                if type(tick) is not int or not 0<=tick<len(recording['frames']): raise ValueError('Invalid report tick')
                selected={**recording,'frames':recording['frames'][:tick+1],'report_tick':tick}
                folder=ROOT/'experiments/reports'/(ident+'-'+str(tick)+'-'+os.urandom(3).hex())
                folder.mkdir(parents=True)
                (folder/'recording.json').write_text(json.dumps(selected,indent=2))
                with (folder/'metrics.csv').open('w',newline='') as f:
                    writer=csv.DictWriter(f,fieldnames=['tick',*selected['frames'][0]['metrics']])
                    writer.writeheader()
                    for frame in selected['frames']: writer.writerow({'tick':frame['tick'],**frame['metrics']})
                report={'id':ident,'status':recording['status'],'condition':recording['condition'],
                        'mechanism':recording['mechanism'],'config':recording['config'],
                        'observed_through_tick':tick,'measurements':selected['frames'][-1]['metrics'],
                        'limitations':'Single-episode descriptive measurements. Not a validated biological model. Partial reports are not final outcomes.'}
                (folder/'report.json').write_text(json.dumps(report,indent=2))
                return self.send(201,{'directory':folder.relative_to(ROOT).as_posix()})
            if path=='/api/shutdown':
                self.send(200,{'ok':True})
                threading.Thread(target=self.server.shutdown,daemon=True).start(); return
            self.send(404,{'error':'Unknown operation'})
        except PermissionError as exc: self.send(403,{'error':str(exc)})
        except (ValueError,KeyError,TypeError) as exc: self.send(400,{'error':str(exc)})
        except Exception: self.send(400,{'error':'Local model operation failed. Check GGUF compatibility and installed llama.cpp runtime. Mechanistic and replay modes remain available.'})

    def import_model(self,length,query):
        if not 32<=length<=16*1024**3: raise ValueError('GGUF size must be between 32 bytes and 16 GiB')
        if length+256*1024**2>shutil.disk_usage(ROOT).free: raise ValueError('Insufficient project-volume disk space for model import')
        name=query.get('name',[''])[0]
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.gguf',name): raise ValueError('Use a short GGUF filename containing letters, digits, dots, underscores or hyphens')
        dest=model_path(name)
        if not self.server.operation_lock.acquire(blocking=False): raise ValueError('Another model operation is in progress')
        temp=ROOT/'tmp'/('import-'+os.urandom(6).hex()+'.gguf')
        try:
            if dest.exists(): raise ValueError('This filename is already in the model library; select it instead')
            digest=hashlib.sha256()
            with temp.open('xb') as f:
                remaining=length
                while remaining:
                    block=self.rfile.read(min(1024*1024,remaining))
                    if not block: raise ValueError('Incomplete upload')
                    f.write(block); digest.update(block); remaining-=len(block)
            info=metadata(temp)
            if not info['has_chat_template']: raise ValueError('Model has no embedded chat template')
            for existing in (ROOT/'models').glob('*.gguf'):
                if existing.is_symlink() or existing.stat().st_size!=length: continue
                other=hashlib.sha256()
                with existing.open('rb') as f:
                    for block in iter(lambda:f.read(1024*1024),b''): other.update(block)
                if other.digest()==digest.digest(): return self.send(200,{'file':existing.name,'duplicate':True})
            temp.replace(dest)
            return self.send(201,{'file':name,'sha256':digest.hexdigest()})
        finally:
            temp.unlink(missing_ok=True); self.server.operation_lock.release()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--open',action='store_true')
    parser.add_argument('--desktop',action='store_true')
    parser.add_argument('--ready-file')
    args=parser.parse_args()
    configure_local_environment()
    if not (ROOT/'web/dist/index.html').is_file(): raise SystemExit('Build the web app first: scripts/build_web.sh')
    server=ObservatoryServer(('127.0.0.1',args.port)); server.desktop=args.desktop
    url=f'http://127.0.0.1:{server.server_port}'
    if args.ready_file:
        ready=(ROOT/args.ready_file).resolve()
        if not ready.is_relative_to((ROOT/'tmp').resolve()): raise SystemExit('Ready file must be under tmp/')
        ready.write_text(json.dumps({'url':url,'pid':os.getpid()}))
    print('ProtoMind Lab: '+url,flush=True)
    def stop(*_): threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    if args.desktop:
        def watchdog():
            while time.monotonic()-server.last_heartbeat<20: time.sleep(2)
            server.shutdown()
        threading.Thread(target=watchdog,daemon=True).start()
    if args.open: webbrowser.open(url)
    try: server.serve_forever(poll_interval=.2)
    finally: server.server_close()

if __name__=='__main__': main()
