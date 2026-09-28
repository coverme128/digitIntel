from __future__ import annotations
import json
import uuid
from copy import deepcopy
from datetime import timedelta
from .util import canonical,digest,utcnow,dt,number,money,read_rules,DomainError
from .storage import Store
from .engine import evaluate,allowed_transition,risk_worksheet,FAMILIES
from .exports import envelope,core_only
from .validation import validate_fact,json_pointer

class Service:
    def __init__(self,store,demo=False,clock=None):
        self.store=store; self.demo=demo; self.rules=read_rules(); self.clock=clock or utcnow

    def now(self):
        return self.store.setting('demo_as_of',self.clock()) if self.demo else self.clock()

    def seed_demo(self):
        from .demo import fixtures,portfolio,AS_OF
        if self.store.query('SELECT id FROM events LIMIT 1'): return
        with self.store.transaction() as db:
            Store.set_setting(db,'demo_as_of',AS_OF)
        self.save_portfolio(portfolio())
        for p,m in fixtures(): self.ingest(p,m)

    def save_portfolio(self,p):
        if bool(p.get('is_demo'))!=self.demo: raise DomainError('Demo and real data cannot mix')
        for k in ('equity','cash','buying_power'):
            if p.get(k) is not None: number(p[k],k)
        dt(p['captured_at'])
        with self.store.transaction() as db:
            self._put_snapshot(db,'portfolio_snapshots',p)
            Store.set_setting(db,'portfolio_snapshot_id',p['snapshot_id'])
            Store.audit(db,'PORTFOLIO_SNAPSHOT',p['snapshot_id'],{'reconciled':p.get('reconciled')})

    @staticmethod
    def _put_snapshot(db,table,payload):
        if table not in ('market_snapshots','portfolio_snapshots'):raise ValueError('Unknown snapshot table')
        encoded=canonical(payload)
        previous=db.execute(f'SELECT data_json FROM {table} WHERE id=?',(payload['snapshot_id'],)).fetchone()
        if previous and previous['data_json']!=encoded:
            raise DomainError('Snapshot ID already belongs to different immutable data','SNAPSHOT_CONFLICT',409)
        db.execute(f'INSERT OR IGNORE INTO {table} VALUES (?,?,?)',(payload['snapshot_id'],payload['captured_at'],encoded))

    def portfolio(self,db=None):
        own=db is None; db=db or self.store.connect()
        try:
            s=db.execute("SELECT value FROM settings WHERE key='portfolio_snapshot_id'").fetchone()
            row=db.execute('SELECT data_json FROM portfolio_snapshots WHERE id=?',(json.loads(s['value']),)).fetchone() if s else None
            p=json.loads(row['data_json']) if row else {'snapshot_id':'UNAVAILABLE','captured_at':None,'equity':0,'cash':0,'buying_power':None,'reconciled':False,'positions':[],'is_demo':self.demo}
            # Only synthetic workspace executes paper fills. Real snapshots remain read-only.
            positions=db.execute("SELECT p.*,e.snapshot_json FROM positions p JOIN opportunities o ON o.id=p.opportunity_id JOIN events e ON e.id=o.event_id WHERE p.status='OPEN'").fetchall()
            for pos in positions:
                packet=json.loads(pos['snapshot_json']); thesis=json.loads(pos['thesis_json']); capital=pos['quantity']*pos['entry_price']
                p['positions'].append({'position_id':pos['id'],'opportunity_id':pos['opportunity_id'],'security_id':packet['security']['security_id'],'ticker':packet['security']['ticker'],'sector':packet['security']['sector'],'event_family':packet['event_family'],'quantity':pos['quantity'],'entry_price':pos['entry_price'],'market_value':capital,'planned_loss':thesis['sizing']['planned_loss'],'thesis':thesis})
                p['cash']-=capital
                if p['buying_power'] is not None: p['buying_power']-=capital
            realized=sum(json.loads(r['data_json']).get('net_pnl',0) for r in db.execute("SELECT data_json FROM outcomes WHERE phase='EXIT'"))
            p['cash']+=realized; p['equity']+=realized
            if p['buying_power'] is not None: p['buying_power']+=realized
            p['snapshot_id']=digest([p['snapshot_id'],[dict(r) for r in positions],realized])[:24]
            return p
        finally:
            if own: db.close()

    def register(self,security,universe='USER_WATCHLIST',valid_from=None):
        import re
        if not re.fullmatch(r'[A-Z0-9.\-]{1,16}',security['ticker']): raise DomainError('Invalid ticker')
        if not re.fullmatch(r'\d{10}',security['cik']): raise DomainError('CIK must be 10 digits')
        if universe not in ('USER_WATCHLIST','SP500','NASDAQ100'): raise DomainError('Unknown universe')
        with self.store.transaction() as db:
            self._security(db,security)
            start=valid_from or self.now()[:10]
            identity=digest([security['security_id'],universe,start])[:24]
            db.execute('INSERT OR IGNORE INTO universe_memberships VALUES (?,?,?,?,NULL)',(identity,security['security_id'],universe,start))
            Store.audit(db,'SECURITY_REGISTERED',security['security_id'],{'universe':universe})
        return security

    @staticmethod
    def _security(db,s):
        import re
        if not re.fullmatch(r'[A-Z0-9.\-]{1,16}',s['ticker']) or not re.fullmatch(r'\d{10}',s['cik']):
            raise DomainError('Invalid canonical ticker / CIK')
        row=db.execute('SELECT * FROM securities WHERE id=? OR ticker=?',(s['security_id'],s['ticker'])).fetchone()
        if row and (row['id']!=s['security_id'] or row['cik']!=s['cik'] or row['ticker']!=s['ticker']): raise DomainError('Ticker/CIK mapping conflict','IDENTITY_CONFLICT',409)
        db.execute('INSERT OR IGNORE INTO securities VALUES (?,?,?,?,?,?)',(s['security_id'],s['ticker'],s['cik'],s['issuer_name'],s['sector'],canonical(s)))

    def ingest(self,packet,market):
        packet=core_only(deepcopy(packet)); market=core_only(deepcopy(market))
        if packet['event_family'] not in FAMILIES: raise DomainError('Unknown event family')
        if bool(packet.get('is_demo'))!=self.demo or bool(market.get('is_demo'))!=self.demo: raise DomainError('Demo and real snapshots cannot mix')
        dt(packet['event_at']); dt(market['captured_at'])
        metric_ids=[f['metric_id'] for f in packet['facts']]
        if len(set(metric_ids))!=len(metric_ids): raise DomainError('Duplicate metric; use a new immutable event version')
        with self.store.transaction() as db:
            existing=db.execute('SELECT o.id,e.security_id FROM opportunities o JOIN events e ON e.id=o.event_id JOIN filings f ON f.id=e.filing_id WHERE f.accession=? AND e.family=? AND e.event_type=?',(packet['accession'],packet['event_family'],packet['event_type'])).fetchone()
            if existing:
                if existing['security_id']!=packet['security']['security_id']:raise DomainError('Accession belongs to a different security','IDENTITY_CONFLICT',409)
                return self._get(db,existing['id'])
            self._security(db,packet['security'])
            has_current_filing=False
            for e in packet['evidence']:
                if self.demo:
                    raw=e.pop('raw_content'); content=canonical(raw)
                    rid,sha=Store.raw(db,'demo',packet['accession'],content,packet['event_at'],e['url'],True)
                else:
                    row=db.execute('SELECT * FROM raw_documents WHERE id=?',(e.get('raw_document_id'),)).fetchone()
                    if not row or row['is_demo'] or row['source_id']!='sec': raise DomainError('Evidence must reference an ingested official SEC document')
                    rid,sha=row['id'],row['sha256']; e['url']=row['url']; e['source_id']='sec'
                    filing=db.execute('SELECT * FROM filings WHERE raw_document_id=?',(rid,)).fetchone()
                    if not filing or filing['security_id']!=packet['security']['security_id'] or dt(filing['accepted_at'])>dt(packet['event_at']): raise DomainError('Evidence issuer / point-in-time mismatch')
                    if filing['accession']==packet['accession'] and filing['accepted_at']==packet['event_at']:
                        has_current_filing=True
                    content=bytes(row['content']).decode('utf-8',errors='replace')
                    if not e.get('excerpt') or e['excerpt'] not in content: raise DomainError('Evidence excerpt cannot be resolved')
                    if not e.get('locator'): raise DomainError('Evidence locator required')
                saved=db.execute('SELECT received_at,published_at FROM raw_documents WHERE id=?',(rid,)).fetchone()
                e.update(raw_document_id=rid,sha256=sha,verified=True,level='E1',parser_version='deterministic-import-v1',fact_extractor_version='1',fetched_at=saved['received_at'],source_timestamp=saved['published_at'])
                db.execute('INSERT INTO evidence_spans VALUES (?,?,?,?,?,?)',(e['evidence_id'],rid,e['locator'],e['excerpt'],digest(e['excerpt'].encode()),e['level']))
            if not self.demo and not has_current_filing: raise DomainError('Current event filing evidence is required')
            evmap={e['evidence_id']:e for e in packet['evidence']}
            if not evmap: raise DomainError('Evidence is required')
            for f in packet['facts']:
                validate_fact(f)
                if f.get('supersedes'):
                    prior=db.execute('SELECT * FROM facts WHERE id=?',(f['supersedes'],)).fetchone()
                    if not prior or prior['security_id']!=packet['security']['security_id'] or prior['metric_id']!=f['metric_id'] or f['fact_version']<=prior['fact_version']:
                        raise DomainError('Fact correction must supersede the same issuer/metric at a higher version')
                if f['evidence_id'] not in evmap: raise DomainError('Orphan fact')
                if not f['unit'] or not f['period_start'] or not f['period_end'] or f['period_start']>f['period_end']: raise DomainError('Unit and aligned period required')
                if isinstance(f['value'],(int,float)) and not isinstance(f['value'],bool): number(f['value'])
                if self.demo:
                    source=db.execute('SELECT content FROM raw_documents WHERE id=?',(evmap[f['evidence_id']]['raw_document_id'],)).fetchone()
                    if json_pointer(json.loads(bytes(source['content'])),f['locator'])!=f['value']:raise DomainError('Synthetic fact does not reconcile with raw fixture')
                if not self.demo:
                    # Explicit normalized source token must be present in the cited excerpt.
                    token=f.get('source_token')
                    if not isinstance(token,str) or not token or token not in evmap[f['evidence_id']]['excerpt']: raise DomainError('Source token must resolve within evidence')
                    if isinstance(f['value'],(int,float)) and not isinstance(f['value'],bool):
                        scale=f.get('source_scale',1)
                        if scale not in (1,1000,1000000,1000000000): raise DomainError('Unsupported source scale')
                        try: parsed=float(token.replace(',','').replace('$','').replace('%',''))*scale
                        except ValueError: raise DomainError('Numeric source token cannot be parsed')
                        if abs(parsed-f['value'])>max(1e-8,abs(f['value'])*1e-10): raise DomainError('Numeric fact does not reconcile')
                    else:
                        # Semantic facts require manual provenance, never implicit AI promotion.
                        if f.get('reviewed_by')!='USER': raise DomainError('Non-numeric facts require explicit manual review')
                db.execute('INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?)',(f['fact_id'],packet['security']['security_id'],f['evidence_id'],f['metric_id'],canonical(f['value']),f['unit'],f['period_start'],f['period_end'],f['fact_version'],f.get('supersedes')))
            filing_id='filing-'+digest(packet['accession'])[:20]
            db.execute('INSERT OR IGNORE INTO filings VALUES (?,?,?,?,?,?)',(filing_id,packet['security']['security_id'],packet['accession'],packet['form'],packet['event_at'],packet['evidence'][0]['raw_document_id']))
            filing_id=db.execute('SELECT id FROM filings WHERE accession=?',(packet['accession'],)).fetchone()['id']
            db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',(packet['event_id'],packet['security']['security_id'],filing_id,packet['event_family'],packet['event_type'],packet['event_at'],packet.get('parent_event_id'),canonical(packet)))
            self._put_snapshot(db,'market_snapshots',market)
            portfolio=self.portfolio(db)
            inputs={'packet':packet,'market':market,'portfolio':portfolio,'rules':self.rules,'as_of':self.now()}
            core=evaluate(**inputs)
            evaluation_id=self._save_eval(db,inputs,core)
            db.execute('INSERT INTO opportunities VALUES (?,?,?,?,?)',(packet['opportunity_id'],packet['event_id'],'DISCOVERED',evaluation_id,self.now()))
            self._advance(db,packet['opportunity_id'],core)
            Store.audit(db,'EVENT_INGESTED',packet['event_id'],{'rule_version':self.rules['rule_version'],'core_hash':digest(core)})
            return self._get(db,packet['opportunity_id'])

    def _save_eval(self,db,inputs,core):
        identity='eval-'+digest([inputs,core])[:24]
        db.execute('INSERT OR IGNORE INTO evaluations VALUES (?,?,?,?,?,?,?)',(identity,inputs['packet']['event_id'],inputs['as_of'],inputs['rules']['rule_version'],canonical(inputs),canonical(core),digest(core)))
        return identity

    def _transition(self,db,identity,target,reason,actor='ENGINE'):
        row=Store.require(db,'opportunities',identity); before=row['state']
        if before==target:return
        if not allowed_transition(before,target,actor): raise DomainError(f'Illegal transition {before} → {target}','ILLEGAL_TRANSITION',409)
        db.execute('UPDATE opportunities SET state=? WHERE id=?',(target,identity))
        db.execute('INSERT INTO transitions(opportunity_id,from_state,to_state,reason_code,actor,created_at) VALUES (?,?,?,?,?,?)',(identity,before,target,reason,actor,self.now()))
        Store.audit(db,'STATE_TRANSITION',identity,{'from':before,'to':target,'reason_code':reason,'actor':actor})

    def _advance(self,db,identity,core):
        current=Store.require(db,'opportunities',identity)['state']; target=core['state']
        if current in ('IGNORED','EXITED','INVALIDATED'): return
        if current in ('ENTERED','MANAGE'):
            if core['invalidation_status']!=['NONE'] and current=='MANAGE': self._transition(db,identity,'INVALIDATED',core['invalidation_status'][0])
            return
        order=['DISCOVERED','VERIFIED','QUALIFIED','WATCH','READY']
        if target=='INVALIDATED': path=order[1:4]+['INVALIDATED']
        else: path=order[1:order.index(target)+1]
        if current=='READY' and target!='READY' and target!='INVALIDATED':
            self._transition(db,identity,'WATCH','TRIGGER_NOT_READY'); return
        for state in path:
            current=Store.require(db,'opportunities',identity)['state']
            if state in order and current in order and order.index(state)<=order.index(current): continue
            reason={'VERIFIED':'EVIDENCE_OFFICIAL_CONFIRMED','QUALIFIED':'DATA_COMPLETE','WATCH':'TRIGGER_NOT_READY','READY':'TRIGGER_READY','INVALIDATED':core['invalidation_status'][0]}.get(state,'DATA_COMPLETE')
            self._transition(db,identity,state,reason)

    def _get(self,db,identity):
        o=Store.require(db,'opportunities',identity); ev=Store.require(db,'evaluations',o['evaluation_id'])
        core=json.loads(ev['core_json']); core['state']=o['state']; core['evaluation_id']=ev['id']
        core['transitions']=[dict(r) for r in db.execute('SELECT * FROM transitions WHERE opportunity_id=? ORDER BY id',(identity,))]
        rows=db.execute('SELECT x.data_json FROM outcomes x JOIN positions p ON p.id=x.position_id WHERE p.opportunity_id=? ORDER BY x.created_at,x.phase',(identity,)).fetchall()
        core['outcome']=[json.loads(r['data_json']) for r in rows] or None
        core['core_output_hash']=digest(core)
        return core

    def get(self,identity):
        db=self.store.connect()
        try:return self._get(db,identity)
        finally:db.close()

    def list(self,filters=None):
        filters=filters or {}; result=[]
        db=self.store.connect()
        try:
            for row in db.execute('SELECT id FROM opportunities ORDER BY created_at DESC,id'):
                c=self._get(db,row['id'])
                if any(filters.get(k) and c.get({'family':'event_family','symbol':'ticker'}.get(k,k))!=v for k,v in filters.items() if k in ('family','state','sector','symbol')):continue
                if filters.get('q') and filters['q'].casefold() not in (c['ticker']+' '+c['issuer_name']).casefold(): continue
                result.append(c)
            return result
        finally:db.close()

    def refresh(self,identity,market=None):
        with self.store.transaction() as db:
            row=Store.require(db,'opportunities',identity); ev=Store.require(db,'evaluations',row['evaluation_id']); inputs=json.loads(ev['input_json'])
            if market is not None:
                if bool(market.get('is_demo'))!=self.demo: raise DomainError('Snapshot environment mismatch')
                inputs['market']=market
                self._put_snapshot(db,'market_snapshots',market)
            inputs['portfolio']=self.portfolio(db); inputs['as_of']=self.now()
            core=evaluate(**inputs); eid=self._save_eval(db,inputs,core)
            db.execute('UPDATE opportunities SET evaluation_id=? WHERE id=?',(eid,identity)); self._advance(db,identity,core)
            return self._get(db,identity)

    def replay(self,identity):
        row=self.store.query('SELECT e.* FROM evaluations e JOIN opportunities o ON o.evaluation_id=e.id WHERE o.id=?',(identity,))
        if not row: raise DomainError('Not found','NOT_FOUND',404)
        row=row[0]; actual=evaluate(**json.loads(row['input_json']))
        return {'evaluation_id':row['id'],'expected_hash':row['core_hash'],'actual_hash':digest(actual),'match':digest(actual)==row['core_hash'],'rule_version':row['rule_version']}

    def action(self,identity,action):
        with self.store.transaction() as db:
            o=Store.require(db,'opportunities',identity)
            if action=='ignore':self._transition(db,identity,'IGNORED','USER_IGNORE','USER')
            elif action=='watch':
                if o['state'] not in ('WATCH','READY'): raise DomainError('Only qualified candidates may be watched','ILLEGAL_TRANSITION',409)
                Store.audit(db,'USER_WATCH',identity,{})
            else:raise DomainError('Unknown action')
            return self._get(db,identity)

    @staticmethod
    def _idem(db,key,request):
        if not key or len(key)>200:raise DomainError('Idempotency-Key required')
        row=db.execute('SELECT * FROM idempotency WHERE key=?',(key,)).fetchone()
        if row:
            if row['request_hash']!=digest(request):raise DomainError('Idempotency key reused with different request','IDEMPOTENCY_CONFLICT',409)
            return json.loads(row['response_json'])
        return None

    @staticmethod
    def _remember(db,key,request,response):
        db.execute('INSERT INTO idempotency VALUES (?,?,?)',(key,digest(request),canonical(response)))
        return response

    def create_intent(self,body,key):
        if not self.demo:raise DomainError('Live execution is disabled; use the isolated demo workspace','PRODUCTION_BLOCKED',403)
        identity=body['opportunity_id']; self.refresh(identity)
        request={'operation':'create_intent','body':body}
        with self.store.transaction() as db:
            previous=self._idem(db,key,request)
            if previous is not None:return previous
            core=self._get(db,identity)
            if core['state']!='READY' or core['trigger_status']!='READY':raise DomainError('Opportunity is not READY','NOT_READY',409)
            if db.execute("SELECT id FROM order_intents WHERE opportunity_id=? AND status IN ('DRAFT','CONFIRMED')",(identity,)).fetchone():raise DomainError('An active intent already exists','DUPLICATE_INTENT',409)
            qty=body.get('quantity'); entry=number(body.get('entry'),'entry',True); stop=number(body.get('invalidation'),'invalidation',True)
            if isinstance(qty,bool) or not isinstance(qty,int) or qty<=0:raise DomainError('Quantity must be a positive integer')
            if entry!=core['market_snapshot']['price'] or stop!=core['invalidation_rules']['price']:raise DomainError('Entry and invalidation must match the current deterministic worksheet')
            if not str(body.get('management_hypothesis','')).strip():raise DomainError('Management hypothesis required')
            security={'security_id':core['security_id'],'sector':core['sector']}
            risk=risk_worksheet(security,core['event_family'],core['market_snapshot'],self.portfolio(db),self.now(),self.rules,qty,entry,stop)
            if risk['hard_blocks']:raise DomainError(' / '.join(risk['hard_blocks']),'RISK_BLOCKED',409)
            intent={'intent_id':'intent-'+uuid.uuid4().hex,'opportunity_id':identity,'ticker':core['ticker'],'status':'DRAFT','side':'BUY','order_type':'LOCAL_PAPER','quantity':qty,'entry':entry,'invalidation':stop,'sizing':risk['sizing'],'warnings':risk['warnings'],'management_hypothesis':body['management_hypothesis'],'thesis':core['catalyst'],'rule_version':core['rule_version'],'evaluation_id':core['evaluation_id'],'account_snapshot_id':core['portfolio']['snapshot_id'],'created_at':self.now(),'expires_at':(dt(self.now())+timedelta(minutes=5)).isoformat(),'is_demo':True}
            db.execute('INSERT INTO order_intents VALUES (?,?,?,?,?,NULL)',(intent['intent_id'],identity,'DRAFT',canonical(intent),self.now()))
            Store.audit(db,'ORDER_INTENT_CREATED',intent['intent_id'],{'quantity':qty,'planned_loss':risk['sizing']['planned_loss']})
            return self._remember(db,key,request,intent)

    def confirm_intent(self,identity,body,key):
        if not self.demo:raise DomainError('Live execution disabled','PRODUCTION_BLOCKED',403)
        if body.get('confirmed') is not True:raise DomainError('Explicit confirmation required')
        request={'operation':'confirm_intent','id':identity,'body':body}
        with self.store.transaction() as db:
            previous=self._idem(db,key,request)
            if previous is not None:return previous
            row=Store.require(db,'order_intents',identity)
            if row['status']!='DRAFT':raise DomainError('Intent already finalized','INTENT_FINAL',409)
            intent=json.loads(row['data_json'])
            if dt(self.now())>dt(intent['expires_at']):raise DomainError('Intent expired','INTENT_EXPIRED',409)
            core=self._get(db,row['opportunity_id']); ev=Store.require(db,'evaluations',core['evaluation_id']); inputs=json.loads(ev['input_json'])
            inputs.update(as_of=self.now(),portfolio=self.portfolio(db)); current=evaluate(**inputs)
            risk=risk_worksheet(inputs['packet']['security'],core['event_family'],inputs['market'],inputs['portfolio'],self.now(),self.rules,intent['quantity'],intent['entry'],intent['invalidation'])
            if core['state']!='READY' or current['state']!='READY' or risk['hard_blocks'] or (inputs['market']['price']!=intent['entry'] or inputs['market'].get('invalidation_price')!=intent['invalidation']):raise DomainError('Eligibility changed; review a new intent','ELIGIBILITY_CHANGED',409)
            pid='position-'+uuid.uuid4().hex
            intent['status']='FILLED';intent['confirmed_at']=self.now(); intent['sizing']=risk['sizing']
            db.execute("UPDATE order_intents SET status='FILLED',confirmed_at=?,data_json=? WHERE id=?",(self.now(),canonical(intent),identity))
            db.execute('INSERT INTO positions VALUES (?,?,?,?,?,?,?)',(pid,row['opportunity_id'],intent['quantity'],intent['entry'],'OPEN',canonical(intent),self.now()))
            outcome={'trade_id':pid,'opportunity_id':row['opportunity_id'],'ticker':core['ticker'],'event_family':core['event_family'],'rule_version':core['rule_version'],'account_snapshot_id':inputs['portfolio']['snapshot_id'],'entry_intent':intent,'actual_fills':[{'quantity':intent['quantity'],'price':intent['entry'],'at':self.now(),'venue':'LOCAL_PAPER_SIMULATOR'}],'planned_loss':intent['sizing']['planned_loss'],'mfe':None,'mae':None,'is_demo':True}
            db.execute('INSERT INTO outcomes VALUES (?,?,?,?,?)',('entry-'+pid,pid,'ENTRY',canonical(outcome),self.now()))
            self._transition(db,row['opportunity_id'],'ENTERED','USER_ENTER_CONFIRMED','USER')
            self._transition(db,row['opportunity_id'],'MANAGE','POSITION_RECONCILED')
            Store.audit(db,'PAPER_FILL',identity,{'position_id':pid})
            return self._remember(db,key,request,{'intent':intent,'position_id':pid,'state':'MANAGE'})

    def cancel_intent(self,identity):
        with self.store.transaction() as db:
            row=Store.require(db,'order_intents',identity)
            if row['status']!='DRAFT':raise DomainError('Only drafts can be cancelled','INTENT_FINAL',409)
            db.execute("UPDATE order_intents SET status='CANCELLED' WHERE id=?",(identity,))
            Store.audit(db,'ORDER_INTENT_CANCELLED',identity,{})
            return {'intent_id':identity,'status':'CANCELLED'}

    def exit_intent(self,pid,body,key):
        if not self.demo:raise DomainError('Live execution disabled','PRODUCTION_BLOCKED',403)
        request={'operation':'exit_intent','position_id':pid,'body':body}
        with self.store.transaction() as db:
            prev=self._idem(db,key,request)
            if prev is not None:return prev
            p=Store.require(db,'positions',pid)
            if p['status']!='OPEN':raise DomainError('Position already closed','POSITION_CLOSED',409)
            price=number(body.get('price'),'price',True); fees=number(body.get('fees',0),'fees')
            if fees<0 or not str(body.get('reason','')).strip():raise DomainError('Nonnegative fees and exit reason required')
            identity='exit-'+uuid.uuid4().hex
            data={'exit_intent_id':identity,'position_id':pid,'price':price,'fees':fees,'reason':body['reason'],'quantity':p['quantity'],'estimated_net_pnl':money((price-p['entry_price'])*p['quantity']-fees),'is_demo':True,'expires_at':(dt(self.now())+timedelta(minutes=5)).isoformat()}
            db.execute('INSERT INTO exit_intents VALUES (?,?,?,?,?)',(identity,pid,'DRAFT',canonical(data),self.now()))
            Store.audit(db,'EXIT_INTENT_CREATED',identity,{'position_id':pid})
            return self._remember(db,key,request,data)

    def confirm_exit(self,identity,body,key):
        if not self.demo or body.get('confirmed') is not True:raise DomainError('Explicit paper exit confirmation required')
        request={'operation':'confirm_exit','id':identity,'body':body}
        with self.store.transaction() as db:
            prev=self._idem(db,key,request)
            if prev is not None:return prev
            row=Store.require(db,'exit_intents',identity); p=Store.require(db,'positions',row['position_id']); data=json.loads(row['data_json'])
            if row['status']!='DRAFT' or p['status']!='OPEN' or dt(self.now())>dt(data['expires_at']):raise DomainError('Exit intent stale or finalized','INTENT_FINAL',409)
            thesis=json.loads(p['thesis_json']); c=self._get(db,p['opportunity_id'])
            gross=money((data['price']-p['entry_price'])*p['quantity']); net=money(gross-data['fees'])
            outcome={'trade_id':p['id'],'opportunity_id':p['opportunity_id'],'ticker':c['ticker'],'event_family':c['event_family'],'rule_version':thesis['rule_version'],'entry_intent_id':thesis['intent_id'],'entry_price':p['entry_price'],'exit_price':data['price'],'quantity':p['quantity'],'planned_loss':thesis['sizing']['planned_loss'],'realized_pnl':gross,'fees':data['fees'],'net_pnl':net,'r_multiple':net/thesis['sizing']['planned_loss'],'exit_reason':data['reason'],'holding_days':(dt(self.now())-dt(p['created_at'])).total_seconds()/86400,'mfe':None,'mae':None,'slippage':None,'benchmark_excess_return':None,'measurement_status':'PRICE_PATH_NOT_COLLECTED','is_demo':True}
            db.execute('INSERT INTO outcomes VALUES (?,?,?,?,?)',('exit-'+p['id'],p['id'],'EXIT',canonical(outcome),self.now()))
            db.execute("UPDATE positions SET status='CLOSED' WHERE id=?",(p['id'],)); db.execute("UPDATE exit_intents SET status='FILLED' WHERE id=?",(identity,))
            self._transition(db,p['opportunity_id'],'EXITED','USER_EXIT_CONFIRMED','USER'); Store.audit(db,'PAPER_EXIT',identity,{'net_pnl':net})
            return self._remember(db,key,request,outcome)

    def outcomes(self):
        return [json.loads(r['data_json'])|{'phase':r['phase']} for r in self.store.query('SELECT * FROM outcomes ORDER BY created_at DESC')]

    def performance(self):
        result=[]; rows=[x for x in self.outcomes() if x['phase']=='EXIT']
        for family in FAMILIES:
            trades=[r for r in rows if r['event_family']==family]; n=len(trades)
            result.append({'event_family':family,'n':n,'net_pnl':money(sum(t['net_pnl'] for t in trades)),'mean_r':sum(t['r_multiple'] for t in trades)/n if n else None,'review_level':'FORMAL_REVIEW' if n>=100 else ('PROVISIONAL_REVIEW' if n>=30 else ('DATA_QUALITY_REVIEW' if n>=10 else 'INSUFFICIENT_SAMPLE')),'is_demo':self.demo})
        return result

    def status(self):
        blockers=['未完成 100 个真实历史 Golden 样本验收','SEC 尚未通过连续 14 个交易日稳定性验证','未完成至少 20 个交易日 Shadow 验证','Massive 实时窗口、交易所日历与数据授权待验证','IBKR 纸面成交、部分成交、拒单及对账尚未验收','备份恢复演练、告警投递和数据许可待验证']
        if self.demo:blockers.insert(0,'当前为合成数据回放工作区，不可用于实际投资决策')
        return {'version':'1.0.2','release_status':'PRODUCTION_BLOCKED','mode':'demo' if self.demo else 'shadow','ai_mode':self.store.setting('ai_mode','off'),'ai_status':'OFF' if self.store.setting('ai_mode','off')=='off' else 'AI_ASSIST_UNAVAILABLE','rule_version':self.rules['rule_version'],'as_of':self.now(),'live_trading':False,'sources':self.store.query('SELECT * FROM sources'),'blockers':blockers,'audit':self.store.verify_audit()}

    def export(self,payload):
        return envelope(payload,self.store.setting('ai_mode','off'),self.rules['rule_version'])
