from __future__ import annotations
import json
import mimetypes
import re
import secrets
import os
import traceback
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import urlparse,parse_qs
from .util import ROOT,canonical,DomainError,utcnow
from .exports import markdown,csv_export
from .sources import Sources,SourceUnavailable
from .integrations.service import Integrations
from .integrations.orders import BrokerOrders

class AppServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,service):
        self.service=service;self.sources=Sources(service);self.sessions={};self.integrations=Integrations(service);self.broker_orders=BrokerOrders(self.integrations)
        super().__init__(address,Handler)

class Handler(BaseHTTPRequestHandler):
    server_version='USOE/1.0.2'
    def log_message(self,format,*args):pass

    def respond(self,status,payload,ctype='application/json; charset=utf-8',headers=None):
        if isinstance(payload,(dict,list)):payload=canonical(payload).encode()
        elif isinstance(payload,str):payload=payload.encode()
        self.send_response(status)
        self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(payload)))
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Cache-Control','no-store');self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(payload)

    def error(self,error):
        if isinstance(error,DomainError):self.respond(error.status,{'error':str(error),'code':error.code})
        elif isinstance(error,SourceUnavailable):self.respond(502,{'error':str(error),'code':'SOURCE_DEGRADED'})
        elif isinstance(error,(KeyError,ValueError,TypeError)):self.respond(400,{'error':'Invalid request: '+str(error),'code':'VALIDATION_ERROR'})
        else:
            print(canonical({'at':utcnow(),'level':'ERROR','event':'request_failed','type':type(error).__name__}),flush=True)
            self.respond(500,{'error':'Internal error; operation rolled back','code':'INTERNAL_ERROR'})

    def host_check(self):
        allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}',f'[::1]:{self.server.server_port}'}
        if self.headers.get('Host') not in allowed:raise DomainError('Invalid Host','FORBIDDEN',403)

    def session(self):
        cookies=SimpleCookie();cookies.load(self.headers.get('Cookie',''))
        sid=cookies.get(f'usoe_session_{self.server.server_port}');return self.server.sessions.get(sid.value) if sid else None

    def do_GET(self):
        try:
            self.host_check();self.get()
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as exc:self.error(exc)

    def do_POST(self):
        try:
            self.host_check()
            origin=self.headers.get('Origin');host=self.headers['Host']
            session=self.session()
            if origin!=f'http://{host}' or not session or not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),session):raise DomainError('Same-origin session and CSRF token required','FORBIDDEN',403)
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise DomainError('JSON Content-Type required')
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>2*1024*1024:raise DomainError('Request body size invalid')
            body=json.loads(self.rfile.read(size))
            if not isinstance(body,dict):raise DomainError('JSON object required')
            self.post(body)
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as exc:self.error(exc)

    def get(self):
        s=self.server.service;parsed=urlparse(self.path);path=parsed.path;query={k:v[-1] for k,v in parse_qs(parsed.query).items()}
        if path=='/api/v1/session':
            existing=self.session()
            if existing:return self.respond(200,{'csrf_token':existing})
            if len(self.server.sessions)>1000:self.server.sessions.clear()
            sid=secrets.token_urlsafe(32);token=secrets.token_urlsafe(32);self.server.sessions[sid]=token
            return self.respond(200,{'csrf_token':token},headers={'Set-Cookie':f'usoe_session_{self.server.server_port}={sid}; HttpOnly; SameSite=Strict; Path=/'})
        if path.startswith('/api/') and not self.session():raise DomainError('Local session required','UNAUTHORIZED',401)
        if path=='/api/v1/integrations':return self.respond(200,self.server.integrations.status())
        if path=='/api/v1/broker/orders':return self.respond(200,{'items':self.server.broker_orders.list()})
        if path=='/api/v1/status':return self.respond(200,s.status())
        if path=='/api/v1/securities':return self.respond(200,s.store.query('SELECT * FROM securities ORDER BY ticker'))
        if path=='/api/v1/review-queue':return self.respond(200,[dict(r,data=json.loads(r['data_json'])) for r in s.store.query('SELECT * FROM review_queue ORDER BY created_at DESC')])
        if path=='/api/v1/audit':return self.respond(200,{'integrity':s.store.verify_audit(),'items':s.store.query('SELECT * FROM audit ORDER BY id DESC LIMIT 200')})
        if path=='/api/v1/order-intents':return self.respond(200,[json.loads(r['data_json'])|{'status':r['status']} for r in s.store.query('SELECT * FROM order_intents ORDER BY created_at DESC')])
        if path=='/api/v1/events':return self.respond(200,[json.loads(r['snapshot_json']) for r in s.store.query('SELECT * FROM events ORDER BY event_at DESC')])
        if path=='/api/v1/opportunities':return self.respond(200,{'items':s.list(query)})
        if path=='/api/v1/today':
            items=s.list();return self.respond(200,{'opportunities':[c for c in items if c['state']=='WATCH'],'ready':[c for c in items if c['state']=='READY'],'position_attention':[c for c in items if c['role']=='POSITION_RISK' or (c['state']=='INVALIDATED' and c['outcome'])],'invalidated':[c for c in items if c['state']=='INVALIDATED'],'filtered_event_count':sum(c['state'] in ('DISCOVERED','VERIFIED','IGNORED') for c in items),'as_of':s.now()})
        if path=='/api/v1/portfolio':return self.respond(200,{'snapshot':s.portfolio(),'attention':[c for c in s.list() if c['role']=='POSITION_RISK' or c['state']=='INVALIDATED']})
        if path=='/api/v1/history':return self.respond(200,{'items':[c for c in s.list() if c['state'] in ('EXITED','INVALIDATED','IGNORED')],'outcomes':s.outcomes(),'family_performance':s.performance()})
        if path=='/api/v1/outcomes':return self.respond(200,{'items':s.outcomes()})
        if path=='/api/v1/performance':return self.respond(200,{'items':s.performance()})
        match=re.fullmatch(r'/api/v1/opportunities/([\w-]+)(/export|/replay)?',path)
        if match and match[1]!='export':
            if match[2]=='/replay':return self.respond(200,s.replay(match[1]))
            c=s.get(match[1])
            if match[2]=='/export':return self.send_export(s.export(c),query,c['ticker'])
            return self.respond(200,c)
        if path.endswith('/export'):
            scope=path.split('/')[-2]
            if scope=='opportunities':payload={'items':s.list(query)}
            elif scope=='watchlist':payload={'items':[c for c in s.list(query) if c['state'] in ('WATCH','READY','INVALIDATED')]}
            elif scope=='today':payload={'items':[c for c in s.list(query) if c['state'] in ('WATCH','READY')]}
            elif scope=='portfolio':payload={'portfolio_snapshot':s.portfolio(),'items':s.portfolio()['positions']}
            elif scope=='outcomes':payload={'items':s.outcomes()}
            elif scope=='performance':payload={'items':s.performance()}
            elif scope=='events':payload={'items':[json.loads(r['snapshot_json']) for r in s.store.query('SELECT * FROM events')]}
            else:raise DomainError('Unknown export scope','NOT_FOUND',404)
            payload['is_demo']=s.demo
            return self.send_export(s.export(payload),query,scope)
        match=re.fullmatch(r'/api/v1/evidence/([\w-]+)/raw',path)
        if match:
            rows=s.store.query('SELECT * FROM raw_documents WHERE id=?',(match[1],))
            if not rows:raise DomainError('Raw evidence not found','NOT_FOUND',404)
            return self.respond(200,bytes(rows[0]['content']),'text/plain; charset=utf-8')
        if path=='/metrics':
            if not self.session():raise DomainError('Session required','UNAUTHORIZED',401)
            counts={r['state']:r['n'] for r in s.store.query('SELECT state,count(*) n FROM opportunities GROUP BY state')}
            body='\n'.join(f'usoe_opportunities{{state="{k}"}} {v}' for k,v in counts.items())+'\n'
            body+=f'usoe_audit_integrity {int(s.store.verify_audit()["valid"])}\n'
            body+=f'usoe_review_queue {len(s.store.query("SELECT id FROM review_queue WHERE status=\'REVIEW_REQUIRED\'"))}\n'
            for row in s.store.query('SELECT * FROM sources'):body+=f'usoe_source_healthy{{source="{row["id"]}"}} {int(row["state"]=="HEALTHY")}\n'
            return self.respond(200,body,'text/plain; version=0.0.4')
        if path in ('/','/index.html','/app.js','/style.css','/favicon.svg'):
            p=ROOT/'web'/('index.html' if path=='/' else path.lstrip('/'))
            return self.respond(200,p.read_bytes(),(mimetypes.guess_type(str(p))[0] or 'application/octet-stream')+'; charset=utf-8')
        raise DomainError('Not found','NOT_FOUND',404)

    def send_export(self,data,query,name):
        fmt=query.get('format','json')
        if fmt=='json':body=canonical(data);ctype='application/json';ext='json'
        elif fmt=='markdown':body=markdown(data);ctype='text/markdown';ext='md'
        elif fmt=='csv':body=csv_export(data);ctype='text/csv';ext='csv'
        else:raise DomainError('format must be json, markdown, or csv')
        self.respond(200,body,ctype+'; charset=utf-8',{'Content-Disposition':f'attachment; filename="usoe-{name}.{ext}"'})

    def post(self,body):
        s=self.server.service;path=urlparse(self.path).path;key=self.headers.get('Idempotency-Key')
        if path=='/api/v1/settings':
            mode=body.get('ai_mode')
            if mode not in ('off','assist'):raise DomainError('AI mode must be off or assist')
            with s.store.transaction() as db:
                Store=type(s.store);Store.set_setting(db,'ai_mode',mode);Store.audit(db,'AI_MODE_CHANGED','settings',{'mode':mode})
            return self.respond(200,s.status())
        if path=='/api/v1/securities':return self.respond(201,s.register(body['security'],body.get('universe','USER_WATCHLIST'),body.get('valid_from')))
        if path=='/api/v1/import':return self.respond(201,s.ingest(body['event'],body['market_snapshot']))
        if path=='/api/v1/sources/sec/sync':return self.respond(200,self.server.sources.sec_sync(body['security_id'],body.get('limit',5)))
        if path=='/api/v1/sources/massive/bars':return self.respond(200,self.server.integrations.bars(body))
        if path=='/api/v1/sources/ibkr/sync':return self.respond(200,self.server.integrations.sync_broker())
        if path=='/api/v1/integrations/self-test':return self.respond(200,self.server.integrations.offline_check())
        if path=='/api/v1/market/calculate':return self.respond(200,self.server.integrations.calculate_market(body))
        if path=='/api/v1/market/outcomes':return self.respond(200,self.server.integrations.calculate_outcome(body))
        if path=='/api/v1/broker/contracts/search':return self.respond(200,self.server.integrations.broker().candidates(body['symbol']))
        if path=='/api/v1/broker/contracts/map':return self.respond(200,self.server.integrations.map_contract(body))
        if path=='/api/v1/broker/position-plan':return self.respond(200,self.server.integrations.position_plan(body))
        if path=='/api/v1/broker/keepalive':return self.respond(200,self.server.integrations.broker().keepalive())
        if path=='/api/v1/broker/orders':return self.respond(201,self.server.broker_orders.create(body,key))
        match=re.fullmatch(r'/api/v1/broker/orders/([\w-]+)/(preview|submit|reply|cancel|abandon)',path)
        if match:return self.respond(200,self.server.broker_orders.act(match[1],match[2],body))
        match=re.fullmatch(r'/api/v1/opportunities/([\w-]+)/market-sync',path)
        if match:return self.respond(200,self.server.integrations.refresh_market(match[1]))
        if path=='/api/v1/order-intents':return self.respond(201,s.create_intent(body,key))
        match=re.fullmatch(r'/api/v1/opportunities/([\w-]+)/(watch|ignore|refresh)',path)
        if match:return self.respond(200,s.refresh(match[1],body.get('market_snapshot')) if match[2]=='refresh' else s.action(match[1],match[2]))
        match=re.fullmatch(r'/api/v1/order-intents/([\w-]+)/(confirm|cancel)',path)
        if match:return self.respond(200,s.confirm_intent(match[1],body,key) if match[2]=='confirm' else s.cancel_intent(match[1]))
        match=re.fullmatch(r'/api/v1/positions/([\w-]+)/exit-intent',path)
        if match:return self.respond(201,s.exit_intent(match[1],body,key))
        match=re.fullmatch(r'/api/v1/exit-intents/([\w-]+)/confirm',path)
        if match:return self.respond(200,s.confirm_exit(match[1],body,key))
        raise DomainError('Not found','NOT_FOUND',404)
