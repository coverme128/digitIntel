"""IBKR Client Portal adapter and deterministic portfolio / execution reconciliation.
All network order writes are separately gated to verified paper accounts.
"""
from __future__ import annotations
from urllib.parse import urlparse,urlencode,quote
from datetime import datetime,timezone
from decimal import Decimal
import re
from ..util import number,digest,DomainError,utcnow,dt,money
from ..sources import SourceUnavailable
from .transport import JSONTransport


def numeric(value,name):
    if isinstance(value,str):
        try:value=float(value.replace(',',''))
        except ValueError:raise DomainError('Invalid broker numeric field: '+name) from None
    return number(value,name)


def redact(value,account):
    hidden={'accountId','account','acct','accountCode','accountAlias','accountTitle','displayName','submitter','userName','session','ssoExpires'}
    if isinstance(value,dict):return {k:redact(v,account) for k,v in value.items() if k not in hidden}
    if isinstance(value,list):return [redact(x,account) for x in value]
    if isinstance(value,str):return value.replace(account,'[ACCOUNT]')
    return value

class IBKRClient:
    def __init__(self,account,base='https://localhost:5000/v1/api',transport=None,archive=None,paper_enabled=False):
        parsed=urlparse(base)
        if parsed.scheme!='https' or parsed.hostname not in ('localhost','127.0.0.1','api.ibkr.com') or parsed.path.rstrip('/')!='/v1/api' or parsed.query or parsed.username or parsed.password:raise DomainError('IBKR requires an approved TLS Client Portal / API URL')
        if not re.fullmatch(r'[A-Za-z0-9]+',account or ''):raise DomainError('Configure IBKR_ACCOUNT_ID','SOURCE_NOT_CONFIGURED',409)
        self.account=account;self.base=base.rstrip('/');self.http=transport or JSONTransport();self.archive=archive or (lambda *a:None);self.paper_enabled=paper_enabled
        self.account_ref=digest(account)[:16]

    def request(self,method,path,body=None):
        data=self.http.request(method,self.base+path,body=body)
        self.archive('ibkr',path.replace(self.account,'ACCOUNT'),redact(data,self.account))
        return data

    def auth_status(self):
        data=self.request('GET','/iserver/auth/status')
        return {'authenticated':data.get('authenticated') is True,'connected':data.get('connected') is True,'competing':data.get('competing') is True,'message':'User login required' if data.get('authenticated') is not True else None}

    def require_session(self):
        s=self.auth_status()
        if not s['authenticated'] or not s['connected'] or s['competing']:raise DomainError('IBKR brokerage session is unavailable / competing; sign in to Gateway','BROKER_AUTH_REQUIRED',409)
        return s

    def keepalive(self):
        # Never persist session tokens returned by tickle.
        result=self.http.request('POST',self.base+'/tickle',body={})
        auth=result.get('iserver',{}).get('authStatus',{})
        return {k:auth.get(k) for k in ('authenticated','connected','competing')}

    def accounts(self):
        data=self.request('GET','/portfolio/accounts')
        if not isinstance(data,list):raise SourceUnavailable('Invalid account list')
        matches=[a for a in data if (a.get('accountId') or a.get('id'))==self.account]
        if len(matches)!=1:raise DomainError('Configured account not uniquely available','BROKER_ACCOUNT_MISMATCH',409)
        return matches[0]

    def require_selected(self):
        data=self.request('GET','/iserver/accounts')
        if data.get('selectedAccount')!=self.account:raise DomainError('Select the configured account in IBKR before continuing','BROKER_ACCOUNT_MISMATCH',409)
        return data

    def verify_paper(self):
        if not self.paper_enabled:raise DomainError('IBKR paper execution is disabled','PAPER_DISABLED',403)
        self.require_session();a=self.accounts();self.require_selected()
        if not self.account.startswith('DU') or not (a.get('type')=='DEMO' or a.get('isPaper') is True):raise DomainError('Verified paper account required; live trading is disabled','LIVE_TRADING_DISABLED',403)
        return True

    def positions(self):
        rows=[];seen=set()
        for page in range(100):
            part=self.request('GET',f'/portfolio/{self.account}/positions/{page}')
            if not isinstance(part,list):raise SourceUnavailable('Malformed positions page')
            for r in part:
                if r.get('acctId',self.account)!=self.account:raise DomainError('Position account mismatch','BROKER_ACCOUNT_MISMATCH',409)
                if r.get('conid') in seen:raise SourceUnavailable('Duplicate positions / pagination loop')
                seen.add(r.get('conid'));rows.append(r)
            if len(part)<100:return rows
        raise SourceUnavailable('Position pagination safety limit')

    def orders(self):
        self.require_selected()
        # Pre-flight is required; never force=true because it returns a blank cache reset.
        data=self.request('GET','/iserver/account/orders')
        if data.get('snapshot') is not True:data=self.request('GET','/iserver/account/orders')
        if data.get('snapshot') is not True or not isinstance(data.get('orders'),list) or len(data['orders'])>=1000:raise SourceUnavailable('Order snapshot incomplete')
        if any(r.get('acct')!=self.account for r in data['orders']):raise DomainError('Orders belong to another / unknown account','BROKER_ACCOUNT_MISMATCH',409)
        return data['orders']

    def trades(self):
        self.require_selected();rows=self.request('GET','/iserver/account/trades')
        if not isinstance(rows,list):raise SourceUnavailable('Invalid execution payload')
        if any((r.get('account') or r.get('accountCode'))!=self.account for r in rows):raise DomainError('Execution account mismatch','BROKER_ACCOUNT_MISMATCH',409)
        return rows

    def snapshot(self,securities,plans=None,captured_at=None):
        self.require_session();a=self.accounts();positions=self.positions()
        summary=self.request('GET',f'/portfolio/{self.account}/summary')
        ledger=self.request('GET',f'/portfolio/{self.account}/ledger')
        orders=self.orders();trades=self.trades()
        result=reconcile_portfolio(positions,summary,ledger,securities,plans or {},orders,captured_at or utcnow(),self.account_ref)
        result['broker_account_mode']='paper' if a.get('type')=='DEMO' or a.get('isPaper') is True else 'live_read_only'
        result.pop('snapshot_id',None);result['snapshot_id']='portfolio-'+digest(result)[:24]
        return {'portfolio':result,'orders':[redact(r,self.account) for r in orders],'trades':[redact(r,self.account) for r in trades]}

    def candidates(self,ticker):
        from .market import symbol
        return self.request('GET','/trsrv/stocks?'+urlencode({'symbols':symbol(ticker)}))

    def contract(self,conid):
        conid=positive_int(conid,'conid');return self.request('GET',f'/iserver/contract/{conid}/info')

    def preview(self,ticket):
        self.verify_paper();order=order_payload(ticket)
        self.request('GET','/iserver/marketdata/snapshot?'+urlencode({'conids':order['conid'],'fields':'31,84,86'}))
        return redact(self.request('POST',f'/iserver/account/{self.account}/orders/whatif',{'orders':[order]}),self.account)

    def submit(self,ticket,confirmed=False):
        if confirmed is not True:raise DomainError('Explicit paper order confirmation required')
        self.verify_paper();return normalize_ack(self.request('POST',f'/iserver/account/{self.account}/orders',{'orders':[order_payload(ticket)]}),self.account)

    def reply(self,reply_id,confirmed=False):
        if confirmed is not True:raise DomainError('Explicit broker warning confirmation required')
        if not re.fullmatch(r'[A-Za-z0-9-]{1,160}',str(reply_id)):raise DomainError('Invalid reply ID')
        self.verify_paper();return normalize_ack(self.request('POST',f'/iserver/reply/{reply_id}',{'confirmed':True}),self.account)

    def cancel(self,order_id,confirmed=False):
        if confirmed is not True:raise DomainError('Explicit paper cancellation confirmation required')
        order_id=positive_int(order_id,'order ID');self.verify_paper()
        return redact(self.request('DELETE',f'/iserver/account/{self.account}/order/{order_id}'),self.account)


