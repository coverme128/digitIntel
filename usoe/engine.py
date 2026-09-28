"""Pure domain functions. No network, storage, AI, or clock dependencies."""
from __future__ import annotations
from statistics import median
from .util import number, dt, digest, floor_ratio, money
from .calendar import classify_session, trading_age
from .exports import core_only

FAMILIES = ('EARNINGS_REVISION','GUIDANCE_CHANGE','CAPITAL_RETURN','INSIDER_OPEN_MARKET_BUY','ACTIVIST_OWNERSHIP','MATERIAL_CORPORATE_EVENT','FINANCING_DILUTION','MNA_SPECIAL')
MATERIAL_TYPES = ('material_contract','asset_sale','major_restructuring','debt_refinancing','ceo_cfo_change','material_impairment','large_customer')
STATE_EDGES = {
    'DISCOVERED': {'VERIFIED','IGNORED'}, 'VERIFIED': {'QUALIFIED','IGNORED'},
    'QUALIFIED': {'WATCH','IGNORED'}, 'WATCH': {'READY','INVALIDATED','IGNORED'},
    'READY': {'WATCH','ENTERED','INVALIDATED','IGNORED'}, 'ENTERED': {'MANAGE'},
    'MANAGE': {'INVALIDATED','EXITED'}, 'INVALIDATED': {'EXITED'}, 'EXITED': set(), 'IGNORED': set()
}

def allowed_transition(before, after, actor):
    return after in STATE_EDGES.get(before,set()) and (after not in {'ENTERED','EXITED','IGNORED'} or actor == 'USER')

def percent_delta(old, new):
    old,new = number(old),number(new)
    return None if old == 0 else round((new-old)/abs(old)*100,6)

def bucket(value, low, high, very):
    if value < low: return 'LOW'
    if value < high: return 'MEDIUM'
    if value <= very: return 'HIGH'
    return 'VERY_HIGH'

def facts_by_metric(packet):
    return {f['metric_id']:f['value'] for f in packet.get('facts',[])}

def fundamentals(packet):
    facts = {f['metric_id']:f for f in packet.get('facts',[])}
    result, errors = [], []
    for metric, thresholds in [('revenue_guidance',(3,5,10)),('eps_guidance',(5,10,20))]:
        ids = [f'{era}_{metric}_{end}' for era in ('prior','current') for end in ('low','high')]
        present = [k in facts for k in ids]
        if not any(present): continue
        if not all(present):
            errors.append('DATA_FIELDS_MISSING'); continue
        rows = [facts[k] for k in ids]
        if len({(r['period_start'],r['period_end']) for r in rows}) != 1:
            errors.append('DATA_PERIOD_MISMATCH'); continue
        if len({r['unit'] for r in rows}) != 1:
            errors.append('DATA_UNIT_MISMATCH'); continue
        a,b,c,d = [number(r['value']) for r in rows]
        if a>b or c>d:
            errors.append('DATA_RANGE_INVALID'); continue
        old,new = (a+b)/2,(c+d)/2
        change = percent_delta(old,new)
        if change is None:
            errors.append('DATA_ZERO_BASE'); continue
        result.append({'metric':metric,'old':old,'new':new,'change':change,'unit':'%','bucket':bucket(abs(change),*thresholds),'input_fact_ids':[r['fact_id'] for r in rows], 'formula':'((new_low+new_high)/2 - (old_low+old_high)/2) / abs((old_low+old_high)/2) * 100'})
    for metric in ('gross_margin_guidance','operating_margin'):
        keys = [f'{era}_{metric}' for era in ('prior','current')]
        if not all(k in facts for k in keys): continue
        a,b = [facts[k] for k in keys]
        if a['unit'] != 'percent' or b['unit'] != 'percent':
            errors.append('DATA_UNIT_MISMATCH'); continue
        if (a['period_start'],a['period_end']) != (b['period_start'],b['period_end']):
            errors.append('DATA_PERIOD_MISMATCH'); continue
        change = round((number(b['value'])-number(a['value']))*100,6)
        result.append({'metric':metric,'old':a['value'],'new':b['value'],'change':change,'unit':'bps','bucket':bucket(abs(change),50,100,200),'input_fact_ids':[a['fact_id'],b['fact_id']], 'formula':'(new_margin_percent - old_margin_percent) * 100'})
    f = facts_by_metric(packet)
    for pair in [('authorization','market_cap'),('new_shares','existing_shares'),('offer_price','reference_price')]:
        if all(k in facts for k in pair) and facts[pair[0]]['unit'] != facts[pair[1]]['unit']:
            errors.append('DATA_UNIT_MISMATCH')
    if 'operating_cash_flow' in f and 'capex' in f:
        a,b = facts['operating_cash_flow'],facts['capex']
        if (a['period_start'],a['period_end'],a['unit']) != (b['period_start'],b['period_end'],b['unit']):
            errors.append('DATA_PERIOD_MISMATCH')
        else:
            result.append({'metric':'free_cash_flow','new':number(a['value'])-abs(number(b['value'])),'unit':a['unit'],'input_fact_ids':[a['fact_id'],b['fact_id']], 'formula':'operating_cash_flow - abs(capex)'})
    return result, sorted(set(errors))

