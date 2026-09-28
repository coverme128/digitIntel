"""Personal research workflow, deliberately independent of execution eligibility."""
import json
import threading
from copy import deepcopy
from .ai import DeepSeek
from .util import canonical,digest,utcnow,dt,DomainError
from .validation import validate_fact,REGISTRY
from .engine import evaluate
from .storage import Store

DEFAULTS={'families':['GUIDANCE_CHANGE','EARNINGS_REVISION'],'watchlist_only':True,'auto_extract':False,'security_ids':None}

class Research:
    def __init__(self,service,integrations=None,ai=None):
        self.s=service;self.store=service.store;self.integrations=integrations;self.ai=ai or DeepSeek(service);self.lock=threading.Lock()

    def preferences(self):return self.store.setting('research_preferences',DEFAULTS)

    def save_preferences(self,body):
        from .engine import FAMILIES
        families=body.get('families')
        if not isinstance(families,list) or not families or any(x not in FAMILIES for x in families):raise DomainError('请选择至少一个有效事件族')
        if type(body.get('watchlist_only')) is not bool or type(body.get('auto_extract')) is not bool:raise DomainError('Invalid preferences')
        ids=body.get('security_ids',self.preferences().get('security_ids'))
        registered={r['id'] for r in self.store.query('SELECT id FROM securities')}
        if ids is not None and (not isinstance(ids,list) or any(not isinstance(x,str) or x not in registered for x in ids)):raise DomainError('请选择已注册的证券')
        value={k:body[k] for k in ('families','watchlist_only','auto_extract')};value['security_ids']=ids
        with self.store.transaction() as db:Store.set_setting(db,'research_preferences',value);Store.audit(db,'RESEARCH_PREFERENCES','research',value)
        return value

    @staticmethod
    def research_state(core):
        conditions=[x for x in core['entry_conditions'] if x['id']!='portfolio']
        if core['invalidation_status']!=['NONE']:state='INVALIDATED'
        elif core['role']!='ENTRY_CANDIDATE':state='CONTEXT'
        elif core['evidence_quality']!='CONFIRMED':state='NEEDS_REVIEW'
        elif core['materiality'] in ('HIGH','VERY_HIGH') and conditions and all(x['pass'] for x in conditions):state='RESEARCH_READY'
        else:state='RESEARCH_WATCH'
        return {'state':state,'conditions':conditions,'execution_state':core['state'],'execution_blockers':core['portfolio']['hard_blocks'],'note':'研究状态不代表可执行入场，不绕过账户风控。'}

    def dashboard(self):
        prefs=self.preferences();day=self.s.now()[:10]
        members={r['security_id'] for r in self.store.query('SELECT DISTINCT security_id FROM universe_memberships WHERE valid_from<=? AND (valid_to IS NULL OR valid_to>?)',(day,day))}
        items=[]
        for c in self.s.list():
            if c['event_family'] not in prefs['families'] or c['state'] in ('IGNORED','EXITED'):continue
            if prefs['watchlist_only'] and not self.s.demo and c['security_id'] not in members:continue
            if prefs.get('security_ids') is not None and c['security_id'] not in prefs['security_ids']:continue
            row=self.store.query('SELECT input_json FROM evaluations WHERE id=?',(c['evaluation_id'],))[0]
            inputs=json.loads(row['input_json']);inputs.update(as_of=self.s.now(),portfolio=self.s.portfolio())
            fresh=evaluate(**inputs);fresh['state']=c['state']
            items.append({'opportunity_id':c['opportunity_id'],'ticker':c['ticker'],'catalyst':c['catalyst'],'event_family':c['event_family'],'event_at':c['event_at'],'materiality':fresh['materiality'],'reaction':fresh['reaction'],'research':self.research_state(fresh),'is_demo':self.s.demo})
        drafts=[json.loads(r['data_json'])|{'id':r['id'],'status':r['status']} for r in self.store.query("SELECT * FROM research_drafts ORDER BY created_at DESC LIMIT 100")]
        notices=[r|{'data':json.loads(r['data_json'])} for r in self.store.query('SELECT * FROM research_notices ORDER BY created_at DESC LIMIT 50')]
        return {'securities':self.store.query('SELECT id,ticker,issuer_name FROM securities ORDER BY ticker'),'items':items,'drafts':drafts,'preferences':prefs,'ai':self.ai.status(),'notices':notices,'last_run':self.store.setting('research_last_run'),'as_of':self.s.now(),'is_demo':self.s.demo}

    def notice(self,kind,entity,data):
        identity=digest([kind,entity,data])
        with self.store.transaction() as db:db.execute('INSERT OR IGNORE INTO research_notices VALUES (?,?,?,?,?,NULL)',(identity,kind,entity,canonical(data),utcnow()))

    def documents(self,filing_id):
        rows=self.store.query('SELECT * FROM filings WHERE id=?',(filing_id,))
        if not rows:raise DomainError('Filing not found','NOT_FOUND',404)
        filing=rows[0]
        older=self.store.query('SELECT * FROM filings WHERE security_id=? AND accepted_at<? AND form IN (\'8-K\',\'10-Q\',\'10-K\') ORDER BY accepted_at DESC LIMIT 1',(filing['security_id'],filing['accepted_at']))
        docs=[]
        selected=[]
        for f in [filing]+older:
            selected.append((f,f['raw_document_id']))
            selected.extend((f,r['raw_document_id']) for r in self.store.query('SELECT raw_document_id FROM filing_documents WHERE filing_id=? ORDER BY raw_document_id LIMIT 5',(f['id'],)))
        budget=160000
        for f,rid in selected:
            if budget<=0:break
            raw=self.store.query('SELECT * FROM raw_documents WHERE id=?',(rid,))[0]
            if raw['source_id']!='sec' or raw['is_demo']:raise DomainError('Only archived public SEC documents can be extracted')
            text=bytes(raw['content']).decode('utf-8',errors='replace')
            limit=min(40000,budget);budget-=min(len(text),limit)
            docs.append({'raw_document_id':raw['id'],'accepted_at':f['accepted_at'],'form':f['form'],'text':text[:limit],'truncated':len(text)>limit})
        return filing,docs

    def extract(self,filing_id):
        if self.s.demo:raise DomainError('披露提取请使用独立真实数据工作区','WORKSPACE_MISMATCH',409)
        if not self.ai.status()['enabled']:raise DomainError('请先开启 AI Assist','AI_OFF',409)
        if not self.ai.status()['configured']:raise DomainError('请配置 DEEPSEEK_API_KEY','AI_NOT_CONFIGURED',409)
        filing,docs=self.documents(filing_id)
        artifact=self.ai.generate('extract',{'documents':docs,'metric_registry':REGISTRY['units'],'allowed_families':['GUIDANCE_CHANGE','EARNINGS_REVISION']})
        output=artifact['output'];draft={'filing_id':filing_id,'artifact_id':artifact['artifact_id'],'candidate':output,'documents':[dict(d,text=None) for d in docs],'requires_user_review':True}
        draft['validation_errors']=self.validate_candidate(filing,output)[0]
        identity=digest([filing_id,artifact['artifact_id']])
        with self.store.transaction() as db:db.execute('INSERT OR IGNORE INTO research_drafts VALUES (?,?,?,?,?)',(identity,filing_id,'REVIEW_REQUIRED',canonical(draft),utcnow()))
        self.notice('DRAFT_REVIEW_REQUIRED',identity,{'message':'DeepSeek 提取已完成，请核对指标含义、期间与原文。'})
        return draft|{'id':identity,'status':'REVIEW_REQUIRED'}

    def validate_candidate(self,filing,candidate):
        errors=[];facts=[];evidence=[];seen=set()
        if candidate.get('event_family') not in DEFAULTS['families']:errors.append('目前提取仅支持财报与指引事件')
        if not isinstance(candidate.get('catalyst'),str) or not candidate['catalyst'].strip():errors.append('缺少事件说明')
        rows=candidate.get('facts')
        if not isinstance(rows,list) or not 1<=len(rows)<=40:return errors+['需要 1–40 个可核对事实'],[],[]
        for i,row in enumerate(rows):
            try:
                if not isinstance(row,dict):raise DomainError('事实必须为对象')
                metric=row['metric_id']
                if metric in seen:raise DomainError('重复指标')
                seen.add(metric)
                raw=self.store.query('SELECT r.*,f.security_id,f.accepted_at,f.id AS filing_id FROM raw_documents r JOIN filings f ON f.raw_document_id=r.id OR f.id IN (SELECT filing_id FROM filing_documents WHERE raw_document_id=r.id) WHERE r.id=?',(row['raw_document_id'],))
                if not raw or raw[0]['source_id']!='sec' or raw[0]['is_demo'] or raw[0]['security_id']!=filing['security_id'] or dt(raw[0]['accepted_at'])>dt(filing['accepted_at']):raise DomainError('原文归属或时间不匹配')
                text=bytes(raw[0]['content']).decode('utf-8',errors='replace');excerpt=row['excerpt'];token=row['source_token'];scale=row.get('source_scale',1)
                if not isinstance(excerpt,str) or not 1<=len(excerpt)<=5000 or excerpt not in text or not isinstance(token,str) or not token or token not in excerpt:raise DomainError('原文或数字 token 不匹配')
                if isinstance(row['value'],bool) or not isinstance(row['value'],(int,float)) or scale not in (1,1000,1000000,1000000000):raise DomainError('仅支持数值及明确单位倍率')
                parsed=float(token.replace(',','').replace('$','').replace('%',''))*scale
                if abs(parsed-row['value'])>max(1e-8,abs(row['value'])*1e-10):raise DomainError('数字与原文无法对账')
                eid='research-ev-'+digest([filing['id'],i,row])[:24]
                fact={k:row[k] for k in ('metric_id','value','unit','period_start','period_end','source_token')};fact.update(source_scale=scale,fact_id='research-fact-'+digest([filing['id'],i,row])[:24],fact_version=1,evidence_id=eid)
                validate_fact(fact);facts.append(fact)
                evidence.append({'evidence_id':eid,'raw_document_id':row['raw_document_id'],'excerpt':excerpt,'locator':'exact substring at character '+str(text.index(excerpt))})
            except (DomainError,KeyError,TypeError,ValueError) as e:errors.append(f'事实 {i+1}: {e}')
        current_ids={filing['raw_document_id']}|{r['raw_document_id'] for r in self.store.query('SELECT raw_document_id FROM filing_documents WHERE filing_id=?',(filing['id'],))}
        if not any(e['raw_document_id'] in current_ids for e in evidence):errors.append('必须包含本次披露的证据')
        return errors,facts,evidence

    def approve(self,identity,body):
        if body.get('confirmed') is not True:raise DomainError('需要明确确认已核对指标含义、单位、期间和原文')
        rows=self.store.query('SELECT * FROM research_drafts WHERE id=?',(identity,))
        if not rows:raise DomainError('Draft not found','NOT_FOUND',404)
        row=rows[0];draft=json.loads(row['data_json'])
        if row['status']=='APPROVED':return self.s.get(draft['opportunity_id'])
        filing=self.store.query('SELECT * FROM filings WHERE id=?',(row['filing_id'],))[0]
        candidate=body.get('candidate',draft['candidate']);errors,facts,evidence=self.validate_candidate(filing,candidate)
        if errors:raise DomainError('; '.join(errors),'EVIDENCE_VALIDATION_FAILED',409)
        security=json.loads(self.store.query('SELECT data_json FROM securities WHERE id=?',(filing['security_id'],))[0]['data_json'])
        packet={'event_id':'research-event-'+identity[:24],'opportunity_id':'research-opp-'+identity[:24],'security':security,'accession':filing['accession'],'form':filing['form'],'event_at':filing['accepted_at'],'event_family':candidate['event_family'],'event_type':'reviewed_'+candidate['event_family'].lower(),'catalyst':candidate['catalyst'],'facts':facts,'evidence':evidence,'is_demo':False}
        market={'snapshot_id':'research-pending-'+identity[:24],'ticker':security['ticker'],'captured_at':self.s.now(),'is_demo':False,'complete':False,'adjustment_consistent':False,'data_mode':'unavailable','calendar':{},'quality_errors':['DATA_MARKET_PENDING']}
        existing=self.store.query('SELECT id FROM events WHERE filing_id=? AND family=? AND event_type=?',(filing['id'],packet['event_family'],packet['event_type']))
        if existing:raise DomainError('本次披露已纳入研究；修订需创建新的事实版本','ALREADY_REVIEWED',409)
        result=self.s.ingest(packet,market)
        draft.update(candidate=candidate,opportunity_id=result['opportunity_id'],reviewed_at=utcnow(),reviewed_by='USER')
        with self.store.transaction() as db:
            db.execute("UPDATE research_drafts SET status='APPROVED',data_json=? WHERE id=?",(canonical(draft),identity))
            db.execute("UPDATE review_queue SET status='REVIEWED' WHERE filing_id=?",(filing['id'],))
            Store.audit(db,'RESEARCH_DRAFT_APPROVED',identity,{'opportunity_id':result['opportunity_id']})
        self.notice('RESEARCH_CREATED',result['opportunity_id'],{'message':security['ticker']+' 事实复核完成，行情待更新。'})
        return result

    def explain(self,identity):
        core=self.s.get(identity)
        # No portfolio snapshots, account values, position sizes or secrets leave the machine.
        data={k:core[k] for k in ('ticker','event_family','catalyst','calculations','reaction','is_demo')}
        data['facts']=[{k:f[k] for k in ('metric_id','value','unit','period_start','period_end')} for f in core['facts']]
        return self.ai.generate('explain',data)

    def run_once(self):
        if self.s.demo:raise DomainError('真实研究更新请使用 shadow 工作区','WORKSPACE_MISMATCH',409)
        if not self.lock.acquire(blocking=False):raise DomainError('研究更新正在运行','RUNNING',409)
        result={'started_at':utcnow(),'extracted':0,'market_updated':0,'errors':[]}
        try:
            from .jobs import SECWorker
            result['sec']=SECWorker(self.s).run_once(self.preferences().get('security_ids'))
            if self.preferences()['auto_extract'] and self.ai.status()['enabled'] and self.ai.status()['configured']:
                selected=self.preferences().get('security_ids')
                day=self.s.now()[:10]
                active={r['security_id'] for r in self.store.query('SELECT DISTINCT security_id FROM universe_memberships WHERE valid_from<=? AND (valid_to IS NULL OR valid_to>?)',(day,day))}
                eligible=active if selected is None else active.intersection(selected)
                pending=[]
                if eligible:
                    placeholders=','.join('?' for _ in eligible)
                    pending=self.store.query("SELECT q.filing_id FROM review_queue q JOIN filings f ON f.id=q.filing_id WHERE q.status='REVIEW_REQUIRED' AND f.form IN ('8-K','10-K','10-Q') AND NOT EXISTS(SELECT 1 FROM research_drafts d WHERE d.filing_id=q.filing_id) AND f.security_id IN ("+placeholders+") ORDER BY f.accepted_at DESC LIMIT 5",tuple(sorted(eligible)))
                for r in pending:
                    try:self.extract(r['filing_id']);result['extracted']+=1
                    except DomainError as e:result['errors'].append(str(e))
            if self.integrations:
                import os
                if os.environ.get('MASSIVE_API_KEY'):
                    for c in self.dashboard()['items']:
                        if c['research']['state']=='INVALIDATED':continue
                        try:self.integrations.refresh_market(c['opportunity_id']);result['market_updated']+=1
                        except Exception:result['errors'].append(c['ticker']+' 行情更新失败')
            previous=self.store.setting('research_seen_states',{})
            for c in self.dashboard()['items']:
                current=c['research']['state'];identity=c['opportunity_id']
                if previous.get(identity)!=current and current in ('RESEARCH_READY','INVALIDATED'):
                    self.notice('RESEARCH_STATE_CHANGED',identity,{'message':c['ticker']+(' 研究价格条件满足，仍需个人判断。' if current=='RESEARCH_READY' else ' 研究逻辑已触发失效，请复核。'),'from':previous.get(identity),'to':current,'at':self.s.now()})
                previous[identity]=current
            with self.store.transaction() as db:Store.set_setting(db,'research_seen_states',previous)
            result['state']='DEGRADED' if result['errors'] or result['sec']['state']!='SUCCEEDED' else 'SUCCEEDED'
            if result['state']=='DEGRADED':self.notice('UPDATE_FAILED',utcnow()[:10],{'message':'研究更新有失败项，请检查数据源与最近运行记录。'})
            return result
        except Exception:
            result.update(state='FAILED');result['errors'].append('研究更新失败，请检查配置及数据源')
            self.notice('UPDATE_FAILED',utcnow()[:10],{'message':'研究更新失败，请检查配置及数据源。'})
            return result
        finally:
            result['finished_at']=utcnow()
            with self.store.transaction() as db:Store.set_setting(db,'research_last_run',result)
            self.lock.release()

class ResearchWorker:
    def __init__(self,research,interval=900):
        if research.s.demo or interval<300:raise ValueError('Research polling requires shadow mode and interval >= 300 seconds')
        self.research=research;self.interval=interval;self.stop_event=threading.Event();self.thread=None
    def start(self):
        def work():
            while not self.stop_event.is_set():
                try:self.research.run_once()
                except Exception:self.research.notice('UPDATE_FAILED',utcnow()[:10],{'message':'自动研究更新失败，请查看服务配置。'})
                if self.stop_event.wait(self.interval):break
        self.thread=threading.Thread(target=work,name='personal-research',daemon=True);self.thread.start()
    def stop(self):self.stop_event.set()
