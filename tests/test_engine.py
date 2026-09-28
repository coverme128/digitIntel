import unittest
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from usoe.demo import fixtures,portfolio,market,packet,AS_OF,calendar
from usoe.engine import evaluate,bucket,percent_delta,allowed_transition,analogs,risk_worksheet
from usoe.util import read_rules,digest
from usoe.calendar import classify_session,trading_age

class EngineTests(unittest.TestCase):
    def setUp(self):self.p,self.m=fixtures()[0];self.port=portfolio();self.rules=read_rules()
    def core(self):return evaluate(self.p,self.m,self.port,self.rules,AS_OF)
    def fact(self,key,value):
        for f in self.p['facts']:
            if f['metric_id']==key:f['value']=value;return
        self.p['facts'].append({'fact_id':key,'metric_id':key,'value':value,'unit':'boolean','period_start':'2026-01-01','period_end':'2026-12-31','evidence_id':self.p['evidence'][0]['evidence_id'],'fact_version':1})

    def test_normal_guidance_calculation_and_ready(self):
        c=self.core();self.assertEqual(c['state'],'READY');self.assertAlmostEqual(c['calculations'][0]['change'],7.619048)
        self.assertEqual(c['reaction']['sector_excess_pct'],5);self.assertEqual(c['portfolio']['sizing']['max_shares'],83)
    def test_materiality_boundaries(self):
        for value,expected in [(2.999,'LOW'),(3,'MEDIUM'),(4.999,'MEDIUM'),(5,'HIGH'),(10,'HIGH'),(10.001,'VERY_HIGH')]:
            with self.subTest(value=value):self.assertEqual(bucket(value,3,5,10),expected)
    def test_zero_and_negative_base(self):self.assertIsNone(percent_delta(0,10));self.assertEqual(percent_delta(-5,5),200)
    def test_period_mismatch_blocks(self):
        self.p['facts'][0]['period_end']='2025-12-31';c=self.core();self.assertNotEqual(c['state'],'READY');self.assertIn('DATA_PERIOD_MISMATCH',c['reason_codes'])
    def test_unit_mismatch_blocks(self):
        self.p['facts'][0]['unit']='EUR';self.assertIn('DATA_UNIT_MISMATCH',self.core()['reason_codes'])
    def test_evidence_missing_blocks(self):self.p['evidence']=[];self.assertEqual(self.core()['state'],'DISCOVERED')
    def test_unsupported_ai_evidence_blocks(self):self.p['evidence'][0]['level']='E4';self.assertEqual(self.core()['state'],'DISCOVERED')
    def test_extended_cannot_ready(self):self.m['price']=120;self.assertEqual(self.core()['reaction']['bucket'],'EXTENDED_REACTION');self.assertNotEqual(self.core()['state'],'READY')
    def test_negative_reaction_never_underreaction(self):self.m['price']=100;self.assertEqual(self.core()['reaction']['bucket'],'ADVERSE_REACTION');self.assertNotEqual(self.core()['state'],'READY')
    def test_caution_does_not_use_generic_trigger(self):self.m['price']=112;self.assertEqual(self.core()['reaction']['bucket'],'CAUTION');self.assertNotEqual(self.core()['state'],'READY')
    def test_missing_market_window(self):self.m['complete']=False;self.assertNotEqual(self.core()['state'],'READY')
    def test_market_stale(self):self.m['captured_at']='2026-09-25T15:00:00+00:00';self.assertIn('DATA_STALE',self.core()['reason_codes']);self.assertNotEqual(self.core()['state'],'READY')
    def test_future_market(self):self.m['captured_at']='2026-09-25T15:31:00+00:00';self.assertNotEqual(self.core()['state'],'READY')
    def test_delayed_data(self):self.m['data_mode']='delayed';self.assertNotEqual(self.core()['state'],'READY')
    def test_broker_stale(self):self.port['captured_at']='2026-09-25T15:00:00+00:00';c=self.core();self.assertEqual(c['trigger_status'],'READY_BLOCKED');self.assertNotEqual(c['state'],'READY')
    def test_buying_power_unknown(self):self.port['buying_power']=None;self.assertIn('RISK_BUYING_POWER',self.core()['risk_flags'])
    def test_reconciliation_failure(self):self.port['reconciled']=False;self.assertNotEqual(self.core()['state'],'READY')
    def test_opening_guard(self):self.m['regular_open_at']='2026-09-25T15:28:00+00:00';self.assertNotEqual(self.core()['state'],'READY')
    def test_halted_or_wide_spread(self):
        for k,v in [('halted',True),('spread_bps',100)]:
            with self.subTest(k=k):
                m=deepcopy(self.m);m[k]=v;self.assertNotEqual(evaluate(self.p,m,self.port,self.rules,AS_OF)['state'],'READY')
    def test_volume_required(self):self.m['volume']=1000000;self.assertNotEqual(self.core()['state'],'READY')
    def test_expiry_uses_sessions(self):self.p['event_at']='2026-08-28T20:15:00+00:00';self.assertEqual(self.core()['state'],'INVALIDATED')
    def test_missing_calendar_blocks(self):self.m['calendar']={};self.assertNotEqual(self.core()['state'],'READY')
    def test_withdrawal_cannot_be_entry_candidate(self):self.fact('guidance_withdrawn',True);c=self.core();self.assertEqual(c['role'],'POSITION_RISK');self.assertNotEqual(c['state'],'READY')
    def test_price_invalidation_only_closed_session(self):
        self.m['close_price']=99;self.assertEqual(self.core()['state'],'READY');self.m['session_closed']=True;self.assertEqual(self.core()['state'],'INVALIDATED')
    def test_long_risk_limit(self):
        r=risk_worksheet(self.p['security'],self.p['event_family'],self.m,self.port,AS_OF,self.rules,quantity=1000,entry=106,stop=100)
        self.assertIn('RISK_PLANNED_LOSS',r['hard_blocks']);self.assertIn('RISK_POSITION_CONCENTRATION',r['hard_blocks'])
    def test_sector_and_catalyst_limits(self):
        self.port['positions']=[{'security_id':'other','market_value':40000,'sector':'Technology','event_family':'GUIDANCE_CHANGE','planned_loss':0}]
        r=risk_worksheet(self.p['security'],self.p['event_family'],self.m,self.port,AS_OF,self.rules,quantity=1,entry=106,stop=100)
        self.assertIn('RISK_SECTOR_CONCENTRATION',r['hard_blocks']);self.assertIn('RISK_DUPLICATE_THESIS',r['hard_blocks'])
    def test_transition_actor_and_edges(self):
        self.assertFalse(allowed_transition('WATCH','ENTERED','USER'));self.assertFalse(allowed_transition('READY','ENTERED','ENGINE'));self.assertTrue(allowed_transition('READY','ENTERED','USER'));self.assertFalse(allowed_transition('EXITED','WATCH','USER'))
    def test_ai_fields_no_core_influence(self):
        before=self.core();self.p['ai_explanation']='STRONG BUY';self.p['ai_summary']='invented';after=self.core()
        self.assertEqual(before,after)
    def test_history_future_outcomes_excluded(self):
        row={'event_family':'GUIDANCE_CHANGE','event_at':'2026-09-01T13:00:00+00:00','outcome_known_at':'2026-09-26T13:00:00+00:00','return_5d':10}
        self.assertEqual(analogs([row]*40,self.p['event_at'],'GUIDANCE_CHANGE')['n'],0)
        row['outcome_known_at']='2026-09-20T13:00:00+00:00'
        self.assertIsNone(analogs([row]*9,self.p['event_at'],'GUIDANCE_CHANGE')['statistics'])
        self.assertEqual(analogs([row]*10,self.p['event_at'],'GUIDANCE_CHANGE')['status'],'LOW_SAMPLE')
    def test_calendar_timezone_and_holiday(self):
        self.assertEqual(classify_session('2026-09-25T12:00:00Z',calendar())['session'],'PREMARKET')
        self.assertEqual(classify_session('2026-09-25T15:00:00Z',calendar())['session'],'REGULAR')
        self.assertEqual(classify_session('2026-09-25T21:00:00Z',calendar())['session'],'AFTER_HOURS')
        self.assertEqual(classify_session('2026-09-07T15:00:00Z',calendar())['session'],'NON_TRADING')
        self.assertEqual(trading_age('2026-09-04T21:00:00Z','2026-09-08T19:00:00Z',calendar()),0)
    def test_early_close(self):
        c={'start':'2026-11-25','end':'2026-12-01','sessions':[{'open':'2026-11-25T14:30:00Z','close':'2026-11-25T21:00:00Z'},{'open':'2026-11-27T14:30:00Z','close':'2026-11-27T18:00:00Z'},{'open':'2026-11-30T14:30:00Z','close':'2026-11-30T21:00:00Z'}]}
        self.assertEqual(classify_session('2026-11-27T18:05:00Z',c)['session'],'AFTER_HOURS')