def materiality(packet, calculations):
    f = facts_by_metric(packet)
    family,typ = packet['event_family'],packet['event_type']
    role, level, qualifies, reason = 'ENTRY_CANDIDATE','LOW',False,'NOT_MATERIAL'
    adverse = f.get('guidance_withdrawn') or f.get('thesis_breaking') or typ in ('restatement','going_concern','bankruptcy')
    if family in ('GUIDANCE_CHANGE','EARNINGS_REVISION'):
        changes = [c for c in calculations if 'bucket' in c]
        levels = [c['bucket'] for c in changes]
        rank = {'LOW':0,'MEDIUM':1,'HIGH':2,'VERY_HIGH':3}
        level = max(levels,key=lambda v:rank[v],default='LOW')
        qualifies = any(x in ('HIGH','VERY_HIGH') for x in levels) or levels.count('MEDIUM') >= 2
        if f.get('first_positive_fcf_guidance') or f.get('decline_to_growth'):
            level,qualifies = 'HIGH',True
        if any(c.get('change',0)<0 for c in changes): role = 'POSITION_RISK'
        reason = 'MATERIAL_GUIDANCE_CHANGE' if family == 'GUIDANCE_CHANGE' else 'MATERIAL_EARNINGS_INFLECTION'
    elif family == 'CAPITAL_RETURN':
        if typ == 'ordinary_dividend': role = 'CONTEXT_ONLY'
        elif f.get('market_cap',0)>0 and 'authorization' in f:
            ratio = f['authorization']/f['market_cap']*100
            level = bucket(ratio,2,5,10)
            qualifies = ratio>=5 or (ratio>=2 and f.get('execution_credibility') is True and f.get('balance_sheet_capacity') is True)
            if f.get('leverage_stress') or f.get('offsetting_dilution') or f.get('balance_sheet_capacity') is False: qualifies=False
            calculations.append({'metric':'buyback_to_market_cap','new':round(ratio,6),'unit':'%','formula':'authorization / market_cap * 100','input_fact_ids':[r['fact_id'] for r in packet['facts'] if r['metric_id'] in ('authorization','market_cap')]})
            reason = 'MATERIAL_BUYBACK'
    elif family == 'INSIDER_OPEN_MARKET_BUY':
        trades = packet.get('insider_transactions',[])
        valid = [t for t in trades if t.get('code')=='P' and t.get('acquired_disposed')=='A' and t.get('derivative') is False and t.get('evidence_id') in {e['evidence_id'] for e in packet['evidence']} and dt(t['at'])<=dt(packet['event_at']) and (dt(packet['event_at'])-dt(t['at'])).days<=10]
        people = {t['owner_id'] for t in valid}
        total = sum(number(t['value']) for t in valid)
        executive = any(t.get('title') in ('CEO','CFO','Chair') for t in valid)
        directors = {t['owner_id'] for t in valid if t.get('title')=='Director'}
        cluster = len(people)>=2 and total>=500000 and (executive or len(directors)>=3)
        single_high = max((sum(t['value'] for t in valid if t['owner_id']==p) for p in people),default=0)>500000
        level = 'HIGH' if cluster or single_high else ('MEDIUM' if total>=100000 else 'LOW')
        qualifies = cluster or single_high
        calculations.append({'metric':'insider_cluster','new':total,'unit':'USD','cluster_pass':cluster,'qualifying_insiders':len(people),'formula':'sum(qualifying code P / A non-derivative purchases within 10 calendar days)'})
        if not valid: role='CONTEXT_ONLY'
        reason='MATERIAL_INSIDER_BUY'
    elif family == 'ACTIVIST_OWNERSHIP':
        qualifies = f.get('ownership_pct',0)>=5 and f.get('active_intent') is True and typ!='passive_13g'
        level='HIGH' if qualifies and f.get('explicit_activist_purpose') else ('MEDIUM' if qualifies else 'LOW')
        if typ=='passive_13g': role='CONTEXT_ONLY'
        reason='MATERIAL_ACTIVIST_EVENT'
    elif family == 'FINANCING_DILUTION':
        role='POSITION_RISK'
        if f.get('existing_shares',0)>0 and 'new_shares' in f:
            ratio=f['new_shares']/f['existing_shares']*100
            level=bucket(ratio,3,7,15); qualifies=ratio>=3
            calculations.append({'metric':'potential_dilution','new':round(ratio,6),'unit':'%','formula':'new_shares / existing_shares * 100'})
        reason='MATERIAL_FINANCING'
    elif family == 'MNA_SPECIAL':
        role='CONTEXT_ONLY'; level='HIGH' if f.get('definitive_agreement') else 'LOW'
        if f.get('offer_price',0)>0 and f.get('reference_price',0)>0:
            calculations.append({'metric':'deal_spread','new':round((f['offer_price']/f['reference_price']-1)*100,6),'unit':'%','formula':'(offer_price / reference_price - 1) * 100'})
        reason='MATERIAL_MNA_EVENT'
    elif family == 'MATERIAL_CORPORATE_EVENT':
        qualifies=typ in MATERIAL_TYPES and bool(f.get('economic_mechanism'))
        level='HIGH' if qualifies else 'LOW'
        reason='MATERIAL_CORPORATE_EVENT'
    if adverse:
        role,level,qualifies='POSITION_RISK','MATERIAL_RISK',True
    return {'bucket':level,'role':role,'qualifies':bool(qualifies),'reason':reason if qualifies or role!='ENTRY_CANDIDATE' else 'NOT_MATERIAL'}