def positive_int(value,name):
    if isinstance(value,bool) or not isinstance(value,int) or value<=0:raise DomainError(name+' must be a positive integer')
    return value


def order_payload(ticket):
    if ticket.get('side') not in ('BUY','SELL'):raise DomainError('Unsupported side')
    if ticket.get('order_type','LMT')!='LMT' or ticket.get('tif','DAY')!='DAY':raise DomainError('V1 paper connector supports DAY limit orders only')
    if not re.fullmatch(r'[A-Za-z0-9-]{1,64}',ticket.get('client_order_id','')):raise DomainError('Stable client order ID required')
    return {'conid':positive_int(ticket['conid'],'conid'),'orderType':'LMT','side':ticket['side'],'quantity':positive_int(ticket['quantity'],'quantity'),'price':number(ticket['limit_price'],'price',True),'tif':'DAY','outsideRTH':False,'cOID':ticket['client_order_id']}


def normalize_ack(data,account):
    if isinstance(data,dict) and data.get('error'):return {'state':'REJECTED','error':redact(data['error'],account)}
    if not isinstance(data,list) or len(data)!=1:raise SourceUnavailable('Ambiguous order response; do not resubmit')
    row=data[0]
    if row.get('error'):return {'state':'REJECTED','error':redact(row['error'],account)}
    if row.get('id') and row.get('message'):
        return {'state':'AWAITING_REPLY','reply_id':str(row['id']),'messages':redact(row['message'],account),'message_ids':row.get('messageIds',[])}
    if row.get('order_id') or row.get('orderId'):
        return {'state':'ACKNOWLEDGED','broker_order_id':str(row.get('order_id') or row['orderId']),'broker_status':row.get('order_status'),'note':'Acknowledgement is not a fill; execution reconciliation required.'}
    raise SourceUnavailable('Unrecognized order response; do not resubmit')


