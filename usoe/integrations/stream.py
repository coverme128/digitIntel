"""Massive AM/Q websocket receiver. REST remains the authoritative recovery path."""
import json
import os
import ssl
import threading
from collections import OrderedDict
from .market import symbol,validate_bar,stamp
from ..util import dt,utcnow,number,DomainError
from ..sources import SourceUnavailable

class MarketStream:
    def __init__(self,key,symbols,mode='delayed',connector=None,on_recovery=None,clock=utcnow):
        if not key:raise DomainError('Configure MASSIVE_API_KEY','SOURCE_NOT_CONFIGURED',409)
        if mode not in ('realtime','delayed'):raise DomainError('Invalid streaming mode')
        self.key=key;self.symbols=sorted(set(symbol(s) for s in symbols))
        if not 1<=len(self.symbols)<=100:raise DomainError('Subscribe 1–100 symbols')
        self.mode=mode;self.connector=connector;self.clock=clock;self.on_recovery=on_recovery
        self.bars={s:OrderedDict() for s in self.symbols};self.quotes={};self.lock=threading.RLock()
        self.state='STOPPED';self.gap=True;self.last_message=None;self.error=None;self.stop_event=threading.Event();self.thread=None;self.socket=None

    def status(self):
        with self.lock:
            age=(dt(self.clock())-dt(self.last_message)).total_seconds() if self.last_message else None
            return {'state':self.state,'mode':self.mode,'symbols':self.symbols,'recovery_required':self.gap,'last_message':self.last_message,'stale':age is None or age>90,'error':self.error,'note':'Streaming observations only; REST recovery and complete snapshots required for decisions.'}

    def consume(self,message):
        try:events=json.loads(message)
        except (ValueError,TypeError):raise SourceUnavailable('Invalid stream JSON') from None
        if not isinstance(events,list):raise SourceUnavailable('Invalid stream envelope')
        with self.lock:
            for r in events:
                kind=r.get('ev')
                if kind=='status':
                    if r.get('status') in ('auth_failed','error'):raise SourceUnavailable('Stream authentication / subscription rejected')
                    continue
                s=r.get('sym')
                if s not in self.bars:continue
                if kind=='AM':
                    b={k:r[k] for k in ('o','h','l','c','v')};b.update(t=r['s'],vw=r.get('vw'))
                    validate_bar(b)
                    if b['t']%60000 or not b['t']<r['e']<=b['t']+60000:raise SourceUnavailable('Invalid minute aggregate interval')
                    # Provider corrections replace the same minute. No volume double counting.
                    self.bars[s][b['t']]=b;self.bars[s]=OrderedDict(sorted(self.bars[s].items()))
                    while len(self.bars[s])>2000:self.bars[s].popitem(last=False)
                elif kind=='Q':
                    bid=number(r['bp'],'bid',True);ask=number(r['ap'],'ask',True);at=stamp(number(r['t']))
                    if ask<bid:raise SourceUnavailable('Crossed stream quote')
                    old=self.quotes.get(s)
                    if old and dt(at)<dt(old['at']):continue
                    # q sequence is not contiguous; never infer a gap from q+1.
                    self.quotes[s]={'ticker':s,'bid':bid,'ask':ask,'at':at,'sequence':r.get('q')}
            self.last_message=self.clock()

    def run_connection(self,ws):
        with self.lock:self.state='AUTHENTICATING';self.gap=True
        ws.send(json.dumps({'action':'auth','params':self.key}))
        authenticated=False
        for _ in range(10):
            message=ws.recv(timeout=20);self.consume(message)
            if any(r.get('status')=='auth_success' for r in json.loads(message)):
                authenticated=True;break
        if not authenticated:raise SourceUnavailable('Stream authentication not acknowledged')
        ws.send(json.dumps({'action':'subscribe','params':','.join(f'{kind}.{s}' for s in self.symbols for kind in ('AM','Q'))}))
        with self.lock:self.state='RECOVERING'
        # The callback must actually fetch REST windows. No callback => gap remains blocked.
        recovered=self.on_recovery(self.symbols) is True if self.on_recovery else False
        with self.lock:self.gap=not recovered;self.state='CONNECTED';self.error=None
        while not self.stop_event.is_set():self.consume(ws.recv(timeout=60))

    def _run(self):
        delay=1
        while not self.stop_event.is_set():
            try:
                connector=self.connector
                if connector is None:
                    from websockets.sync.client import connect
                    connector=connect
                host='socket.massive.com' if self.mode=='realtime' else 'delayed.massive.com'
                context=ssl.create_default_context(cafile=os.environ.get('USOE_CA_BUNDLE') or None)
                with connector(f'wss://{host}/stocks',ssl=context,open_timeout=20,ping_interval=20,ping_timeout=20,max_size=4*1024*1024) as ws:
                    self.socket=ws;self.run_connection(ws)
                delay=1
            except Exception:
                with self.lock:self.state='DISCONNECTED';self.gap=True;self.error='Stream disconnected; REST recovery required'
                if self.stop_event.wait(delay):break
                delay=min(delay*2,30)
            finally:self.socket=None
        with self.lock:self.state='STOPPED';self.gap=True

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.stop_event.clear();self.thread=threading.Thread(target=self._run,name='massive-stream',daemon=True);self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.socket:self.socket.close()
        if self.thread:self.thread.join(timeout=3)
