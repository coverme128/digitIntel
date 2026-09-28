import csv
import io
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from usoe.storage import Store
from usoe.service import Service
from usoe.demo import fixtures,AS_OF
from usoe.util import DomainError,canonical,digest
from usoe.exports import envelope,csv_export,markdown
from usoe.sources import parse_form4,xbrl_candidates,Sources,SourceUnavailable

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.s=Service(Store(self.temp.name+'/demo.db'),demo=True);self.s.seed_demo()
    def tearDown(self):self.temp.cleanup()
    def create(self,key='create-1',quantity=10):
        return self.s.create_intent({'opportunity_id':'opp-nova-d','quantity':quantity,'entry':106,'invalidation':100,'management_hypothesis':'Review when thesis breaks'},key)
    def test_seed_and_replay(self):
        self.assertEqual(len(self.s.list()),7)
        for c in self.s.list():self.assertTrue(self.s.replay(c['opportunity_id'])['match'])
    def test_dedup_accession_event(self):
        p,m=fixtures()[0];self.s.ingest(p,m);self.assertEqual(len(self.s.list()),7)
    def test_immutable_raw_facts_and_audit(self):
        for table in ('raw_documents','facts','evaluations','transitions','audit'):
            with self.subTest(table=table),self.assertRaises(sqlite3.IntegrityError):
                with self.s.store.transaction() as db:db.execute(f'DELETE FROM {table}')
        self.assertTrue(self.s.store.verify_audit()['valid'])
    def test_environment_isolation(self):
        p,m=fixtures()[0];p['is_demo']=False
        with self.assertRaises(DomainError):self.s.ingest(p,m)
    def test_no_automatic_entry(self):
        self.assertEqual(self.s.get('opp-nova-d')['state'],'READY');self.assertEqual(self.s.store.query('SELECT * FROM positions'),[])
    def test_double_confirmation_and_outcome_lifecycle(self):
        before=self.s.portfolio()['cash'];intent=self.create()
        self.assertEqual(self.s.get('opp-nova-d')['state'],'READY')
        with self.assertRaises(DomainError):self.s.confirm_intent(intent['intent_id'],{'confirmed':False},'confirm-no')
        result=self.s.confirm_intent(intent['intent_id'],{'confirmed':True},'confirm-1')
        self.assertEqual(result['state'],'MANAGE');self.assertEqual(self.s.portfolio()['cash'],before-1060)
        replay=self.s.confirm_intent(intent['intent_id'],{'confirmed':True},'confirm-1');self.assertEqual(result,replay)
        self.assertEqual(len(self.s.store.query('SELECT * FROM positions')),1)
        exit=self.s.exit_intent(result['position_id'],{'price':110,'fees':2,'reason':'Thesis complete'},'exit-1')
        self.assertEqual(self.s.get('opp-nova-d')['state'],'MANAGE')
        outcome=self.s.confirm_exit(exit['exit_intent_id'],{'confirmed':True},'exit-confirm-1')
        self.assertEqual(outcome['net_pnl'],38);self.assertAlmostEqual(outcome['r_multiple'],38/60)
        self.assertEqual(self.s.portfolio()['cash'],before+38);self.assertEqual(self.s.get('opp-nova-d')['state'],'EXITED')
        self.assertEqual(len(self.s.outcomes()),2);self.assertTrue(self.s.store.verify_audit()['valid'])
    def test_idempotency_conflict_and_duplicate_draft(self):
        first=self.create();self.assertEqual(first,self.create())
        with self.assertRaises(DomainError):self.create('create-1',20)
        with self.assertRaises(DomainError):self.create('new-key',10)
        self.s.cancel_intent(first['intent_id']);second=self.create('new-key',10);self.assertNotEqual(first['intent_id'],second['intent_id'])
    def test_oversizing_rejected(self):
        with self.assertRaises(DomainError):self.create(quantity=1000)
        self.assertEqual(self.s.store.query('SELECT * FROM order_intents'),[])
    def test_arbitrary_entry_or_stop_rejected(self):
        with self.assertRaises(DomainError):self.s.create_intent({'opportunity_id':'opp-nova-d','quantity':10,'entry':80,'invalidation':79,'management_hypothesis':'test'},'bad-price')
    def test_confirm_rechecks_stale_portfolio(self):
        intent=self.create()
        with self.s.store.transaction() as db:Store.set_setting(db,'demo_as_of','2026-09-25T15:36:00+00:00')
        with self.assertRaises(DomainError):self.s.confirm_intent(intent['intent_id'],{'confirmed':True},'stale')
        self.assertEqual(self.s.store.query('SELECT * FROM positions'),[])
    def test_concurrent_confirmation_one_fill(self):
        intent=self.create()
        def confirm(i):
            try:return self.s.confirm_intent(intent['intent_id'],{'confirmed':True},f'concurrent-{i}')
            except DomainError:return None
        with ThreadPoolExecutor(max_workers=4) as executor:results=list(executor.map(confirm,range(4)))
        self.assertEqual(sum(r is not None for r in results),1);self.assertEqual(len(self.s.store.query('SELECT * FROM positions')),1)
    def test_cancelled_draft_cannot_fill(self):
        i=self.create();self.s.cancel_intent(i['intent_id'])
        with self.assertRaises(DomainError):self.s.confirm_intent(i['intent_id'],{'confirmed':True},'c')
    def test_terminal_ignored_not_revived(self):
        self.s.action('opp-nova-d','ignore');self.s.refresh('opp-nova-d');self.assertEqual(self.s.get('opp-nova-d')['state'],'IGNORED')
    def test_ai_mode_parity_export(self):
        c=self.s.get('opp-nova-d');off=self.s.export(c)
        with self.s.store.transaction() as db:Store.set_setting(db,'ai_mode','assist')
        assist=self.s.export(self.s.get('opp-nova-d'))
        self.assertEqual(off['payload'],assist['payload']);self.assertEqual(off['core_output_hash'],assist['core_output_hash'])
        self.assertEqual(assist['ai_mode'],'assist')
    def test_export_hash_excludes_ai_prose(self):
        c=self.s.get('opp-nova-d');a=envelope(c,'off','v1');c['ai_explanation']='untrusted';c['facts'][0]['ai_notes']='untrusted'
        b=envelope(c,'assist','v1');self.assertEqual(a['core_output_hash'],b['core_output_hash']);self.assertNotIn('untrusted',canonical(b['payload']))
    def test_csv_injection_and_markdown_sections(self):
        data=envelope({'items':[{'ticker':'=HYPERLINK("evil")','net_pnl':12}]},'off','v1')
        row=list(csv.DictReader(io.StringIO(csv_export(data))))[0];self.assertTrue(row['ticker'].startswith("'="))
        md=markdown(self.s.export(self.s.get('opp-nova-d')))
        for title in ('Evidence','Fundamental Changes','Invalidation Conditions','Portfolio Context','Rule Version'):self.assertIn('## '+title,md)
    def test_real_execution_always_disabled(self):
        self.s.demo=False
        with self.assertRaises(DomainError) as c:self.create()
        self.assertEqual(c.exception.code,'PRODUCTION_BLOCKED')
    def test_empty_shadow_workspace(self):
        other=Service(Store(self.temp.name+'/real.db'));self.assertEqual(other.list(),[]);self.assertFalse(other.status()['live_trading'])
    def test_failed_import_rolls_back(self):
        p,m=fixtures()[0];p['accession']='DEMO-NEW';p['event_id']='new-event';p['opportunity_id']='new-opp';p['evidence'][0]['evidence_id']='new-evidence';p['facts'][0]['evidence_id']='missing'
        before=len(self.s.store.query('SELECT * FROM raw_documents'))
        with self.assertRaises(DomainError):self.s.ingest(p,m)
        self.assertEqual(len(self.s.store.query('SELECT * FROM raw_documents')),before)