def reconcile_portfolio(positions,summary,ledger,securities,plans,orders,captured_at,account_ref):
    blocks=[];mapped=[];seen=set();registry={}
    for s in securities:
        if s.get('ibkr_conid') is not None:
            if str(s['ibkr_conid']) in registry:raise DomainError('Ambiguous conid registry')
            registry[str(s['ibkr_conid'])]=s
    def amount(key):
        row=summary.get(key,{})
        if row.get('currency')!='USD' or row.get('amount') is None:
            blocks.append('RISK_CURRENCY_OR_VALUE_UNKNOWN');return None
        return numeric(row['amount'],key)
    equity,cash,bp=amount('netliquidation'),amount('totalcashvalue'),amount('buyingpower')
    base=ledger.get('BASE',{});usd=ledger.get('USD',{})
    if base.get('currency')!='USD':blocks.append('RISK_UNSUPPORTED_BASE_CURRENCY')
    if any(k not in ('BASE','USD') and abs(numeric(v.get('cashbalance',0),'cashbalance'))>0.01 for k,v in ledger.items() if isinstance(v,dict)):blocks.append('RISK_MULTICURRENCY_REVIEW')
    if usd.get('cashbalance') is None or cash is None or abs(numeric(usd['cashbalance'],'cashbalance')-cash)>1:blocks.append('RISK_CASH_RECONCILIATION')
    if not equity or equity<=0:blocks.append('RISK_EQUITY_UNKNOWN')
    total=0
    for p in positions:
        conid=str(p.get('conid'));s=registry.get(conid);qty=numeric(p.get('position'),'position');value=numeric(p.get('mktValue'),'mktValue');price=numeric(p.get('mktPrice'),'mktPrice');avg=numeric(p.get('avgCost'),'avgCost')
        total+=value
        if conid in seen:blocks.append('RISK_DUPLICATE_POSITION')
        seen.add(conid)
        if p.get('currency')!='USD' or p.get('assetClass')!='STK' or qty<0:blocks.append('RISK_UNSUPPORTED_POSITION')
        if abs(qty*price-value)>max(1,abs(qty)*0.01):blocks.append('RISK_POSITION_VALUATION_MISMATCH')
        if not s:blocks.append('RISK_SECURITY_MAPPING')
        ticker=p.get('ticker') or p.get('contractDesc')
        if s and ticker!=s['ticker']:blocks.append('RISK_SECURITY_MAPPING')
        plan=plans.get(s['security_id'],{}) if s else {}
        stop=plan.get('invalidation_price')
        if qty and (stop is None or not 0<number(stop,'invalidation')<price):blocks.append('RISK_POSITION_PLAN_MISSING');loss=None
        else:loss=money(qty*(price-stop)) if qty else 0
        if qty and not plan.get('event_family'):blocks.append('RISK_CATALYST_UNCLASSIFIED')
        mapped.append({'conid':conid,'security_id':s['security_id'] if s else None,'ticker':ticker,'sector':s['sector'] if s else 'UNKNOWN','quantity':qty,'avg_price':avg,'market_price':price,'market_value':value,'planned_loss':loss,'invalidation_price':stop,'event_family':plan.get('event_family'),'correlation_group':s.get('correlation_group') if s else None,'unrealized_pnl':money((price-avg)*qty)})
    if equity is None or cash is None or abs(equity-cash-total)>max(1,(equity or 0)*0.00001):blocks.append('RISK_EQUITY_RECONCILIATION')
    terminal={'Filled','Cancelled','Canceled','Inactive','Rejected'}
    active=[o for o in orders if o.get('status') not in terminal]
    if active:blocks.append('RISK_OPEN_ORDERS_REVIEW')
    result={'captured_at':captured_at,'account_ref':account_ref,'equity':equity or 0,'cash':cash if cash is not None else 0,'buying_power':bp,'positions':mapped,'reconciled':not blocks,'duplicate_order_uncertainty':bool(active),'hard_blocks':sorted(set(blocks)),'is_demo':False,'reconciliation_version':'ibkr-2','exposure':{'gross_market_value':sum(abs(x['market_value']) for x in mapped),'net_market_value':total,'open_planned_loss':sum(x['planned_loss'] or 0 for x in mapped) if all(x['planned_loss'] is not None for x in mapped) else None}}
    result['snapshot_id']='portfolio-'+digest(result)[:24];return result


