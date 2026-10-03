import tempfile
import sqlite3
import unittest
from copy import deepcopy
from usoe.impact import assess,record
from usoe.storage import Store

class ImpactTests(unittest.TestCase):
    def card(self,changes=(5,),**overrides):
        args=dict(identity='draft:test',ticker='TEST',catalyst='AI text says BUY',event_at='2026-09-28T14:00:00Z',as_of='2026-09-28T16:00:00Z',calculations=[{'metric':m,'change':v,'unit':'%','input_fact_ids':['f']} for m,v in zip(('revenue_guidance','eps_guidance'),changes)])
        args.update(overrides);return assess(**args)
    def test_direction_and_mixed_evidence(self):
        for values,expected in [((5,),'BULLISH'),((-5,),'BEARISH'),((5,-5),'MIXED'),((0,),'NEUTRAL'),((),'UNKNOWN')]:
            with self.subTest(values=values):self.assertEqual(self.card(values)['direction'],expected)
    def test_no_fabricated_forecasts(self):
        c=self.card();self.assertIsNone(c['probability_up']);self.assertIsNone(c['expected_return_pct'])
        self.assertEqual(c['status'],'REVIEW_REQUIRED');self.assertFalse(c['evidence_reviewed'])
        for h in c['horizons']:self.assertIsNone(h['probability_up']);self.assertIsNone(h['expected_return_pct'])
    def test_unmatched_period_or_invalid_evidence_blocks_bias(self):
        self.assertEqual(self.card(errors=['DATA_PERIOD_MISMATCH'])['direction'],'UNKNOWN')
    def test_ai_narrative_cannot_create_direction(self):
        self.assertEqual(self.card((),catalyst='guaranteed 1000% gain')['direction'],'UNKNOWN')
    def test_single_cash_flow_is_not_growth_forecast(self):
        self.assertEqual(self.card(calculations=[{'metric':'free_cash_flow','new':100,'unit':'USD'}])['direction'],'UNKNOWN')
    def test_missing_delayed_stale_quotes_not_current(self):
        for mode,age,complete in [('historical',0,True),('delayed',0,True),('realtime',500,True),('realtime',0,False)]:
            c=self.card(core={'reaction':{'complete':complete,'data_mode':mode,'age_seconds':age,'raw_return_pct':10}})
            self.assertEqual(c['market']['state'],'UNKNOWN');self.assertIsNone(c['market']['observed_return_pct'])
    def test_observed_return_is_not_expected_return(self):
        c=self.card(core={'reaction':{'complete':True,'data_mode':'realtime','age_seconds':1,'raw_return_pct':18,'bucket':'EXTENDED_REACTION'}})
        self.assertEqual(c['market']['state'],'EXTENDED');self.assertEqual(c['market']['observed_return_pct'],18);self.assertIsNone(c['expected_return_pct'])
    def test_calendar_windows_expire_and_weekends_do_not_count(self):
        c=self.card(event_at='2026-09-25T22:00:00Z',as_of='2026-09-27T20:00:00Z')
        self.assertTrue(c['horizons'][0]['ends_at'].startswith('2026-09-28'));self.assertEqual(c['horizons'][0]['state'],'OPEN')
        self.assertEqual(self.card(as_of='2026-12-01T00:00:00Z')['status'],'HISTORICAL')
    def test_invalidation_and_future_data(self):
        self.assertEqual(self.card(core={'invalidation_status':['INVALID_PRICE']})['status'],'INVALIDATED')
        self.assertEqual(self.card(as_of='2026-09-20T00:00:00Z')['direction'],'UNKNOWN')
    def test_judgments_append_and_cannot_be_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=Store(tmp+'/db');a=self.card();b=self.card((-5,))
            self.assertEqual(record(st,[a]),1);self.assertEqual(record(st,[dict(a,as_of='2026-09-28T16:01:00Z')]),0)
            record(st,[b]);record(st,[a]);self.assertEqual(len(st.query('SELECT * FROM impact_judgments')),3)
            for sql in ('UPDATE impact_judgments SET fingerprint=\'x\'','DELETE FROM impact_judgments'):
                with self.assertRaises(sqlite3.IntegrityError):
                    with st.transaction() as db:db.execute(sql)
            self.assertTrue(st.verify_audit()['valid'])