class FamilyRegression100(unittest.TestCase):
    """100 synthetic rule scenarios; explicitly NOT historical Golden 100."""
    def test_100_synthetic_family_cases(self):
        rules=read_rules();cases=[]
        # 30 earnings, 15 buyback, 15 insider, 10 activist, 10 dilution, 10 corporate, 10 M&A.
        for i in range(30):
            change=[1,4,7,12,18][i%5]
            p=packet('E.D','Synthetic earnings','GUIDANCE_CHANGE','guidance_raised',{'prior_revenue_guidance_low':100,'prior_revenue_guidance_high':100,'current_revenue_guidance_low':100+change,'current_revenue_guidance_high':100+change})
            cases.append((p,market('E.D'),'ENTRY_CANDIDATE','READY' if change>=5 else 'VERIFIED'))
        for i in range(15):
            ratio=[1,3,6,10,12][i%5]
            p=packet('B.D','Synthetic buyback','CAPITAL_RETURN','buyback',{'authorization':ratio*1000000,'market_cap':100000000,'balance_sheet_capacity':True,'execution_credibility':True})
            cases.append((p,market('B.D'),'ENTRY_CANDIDATE','READY' if ratio>=5 else ('WATCH' if ratio>=2 else 'VERIFIED')))
        for i in range(15):
            p=packet('I.D','Synthetic insider','INSIDER_OPEN_MARKET_BUY','purchase',{})
            code=['P','A','M'][i%3]
            p['insider_transactions']=[{'owner_id':str(j),'code':code,'acquired_disposed':'A','derivative':False,'at':'2026-09-24T18:00:00Z','value':300000,'title':'CEO' if j==0 else 'Director','evidence_id':p['evidence'][0]['evidence_id']} for j in range(2)]
            cases.append((p,market('I.D'),'ENTRY_CANDIDATE' if code=='P' else 'CONTEXT_ONLY','READY' if code=='P' else 'VERIFIED'))
        for i in range(10):
            active=i%2==0
            p=packet('A.D','Synthetic activist','ACTIVIST_OWNERSHIP','initial_13d',{'ownership_pct':6,'active_intent':active,'explicit_activist_purpose':True})
            cases.append((p,market('A.D'),'ENTRY_CANDIDATE','READY' if active else 'VERIFIED'))
        for i in range(10):
            p=packet('F.D','Synthetic financing','FINANCING_DILUTION','secondary',{'existing_shares':1000000,'new_shares':(i+1)*20000})
            cases.append((p,market('F.D'),'POSITION_RISK','VERIFIED'))
        for i in range(10):
            p=packet('C.D','Synthetic corporate','MATERIAL_CORPORATE_EVENT','material_contract',{'economic_mechanism':'contract_backlog'})
            cases.append((p,market('C.D'),'ENTRY_CANDIDATE','WATCH'))
        for i in range(10):
            p=packet('M.D','Synthetic merger','MNA_SPECIAL','definitive_merger',{'definitive_agreement':True,'offer_price':120,'reference_price':106})
            cases.append((p,market('M.D'),'CONTEXT_ONLY','VERIFIED'))
        self.assertEqual(len(cases),100)
        for index,(p,m,role,state) in enumerate(cases):
            with self.subTest(index=index,family=p['event_family']):
                result=evaluate(p,m,portfolio(),rules,AS_OF)
                self.assertEqual(result['role'],role);self.assertEqual(result['state'],state)
