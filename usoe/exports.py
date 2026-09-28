from __future__ import annotations
import csv
import io
from .util import canonical, digest, utcnow

AI_FIELDS={'ai_explanation','ai_summary','ai_notes','candidate_extraction'}

def core_only(value):
    if isinstance(value,dict): return {k:core_only(v) for k,v in value.items() if k not in AI_FIELDS}
    if isinstance(value,list): return [core_only(x) for x in value]
    return value

def envelope(payload, ai_mode, rule_version, exported_at=None):
    core=core_only(payload)
    return {'export_version':'1.0.2','exported_at':exported_at or utcnow(),'ai_mode':ai_mode,'core_output_hash':digest(core),'rule_version':rule_version,'source_snapshot':digest(core.get('evidence',core.get('items',[]))),'market_snapshot':digest(core.get('market_snapshot',{})),'portfolio_snapshot':digest(core.get('portfolio_snapshot',{})),'payload':core}

def markdown(data):
    p=data['payload']
    lines=['# Decision & Analysis Export','',f"Exported: {data['exported_at']}",f"Rule: {data['rule_version']} · AI mode: {data['ai_mode']}",f"Core SHA-256: {data['core_output_hash']}",f"Source snapshot: {data['source_snapshot']}",f"Market snapshot: {data['market_snapshot']}",f"Portfolio snapshot: {data['portfolio_snapshot']}",'']
    if p.get('is_demo'): lines+=['> SYNTHETIC DEMO. All companies, facts and prices are fictional.','']
    for title,key in [('Security','ticker'),('Opportunity State','state'),('Catalyst','catalyst'),('Evidence','evidence'),('Fundamental Changes','calculations'),('Price Reaction','reaction'),('Historical Context','historical_context'),('Entry Conditions','entry_conditions'),('Invalidation Conditions','invalidation_rules'),('Portfolio Context','portfolio'),('Risk Flags','risk_flags'),('Outcome History','outcome'),('Rule Version','rule_version')]:
        lines += ['## '+title,'','```json',canonical(p.get(key)), '```','']
    if 'items' in p: lines += ['## Items','','```json',canonical(p['items']),'```']
    return '\n'.join(lines)

def csv_export(data):
    p=data['payload']; rows=p.get('items',[p])
    output=io.StringIO(newline='')
    cols=['export_version','exported_at','rule_version','ai_mode','core_output_hash','source_snapshot','market_snapshot','portfolio_snapshot','opportunity_id','ticker','event_family','state','materiality','role','reason_codes','net_pnl','r_multiple','is_demo','record_json']
    w=csv.DictWriter(output,fieldnames=cols); w.writeheader()
    def safe(value):
        text=canonical(value) if isinstance(value,(dict,list)) else str(value if value is not None else '')
        return "'"+text if text.startswith(('=','+','-','@','\t','\r')) else text
    for row in rows:
        out={k:data.get(k,'') for k in cols[:8]}
        out.update({k:row.get(k,'') for k in cols[8:]})
        out['record_json']=canonical(core_only(row))
        w.writerow({k:safe(v) for k,v in out.items()})
    return output.getvalue()
