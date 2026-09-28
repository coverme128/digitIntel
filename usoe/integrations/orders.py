"""Durable, explicitly confirmed IBKR paper orders; acknowledgements never create fills.
A reserved mutation is never retried, including after process restart or lost responses.
"""
import json
import uuid
from ..util import canonical,digest,dt,utcnow,DomainError,number
from ..storage import Store
from ..engine import evaluate,risk_worksheet
from .broker import positive_int,reconcile_order

TERMINAL={'FILLED','CANCELLED','CANCELLED_PARTIAL','REJECTED','REJECTED_PARTIAL','ABANDONED'}

class BrokerOrders:
    def __init__(self,integrations):
        self.i=integrations;self.s=integrations.service;self.store=self.s.store

    def get(self,identity):
        rows=self.store.query('SELECT data_json FROM broker_tickets WHERE id=?',(identity,))
        if not rows:raise DomainError('Broker ticket not found','NOT_FOUND',404)
        return json.loads(rows[0]['data_json'])

    def list(self):return [json.loads(r['data_json']) for r in self.store.query('SELECT data_json FROM broker_tickets ORDER BY created_at DESC')]

    def _save(self,db,ticket,kind):
        ticket['updated_at']=self.s.now()
        db.execute('UPDATE broker_tickets SET state=?,data_json=?,updated_at=? WHERE id=?',(ticket['state'],canonical(ticket),ticket['updated_at'],ticket['id']))
        db.execute('INSERT INTO broker_receipts(ticket_id,kind,data_json,created_at) VALUES (?,?,?,?)',(ticket['id'],kind,canonical(ticket),self.s.now()))
        Store.audit(db,'BROKER_'+kind,ticket['id'],{'state':ticket['state']})

    def _eligibility(self,body):
        self.i.shadow();side=body.get('side','BUY');quantity=positive_int(body['quantity'],'quantity');limit=number(body['limit_price'],'limit_price',True)
        if side not in ('BUY','SELL'):raise DomainError('Unsupported order side')
        p=self.s.portfolio();age=(dt(self.s.now())-dt(p['captured_at'])).total_seconds() if p.get('captured_at') else None
        if age is None or not 0<=age<=self.s.rules['portfolio_max_age_seconds'] or not p.get('reconciled') or p.get('hard_blocks'):raise DomainError('Fresh reconciled broker portfolio required','RISK_BLOCKED',409)
        if side=='BUY':
            core=self.s.get(body['opportunity_id'])
            rows=self.store.query('SELECT input_json FROM evaluations WHERE id=?',(core['evaluation_id'],));inputs=json.loads(rows[0]['input_json'])
            inputs.update(portfolio=p,as_of=self.s.now());current=evaluate(**inputs)
            security=self.i.security(current['security_id'])
            risk=risk_worksheet(security,current['event_family'],inputs['market'],p,self.s.now(),inputs['rules'],quantity,limit)
            if current['state']!='READY' or core['state']!='READY' or current['trigger_status']!='READY' or risk['hard_blocks']:raise DomainError('Opportunity / risk no longer eligible','RISK_BLOCKED',409)
            if limit!=inputs['market']['price']:raise DomainError('Limit must equal reviewed market snapshot price')
            thesis={'event_id':current['event_id'],'event_family':current['event_family'],'invalidation_price':current['invalidation_rules']['price'],'sizing':risk['sizing'],'evaluation_id':core['evaluation_id'],'rule_version':current['rule_version'],'market_snapshot_id':inputs['market']['snapshot_id']}
        else:
            security=self.i.security(body['security_id']);position=next((p for p in p['positions'] if p['security_id']==security['security_id']),None)
            if not position or quantity>position['quantity']:raise DomainError('Cannot sell more than the reconciled holding','RISK_BLOCKED',409)
            if not body.get('reason'):raise DomainError('Exit reason required')
            thesis={'position':position,'reason':body['reason']}
        if not security.get('ibkr_conid') or not security.get('ibkr_contract_verified_at'):raise DomainError('Verified IBKR conid mapping required','BROKER_SECURITY_MISMATCH',409)
        return security,thesis,p['snapshot_id']

    def create(self,body,key):
        if not isinstance(key,str) or not 8<=len(key)<=160:raise DomainError('Idempotency-Key of 8–160 characters required')
        request_hash=digest(body)
        with self.i.operation_lock:
            prior=self.store.query('SELECT * FROM broker_tickets WHERE idempotency_key=?',(key,))
            if prior:
                if prior[0]['request_hash']!=request_hash:raise DomainError('Idempotency key belongs to another request','IDEMPOTENCY_CONFLICT',409)
                return json.loads(prior[0]['data_json'])
            security,thesis,portfolio_id=self._eligibility(body)
            identity='broker-'+uuid.uuid4().hex
            ticket={'id':identity,'client_order_id':identity,'conid':security['ibkr_conid'],'security_id':security['security_id'],'ticker':security['ticker'],'side':body.get('side','BUY'),'quantity':body['quantity'],'limit_price':body['limit_price'],'order_type':'LMT','tif':'DAY','state':'DRAFT','request':body,'thesis':thesis,'portfolio_snapshot_id':portfolio_id,'created_at':self.s.now(),'account_ref':self.i.broker().account_ref,'environment':'IBKR_PAPER_ONLY'}
            with self.store.transaction() as db:
                db.execute('INSERT INTO broker_tickets VALUES (?,?,?,?,?,?,?)',(identity,key,request_hash,'DRAFT',canonical(ticket),self.s.now(),self.s.now()))
                self._save(db,ticket,'DRAFT_CREATED')
            return ticket

    def act(self,identity,action,body):
        self.i.shadow()
        if action not in ('preview','submit','reply','cancel','abandon'):raise DomainError('Unknown paper order action')
        if body.get('confirmed') is not True:raise DomainError('Explicit confirmation required')
        with self.i.operation_lock:
            ticket=self.get(identity);client=self.i.broker()
            if ticket['account_ref']!=client.account_ref:raise DomainError('Ticket belongs to a different account','BROKER_ACCOUNT_MISMATCH',409)
            expected={'preview':{'DRAFT'},'submit':{'PREVIEWED'},'reply':{'AWAITING_REPLY'},'cancel':{'ACKNOWLEDGED','WORKING','PARTIALLY_FILLED'},'abandon':{'DRAFT','PREVIEWED','PREVIEW_FAILED'}}[action]
            # Duplicate confirmations return the durable current state, never resend.
            if ticket['state'] not in expected:return ticket
            if action=='abandon':
                ticket['state']='ABANDONED'
                with self.store.transaction() as db:self._save(db,ticket,'ABANDONED')
                return ticket
            if action in ('preview','submit','reply'):
                if not 0<=(dt(self.s.now())-dt(ticket['created_at'])).total_seconds()<=300:raise DomainError('Draft expired; reconcile or reject pending broker warning in Gateway','DRAFT_EXPIRED',409)
                security,thesis,portfolio_id=self._eligibility(ticket['request'])
                if security['ibkr_conid']!=ticket['conid']:raise DomainError('Security mapping changed','ELIGIBILITY_CHANGED',409)
                if action=='reply' and body.get('reply_id')!=ticket.get('reply_id'):raise DomainError('Confirm the displayed broker reply ID')
                ticket['thesis']=thesis;ticket['portfolio_snapshot_id']=portfolio_id
            if action in ('submit','reply'):
                other=[t for t in self.list() if t['id']!=identity and t['state'] not in TERMINAL|{'DRAFT','PREVIEWED','PREVIEW_FAILED'}]
                if other:raise DomainError('Reconcile outstanding broker orders before another submission','BROKER_PENDING_ORDER',409)
            client.verify_paper()
            ticket['state']={'preview':'PREVIEWING','submit':'SUBMITTING','reply':'REPLYING','cancel':'CANCELLING'}[action]
            with self.store.transaction() as db:
                current=db.execute('SELECT state,data_json FROM broker_tickets WHERE id=?',(identity,)).fetchone()
                if current['state'] not in expected:return json.loads(current['data_json'])
                if action in ('submit','reply'):
                    unresolved=db.execute('SELECT id,state FROM broker_tickets WHERE id<>?',(identity,)).fetchall()
                    if any(r['state'] not in TERMINAL|{'DRAFT','PREVIEWED','PREVIEW_FAILED'} for r in unresolved):raise DomainError('Outstanding broker mutation','BROKER_PENDING_ORDER',409)
                self._save(db,ticket,action.upper()+'_RESERVED')
            try:
                if action=='preview':
                    response=client.preview(ticket)
                    ticket.update(state='PREVIEW_FAILED' if isinstance(response,dict) and response.get('error') else 'PREVIEWED',preview=response)
                elif action=='submit':ticket.update(client.submit(ticket,confirmed=True))
                elif action=='reply':ticket.update(client.reply(ticket['reply_id'],confirmed=True))
                else:
                    if not ticket.get('broker_order_id'):raise DomainError('Broker order ID required')
                    response=client.cancel(int(ticket['broker_order_id']),confirmed=True)
                    ticket.update(state='CANCEL_PENDING',cancel_response=response)
            except Exception:
                ticket.update(state='PREVIEW_FAILED' if action=='preview' else 'UNKNOWN',error='Broker response unavailable; do not resubmit. Reconcile with broker.')
            with self.store.transaction() as db:self._save(db,ticket,action.upper()+'_RESULT')
            return ticket

    def reconcile_all(self,bundle):
        for ticket in self.list():
            if ticket['account_ref']!=bundle['portfolio'].get('account_ref'):continue
            if ticket['state'] in {'DRAFT','PREVIEWED','PREVIEW_FAILED','PREVIEWING','ABANDONED','AWAITING_REPLY'}:continue
            # Include persisted executions: Client Portal returns only a short rolling history.
            stored=[json.loads(r['data_json'])['raw'] for r in self.store.query('SELECT data_json FROM broker_executions WHERE ticket_id=?',(ticket['id'],))]
            result=reconcile_order(ticket,bundle['orders'],stored+bundle['trades'])
            if result['state']=='UNKNOWN' and ticket['state'] in TERMINAL:continue
            with self.store.transaction() as db:
                for fill in result.get('fills',[]):
                    identity=digest([ticket['account_ref'],fill['execution_id']]);previous=db.execute('SELECT data_json FROM broker_executions WHERE id=?',(identity,)).fetchone()
                    if previous and previous['data_json']!=canonical(fill):result.update(state='RECONCILIATION_REQUIRED',reason='EXECUTION_CORRECTION_REQUIRES_REVIEW')
                    elif not previous:db.execute('INSERT INTO broker_executions VALUES (?,?,?,?)',(identity,ticket['id'],canonical(fill),self.s.now()))
                ticket.update(result);self._save(db,ticket,'RECONCILED')
