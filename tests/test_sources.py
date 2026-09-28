import json
import os
import tempfile
import unittest
from unittest.mock import patch
from usoe.storage import Store
from usoe.service import Service
from usoe.sources import Sources,SourceUnavailable
from usoe.util import DomainError

class FakeHTTP:
    def __init__(self,responses):self.responses=responses;self.calls=[]
    def get(self,url,headers=None):
        self.calls.append(url)
        for suffix,body in self.responses.items():
            if suffix in url:
                if isinstance(body,Exception):raise body
                return body if isinstance(body,bytes) else json.dumps(body).encode()
        raise SourceUnavailable('Unexpected URL in fixture')

class SourceContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.s=Service(Store(self.temp.name+'/shadow.db'))
        self.security={'security_id':'msft','ticker':'MSFT','cik':'0000789019','issuer_name':'Microsoft Corporation','sector':'Technology'}
        self.s.register(self.security)
        self.env=patch.dict(os.environ,{'SEC_USER_AGENT':'USOE contract-test contact test@example.invalid','MASSIVE_API_KEY':'test-only-key','IBKR_ACCOUNT_ID':'DU0000','IBKR_BASE_URL':'https://localhost:5000/v1/api'});self.env.start()
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def submission(self,cik='789019',ticker='MSFT'):
        return {'cik':cik,'tickers':[ticker],'filings':{'recent':{'accessionNumber':['0000789019-26-000001'],'primaryDocument':['report.htm'],'acceptanceDateTime':['2026-09-20T20:00:00Z'],'form':['8-K']}}}
    def test_sec_archives_and_deduplicates_without_invented_event(self):
        client=FakeHTTP({'submissions':self.submission(),'report.htm':b'<html>Revenue outlook: 1080 to 1180 USD million.</html>','companyfacts':{'cik':789019,'facts':{}}})
        sources=Sources(self.s,client)
        self.assertEqual(sources.sec_sync('msft')['filings_archived'],1)
        self.assertEqual(sources.sec_sync('msft')['filings_archived'],0)
        self.assertEqual(self.s.list(),[]);self.assertEqual(len(self.s.store.query('SELECT * FROM review_queue')),1)
        self.assertEqual(self.s.store.query("SELECT state FROM sources WHERE id='sec'")[0]['state'],'HEALTHY')
        self.assertEqual(len(self.s.store.query('SELECT * FROM raw_documents')),3)
    def test_identity_mismatch_is_hard_failure(self):
        sources=Sources(self.s,FakeHTTP({'submissions':self.submission(ticker='OTHER')}))
        with self.assertRaises(DomainError):sources.sec_sync('msft')
        self.assertEqual(self.s.store.query("SELECT state FROM sources WHERE id='sec'")[0]['state'],'DEGRADED')
        self.assertEqual(self.s.store.query('SELECT * FROM filings'),[])
    def test_source_failure_persists_degraded_and_no_fake_facts(self):
        sources=Sources(self.s,FakeHTTP({'submissions':SourceUnavailable('Upstream HTTP 503')}))
        with self.assertRaises(SourceUnavailable):sources.sec_sync('msft')
        self.assertEqual(self.s.store.query("SELECT state FROM sources WHERE id='sec'")[0]['state'],'DEGRADED');self.assertEqual(self.s.store.query('SELECT * FROM facts'),[])
    def test_massive_timestamps_and_mode_explicit(self):
        bar={'t':1720000000000,'o':100,'h':103,'l':98,'c':101,'v':1234}
        sources=Sources(self.s,FakeHTTP({'aggs':{'status':'OK','results':[bar]}}))
        data=sources.massive_bars('MSFT','2026-09-20','2026-09-21');self.assertEqual(data['data_mode'],'historical');self.assertFalse(data['window_complete'])
        bad=Sources(self.s,FakeHTTP({'aggs':{'status':'OK','results':[bar,bar]}}))
        with self.assertRaises(SourceUnavailable):bad.massive_bars('MSFT','2026-09-20','2026-09-21')
    def test_empty_market_not_success(self):
        sources=Sources(self.s,FakeHTTP({'aggs':{'status':'OK','results':[]}}))
        with self.assertRaises(SourceUnavailable):sources.massive_bars('MSFT','2026-09-20','2026-09-21')
    def test_ibkr_read_only_and_account_redaction(self):
        client=FakeHTTP({'portfolio/accounts':[{'accountId':'DU0000'}],'positions/0':[{'conid':1,'ticker':'MSFT','position':10,'mktValue':1000,'avgCost':99}],'summary':{'netliquidation':{'amount':100000,'currency':'USD'},'accountId':'DU0000'}})
        result=Sources(self.s,client).ibkr_read();self.assertFalse(result['portfolio']['reconciled'])
        self.assertNotIn('DU0000',json.dumps(result));self.assertTrue(all('/portfolio/' in url for url in client.calls));self.assertFalse(any('/orders' in url for url in client.calls))
    def test_ibkr_account_mismatch_blocks(self):
        sources=Sources(self.s,FakeHTTP({'portfolio/accounts':[{'accountId':'OTHER'}]}))
        with self.assertRaises(SourceUnavailable):sources.ibkr_read()
    def test_poller_no_unknown_index_membership(self):
        from usoe.jobs import SECWorker
        worker=SECWorker(self.s,300)
        worker.sources=Sources(self.s,FakeHTTP({'submissions':self.submission(),'report.htm':b'Official test text','companyfacts':{'cik':789019,'facts':{}}}))
        result=worker.run_once();self.assertEqual(result['synced'],1);self.assertEqual(result['state'],'SUCCEEDED')
        with self.assertRaises(ValueError):SECWorker(self.s,1)
    def test_canonical_rejects_wrong_numeric_token(self):
        sources=Sources(self.s,FakeHTTP({'submissions':self.submission(),'report.htm':b'Revenue 1080 to 1180 USD million.','companyfacts':{'cik':789019,'facts':{}}}))
        result=sources.sec_sync('msft');raw=result['items'][0]['primary_document_id']
        event={'security':self.security,'event_id':'new-event','opportunity_id':'new-opp','event_family':'GUIDANCE_CHANGE','event_type':'guidance_raised','event_at':'2026-09-20T20:00:00Z','accession':'0000789019-26-000001','form':'8-K','is_demo':False,'catalyst':'source test','evidence':[{'evidence_id':'ev-real','raw_document_id':raw,'locator':'paragraph 1','excerpt':'Revenue 1080 to 1180 USD million.'}],'facts':[{'fact_id':'fact-real','metric_id':'current_revenue_guidance_low','value':999000000,'unit':'USD','period_start':'2026-01-01','period_end':'2026-12-31','fact_version':1,'evidence_id':'ev-real','source_token':'1080','source_scale':1000000}]}
        market={'snapshot_id':'real-market','captured_at':'2026-09-20T20:10:00Z','is_demo':False,'ticker':'MSFT'}
        with self.assertRaises(DomainError) as e:self.s.ingest(event,market)
        self.assertIn('reconcile',str(e.exception));self.assertEqual(self.s.store.query('SELECT * FROM facts'),[])
