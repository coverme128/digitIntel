import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch,Mock
from usoe.util import canonical,digest,DomainError
from usoe.storage import Store
from usoe.service import Service
from usoe.ai import DeepSeek
from usoe.research import Research
from usoe.sources import SourceUnavailable,Sources

class FakeTransport:
    def __init__(self,output):self.output=output;self.calls=[]
    def request(self,*args,**kwargs):
        self.calls.append((args,kwargs))
        if isinstance(self.output,Exception):raise self.output
        return self.output

def completion(output):return {'choices':[{'finish_reason':'stop','message':{'content':canonical(output)}}],'usage':{'total_tokens':50}}

class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name+'/s.db');self.s=Service(self.store,clock=lambda:'2026-09-28T15:00:00+00:00');self.r=Research(self.s)
        self.s.register({'security_id':'test','ticker':'TEST','cik':'0000000001','issuer_name':'Test issuer','sector':'Technology'})
        with self.store.transaction() as db:
            self.raw,_=Store.raw(db,'sec','test','Revenue guidance 100 to 120 million for fiscal 2026.',self.s.now(),'https://www.sec.gov/Archives/edgar/data/1/000000000126000001/report.htm')
            db.execute('INSERT INTO filings VALUES (?,?,?,?,?,?)',('filing-test','test','0000000001-26-000001','8-K',self.s.now(),self.raw))
        self.candidate={'event_family':'GUIDANCE_CHANGE','catalyst':'Revenue guidance range','facts':[{'metric_id':'current_revenue_guidance_low','value':100000000,'unit':'USD','period_start':'2026-01-01','period_end':'2026-12-31','source_token':'100','source_scale':1000000,'raw_document_id':self.raw,'excerpt':'Revenue guidance 100 to 120 million for fiscal 2026.'}],'uncertainties':['Prior guidance missing']}
        self.env=patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake-key-not-live','DEEPSEEK_MODEL':'deepseek-flash','DEEPSEEK_DAILY_REQUEST_LIMIT':'20'});self.env.start()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def enable(self):
        with self.store.transaction() as db:Store.set_setting(db,'ai_mode','assist')
    def fake_ai(self,output=None):
        self.enable();http=FakeTransport(completion(output or self.candidate));self.r.ai=DeepSeek(self.s,http);return http
    def test_new_stock_joins_explicit_research_selection(self):
        self.r.save_preferences({'families':['GUIDANCE_CHANGE'],'watchlist_only':True,'auto_extract':False,'security_ids':['test']})
        stock={'security_id':'new','ticker':'NEW','cik':'0000000002','issuer_name':'New issuer','sector':'Technology'}
        self.s.register(stock)
        self.assertEqual(self.r.preferences()['security_ids'],['test','new'])
        self.s.register(stock)
        self.assertEqual(self.r.preferences()['security_ids'],['test','new'])
        self.assertTrue(self.store.verify_audit()['valid'])

    def test_other_universe_and_readding_paused_stock_do_not_change_selection(self):
        self.r.save_preferences({'families':['GUIDANCE_CHANGE'],'watchlist_only':True,'auto_extract':False,'security_ids':[]})
        self.s.register({'security_id':'other','ticker':'OTHER','cik':'0000000002','issuer_name':'Other issuer','sector':'Technology'},'SP500')
        self.s.register({'security_id':'test','ticker':'TEST','cik':'0000000001','issuer_name':'Test issuer','sector':'Technology'})
        self.assertEqual(self.r.preferences()['security_ids'],[])

    def test_all_stocks_preference_stays_all_on_registration(self):
        self.s.register({'security_id':'new','ticker':'NEW','cik':'0000000002','issuer_name':'New issuer','sector':'Technology'})
        self.assertIsNone(self.r.preferences()['security_ids'])

    def test_off_makes_no_request(self):
        http=FakeTransport(completion(self.candidate));ai=DeepSeek(self.s,http)
        with self.assertRaises(DomainError):ai.generate('extract',{})
        self.assertEqual(http.calls,[])
    def test_missing_key_no_network(self):
        self.enable();http=FakeTransport(completion(self.candidate))
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':''}):
            with self.assertRaises(DomainError):DeepSeek(self.s,http).generate('extract',{})
        self.assertEqual(http.calls,[])
    def test_api_shape_and_cache(self):
        http=self.fake_ai();a=self.r.ai.generate('extract',{'documents':[]});b=self.r.ai.generate('extract',{'documents':[]})
        self.assertEqual(len(http.calls),1);self.assertTrue(b['cached']);self.assertEqual(a['artifact_id'],b['artifact_id']);body=http.calls[0][1]['body'];self.assertEqual(body['response_format'],{'type':'json_object'});self.assertNotIn('tools',body)
    def test_unrequested_explanation_unit_rescaling_rejected(self):
        self.enable()
        http=FakeTransport(completion({'summary':'营收为1000百万美元','risks':[],'questions':[]}))
        with self.assertRaises(DomainError):DeepSeek(self.s,http).generate('explain',{'facts':[{'value':1000,'unit':'USD'}]})
        self.assertFalse(self.store.query('SELECT * FROM ai_artifacts'))
    def test_extraction_unscaled_value_is_blocked(self):
        candidate=copy.deepcopy(self.candidate);candidate['facts'][0]['value']=100
        errors,_,_=self.r.validate_candidate(self.store.query('SELECT * FROM filings')[0],candidate)
        self.assertTrue(any('无法对账' in e for e in errors))
    def test_empty_or_truncated_response_rejected(self):
        self.enable()
        for raw in ({}, {'choices':[{'finish_reason':'length','message':{'content':'{}'}}]}):
            with self.assertRaises(DomainError):DeepSeek(self.s,FakeTransport(raw)).generate('extract',{})
        self.assertFalse(self.store.query('SELECT * FROM ai_artifacts'))
    def test_provider_exception_sanitized(self):
        self.enable()
        with self.assertRaises(DomainError) as e:DeepSeek(self.s,FakeTransport(SourceUnavailable('fake-key-not-live'))).generate('extract',{})
        self.assertNotIn('fake-key',str(e.exception))
    def test_daily_budget_includes_failed_attempt(self):
        self.enable();ai=DeepSeek(self.s,FakeTransport(SourceUnavailable('failed')))
        with patch.dict(os.environ,{'DEEPSEEK_DAILY_REQUEST_LIMIT':'1'}):
            with self.assertRaises(DomainError):ai.generate('extract',{'a':1})
            with self.assertRaises(DomainError) as e:ai.generate('extract',{'a':2})
        self.assertEqual(e.exception.code,'AI_BUDGET_LIMIT')
    def test_extraction_never_creates_canonical_event(self):
        self.fake_ai();d=self.r.extract('filing-test');self.assertEqual(d['validation_errors'],[]);self.assertFalse(self.s.list());self.assertFalse(self.store.query('SELECT * FROM facts'))
    def test_approval_requires_confirmation(self):
        self.fake_ai();d=self.r.extract('filing-test')
        with self.assertRaises(DomainError):self.r.approve(d['id'],{})
        self.assertFalse(self.s.list())
    def test_user_approval_imports_verified_numeric_facts(self):
        self.fake_ai();d=self.r.extract('filing-test');core=self.r.approve(d['id'],{'confirmed':True})
        self.assertEqual(len(core['facts']),1);self.assertNotEqual(core['state'],'READY');self.assertEqual(core['evidence_quality'],'CONFIRMED');self.assertEqual(self.r.approve(d['id'],{'confirmed':True})['opportunity_id'],core['opportunity_id'])
    def test_hallucinated_number_or_quote_blocked(self):
        for changed in ({'value':101000000},{'excerpt':'Invented text 100'},{'period_end':'2025-12-31'},{'unit':'percent'}):
            candidate=copy.deepcopy(self.candidate);candidate['facts'][0].update(changed)
            filing=self.store.query('SELECT * FROM filings')[0];self.assertTrue(self.r.validate_candidate(filing,candidate)[0])
    def test_wrong_issuer_raw_blocked(self):
        c=copy.deepcopy(self.candidate);c['facts'][0]['raw_document_id']='does-not-exist'
        self.assertTrue(self.r.validate_candidate(self.store.query('SELECT * FROM filings')[0],c)[0])
    def test_prompt_instructions_not_promoted(self):
        c=copy.deepcopy(self.candidate);c.update(state='READY',reviewed_by='USER');self.fake_ai(c);d=self.r.extract('filing-test');self.assertFalse(self.s.list());self.assertEqual(d['status'],'REVIEW_REQUIRED')
    def test_research_run_respects_selected_securities(self):
        self.r.save_preferences({'families':['GUIDANCE_CHANGE'],'watchlist_only':True,'auto_extract':False,'security_ids':[]})
        with patch('usoe.jobs.SECWorker.run_once',return_value={'state':'SUCCEEDED','failures':[]}) as sync:
            result=self.r.run_once()
        sync.assert_called_once_with([]);self.assertEqual(result['state'],'SUCCEEDED')
    def test_state_change_notices_deduplicate_until_transition(self):
        item={'ticker':'TEST','opportunity_id':'o','research':{'state':'RESEARCH_READY'}}
        with patch('usoe.jobs.SECWorker.run_once',return_value={'state':'SUCCEEDED','failures':[]}),patch.object(self.r,'dashboard',return_value={'items':[item]}):
            self.r.run_once();self.r.run_once()
            self.assertEqual(len(self.store.query('SELECT * FROM research_notices')),1)
            item['research']['state']='RESEARCH_WATCH';self.r.run_once()
            item['research']['state']='RESEARCH_READY';self.r.run_once()
        self.assertEqual(len(self.store.query('SELECT * FROM research_notices')),2)
    def test_preferences_validation(self):
        with self.assertRaises(DomainError):self.r.save_preferences({'families':['FAKE'],'watchlist_only':True,'auto_extract':False})
        result=self.r.save_preferences({'families':['GUIDANCE_CHANGE'],'watchlist_only':False,'auto_extract':False});self.assertEqual(result,self.r.preferences())
    def test_notice_dedup_and_read(self):
        self.r.notice('CHANGE','x',{'message':'a'});self.r.notice('CHANGE','x',{'message':'a'});self.assertEqual(len(self.store.query('SELECT * FROM research_notices')),1)
    def test_exhibit_evidence_is_validated(self):
        with self.store.transaction() as db:
            rid,_=Store.raw(db,'sec','ex991','Revenue guidance 100 to 120 million for fiscal 2026.',self.s.now(),'https://www.sec.gov/Archives/edgar/data/1/000000000126000001/ex991.htm')
            db.execute('INSERT INTO filing_documents VALUES (?,?,?)',('filing-test',rid,'EX99'))
        c=copy.deepcopy(self.candidate);c['facts'][0]['raw_document_id']=rid;self.fake_ai(c);d=self.r.extract('filing-test');self.assertEqual(d['validation_errors'],[]);self.assertEqual(self.r.approve(d['id'],{'confirmed':True})['evidence'][0]['raw_document_id'],rid)

class ResearchDemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Service(Store(self.tmp.name+'/d.db'),demo=True);self.s.seed_demo();self.r=Research(self.s)
    def tearDown(self):self.tmp.cleanup()
    def test_research_ready_independent_of_missing_account(self):
        core=self.s.get('opp-nova-d');core=copy.deepcopy(core)
        for c in core['entry_conditions']:
            if c['id']=='portfolio':c['pass']=False
        core['state']='WATCH';core['portfolio']['hard_blocks']=['RISK_EQUITY_UNKNOWN']
        r=Research.research_state(core);self.assertEqual(r['state'],'RESEARCH_READY');self.assertEqual(r['execution_state'],'WATCH');self.assertTrue(r['execution_blockers'])
    def test_research_does_not_ignore_market_requirement(self):
        core=copy.deepcopy(self.s.get('opp-nova-d'))
        for c in core['entry_conditions']:
            if c['id']=='market_fresh':c['pass']=False
        self.assertNotEqual(Research.research_state(core)['state'],'RESEARCH_READY')
    def test_ai_explanation_excludes_portfolio_and_preserves_replay(self):
        before=self.s.replay('opp-nova-d');http=FakeTransport(completion({'summary':'Synthetic test','risks':[],'questions':[]}))
        with self.s.store.transaction() as db:Store.set_setting(db,'ai_mode','assist')
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test','DEEPSEEK_DAILY_REQUEST_LIMIT':'20'}):
            self.r.ai=DeepSeek(self.s,http);self.r.explain('opp-nova-d')
        outbound=json.loads(http.calls[0][1]['body']['messages'][1]['content'])['data']
        self.assertNotIn('portfolio',outbound);self.assertNotIn('portfolio_snapshot',outbound);self.assertEqual(before,self.s.replay('opp-nova-d'))
    def test_dashboard_no_implicit_ai_network(self):
        self.r.ai=Mock();self.r.ai.status.return_value={};r=self.r.dashboard();self.assertTrue(r['items']);self.r.ai.generate.assert_not_called()
    def test_demo_cannot_run_real_research(self):
        with self.assertRaises(DomainError):self.r.run_once()

