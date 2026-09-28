"""Massive REST, point-in-time market windows, corporate actions and outcome math."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime,timedelta,timezone,date,time
from statistics import mean
from urllib.parse import urlencode,urlparse,parse_qsl,urlunparse
from zoneinfo import ZoneInfo
import json
import re
from ..util import number,dt,digest,DomainError,utcnow
from ..sources import SourceUnavailable
from ..calendar import classify_session
from .transport import JSONTransport

ET=ZoneInfo('America/New_York')

def symbol(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Z0-9.\-]{1,16}',value):raise DomainError('Invalid US stock ticker')
    return value

def millis(value):return int(dt(value).timestamp()*1000)
def stamp(value):return datetime.fromtimestamp(value/1000,timezone.utc).isoformat()

def validate_bar(row):
    for k in ('t','o','h','l','c','v'):number(row[k],k)
    if isinstance(row['t'],bool) or row['t']!=int(row['t']) or row['t']<946684800000 or row['t']>4102444800000:raise ValueError('Invalid millisecond timestamp')
    if min(row[k] for k in ('o','h','l','c'))<=0 or row['v']<0 or not row['l']<=min(row['o'],row['c'])<=max(row['o'],row['c'])<=row['h']:raise ValueError('Invalid OHLCV')
    if 'vw' in row and row['vw'] is not None:number(row['vw'],'vw',True)
    return row

class MassiveClient:
    BASE='https://api.massive.com'
    def __init__(self,key,transport=None,archive=None):
        if not key:raise DomainError('Configure MASSIVE_API_KEY','SOURCE_NOT_CONFIGURED',409)
        self.key=key;self.http=transport or JSONTransport();self.archive=archive or (lambda *a:None)

    def _page(self,path):
        parsed=urlparse(path)
        if parsed.scheme:
            if parsed.scheme!='https' or parsed.netloc!='api.massive.com' or parsed.username or parsed.password:raise SourceUnavailable('Untrusted pagination destination')
            path=parsed.path+('?' + parsed.query if parsed.query else '')
        if not path.startswith('/') or path.startswith('//'):raise SourceUnavailable('Invalid upstream path')
        u=urlparse(path);query=[(k,v) for k,v in parse_qsl(u.query) if k.lower() not in ('apikey','api_key')]
        clean=u.path+('?' + urlencode(query) if query else '')
        payload=self.http.request('GET',self.BASE+clean,headers={'Authorization':'Bearer '+self.key})
        if not isinstance(payload,(dict,list)) or (isinstance(payload,dict) and (payload.get('status') in ('ERROR','NOT_AUTHORIZED','NOT_ENTITLED') or payload.get('error'))):raise SourceUnavailable('Massive request denied or malformed')
        # Pagination links can echo credentials. Archive a sanitized JSON representation.
        payload=deepcopy(payload)
        if isinstance(payload,dict) and payload.get('next_url'):
            link=urlparse(payload['next_url'])
            payload['next_url']=urlunparse(link._replace(query=urlencode([(k,v) for k,v in parse_qsl(link.query) if k.lower() not in ('apikey','api_key')])))
        ref=self.archive('massive',clean,payload)
        return payload,ref

    def paginate(self,path,kind='results',max_pages=200):
        rows,refs,seen=[],[],set()
        while path:
            if path in seen or len(seen)>=max_pages:raise SourceUnavailable('Pagination loop / safety limit; incomplete data')
            seen.add(path);data,ref=self._page(path)
            if not isinstance(data,dict) or not isinstance(data.get(kind,[]),list):raise SourceUnavailable('Invalid result schema')
            rows.extend(data.get(kind,[]));refs.append(ref)
            path=data.get('next_url')
        return rows,[r for r in refs if r]

    def bars(self,ticker,start,end,timespan='minute',adjusted=False):
        symbol(ticker);a=date.fromisoformat(start);b=date.fromisoformat(end)
        if a>b or (b-a).days>730 or timespan not in ('minute','day'):raise DomainError('Invalid aggregate range')
        path=f'/v2/aggs/ticker/{ticker}/range/1/{timespan}/{start}/{end}?'+urlencode({'adjusted':str(adjusted).lower(),'sort':'asc','limit':50000})
        rows,refs=self.paginate(path)
        previous=-1
        try:
            for r in rows:
                validate_bar(r)
                day=dt(stamp(r['t'])).astimezone(ET).date()
                if not a<=day<=b:raise ValueError('Aggregate outside requested date range')
                if timespan=='minute' and r['t']%60000:raise ValueError('Aggregate not aligned to a minute')
                if r['t']<=previous:raise ValueError('Out-of-order / duplicate aggregate')
                previous=r['t']
        except (ValueError,KeyError,TypeError):raise SourceUnavailable('Invalid aggregate OHLCV or timestamps') from None
        if not rows:raise SourceUnavailable('Empty aggregate window')
        return {'ticker':ticker,'bars':rows,'raw_refs':refs,'adjusted':adjusted,'data_mode':'historical','pagination_complete':True,'timespan':timespan,'start':start,'end':end}

    def splits(self,ticker,start,end):
        rows,refs=self.paginate('/v3/reference/splits?'+urlencode({'ticker':symbol(ticker),'execution_date.gte':start,'execution_date.lte':end,'limit':1000,'sort':'execution_date','order':'asc'}))
        return {'results':rows,'raw_refs':refs}

    def dividends(self,ticker,start,end):
        rows,refs=self.paginate('/v3/reference/dividends?'+urlencode({'ticker':symbol(ticker),'ex_dividend_date.gte':start,'ex_dividend_date.lte':end,'limit':1000}))
        return {'results':rows,'raw_refs':refs}

    def quote(self,ticker):
        data,ref=self._page('/v2/last/nbbo/'+symbol(ticker));r=data.get('results',{})
        try:
            bid=number(r['p'],'bid',True);ask=number(r['P'],'ask',True)
            if ask<bid:raise ValueError('Crossed quote')
            at=stamp(number(r['t'])/1000000) # REST SIP nanoseconds -> milliseconds
        except (ValueError,KeyError,TypeError):raise SourceUnavailable('Missing / crossed NBBO') from None
        return {'ticker':ticker,'bid':bid,'ask':ask,'at':at,'raw_ref':ref,'spread_bps':(ask-bid)/((ask+bid)/2)*10000}

    def status(self):return self._page('/v1/marketstatus/now')[0]
    def holidays(self):return self._page('/v1/marketstatus/upcoming')[0]


def split_adjust(rows,actions,as_of):
    """Raw prices adjusted ONLY for splits effective by the observation time."""
    out=deepcopy(rows);day=dt(as_of).astimezone(ET).date().isoformat();used=[]
    for a in actions:
        ex=date.fromisoformat(a['execution_date']).isoformat()
        if ex>day:continue
        factor=number(a['split_from'],'split_from',True)/number(a['split_to'],'split_to',True)
        if factor==1:continue
        used.append(a)
        for row in out:
            if dt(stamp(row['t'])).astimezone(ET).date().isoformat()<ex:
                for k in ('o','h','l','c','vw'):
                    if row.get(k) is not None:row[k]*=factor
                row['v']/=factor
    return out,used


def build_snapshot(ticker,event_at,as_of,series,calendar,quote=None,data_mode='historical',family='GUIDANCE_CHANGE',splits=None,baseline_sessions=20,cluster_start=None):
    """Aligned completed minutes; no forward fill. Missing trading minutes fail closed.
    No-trade minutes are not invented: they are a coverage ambiguity for READY.
    All volume comparisons use equal elapsed regular-session minutes.
    """
    symbol(ticker)
    if data_mode not in ('historical','realtime','delayed','replay'):raise DomainError('Unknown data mode')
    event,now=dt(event_at),dt(as_of)
    if now<event:raise DomainError('as_of precedes event')
    if not 1<=baseline_sessions<=60:raise DomainError('Invalid volume baseline')
    sessions=calendar.get('sessions',[]);mapped=classify_session(event_at,calendar);errors=[]
    adjusted={};refs=[]
    for name in ('security','spy','sector'):
        data=series.get(name,{})
        if not data.get('pagination_complete') or data.get('adjusted') is not False:errors.append('DATA_RAW_BASIS_REQUIRED')
        if name=='security' and data.get('ticker')!=ticker:errors.append('DATA_SECURITY_MISMATCH')
        if name=='spy' and data.get('ticker')!='SPY':errors.append('DATA_BENCHMARK_MISMATCH')
        rows=[dict(r) for r in data.get('bars',[]) if r['t']+60000<=millis(as_of)]
        for row in rows:validate_bar(row)
        rows,actions=split_adjust(rows,(splits or {}).get(name,[]),as_of)
        adjusted[name]={r['t']:r for r in rows};refs.extend(data.get('raw_refs',[]))
        if len(adjusted[name])!=len(rows):errors.append('DATA_DUPLICATE_BAR')
    if not mapped.get('complete'):errors.append('DATA_CALENDAR_INCOMPLETE')
    event_session=next((s for s in sessions if dt(s['close'])>event),None)
    current=next((s for s in reversed(sessions) if dt(s['open'])<=now),None)
    anchor_session=next((s for s in reversed(sessions) if dt(s['close'])<=event),None)
    base={'ticker':ticker,'captured_at':as_of,'event_at':event_at,'data_mode':data_mode,'is_demo':False,'adjusted':True,'adjustment_consistent':not errors,'adjustment_policy':'unadjusted_input_plus_splits_effective_as_of','calendar':calendar,'calculation_version':'market-2','raw_refs':refs,'session':mapped.get('session'),'complete':False,'quality_errors':errors}
    def finish():
        base['quality_errors']=sorted(set(errors));base['complete']=not errors
        base['snapshot_id']='market-'+digest(base)[:24]
        return base
    if not event_session or not current or not anchor_session:
        errors.append('DATA_CALENDAR_INCOMPLETE');return finish()
    anchor_t=(millis(event_at)//60000)*60000-60000 if mapped.get('session')=='REGULAR' and event>dt(event_session['open']) else millis(anchor_session['close'])-60000
    end_t=min(millis(as_of)//60000*60000,millis(current['close']))-60000
    cur_start=millis(current['open']);event_start=millis(event_session['open'])
    if end_t<cur_start or end_t<event_start:errors.append('DATA_EVENT_OPEN_PENDING');return finish()
    required_times=set()
    for s in sessions:
        start=max(millis(s['open']),event_start);end=min(millis(s['close']),end_t+60000)
        if start<end:required_times.update(range(start,end,60000))
    missing={}
    for name,bars in adjusted.items():
        missing[name]=len((required_times|{anchor_t,end_t})-bars.keys())
    if any(missing.values()):errors.append('DATA_MARKET_WINDOW_INCOMPLETE')
    base['coverage']={'required_minutes':len(required_times),'missing_minutes':missing,'policy':'all regular-session minutes; absent minutes require review'}
    if any(anchor_t not in b or end_t not in b for b in adjusted.values()):return finish()
    stock=adjusted['security'];obs=stock[end_t];anchor=stock[anchor_t]
    current_rows=[stock[t] for t in range(cur_start,end_t+1,60000) if t in stock]
    ev_end=min(millis(event_session['close']),end_t+60000)
    ev_rows=[stock[t] for t in range(event_start,ev_end,60000) if t in stock]
    if not ev_rows:errors.append('DATA_EVENT_WINDOW_MISSING');return finish()
    # VWAP starts at the event for regular-session catalysts, otherwise at event session open.
    vwap_start=max(event_start,(millis(event_at)+59999)//60000*60000) if mapped['session']=='REGULAR' else event_start
    vwap_rows=[stock[t] for t in sorted(required_times) if t>=vwap_start and t in stock]
    if not vwap_rows or any(r.get('vw') is None for r in vwap_rows):errors.append('DATA_VWAP_MISSING')
    volume=sum(r['v'] for r in vwap_rows)
    vwap=sum((r.get('vw') or 0)*r['v'] for r in vwap_rows)/volume if volume and all(r.get('vw') is not None for r in vwap_rows) else None
    # Same-time volume baselines come strictly before the event, never future event days.
    elapsed=end_t+60000-cur_start;baseline=[]
    for s in reversed(sessions):
        if dt(s['close'])>event:continue
        if millis(s['close'])-millis(s['open'])<elapsed:continue
        times=range(millis(s['open']),millis(s['open'])+elapsed,60000)
        if all(t in stock for t in times):baseline.append(sum(stock[t]['v'] for t in times))
        if len(baseline)==baseline_sessions:break
    if len(baseline)<baseline_sessions:errors.append('DATA_VOLUME_BASELINE_INCOMPLETE')
    base.update(price=obs['c'],anchor_price=anchor['c'],spy_anchor=adjusted['spy'][anchor_t]['c'],spy_price=adjusted['spy'][end_t]['c'],sector_anchor=adjusted['sector'][anchor_t]['c'],sector_price=adjusted['sector'][end_t]['c'],sector_symbol=series['sector']['ticker'],volume=sum(r['v'] for r in current_rows),average_volume=mean(baseline) if baseline else None,vwap=vwap,event_high=max(r['h'] for r in ev_rows),event_low=min(r['l'] for r in ev_rows),previous_price=stock.get(end_t-60000,{}).get('c'),open_price=stock.get(event_start,{}).get('o'),regular_open_at=current['open'],captured_at=stamp(end_t+60000),session_closed=now>=dt(current['close']),close_price=obs['c'],volume_baseline={'n':len(baseline),'elapsed_minutes':elapsed//60000,'mean_volume':mean(baseline) if baseline else None})
    stop=anchor['c'];basis='事件前价格；确认后收盘跌破'
    if family in ('CAPITAL_RETURN','ACTIVIST_OWNERSHIP'):
        before=[r for t,r in stock.items() if millis(anchor_session['open'])<=t<millis(anchor_session['close'])]
        if len(before)!=(millis(anchor_session['close'])-millis(anchor_session['open']))//60000:errors.append('DATA_INVALIDATION_WINDOW_INCOMPLETE')
        stop=min((r['l'] for r in before),default=None);basis='事件前交易日最低价'
    elif family=='INSIDER_OPEN_MARKET_BUY':
        stop=None;basis='合资格买入集群起日至最终 Form 4 披露的常规交易时段最低价'
        if cluster_start is None:errors.append('DATA_CLUSTER_WINDOW_REQUIRED')
        else:
            start=date.fromisoformat(cluster_start)
            if not 0<=(event.astimezone(ET).date()-start).days<=10:raise DomainError('Invalid insider cluster window')
            times=set()
            for s in sessions:
                if dt(s['open']).astimezone(ET).date()>=start:
                    times.update(range(millis(s['open']),min(millis(s['close']),millis(event_at)//60000*60000),60000))
            if not times or not times.issubset(stock):errors.append('DATA_CLUSTER_WINDOW_INCOMPLETE')
            else:stop=min(stock[t]['l'] for t in times)
    base.update(invalidation_price=stop,invalidation_basis=basis,spread_bps=None,halted=False)
    if quote:
        bid=number(quote['bid'],'bid',True);ask=number(quote['ask'],'ask',True);age=(now-dt(quote['at'])).total_seconds()
        if quote.get('ticker')!=ticker or ask<bid or age<0 or age>300:errors.append('DATA_QUOTE_STALE_OR_INVALID')
        else:base.update(spread_bps=(ask-bid)/((ask+bid)/2)*10000,quote_at=quote['at'],bid=bid,ask=ask)
    elif data_mode=='realtime':errors.append('DATA_QUOTE_MISSING')
    # Computation can complete historically; READY still requires fresh realtime mode + quote.
    if base['spread_bps'] is None:base['spread_bps']=1000000
    # Do not derive VWAP from OHLC average, or carry forward missing prices/volumes.
    if vwap is None or not base['average_volume']:errors.append('DATA_CALCULATION_INPUT_MISSING')
    base['as_of']=as_of
    base['window_returns']={}
    next_open=millis(mapped['next_open']) if mapped.get('next_open') else None
    for label,target in [('event_30m',vwap_start+29*60000),('event_close',millis(event_session['close'])-60000),('next_open',next_open)]:
        if target is None:base['window_returns'][label]=None;continue
        if target<=end_t and all(target in b for b in adjusted.values()):
            field='o' if label=='next_open' else 'c'
            returns={k:(b[target][field]/b[anchor_t]['c']-1)*100 for k,b in adjusted.items()}
            base['window_returns'][label]={'raw_pct':returns['security'],'spy_excess_pct':returns['security']-returns['spy'],'sector_excess_pct':returns['security']-returns['sector'],'at':stamp(target+60000)}
        else:base['window_returns'][label]=None
    return finish()


def outcome_statistics(entry_price,entry_at,as_of,stock_daily,benchmark_daily,calendar,quantity=1,exit_price=None,fees=0,planned_loss=None,planned_entry=None):
    entry=number(entry_price,'entry',True);number(quantity,'quantity',True);number(fees,'fees')
    now=dt(as_of);at=dt(entry_at);sessions=[s for s in calendar['sessions'] if dt(s['open'])>=at and dt(s['close'])<=now]
    if now<at:raise DomainError('as_of precedes entry')
    def by_day(rows):
        result={}
        for r in rows:
            validate_bar(r);day=dt(stamp(r['t'])).astimezone(ET).date().isoformat();result[day]=r
        return result
    stocks,bench=by_day(stock_daily),by_day(benchmark_daily)
    entry_day=at.astimezone(ET).date().isoformat()
    # Entry-day intraday extrema can predate the fill; excluded rather than look ahead/back.
    days=[dt(s['open']).astimezone(ET).date().isoformat() for s in sessions]
    result={'horizons':{},'path_complete':all(d in stocks and d in bench for d in days),'path_basis':'full sessions starting at/after entry; entry-session pre-fill extrema excluded','mfe':None,'mae':None}
    b0=bench.get(entry_day)
    entry_session=next((s for s in calendar['sessions'] if dt(s['open']).astimezone(ET).date().isoformat()==entry_day),None)
    benchmark_entry=b0['o'] if b0 and entry_session and at==dt(entry_session['open']) else None
    for n in (1,5,10,20):
        day=days[n-1] if len(days)>=n else None;s=stocks.get(day);b=bench.get(day)
        value=(s['c']/entry-1)*100 if s else None
        result['horizons'][str(n)+'D']={'return_pct':value,'benchmark_excess_pct':value-(b['c']/benchmark_entry-1)*100 if value is not None and b and benchmark_entry else None,'at':day}
    path=[stocks[d] for d in days if d in stocks]
    if path and result['path_complete']:
        result['mfe']=max(0,(max(r['h'] for r in path)/entry-1)*100)
        result['mae']=min(0,(min(r['l'] for r in path)/entry-1)*100)
    if exit_price is not None:
        gross=(number(exit_price,'exit',True)-entry)*quantity
        result.update(realized_pnl=round(gross,2),net_pnl=round(gross-fees,2),fees=fees,r_multiple=(gross-fees)/planned_loss if planned_loss and planned_loss>0 else None)
    result['slippage_bps']=(entry/number(planned_entry,'planned_entry',True)-1)*10000 if planned_entry else None
    return result