def reaction(market, as_of):
    required=('anchor_price','price','spy_anchor','spy_price','sector_anchor','sector_price','volume','average_volume','vwap','event_high','event_low')
    if not market or not market.get('complete') or any(k not in market for k in required):
        return {'complete':False,'bucket':'PENDING','reason':'DATA_MARKET_WINDOW_INCOMPLETE'}
    try:
        for key in required: number(market[key],key,True)
        age=(dt(as_of)-dt(market['captured_at'])).total_seconds()
        if age<0: return {'complete':False,'bucket':'PENDING','reason':'DATA_FUTURE_SNAPSHOT'}
        raw=(market['price']/market['anchor_price']-1)*100
        spy=(market['spy_price']/market['spy_anchor']-1)*100
        sector=(market['sector_price']/market['sector_anchor']-1)*100
        excess=raw-sector
        category='ADVERSE_REACTION' if excess<0 else ('EXTENDED_REACTION' if excess>15 else ('CAUTION' if excess>8 else 'BALANCED_REACTION'))
        return {'complete':True,'bucket':category,'raw_return_pct':round(raw,6),'spy_excess_pct':round(raw-spy,6),'sector_excess_pct':round(excess,6),'sector_return_pct':round(sector,6),'relative_volume':round(market['volume']/market['average_volume'],4),'vwap_relation':'ABOVE' if market['price']>=market['vwap'] else 'BELOW','gap_pct':percent_delta(market['anchor_price'],market.get('open_price',market['price'])),'event_range_pct':(market['event_high']-market['event_low'])/market['anchor_price']*100,'age_seconds':age,'data_mode':market.get('data_mode','unknown'),'adjusted':market.get('adjusted'),'snapshot_id':market.get('snapshot_id')}
    except (ValueError,KeyError,TypeError,ZeroDivisionError):
        return {'complete':False,'bucket':'PENDING','reason':'DATA_MARKET_WINDOW_INCOMPLETE'}

def analogs(rows, event_at, family):
    # Outcome must already have been observable before this event.
    valid=[r for r in rows if r.get('event_family')==family and dt(r['event_at'])<dt(event_at) and dt(r['outcome_known_at'])<=dt(event_at)]
    n=len(valid)
    if n<10: return {'n':n,'status':'INSUFFICIENT_SAMPLE','cases':valid[:9],'statistics':None}
    stats={}
    for k in ('return_1d','return_5d','return_10d','return_20d','excess_5d','mfe','mae'):
        values=[r[k] for r in valid if isinstance(r.get(k),(int,float))]
        stats[k]={'n':len(values),'median':median(values) if len(values)>=10 else None,'min':min(values) if len(values)>=10 else None,'max':max(values) if len(values)>=10 else None}
    return {'n':n,'status':'LOW_SAMPLE' if n<30 else 'DESCRIPTIVE_ONLY','statistics':stats,'matching':'same_family; point-in-time only'}