class ExhibitTests(unittest.TestCase):
    def test_exhibit_fetch_confined_to_sec_accession(self):
        tmp=tempfile.TemporaryDirectory()
        try:
            service=Service(Store(tmp.name+'/x.db'));service.register({'security_id':'s','ticker':'TEST','cik':'0000000001','issuer_name':'Test','sector':'Technology'})
            with service.store.transaction() as db:
                rid,_=Store.raw(db,'sec','report','primary','2026-09-28T12:00:00Z','https://www.sec.gov/Archives/edgar/data/1/123/report.htm')
                db.execute('INSERT INTO filings VALUES (?,?,?,?,?,?)',('f','s','0000000001-26-000001','8-K','2026-09-28T12:00:00Z',rid))
            class HTTP:
                def __init__(self):self.calls=[]
                def get(self,url,headers=None):
                    self.calls.append(url)
                    if url.endswith('index.json'):return canonical({'directory':{'item':[{'name':'ex991.htm'},{'name':'../ex992.htm'},{'name':'https://evil.example/ex993.htm'},{'name':'other.htm'}]}}).encode()
                    if url.endswith('/ex991.htm'):return b'Official earnings exhibit'
                    raise AssertionError(url)
            http=HTTP()
            with patch.dict(os.environ,{'SEC_USER_AGENT':'test contact test@example.invalid'}):result=Sources(service,http).sec_exhibits('f')
            self.assertEqual(len(result['documents']),1);self.assertEqual(len(http.calls),2)
        finally:tmp.cleanup()