def reconcile_order(ticket,orders,trades):
    matches=[o for o in orders if (ticket.get('broker_order_id') is not None and o.get('orderId') is not None and str(o['orderId'])==str(ticket['broker_order_id'])) or o.get('order_ref')==ticket['client_order_id'] or o.get('cOID')==ticket['client_order_id']]
    if len(matches)>1:return {'state':'RECONCILIATION_REQUIRED','reason':'MULTIPLE_ORDER_MATCHES'}
    unique={};conflict=False
    for t in trades:
        if t.get('order_ref')!=ticket['client_order_id']:continue
        identity=t.get('execution_id')
        if not identity:conflict=True;continue
        if identity in unique and unique[identity]!=t:conflict=True
        unique[identity]=t
    fills=[]
    for t in unique.values():
        if str(t.get('conid'))!=str(ticket['conid']) or t.get('side','').upper() not in ({'B','BUY','BOT'} if ticket['side']=='BUY' else {'S','SELL','SLD'}):conflict=True;continue
        qty=numeric(t.get('size'),'size');price=numeric(t.get('price'),'price')
        if qty<=0 or price<=0:conflict=True;continue
        fees=numeric(t['commission'],'commission') if t.get('commission') is not None else None
        fills.append({'execution_id':t['execution_id'],'quantity':qty,'price':price,'fees':fees,'at':t.get('trade_time_r') or t.get('trade_time'),'raw':t})
    filled=sum(f['quantity'] for f in fills);remaining=ticket['quantity']-filled;avg=sum(f['quantity']*f['price'] for f in fills)/filled if filled else None
    o=matches[0] if matches else {};reported=numeric(o['filledQuantity'],'filledQuantity') if o.get('filledQuantity') is not None else None
    if remaining<0 or (reported is not None and abs(reported-filled)>1e-8):conflict=True
    if o.get('remainingQuantity') is not None and o.get('status') not in ('Cancelled','Canceled','Inactive','Rejected') and abs(numeric(o['remainingQuantity'],'remainingQuantity')-remaining)>1e-8:conflict=True
    if conflict:state='RECONCILIATION_REQUIRED'
    elif remaining==0:state='FILLED'
    elif o.get('status') in ('Cancelled','Canceled'):state='CANCELLED_PARTIAL' if filled else 'CANCELLED'
    elif o.get('status') in ('Inactive','Rejected'):state='REJECTED_PARTIAL' if filled else 'REJECTED'
    elif filled:state='PARTIALLY_FILLED'
    elif o.get('status')=='Filled':state='RECONCILIATION_REQUIRED'
    elif matches:state='WORKING'
    else:state='UNKNOWN'
    return {'state':state,'filled_quantity':filled,'remaining_quantity':max(0,remaining),'average_fill_price':avg,'fees':sum(f['fees'] for f in fills) if all(f['fees'] is not None for f in fills) else None,'fills':fills,'broker_order_id':str(o['orderId']) if o.get('orderId') else ticket.get('broker_order_id'),'slippage_bps':((avg/ticket['limit_price']-1)*10000*(1 if ticket['side']=='BUY' else -1)) if avg else None,'reason':None if not conflict else 'EXECUTION_OR_QUANTITY_MISMATCH'}