def risk_worksheet(security, family, market, portfolio, as_of, rules, quantity=None, entry=None, stop=None):
    hard,warnings=[],[]
    p=portfolio or {}
    equity=p.get('equity',0)
    if not equity or equity<=0: hard.append('RISK_EQUITY_UNKNOWN')
    age=(dt(as_of)-dt(p['captured_at'])).total_seconds() if p.get('captured_at') else None
    if age is None or age<0 or age>rules['portfolio_max_age_seconds']: hard.append('DATA_BROKER_STALE')
    if p.get('reconciled') is not True: hard.append('RISK_BROKER_RECONCILIATION')
    if p.get('buying_power') is None: hard.append('RISK_BUYING_POWER')
    if p.get('duplicate_order_uncertainty'): hard.append('RISK_DUPLICATE_ORDER')
    if market.get('halted'): hard.append('RISK_SECURITY_HALTED')
    price=entry if entry is not None else market.get('price')
    invalidation=stop if stop is not None else market.get('invalidation_price')
    if not price or not invalidation or invalidation>=price or invalidation<=0: hard.append('RISK_INVALIDATION_MISSING')
    position_value=sector_value=catalyst_value=open_risk=0
    for pos in p.get('positions',[]):
        v=pos.get('market_value',0)
        if pos.get('security_id')==security['security_id']: position_value+=v
        if pos.get('sector')==security['sector']: sector_value+=v
        if pos.get('event_family')==family: catalyst_value+=v
        open_risk+=pos.get('planned_loss',0)
        if pos.get('security_id')!=security['security_id'] and pos.get('correlation_group') and pos.get('correlation_group')==security.get('correlation_group'): warnings.append('RISK_CORRELATED_HOLDINGS')
    if p.get('event_clustering'): warnings.append('RISK_EVENT_CLUSTERING')
    risk=rules['risk']; sizing=None
    if equity>0 and price and invalidation and 0<invalidation<price:
        per_share=price-invalidation
        limits={'risk':floor_ratio(equity*risk['planned_loss_default_pct']/100,per_share),'single_name':floor_ratio(max(0,equity*risk['single_name_hard_pct']/100-position_value),price),'sector':floor_ratio(max(0,equity*risk['sector_hard_pct']/100-sector_value),price),'catalyst':floor_ratio(max(0,equity*risk['catalyst_hard_pct']/100-catalyst_value),price),'open_risk':floor_ratio(max(0,equity*risk['open_risk_hard_pct']/100-open_risk),per_share),'buying_power':floor_ratio(max(0,p.get('buying_power') or 0),price),'cash':floor_ratio(max(0,p.get('cash') or 0),price)}
        shares=max(0,min(limits.values())) if quantity is None else quantity
        capital=shares*price; loss=shares*per_share
        exposures={'single_name':(position_value+capital)/equity*100,'sector':(sector_value+capital)/equity*100,'catalyst':(catalyst_value+capital)/equity*100,'open_risk':(open_risk+loss)/equity*100}
        for key,label in [('single_name','RISK_POSITION_CONCENTRATION'),('sector','RISK_SECTOR_CONCENTRATION'),('catalyst','RISK_DUPLICATE_THESIS'),('open_risk','RISK_OPEN_RISK')]:
            if exposures[key]>risk[f'{key}_hard_pct']+1e-8: hard.append(label)
            elif exposures[key]>risk[f'{key}_warning_pct']: warnings.append(label)
        if loss/equity*100>risk['planned_loss_hard_pct']+1e-8: hard.append('RISK_PLANNED_LOSS')
        if capital>(p.get('buying_power') or 0) or capital>(p.get('cash') or 0): hard.append('RISK_BUYING_POWER')
        if shares<=0: hard.append('RISK_ZERO_CAPACITY')
        sizing={'entry':price,'invalidation':invalidation,'per_share_risk':round(per_share,6),'max_shares':max(0,min(limits.values())),'quantity':shares,'limits':limits,'planned_capital':money(capital),'planned_loss':money(loss),'risk_budget':money(equity*risk['planned_loss_default_pct']/100),'post_entry_exposure_pct':exposures}
    if hard and sizing: sizing['executable']=False
    elif sizing: sizing['executable']=True
    return {'hard_blocks':sorted(set(hard)),'warnings':sorted(set(warnings)),'sizing':sizing,'snapshot_id':p.get('snapshot_id'),'status':'BLOCKED' if hard else ('WARNING' if warnings else 'PASS')}

