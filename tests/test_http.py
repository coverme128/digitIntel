import http.client
import json
import tempfile
import threading
import unittest
from usoe.server import AppServer
from usoe.storage import Store
from usoe.service import Service
from usoe.util import digest

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.service=Service(Store(cls.temp.name+'/demo.db'),demo=True);cls.service.seed_demo()
        cls.server=AppServer(('127.0.0.1',0),cls.service);cls.port=cls.server.server_port
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()
    def request(self,path,method='GET',body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10)
        h=headers or {};payload=json.dumps(body) if body is not None else None
        connection.request(method,path,payload,h);response=connection.getresponse();result=response.status,dict(response.getheaders()),response.read();connection.close();return result
    def session(self):
        status,headers,body=self.request('/api/v1/session');self.assertEqual(status,200)
        token=json.loads(body)['csrf_token'];return {'Cookie':headers['Set-Cookie'].split(';')[0],'X-CSRF-Token':token,'Origin':f'http://127.0.0.1:{self.port}','Content-Type':'application/json'}
    def test_static_and_csp(self):
        status,h,b=self.request('/');self.assertEqual(status,200);self.assertIn(b'USOE',b);self.assertIn("frame-ancestors 'none'",h['Content-Security-Policy']);self.assertNotIn('unsafe-inline',h['Content-Security-Policy'])
    def test_reads_require_session(self):self.assertEqual(self.request('/api/v1/portfolio')[0],401)
    def test_cross_origin_and_csrf_rejected(self):
        h=self.session();h['Origin']='https://evil.example';self.assertEqual(self.request('/api/v1/settings','POST',{'ai_mode':'assist'},h)[0],403)
        h=self.session();h['X-CSRF-Token']='wrong';self.assertEqual(self.request('/api/v1/settings','POST',{'ai_mode':'assist'},h)[0],403)
    def test_dns_rebinding_host_rejected(self):self.assertEqual(self.request('/',headers={'Host':'evil.example'})[0],403)
    def test_session_reused_for_multiple_tabs(self):
        h=self.session();status,headers,b=self.request('/api/v1/session',headers=h)
        self.assertEqual(status,200);self.assertNotIn('Set-Cookie',headers);self.assertEqual(json.loads(b)['csrf_token'],h['X-CSRF-Token'])
    def test_json_export_hash_and_filters(self):
        h=self.session();status,headers,b=self.request('/api/v1/opportunities/opp-nova-d/export?format=json',headers=h)
        self.assertEqual(status,200);e=json.loads(b);self.assertEqual(e['core_output_hash'],digest(e['payload']))
        status,_,b=self.request('/api/v1/opportunities/export?format=json&state=READY&q=NOVA',headers=h);self.assertEqual(status,200);self.assertEqual(len(json.loads(b)['payload']['items']),1)
    def test_all_routes(self):
        h=self.session()
        for path in ('today','portfolio','history','opportunities','securities','review-queue','audit','outcomes','performance','events','status','order-intents'):
            with self.subTest(path=path):self.assertEqual(self.request('/api/v1/'+path,headers=h)[0],200)
    def test_all_export_formats_and_scopes(self):
        h=self.session()
        for scope in ('today','opportunities','watchlist','portfolio','outcomes','performance','events'):
            for fmt in ('json','markdown','csv'):
                with self.subTest(scope=scope,format=fmt):
                    status,headers,body=self.request(f'/api/v1/{scope}/export?format={fmt}',headers=h)
                    self.assertEqual(status,200);self.assertIn('attachment',headers['Content-Disposition']);self.assertGreater(len(body),20)
    def test_bad_format_and_missing_id(self):
        h=self.session();self.assertEqual(self.request('/api/v1/portfolio/export?format=exe',headers=h)[0],400);self.assertEqual(self.request('/api/v1/opportunities/missing',headers=h)[0],404)
    def test_ai_parity_via_http(self):
        h=self.session();_,_,a=self.request('/api/v1/opportunities/opp-nova-d/export',headers=h)
        self.assertEqual(self.request('/api/v1/settings','POST',{'ai_mode':'assist'},h)[0],200)
        _,_,b=self.request('/api/v1/opportunities/opp-nova-d/export',headers=h)
        self.assertEqual(json.loads(a)['core_output_hash'],json.loads(b)['core_output_hash'])
    def test_path_traversal_not_served(self):self.assertEqual(self.request('/../.env')[0],404)
