"""Opt-in loopback API tests: PROTOMIND_HTTP_TEST=1 ./scripts/run_tests.sh."""
import json
import os
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from protomind.server import ObservatoryServer

@unittest.skipUnless(os.environ.get('PROTOMIND_HTTP_TEST')=='1','requires loopback socket permission')
class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ObservatoryServer(('127.0.0.1',0));cls.url='http://127.0.0.1:'+str(cls.server.server_port)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(3)
    def get(self,path):
        with urlopen(self.url+path,timeout=3) as r:return r.status,json.load(r)
    def post(self,path,data,headers=None):
        req=Request(self.url+path,data=json.dumps(data).encode(),headers=headers or {'X-ProtoMind':'observatory','Content-Type':'application/json'})
        with urlopen(req,timeout=3) as r:return r.status,json.load(r)
    def test_replay_and_static_assets_no_model(self):
        self.assertEqual(self.get('/api/recordings/bundled')[1]['mechanism'],'mechanistic')
        for path in ('/','/assets/synthetic-atlas.png','/assets/icon.svg'):
            with urlopen(self.url+path) as r:
                self.assertEqual(r.status,200)
                self.assertIn("connect-src 'self'",r.headers['Content-Security-Policy'])
    def test_cross_origin_and_missing_header_blocked(self):
        for headers in ({'Origin':'https://untrusted.example','X-ProtoMind':'observatory'},{'Content-Type':'application/json'}):
            with self.assertRaises(HTTPError) as ctx:self.post('/api/live',{},headers)
            self.assertEqual(ctx.exception.code,403)
    def test_host_and_file_traversal_blocked(self):
        req=Request(self.url+'/api/health',headers={'Host':'untrusted.example'})
        with self.assertRaises(HTTPError) as ctx:urlopen(req)
        self.assertEqual(ctx.exception.code,403)
        with self.assertRaises(HTTPError):urlopen(self.url+'/assets/../../.env')
    def test_reports_saved_under_project(self):
        status,result=self.post('/api/export',{'id':'bundled','tick':12})
        self.assertEqual(status,201);self.assertTrue(result['directory'].startswith('experiments/reports/'))
    def test_invalid_request_and_model_import_rejected(self):
        with self.assertRaises(HTTPError):self.post('/api/live',{'config':{'prey_count':101}})
        req=Request(self.url+'/api/models/import?name=invalid.gguf',data=b'not a model'*5,headers={'X-ProtoMind':'observatory'})
        with self.assertRaises(HTTPError) as ctx:urlopen(req)
        self.assertEqual(ctx.exception.code,400)
