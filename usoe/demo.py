"""Entirely fictional, fixed-time replay data. Never masquerades as SEC filings."""
from copy import deepcopy
from datetime import date, timedelta
from .util import digest

AS_OF='2026-09-25T15:30:00+00:00'

def calendar():
    sessions=[]
    d=date(2026,8,1)
    while d<=date(2026,10,5):
        if d.weekday()<5 and d.isoformat()!='2026-09-07':
            sessions.append({'open':d.isoformat()+'T13:30:00+00:00','close':d.isoformat()+'T20:00:00+00:00'})
        d+=timedelta(days=1)
    return {'start':'2026-08-01','end':'2026-10-05','source':'SYNTHETIC_DEMO_CALENDAR','sessions':sessions}

def portfolio():
    return {'snapshot_id':'demo-portfolio-001','captured_at':AS_OF,'equity':100000,'cash':78000,'buying_power':78000,'reconciled':True,'account_ref':'LOCAL_PAPER','is_demo':True,'positions':[{'security_id':'sec-vela-d','ticker':'VELA.D','sector':'Healthcare','event_family':'EARNINGS_REVISION','quantity':200,'market_value':22000,'planned_loss':900}]}

def market(symbol,price=106):
    return {'ticker':symbol,'snapshot_id':'demo-market-'+symbol,'captured_at':AS_OF,'complete':True,'data_mode':'replay','is_demo':True,'adjusted':True,'adjustment_consistent':True,'anchor_price':100,'price':price,'spy_anchor':500,'spy_price':502,'sector_anchor':200,'sector_price':202,'volume':1560000,'average_volume':1000000,'vwap':104,'previous_price':103,'event_high':108,'event_low':98,'open_price':104,'regular_open_at':'2026-09-25T13:30:00+00:00','invalidation_price':100,'invalidation_basis':'事件前收盘价；确认后收盘跌破时失效','spread_bps':8,'halted':False,'calendar':calendar()}

def packet(symbol,name,family,typ,values,event_at='2026-09-24T20:10:00+00:00',sector='Technology'):
    identity=symbol.lower().replace('.','-')
    raw={'notice':'FICTIONAL SYNTHETIC DEMO — NOT A REAL COMPANY OR SEC FILING','ticker':symbol,'event_family':family,'event_type':typ,'facts':values}
    evidence_id='ev-'+identity
    facts=[]
    for k,v in values.items():
        unit='boolean' if isinstance(v,bool) else ('text' if isinstance(v,str) else ('percent' if 'margin' in k or k=='ownership_pct' else ('shares' if 'shares' in k else ('USD/share' if 'eps_guidance' in k else 'USD'))))
        facts.append({'fact_id':'fact-'+identity+'-'+k,'metric_id':k,'value':v,'unit':unit,'period_start':'2026-01-01','period_end':'2026-12-31','evidence_id':evidence_id,'fact_version':1,'locator':'/facts/'+k})
    catalysts={
        'GUIDANCE_CHANGE':'全年收入指引中值上调，等待量价与板块条件共同确认。',
        'EARNINGS_REVISION':'利润率指引改善；事件变化与初始价格反应需分别评估。',
        'CAPITAL_RETURN':'新的回购授权占市值的比例达到高重要性阈值。',
        'INSIDER_OPEN_MARKET_BUY':'多位内部人在窗口内以自有资金公开市场买入。',
        'ACTIVIST_OWNERSHIP':'13D 持股及主动治理意图形成待观察催化剂。',
        'FINANCING_DILUTION':'增发造成潜在摊薄，仅用于持仓风险复核。',
        'MATERIAL_CORPORATE_EVENT':'重大合同事件已识别，具体经济机制等待持续验证。',
        'MNA_SPECIAL':'已签署并购协议；仅展示条款和价差背景。'
    }
    return {'opportunity_id':'opp-'+identity,'event_id':'event-'+identity,'security':{'security_id':'sec-'+identity,'ticker':symbol,'cik':'0000000000','issuer_name':name,'sector':sector,'exchange':'DEMO'},'accession':'DEMO-'+identity,'form':'SYNTHETIC','event_family':family,'event_type':typ,'event_at':event_at,'catalyst':catalysts[family],'facts':facts,'evidence':[{'evidence_id':evidence_id,'level':'E1','locator':'JSON pointer /facts','excerpt':'本记录的全部数值来自本地合成演示原文，不对应真实 SEC 披露。','url':'demo://'+identity,'sha256':digest(raw),'verified':True,'source_id':'demo','raw_content':raw}],'is_demo':True,'historical_analogs':[]}

def fixtures():
    rows=[]
    def add(symbol,name,family,typ,values,price=106,**kw):
        p=packet(symbol,name,family,typ,values,**kw); m=market(symbol,price); rows.append((p,m)); return p,m
    add('NOVA.D','Nova Systems · 虚构公司','GUIDANCE_CHANGE','guidance_raised',{'prior_revenue_guidance_low':1000,'prior_revenue_guidance_high':1100,'current_revenue_guidance_low':1080,'current_revenue_guidance_high':1180})
    add('ARCO.D','Arco Platforms · 虚构公司','EARNINGS_REVISION','margin_expansion',{'prior_gross_margin_guidance':42,'current_gross_margin_guidance':43.5},price=120)
    p,m=add('BRIO.D','Brio Industrial · 虚构公司','CAPITAL_RETURN','buyback',{'authorization':800000000,'market_cap':10000000000,'balance_sheet_capacity':True,'execution_credibility':True},price=103,sector='Industrials')
    m['previous_price']=102
    add('VELA.D','Vela Health · 虚构公司','FINANCING_DILUTION','secondary',{'new_shares':12000000,'existing_shares':100000000},price=97,sector='Healthcare')
    add('ORBT.D','Orbit Energy · 虚构公司','MNA_SPECIAL','definitive_merger',{'definitive_agreement':True,'offer_price':115,'reference_price':106},sector='Energy')
    add('AXIS.D','Axis Robotics · 虚构公司','MATERIAL_CORPORATE_EVENT','material_contract',{'economic_mechanism':'合同带来已披露订单积压；收入确认仍待复核。'},sector='Industrials')
    add('LUMA.D','Luma Network · 虚构公司','GUIDANCE_CHANGE','guidance_raised',{'prior_revenue_guidance_low':1000,'prior_revenue_guidance_high':1000,'current_revenue_guidance_low':1060,'current_revenue_guidance_high':1080},event_at='2026-08-28T20:15:00+00:00')
    return rows
