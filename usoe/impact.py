"""Explainable event-impact hypotheses, never calibrated price forecasts or orders."""
from .util import dt,digest
from .calendar import exchange_calendar

VERSION='event-impact-1'
LABELS={'BULLISH':'偏多','BEARISH':'偏空','MIXED':'多空分歧','NEUTRAL':'变化不明显','UNKNOWN':'暂不能判断'}
METRICS={'revenue_guidance':'营收指引中值','eps_guidance':'每股收益指引中值','gross_margin_guidance':'毛利率指引','operating_margin':'营业利润率'}

def assess(*,identity,ticker,catalyst,event_at,as_of,calculations,errors=(),reviewed=False,core=None,evidence=()):
    errors=list(errors)
    if dt(event_at)>dt(as_of):errors.append('事件时间晚于判断时点，禁止使用未来信息')
    reasons=[];positive=[];negative=[];unchanged=[]
    for c in calculations:
        if c.get('metric') not in METRICS or not isinstance(c.get('change'),(int,float)):continue
        v=c['change'];label=METRICS[c['metric']]
        reason={'text':f'{label}变化 {v:+.2f} {c["unit"]}（公司前后口径比较，并非股价预测）','metric':c['metric'],'change':v,'unit':c['unit'],'fact_ids':c.get('input_fact_ids',[])}
        reasons.append(reason)
        (positive if v>0 else negative if v<0 else unchanged).append(reason)
    direction='UNKNOWN'
    if reasons and not errors:
        direction='MIXED' if positive and negative else 'BULLISH' if positive else 'BEARISH' if negative else 'NEUTRAL'
    limitations=['未接入市场一致预期，无法判断是否超预期','规则尚未进行独立历史检验，不提供胜率或涨跌幅预测']
    if not reviewed:limitations.insert(0,'AI 提取事实尚未人工核对；方向仅为待验证线索')
    if errors:limitations.append('证据或比较口径未通过校验：'+'；'.join(errors))
    if not reasons:limitations.append('缺少可比较的前后指标；单期利润或现金流不能推断后续股价方向')
    market=(core or {}).get('reaction',{})
    conditions=(core or {}).get('entry_conditions',[])
    market_ready=bool(market.get('complete') and market.get('data_mode')=='realtime' and market.get('age_seconds',float('inf'))<=300)
    market_status='UNKNOWN';market_text='缺少完整且及时的行情，暂不能判断价格是否已反映事件'
    if market_ready:
        bucket=market.get('bucket')
        if bucket=='EXTENDED_REACTION':market_status='EXTENDED';market_text='价格反应已超过现有规则的候选区间，需防范追涨风险'
        elif bucket=='ADVERSE_REACTION':market_status='ADVERSE';market_text='价格相对板块反向反应，需核查事件解释'
        else:market_status='OBSERVED';market_text='已有及时行情可观察；涨跌本身不能证明消息已充分定价'
    else:limitations.append('最新行情缺失、受限或过期，不能判断当前入场条件')
    horizons=[]
    try:
        from datetime import timedelta
        event=dt(event_at)
        cal=exchange_calendar((event.date()-timedelta(days=7)).isoformat(),(event.date()+timedelta(days=60)).isoformat())
        closes=[x['close'] for x in cal['sessions'] if dt(x['close'])>event]
        for n in (1,5,20):
            end=closes[n-1]
            horizons.append({'sessions':n,'ends_at':end,'state':'ELAPSED' if dt(as_of)>=dt(end) else 'OPEN','probability_up':None,'expected_return_pct':None})
    except (ValueError,IndexError,ImportError):
        horizons=[{'sessions':n,'ends_at':None,'state':'CALENDAR_UNAVAILABLE','probability_up':None,'expected_return_pct':None} for n in (1,5,20)]
    invalidated=bool(core and core.get('invalidation_status') not in (None,[],['NONE']))
    elapsed=all(h['state']=='ELAPSED' for h in horizons)
    status='INVALIDATED' if invalidated else 'HISTORICAL' if elapsed else 'REVIEW_REQUIRED' if not reviewed else 'ASSESSED'
    next_step='核对原文中的数值、期间和会计口径' if not reviewed else '跟踪下一次披露与市场反馈'
    if direction=='UNKNOWN':next_step='补齐比较基准和证据，暂不作涨跌判断'
    if status in ('HISTORICAL','INVALIDATED'):next_step='用于复盘；不要作为当前机会'
    payload={'identity':identity,'ticker':ticker,'catalyst':catalyst,'event_at':event_at,'as_of':as_of,'rule_version':VERSION,'direction':direction,'direction_label':LABELS[direction],'status':status,'evidence_reviewed':reviewed,'reasons':reasons,'limitations':limitations,'horizons':horizons,'market':{'state':market_status,'text':market_text,'observed_return_pct':market.get('raw_return_pct') if market_ready else None,'observed_sector_excess_pct':market.get('sector_excess_pct') if market_ready else None},'conditions_missing':[c['label'] for c in conditions if not c['pass'] and c['id']!='portfolio'],'invalidation':['公司撤回或修正相关披露','后续数据推翻前后比较口径','观察期限结束后重新评估，不无限延长原判断'],'next_step':next_step,'evidence':list(evidence),'method':'未经统计校准的事件影响规则；不代表买卖建议','probability_up':None,'expected_return_pct':None}
    payload['input_hash']=digest({'calculations':calculations,'errors':list(errors),'reviewed':reviewed,'core':core,'evidence':list(evidence)})
    return payload


def record(store,cards):
    """Persist changed judgments, preserving an A→B→A history. Reads stay read-only."""
    from .util import canonical,utcnow
    from .storage import Store
    saved=0
    with store.transaction() as db:
        for card in cards:
            # Wall-clock as_of alone is not a new hypothesis; horizon and input changes are.
            fingerprint=digest({k:v for k,v in card.items() if k!='as_of'})
            previous=db.execute('SELECT fingerprint FROM impact_judgments WHERE entity_id=? ORDER BY id DESC LIMIT 1',(card['identity'],)).fetchone()
            if previous and previous['fingerprint']==fingerprint:continue
            db.execute('INSERT INTO impact_judgments(entity_id,fingerprint,snapshot_json,created_at) VALUES (?,?,?,?)',(card['identity'],fingerprint,canonical(card),utcnow()))
            Store.audit(db,'IMPACT_JUDGMENT_RECORDED',card['identity'],{'fingerprint':fingerprint,'rule_version':VERSION})
            saved+=1
    return saved
