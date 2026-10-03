"""Offline regressions for reopening after absence, partial catch-up and concurrency."""
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from usoe.storage import Store
from usoe.service import Service
from usoe.sources import Sources,SourceUnavailable
from usoe.research import Research
from usoe.util import utcnow

class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name+'/test.db');self.s=Service(self.store)
        self.s.register(dict(security_id='t',ticker='TEST',cik='0000000001',issuer_name='Test',sector='Technology'))
        self.r=Research(self.s);self.calls=[];self.fail=False
        self.env=patch.dict(os.environ,{'SEC_USER_AGENT':'test test@example.invalid'});self.env.start()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def client(self,n=60):
        now=utcnow()
        recent=dict(accessionNumber=[f'0000000001-26-{i:06}' for i in range(n)],primaryDocument=[f'r{i}.htm' for i in range(n)],acceptanceDateTime=[now]*n,form=['6-K']*n)
        data={'cik':1,'tickers':['TEST'],'filings':{'recent':recent}}
        parent=self
        class HTTP:
            def get(self,url,headers=None):
                parent.calls.append(url)
                if 'submissions/' in url:return json.dumps(data).encode()
                if parent.fail:raise SourceUnavailable('offline')
                if 'companyfacts' in url:return b'{"cik":1}'
                return b'Public document'
        return Sources(self.s,HTTP()),data
    def test_more_than_five_and_partial_resume_without_loss(self):
        source,_=self.client()
        first=source.sec_sync('t',catchup=True)
        self.assertEqual(first['filings_archived'],50);self.assertTrue(first['pending_more'])
        self.assertIsNone(self.store.setting('sec_cursor_t'))
        second=source.sec_sync('t',catchup=True)
        self.assertEqual(second['filings_archived'],10);self.assertFalse(second['pending_more'])
        self.assertIsNotNone(self.store.setting('sec_cursor_t'))
        self.assertEqual(source.sec_sync('t',catchup=True)['filings_archived'],0)
        self.assertFalse(self.s.list())
    def test_failure_does_not_advance_cursor(self):
        source,_=self.client(2);self.fail=True
        with self.assertRaises(SourceUnavailable):source.sec_sync('t',catchup=True)
        self.assertIsNone(self.store.setting('sec_cursor_t'))
        self.fail=False;self.assertEqual(source.sec_sync('t',catchup=True)['filings_archived'],2)
    def test_week_absence_uses_cursor_not_latest_five(self):
        source,data=self.client(12)
        with self.store.transaction() as db:Store.set_setting(db,'sec_cursor_t','2026-09-01T00:00:00Z')
        self.assertEqual(source.sec_sync('t',catchup=True)['filings_archived'],12)
    def test_tabs_share_one_running_update(self):
        entered=threading.Event();release=threading.Event()
        def slow():entered.set();release.wait(3)
        with patch.object(self.r,'run_once',side_effect=slow) as run:
            try:
                self.r.ensure_fresh();self.assertTrue(entered.wait(1))
                for _ in range(8):self.assertTrue(self.r.ensure_fresh()['running'])
                self.assertEqual(run.call_count,1)
            finally:release.set();self.r.update_thread.join(2)
    def test_fresh_success_does_not_fetch_again_and_failure_is_visible(self):
        for state,expected in [('SUCCEEDED','CURRENT'),('FAILED','DEGRADED')]:
            with self.store.transaction() as db:Store.set_setting(db,'research_last_run',dict(state=state,finished_at=utcnow()))
            with patch.object(self.r,'run_once') as run:
                self.assertEqual(self.r.ensure_fresh()['state'],expected);run.assert_not_called()
    def test_missing_market_is_explicit(self):
        with patch.dict(os.environ,{'MASSIVE_API_KEY':''}):self.assertFalse(self.r.freshness()['market_configured'])
    def test_stale_completed_run_schedules_new_update(self):
        with self.store.transaction() as db:Store.set_setting(db,'research_last_run',dict(state='SUCCEEDED',finished_at='2026-01-01T00:00:00Z'))
        with patch.object(self.r,'run_once') as run:
            self.r.ensure_fresh();self.r.update_thread.join(2);run.assert_called_once()

    def test_history_file_fills_gap_before_recent(self):
        from datetime import timedelta
        from usoe.util import dt
        source,data=self.client(1)
        old=(dt(utcnow())-timedelta(days=7)).isoformat()
        name='CIK0000000001-submissions-001.json'
        data['filings']['files']=[{'name':name,'filingTo':old[:10]}]
        older=dict(accessionNumber=['0000000001-26-999999'],primaryDocument=['old.htm'],acceptanceDateTime=[old],form=['20-F'])
        base=source.http.get
        def get(url,headers=None):
            if url.endswith(name):return json.dumps(older).encode()
            return base(url,headers)
        source.http.get=get
        self.assertEqual(source.sec_sync('t',catchup=True)['filings_archived'],2)
        self.assertEqual(len(self.store.query("SELECT * FROM filings WHERE form='20-F'")),1)

    def test_candidate_calculation_stays_unverified(self):
        from usoe.util import canonical
        text='Guidance 100 110 120 130'
        with self.store.transaction() as db:
            rid,_=Store.raw(db,'sec','report',text,utcnow(),'https://www.sec.gov/report')
            db.execute('INSERT INTO filings VALUES (?,?,?,?,?,?)',('f','t','0000000001-26-000001','6-K',utcnow(),rid))
        facts=[]
        for era,end,value in [('prior','low',100),('prior','high',110),('current','low',120),('current','high',130)]:
            facts.append(dict(metric_id=f'{era}_revenue_guidance_{end}',value=value,unit='USD',period_start='2026-01-01',period_end='2026-12-31',source_token=str(value),source_scale=1,raw_document_id=rid,excerpt=text))
        candidate=dict(event_family='GUIDANCE_CHANGE',catalyst='Unverified guidance',facts=facts)
        with self.store.transaction() as db:db.execute('INSERT INTO research_drafts VALUES (?,?,?,?,?)',('d','f','REVIEW_REQUIRED',canonical(dict(filing_id='f',candidate=candidate,documents=[])),utcnow()))
        board=self.r.dashboard();d=board['drafts'][0]
        self.assertEqual(board['impacts'][0]['direction'],'BULLISH')
        self.assertEqual(board['impacts'][0]['status'],'REVIEW_REQUIRED')
        self.assertFalse(self.store.query('SELECT * FROM impact_judgments'))
        before=len(self.store.query('SELECT * FROM audit'));self.r.dashboard()
        self.assertEqual(before,len(self.store.query('SELECT * FROM audit')))
        self.assertEqual(d['ticker'],'TEST');self.assertAlmostEqual(d['calculations'][0]['change'],19.047619)
        self.assertEqual(d['status'],'REVIEW_REQUIRED');self.assertFalse(self.s.list())
        self.r.save_preferences(dict(families=['GUIDANCE_CHANGE'],watchlist_only=True,auto_extract=False,security_ids=[]))
        self.assertFalse(self.r.dashboard()['drafts'])
