"""Small, deterministic and explicitly synthetic integration exercise; no network."""
from datetime import datetime,timedelta,timezone
from ..util import utcnow,dt
from ..engine import reaction,risk_worksheet
from ..util import read_rules
from .market import build_snapshot,millis
from .broker import reconcile_portfolio,reconcile_order,normalize_ack


def fixture():
    days=[];day=datetime(2026,1,5,14,30,tzinfo=timezone.utc)
    while len(days)<24:
        if day.weekday()<5:days.append(day)
        day+=timedelta(days=1)
    calendar={'start':'2026-01-01','end':(days[-1]+timedelta(days=1)).date().isoformat(),'source':'SYNTHETIC_WEEKDAYS_NOT_EXCHANGE_CALENDAR','sessions':[{'open':d.isoformat(),'close':(d+timedelta(minutes=390)).isoformat()} for d in days]}
    event=days[22]-timedelta(hours=1);as_of=days[22]+timedelta(minutes=30);series={}
    for name,ticker in [('security','TEST'),('spy','SPY'),('sector','XLK')]:
        bars=[]
        for d in days[:23]:
            for minute in range(390 if d<days[22] else 30):
                price=105 if name=='security' and d==days[22] else (101 if name=='sector' and d==days[22] else 100)
                bars.append({'t':millis((d+timedelta(minutes=minute)).isoformat()),'o':price,'h':price+1,'l':price-1,'c':price,'v':200 if d==days[22] else 100,'vw':price})
        series[name]={'ticker':ticker,'bars':bars,'adjusted':False,'pagination_complete':True,'raw_refs':[]}
    return {'ticker':'TEST','event_at':event.isoformat(),'as_of':as_of.isoformat(),'series':series,'calendar':calendar,'quote':{'ticker':'TEST','bid':104.99,'ask':105.01,'at':as_of.isoformat()},'data_mode':'realtime'}


def run():
    inputs=fixture();m=build_snapshot(**inputs);checks=[]
    def check(name,passed):checks.append({'name':name,'passed':bool(passed)})
    check('aligned_market_window',m['complete']);check('vwap',m['vwap']==105)
    r=reaction(m,inputs['as_of']);check('relative_volume',r['relative_volume']==2)
    check('sector_excess_return',r['sector_excess_pct']==4)
    s={'security_id':'test','ticker':'TEST','sector':'Technology','ibkr_conid':123}
    p=reconcile_portfolio([{'conid':123,'ticker':'TEST','position':10,'mktPrice':105,'mktValue':1050,'avgCost':100,'currency':'USD','assetClass':'STK'}],{k:{'currency':'USD','amount':v} for k,v in [('netliquidation',10000),('totalcashvalue',8950),('buyingpower',8950)]},{'BASE':{'currency':'USD'},'USD':{'cashbalance':8950}},[s],{'test':{'invalidation_price':99,'event_family':'GUIDANCE_CHANGE'}},[],inputs['as_of'],'synthetic')
    check('portfolio_cash_equity_reconciliation',p['reconciled'])
    risk=risk_worksheet(s,'GUIDANCE_CHANGE',m,p,inputs['as_of'],read_rules())
    check('risk_sizing',risk['sizing']['max_shares']==4 and not risk['hard_blocks'])
    ticket={'client_order_id':'offline-123','conid':123,'side':'BUY','quantity':5,'limit_price':105}
    trades=[{'execution_id':'test-1','order_ref':'offline-123','conid':123,'side':'B','size':2,'price':'104.5','commission':'1'}]
    partial=reconcile_order(ticket,[{'orderId':1,'order_ref':'offline-123','status':'Submitted','filledQuantity':2}],trades)
    check('partial_fill',partial['state']=='PARTIALLY_FILLED' and partial['remaining_quantity']==3)
    ack=normalize_ack([{'order_id':'1','order_status':'Submitted'}],'DUFAKE')
    check('acknowledgement_is_not_fill',ack['state']=='ACKNOWLEDGED')
    check('duplicate_execution_not_double_counted',reconcile_order(ticket,[],trades+trades)['filled_quantity']==2)
    return {'passed':all(x['passed'] for x in checks),'checks':checks,'at':utcnow(),'is_synthetic':True,'network_requests':0,'market':{'price':m['price'],'vwap':m['vwap'],'reaction':r,'coverage':m['coverage']},'portfolio':p,'risk':risk,'partial_fill':partial,'note':'Synthetic offline contract/calculation check only; no live account or market entitlement verified.'}