def evaluate(packet, market, portfolio, rules, as_of):
    packet,market,portfolio=core_only(packet),core_only(market),core_only(portfolio)
    security=packet['security']; family=packet['event_family']; f=facts_by_metric(packet)
    calculations,quality_errors=fundamentals(packet)
    m=materiality(packet,calculations)
    r=reaction(market,as_of)
    cal=market.get('calendar',{})
    session=classify_session(packet['event_at'],cal)
    age=trading_age(packet['event_at'],as_of,cal)
    evidence=packet.get('evidence',[])
    evidence_ok=bool(evidence) and all(e.get('verified') and e.get('level') in ('E1','E2') and e.get('sha256') for e in evidence)
    evidence_ids={e['evidence_id'] for e in evidence}
    evidence_ok=evidence_ok and all(x.get('evidence_id') in evidence_ids for x in packet.get('facts',[]))
    if f.get('contradiction'): quality_errors.append('EVIDENCE_CONTRADICTED')
    if market.get('ticker') != security['ticker']: quality_errors.append('DATA_SECURITY_MISMATCH')
    if not market.get('adjustment_consistent',False): quality_errors.append('DATA_ADJUSTMENT_UNKNOWN')
    if not session['complete'] or age is None: quality_errors.append('DATA_CALENDAR_INCOMPLETE')
    if dt(packet['event_at'])>dt(as_of): quality_errors.append('DATA_FUTURE_EVENT')
    fresh=r.get('age_seconds',float('inf'))<=rules['market_max_age_seconds'] and r.get('data_mode') in ('realtime','replay')
    risk=risk_worksheet(security,family,market,portfolio,as_of,rules)
    historical=analogs(packet.get('historical_analogs',[]),packet['event_at'],family)
    expiry=rules['expiry_sessions'][family]
    invalid=[]
    if age is not None and age>=expiry: invalid.append('INVALID_TIME_EXPIRED')
    if f.get('guidance_withdrawn'): invalid.append('INVALID_CATALYST_WITHDRAWN')
    if f.get('thesis_breaking') or f.get('guidance_reversal') or f.get('active_intent_withdrawn') or f.get('liquidity_deterioration') or f.get('offsetting_dilution'): invalid.append('INVALID_FUNDAMENTAL')
    if f.get('data_correction'): invalid.append('INVALID_DATA_CORRECTION')
    invalid_price=market.get('invalidation_price')
    if market.get('session_closed') and invalid_price and market.get('close_price',float('inf'))<invalid_price: invalid.append('INVALID_PRICE')
    reasons=[]
    reasons.append('EVIDENCE_OFFICIAL_CONFIRMED' if evidence_ok else 'EVIDENCE_MISSING')
    reasons.extend(quality_errors or ['DATA_COMPLETE'])
    reasons.append(m['reason'])
    if not r['complete']: reasons.append(r['reason'])
    elif not fresh: reasons.append('DATA_STALE')
    reasons.append({'BALANCED_REACTION':'REACTION_BALANCED','EXTENDED_REACTION':'REACTION_EXTENDED','ADVERSE_REACTION':'REACTION_ADVERSE','CAUTION':'REACTION_FOLLOW_THROUGH_REQUIRED','PENDING':'REACTION_PENDING'}[r['bucket']])
    reasons.extend(risk['hard_blocks']+risk['warnings'])
    reasons.extend(invalid)
    common=[('official_evidence',evidence_ok,'官方证据与数字可追溯'),('market_complete',r['complete'],'市场及基准窗口完整'),('market_fresh',fresh,'价格与数据时效通过'),('reaction',r['bucket']=='BALANCED_REACTION','未过度反应、无反向反应'),('portfolio',not risk['hard_blocks'],'组合风险未触及硬限制'),('invalidation',not invalid,'无已触发的失效条件'),('quality',not quality_errors,'单位、期间及交易日历一致'),('tradable',not market.get('halted') and market.get('spread_bps',float('inf'))<=rules['max_spread_bps'],'可交易且买卖价差不超过 30 bps')]
    opened=market.get('regular_open_at')
    gap_clear=bool(opened) and (dt(as_of)-dt(opened)).total_seconds()>=300
    common.append(('opening_guard',gap_clear,'开盘至少 5 分钟后确认'))
    price=market.get('price',0); vwap=market.get('vwap',float('inf'))
    reclaim=market.get('previous_price',float('inf'))<vwap<=price
    breakout=price>market.get('event_high',float('inf')) and market.get('previous_price',0)>=market.get('anchor_price',float('inf')) and age is not None and age>=1
    conditions=[]
    if family in ('GUIDANCE_CHANGE','EARNINGS_REVISION'):
        conditions=[('high_change',m['bucket'] in ('HIGH','VERY_HIGH'),'至少一项 HIGH 变化'),('price_vwap',price>=vwap,'价格站稳或收复事件 VWAP'),('volume',r.get('relative_volume',0)>=1.25,'相对成交量 ≥ 1.25×'),('sector',r.get('sector_return_pct',-100)>=rules['sector_strength_min_pct'],'板块相对强度未显著恶化')]
    elif family=='CAPITAL_RETURN':
        ratio=f.get('authorization',0)/f['market_cap']*100 if f.get('market_cap',0)>0 else 0
        conditions=[('authorization',ratio>=5,'回购授权 / 市值 ≥ 5%'),('capacity',f.get('balance_sheet_capacity') is True,'资产负债表承受能力已核实'),('extension',r.get('raw_return_pct',100)<=10,'价格距事件前收盘不超过 10%'),('pattern',breakout or reclaim,'随后突破事件高点或回踩收复 VWAP')]
    elif family=='INSIDER_OPEN_MARKET_BUY':
        cluster=next((c.get('cluster_pass',False) for c in calculations if c['metric']=='insider_cluster'),False)
        conditions=[('cluster',cluster,'10 天内合资格高管集群买入'),('pattern',reclaim,'最终 Form 4 后回踩收复 VWAP')]
    elif family=='ACTIVIST_OWNERSHIP':
        conditions=[('intent',f.get('active_intent') is True,'Item 4 明确主动意图'),('ownership',f.get('ownership_pct',0)>=5,'持股 ≥ 5%'),('pattern',reclaim,'回踩后收复 VWAP')]
    else:
        conditions=[('subtype_rule',False,'此事件无已验证的入场规则，仅观察 / 风险提示')]
    all_conditions=[{'id':k,'pass':bool(v),'label':label} for k,v,label in common+conditions]
    basic=evidence_ok and m['qualifies'] and not quality_errors and r['complete'] and m['role']=='ENTRY_CANDIDATE'
    desired='DISCOVERED' if not evidence_ok else 'VERIFIED'
    if basic: desired='WATCH'
    ready=basic and all(x['pass'] for x in all_conditions)
    if ready: desired='READY'
    if invalid and basic: desired='INVALIDATED'
    trigger='READY' if ready else ('READY_BLOCKED' if basic and risk['hard_blocks'] else 'NOT_READY')
    reasons.append('TRIGGER_READY' if ready else 'TRIGGER_NOT_READY')
    rule_version=rules['rule_version']
    for c in calculations: c['rule_version']=rule_version
    core={'opportunity_id':packet['opportunity_id'],'security_id':security['security_id'],'ticker':security['ticker'],'issuer_name':security['issuer_name'],'sector':security['sector'],'rule_version':rule_version,'calculation_version':rules['calculation_version'],'data_snapshot_version':digest([packet,market,portfolio]),'event_id':packet['event_id'],'event_family':family,'event_type':packet['event_type'],'event_at':packet['event_at'],'catalyst':packet['catalyst'],'role':m['role'],'materiality':m['bucket'],'state':desired,'reason_codes':sorted(set(reasons)),'evidence':evidence,'evidence_quality':'CONFIRMED' if evidence_ok else 'REVIEW_REQUIRED','facts':packet.get('facts',[]),'calculations':calculations,'reaction':r,'session':session,'historical_context':historical,'entry_conditions':all_conditions,'trigger_status':trigger,'invalidation_rules':{'price':invalid_price,'basis':market.get('invalidation_basis','未提供'),'expiry_trading_sessions':expiry,'elapsed_trading_sessions':age,'fundamental':'指引撤回 / 逻辑破坏 / 数据修正 / 主动意图撤回'},'invalidation_status':invalid or ['NONE'],'holding_window':f'最多 {expiry} 个交易日等待确认；持仓按 thesis 管理','portfolio':risk,'portfolio_snapshot':portfolio,'market_snapshot':market,'risk_flags':risk['hard_blocks']+risk['warnings'],'data_quality':'COMPLETE' if not quality_errors and r['complete'] and fresh else 'INCOMPLETE','outcome':None,'as_of':as_of,'is_demo':bool(packet.get('is_demo'))}
    return core
