"""Application boundary for account-independent calculations and configured adapters."""
import json
import os
import threading
from copy import deepcopy
from datetime import timedelta
from ..util import ROOT,canonical,digest,dt,utcnow,DomainError,number
from ..storage import Store
from ..sources import Sources,SourceUnavailable
from ..calendar import exchange_calendar
from ..engine import FAMILIES
from .market import MassiveClient,build_snapshot,split_adjust,outcome_statistics,ET
from .broker import IBKRClient,positive_int

class Integrations:
    def __init__(self,service,massive=None,broker=None,calendar=exchange_calendar):
        self.service=service;self.store=service.store;self._massive=massive;self._broker=broker;self.calendar=calendar
        self.sources=Sources(service);self.stream=None;self.operation_lock=threading.RLock()

    def archive(self,source,path,payload):
        with self.store.transaction() as db:
            rid,_=Store.raw(db,source,path,canonical(payload),utcnow(),('https://api.massive.com' if source=='massive' else 'ibkr://sanitized')+path)
            return rid

    def massive(self):
        if self._massive is None:self._massive=MassiveClient(os.environ.get('MASSIVE_API_KEY'),archive=self.archive)
        return self._massive

    def broker(self):
        if self._broker is None:self._broker=IBKRClient(os.environ.get('IBKR_ACCOUNT_ID'),os.environ.get('IBKR_BASE_URL','https://localhost:5000/v1/api'),archive=self.archive,paper_enabled=os.environ.get('IBKR_PAPER_ENABLED')=='true')
        return self._broker

    def shadow(self):
        if self.service.demo:raise DomainError('Use a separate shadow workspace for real source data','WORKSPACE_MISMATCH',409)

    def status(self):
        from importlib.util import find_spec
        return {'version':'integrations-2','massive':{'configured':bool(self._massive or os.environ.get('MASSIVE_API_KEY')),'data_mode':os.environ.get('MASSIVE_DATA_MODE','historical'),'rest':'IMPLEMENTED','websocket':'IMPLEMENTED','stream':self.stream.status() if self.stream else {'state':'STOPPED'},'live_verified':False},'ibkr':{'configured':bool(self._broker or os.environ.get('IBKR_ACCOUNT_ID')),'paper_enabled':os.environ.get('IBKR_PAPER_ENABLED')=='true','live_trading':False,'live_verified':False,'adapter':'IMPLEMENTED','portfolio_snapshot':self.store.setting('portfolio_snapshot_id')},'dependencies':{'exchange_calendars':find_spec('exchange_calendars') is not None,'websockets':find_spec('websockets') is not None},'last_offline_check':self.store.setting('integration_selftest'),'note':'Implemented adapters do not imply account connectivity or data entitlement. No credentials are returned.'}

    def security(self,identity):
        rows=self.store.query('SELECT data_json FROM securities WHERE id=?',(identity,))
        if not rows:raise DomainError('Register security first','NOT_FOUND',404)
        return json.loads(rows[0]['data_json'])

    def bars(self,body):
        try:
            result=self.massive().bars(body['symbol'],body['start'],body['end'],body.get('timespan','minute'),adjusted=False)
            self.sources._state('massive','HEALTHY')
            return result|{'note':'Raw unadjusted historical bars; not a realtime decision snapshot.','sha256':digest(result)}
        except (SourceUnavailable,DomainError) as e:
            self.sources._state('massive','NOT_CONFIGURED' if getattr(e,'code','')=='SOURCE_NOT_CONFIGURED' else 'DEGRADED',str(e));raise

    def calculate_market(self,body):
        try:return self._calculate_market(body)
        except (SourceUnavailable,DomainError,ValueError,KeyError,TypeError) as e:
            self.sources._state('massive','NOT_CONFIGURED' if getattr(e,'code','')=='SOURCE_NOT_CONFIGURED' else 'DEGRADED','Market calculation failed; complete source window required')
            raise

    def _calculate_market(self,body):
        self.shadow();security=self.security(body['security_id']);event_at=body['event_at'];as_of=body.get('as_of') or self.service.now()
        event,now=dt(event_at),dt(as_of)
        if now<event or now>dt(self.service.now())+timedelta(seconds=5):raise DomainError('Invalid market observation time')
        if (now-event).days>365:raise DomainError('Market event range exceeds one year')
        sector=json.loads((ROOT/'config/sector-etfs.json').read_text()).get(security['sector'])
        if not sector:raise DomainError('Explicit supported sector mapping required','SECTOR_MAPPING_REQUIRED',409)
        family=body.get('event_family','GUIDANCE_CHANGE')
        if family not in FAMILIES:raise DomainError('Unknown event family')
        start=(event.astimezone(ET).date()-timedelta(days=90)).isoformat();end=now.astimezone(ET).date().isoformat()
        cal=self.calendar(start,(now.astimezone(ET).date()+timedelta(days=10)).isoformat())
        mode=os.environ.get('MASSIVE_DATA_MODE','historical')
        # Explicit historical observation must never inherit realtime entitlement mode.
        if (dt(self.service.now())-now).total_seconds()>300:mode='historical'
        client=self.massive();series={};actions={};action_refs=[]
        for name,ticker in [('security',security['ticker']),('spy','SPY'),('sector',sector)]:
            series[name]=client.bars(ticker,start,end,adjusted=False)
            splits=client.splits(ticker,start,end);actions[name]=splits['results'];action_refs.extend(splits['raw_refs'])
        quote=None;quote_error=None
        if mode in ('realtime','delayed'):
            try:quote=client.quote(security['ticker'])
            except SourceUnavailable as e:quote_error=str(e)
        result=build_snapshot(security['ticker'],event_at,as_of,series,cal,quote,mode,family,actions,cluster_start=body.get('cluster_start'))
        result['raw_refs']=sorted(set(result['raw_refs']+action_refs+([quote['raw_ref']] if quote and quote.get('raw_ref') else [])))
        if quote_error:result['quote_error']=quote_error
        result.pop('snapshot_id',None);result['snapshot_id']='market-'+digest(result)[:24]
        with self.store.transaction() as db:
            self.service._put_snapshot(db,'market_snapshots',result)
            Store.audit(db,'MARKET_CALCULATED',result['snapshot_id'],{'complete':result['complete'],'errors':result['quality_errors']})
        self.sources._state('massive','HEALTHY' if result['complete'] else 'DEGRADED',None if result['complete'] else ', '.join(result['quality_errors']))
        return result

    def refresh_market(self,identity):
        self.shadow();core=self.service.get(identity)
        body={'security_id':core['security_id'],'event_at':core['event_at'],'event_family':core['event_family']}
        # Only archived qualifying transaction dates can supply the insider cluster window.
        rows=self.store.query('SELECT snapshot_json FROM events WHERE id=?',(core['event_id'],))
        packet=json.loads(rows[0]['snapshot_json']);transactions=packet.get('insider_transactions',[])
        evidence_ids={e['evidence_id'] for e in packet.get('evidence',[])}
        dates=[dt(t['at']).astimezone(ET).date().isoformat() for t in transactions if t.get('code')=='P' and t.get('acquired_disposed')=='A' and t.get('derivative') is False and t.get('evidence_id') in evidence_ids and t.get('at') and 0<=(dt(packet['event_at'])-dt(t['at'])).total_seconds()<=10*86400]
        if dates:body['cluster_start']=min(dates)
        try:market=self.calculate_market(body)
        except (SourceUnavailable,DomainError) as e:
            self.sources._state('massive','DEGRADED',str(e))
            # Invalidate previously fresh eligibility immediately after a failed refresh.
            market=deepcopy(core['market_snapshot']);market.update(complete=False,captured_at=self.service.now(),quality_errors=['DATA_SOURCE_REFRESH_FAILED'],is_demo=False)
            market.pop('snapshot_id',None);market['snapshot_id']='market-'+digest(market)[:24]
            self.service.refresh(identity,market);raise
        return self.service.refresh(identity,market)

    def sync_broker(self):
        self.shadow()
        with self.operation_lock:
            try:
                securities=[json.loads(r['data_json']) for r in self.store.query('SELECT data_json FROM securities')]
                bundle=self.broker().snapshot(securities,self.store.setting('broker_position_plans',{}),self.service.now())
                self.service.save_portfolio(bundle['portfolio'])
                with self.store.transaction() as db:Store.set_setting(db,'broker_last_bundle',bundle)
                self.sources._state('ibkr','HEALTHY' if bundle['portfolio']['reconciled'] else 'DEGRADED',None if bundle['portfolio']['reconciled'] else ', '.join(bundle['portfolio']['hard_blocks']))
                from .orders import BrokerOrders
                BrokerOrders(self).reconcile_all(bundle)
            except (SourceUnavailable,DomainError,ValueError,KeyError,TypeError) as e:
                p=self.service.portfolio();p.update(reconciled=False,captured_at=self.service.now(),hard_blocks=['RISK_BROKER_SYNC_FAILED'],is_demo=False)
                p.pop('snapshot_id',None);p['snapshot_id']='portfolio-'+digest(p)[:24];self.service.save_portfolio(p)
                self.sources._state('ibkr','NOT_CONFIGURED' if getattr(e,'code','')=='SOURCE_NOT_CONFIGURED' else 'DEGRADED','Account sync failed; prior eligibility invalidated')
                self._refresh_portfolio();raise
            self._refresh_portfolio();return bundle

    def _refresh_portfolio(self):
        for row in self.store.query("SELECT id FROM opportunities WHERE state NOT IN ('EXITED','IGNORED')"):
            self.service.refresh(row['id'])

    def invalidate_portfolio(self,reason):
        p=self.service.portfolio();p.update(reconciled=False,captured_at=self.service.now(),hard_blocks=[reason],is_demo=False)
        p.pop('snapshot_id',None);p['snapshot_id']='portfolio-'+digest(p)[:24]
        self.service.save_portfolio(p);self._refresh_portfolio()

    def map_contract(self,body):
        self.shadow();s=self.security(body['security_id']);conid=positive_int(body['conid'],'conid');info=self.broker().contract(conid)
        if (info.get('symbol') or info.get('ticker'))!=s['ticker'] or info.get('currency')!='USD' or (info.get('secType') or info.get('instrument_type'))!='STK':raise DomainError('Broker contract does not match USD stock','BROKER_SECURITY_MISMATCH',409)
        for row in self.store.query('SELECT id,data_json FROM securities WHERE id<>?',(s['security_id'],)):
            if json.loads(row['data_json']).get('ibkr_conid')==conid:raise DomainError('Conid already mapped')
        s['ibkr_conid']=conid;s['ibkr_contract_verified_at']=self.service.now()
        with self.store.transaction() as db:
            db.execute('UPDATE securities SET data_json=? WHERE id=?',(canonical(s),s['security_id']))
            Store.audit(db,'BROKER_SECURITY_MAPPED',s['security_id'],{'conid':conid,'verified_contract':info})
        self.invalidate_portfolio('RISK_MAPPING_CHANGED_RESYNC_REQUIRED')
        return s

    def position_plan(self,body):
        self.shadow();s=self.security(body['security_id']);number(body['invalidation_price'],'invalidation_price',True)
        if body.get('event_family') not in FAMILIES:raise DomainError('Known event family required')
        plans=self.store.setting('broker_position_plans',{});plans[s['security_id']]={'event_family':body['event_family'],'invalidation_price':body['invalidation_price'],'recorded_at':self.service.now()}
        with self.store.transaction() as db:
            Store.set_setting(db,'broker_position_plans',plans);Store.audit(db,'BROKER_POSITION_PLAN',s['security_id'],plans[s['security_id']])
        self.invalidate_portfolio('RISK_PLAN_CHANGED_RESYNC_REQUIRED')
        return {'saved':True,'requires_broker_resync':True}

    def calculate_outcome(self,body):
        self.shadow();s=self.security(body['security_id']);start=dt(body['entry_at']).astimezone(ET).date().isoformat();as_of=body.get('as_of') or self.service.now();end=dt(as_of).astimezone(ET).date().isoformat()
        if dt(as_of)>dt(self.service.now()):raise DomainError('Future outcome observation')
        cal=self.calendar(start,end);client=self.massive();series={};refs=[]
        for name,ticker in [('stock',s['ticker']),('benchmark','SPY')]:
            raw=client.bars(ticker,start,end,timespan='day',adjusted=False);actions=client.splits(ticker,start,end)
            series[name],_=split_adjust(raw['bars'],actions['results'],as_of);refs+=raw['raw_refs']+actions['raw_refs']
        # Caller provides prices/quantity on the same split-adjusted basis; explicit basis required.
        if body.get('price_basis')!='split_adjusted_as_of':raise DomainError('Declare split_adjusted_as_of price basis')
        result=outcome_statistics(body['entry_price'],body['entry_at'],as_of,series['stock'],series['benchmark'],cal,body.get('quantity',1),body.get('exit_price'),body.get('fees',0),body.get('planned_loss'),body.get('planned_entry'))
        result.update(raw_refs=refs,calculation_version='outcome-2',price_basis='split_adjusted_as_of',return_basis='price return; excludes dividends',as_of=as_of)
        inputs=body|{'as_of':as_of,'series':series,'calendar':cal};identity=digest([inputs,result])
        with self.store.transaction() as db:db.execute('INSERT OR IGNORE INTO integration_calculations VALUES (?,?,?,?,?)',(identity,'OUTCOME',canonical(inputs),canonical(result),utcnow()))
        return result|{'calculation_id':identity}

    def offline_check(self):
        from .selftest import run
        result=run()
        with self.store.transaction() as db:Store.set_setting(db,'integration_selftest',result)
        return result