class AdapterTests(unittest.TestCase):
    def test_form4_excludes_grants_and_derivatives(self):
        xml='<ownershipDocument><nonDerivativeTable>'
        for code in ('P','A','M','G','F'):
            xml+=f'<nonDerivativeTransaction><transactionCoding><transactionCode>{code}</transactionCode></transactionCoding><transactionAmounts><transactionShares><value>100</value></transactionShares><transactionPricePerShare><value>12</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts><transactionDate><value>2026-09-20</value></transactionDate></nonDerivativeTransaction>'
        xml+='</nonDerivativeTable></ownershipDocument>'
        result=parse_form4(xml.encode());self.assertEqual(len(result),1);self.assertEqual(result[0]['value'],1200)
    def test_xbrl_no_future_restatement(self):
        data={'facts':{'us-gaap':{'Revenues':{'units':{'USD':[{'val':100,'start':'2026-01-01','end':'2026-03-31','accn':'a'},{'val':50,'start':'2026-01-01','end':'2026-03-31','accn':'b'}]}}}}}
        r=xbrl_candidates(data,'2026-05-01T00:00:00Z',{'a':'2026-04-20T00:00:00Z','b':'2026-06-20T00:00:00Z'})
        self.assertEqual(len(r),1);self.assertEqual(r[0]['value'],100)

class SnapshotIntegrityTests(unittest.TestCase):
    setUp=ServiceTests.setUp
    tearDown=ServiceTests.tearDown
    # Additional scenarios are isolated from the base lifecycle suite.
    def test_changed_snapshot_id_conflict(self):
        m=deepcopy(fixtures()[0][1]);m['price']=109
        with self.assertRaises(DomainError) as e:self.s.refresh('opp-nova-d',m)
        self.assertEqual(e.exception.code,'SNAPSHOT_CONFLICT')
        self.assertEqual(self.s.get('opp-nova-d')['market_snapshot']['price'],106)
    def test_changed_market_security_blocks_ready(self):
        m=deepcopy(fixtures()[0][1]);m['snapshot_id']='new-other';m['ticker']='OTHER'
        core=self.s.refresh('opp-nova-d',m)
        self.assertNotEqual(core['state'],'READY');self.assertIn('DATA_SECURITY_MISMATCH',core['reason_codes'])
    def test_synthetic_fact_cannot_disagree_with_raw(self):
        p,m=fixtures()[0];p['accession']='DEMO-MODIFIED';p['event_id']='changed-event';p['opportunity_id']='changed-opp';p['evidence'][0]['evidence_id']='changed-ev'
        for f in p['facts']:f['evidence_id']='changed-ev';f['fact_id']='changed-'+f['fact_id']
        p['facts'][0]['value']=2000
        with self.assertRaises(DomainError):self.s.ingest(p,m)
    def test_unknown_metric_rejected(self):
        p,m=fixtures()[0];p['accession']='DEMO-UNKNOWN';p['event_id']='unknown-event';p['opportunity_id']='unknown-opp';p['evidence'][0]['evidence_id']='unknown-ev'
        for f in p['facts']:f['evidence_id']='unknown-ev';f['fact_id']='unknown-'+f['fact_id']
        p['facts'][0]['metric_id']='invented_alpha_score'
        with self.assertRaises(DomainError):self.s.ingest(p,m)
