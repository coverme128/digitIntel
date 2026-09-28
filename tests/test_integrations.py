import copy
import json
import tempfile
import unittest
from unittest.mock import patch,Mock
from datetime import timedelta
from usoe.integrations.market import MassiveClient,build_snapshot,split_adjust,outcome_statistics,millis
from usoe.integrations.broker import IBKRClient,reconcile_portfolio,reconcile_order,normalize_ack,order_payload,redact
from usoe.integrations.stream import MarketStream
from usoe.integrations.service import Integrations
from usoe.integrations.orders import BrokerOrders
from usoe.integrations.selftest import fixture,run
from usoe.integrations.transport import JSONTransport
from usoe.sources import SourceUnavailable
from usoe.util import DomainError,dt,canonical,read_rules
from usoe.storage import Store
from usoe.service import Service
from usoe.engine import evaluate

class FakeTransport:
    def __init__(self,responses):self.responses=list(responses);self.calls=[]
    def request(self,method,url,body=None,headers=None):
        self.calls.append((method,url,body,headers));r=self.responses.pop(0)
        if isinstance(r,Exception):raise r
        return copy.deepcopy(r)

class MarketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.inputs=fixture()
    def test_offline_check(self):self.assertTrue(run()['passed'])
    def test_paginated_rest_and_secret_redaction(self):
        bar=self.inputs['series']['security']['bars'][0];b2=bar|{'t':bar['t']+60000}
        http=FakeTransport([{'results':[bar],'next_url':'https://api.massive.com/page?cursor=abc&apiKey=secret'},{'results':[b2]}]);archive=[]
        c=MassiveClient('secret',http,lambda *a:archive.append(a));r=c.bars('TEST','2026-01-05','2026-01-06')
        self.assertEqual(len(r['bars']),2);self.assertNotIn('secret',canonical(archive));self.assertNotIn('secret',http.calls[1][1]);self.assertEqual(http.calls[0][3]['Authorization'],'Bearer secret')
    def test_pagination_host_escape(self):
        c=MassiveClient('secret',FakeTransport([{'results':[],'next_url':'https://evil.example/read'}]))
        with self.assertRaises(SourceUnavailable):c.paginate('/first')
    def test_pagination_loop(self):
        c=MassiveClient('secret',FakeTransport([{'results':[],'next_url':'/first'}]))
        with self.assertRaises(SourceUnavailable):c.paginate('/first')
    def test_empty_and_duplicate_bars(self):
        for rows in ([],[self.inputs['series']['security']['bars'][0]]*2):
            with self.assertRaises(SourceUnavailable):MassiveClient('s',FakeTransport([{'results':rows}])).bars('TEST','2026-01-05','2026-01-06')
    def test_outside_requested_dates_rejected(self):
        c=MassiveClient('s',FakeTransport([{'results':self.inputs['series']['security']['bars'][:1]}]))
        with self.assertRaises(SourceUnavailable):c.bars('TEST','2026-01-01','2026-01-02')
    def test_rest_quote_nanoseconds(self):
        c=MassiveClient('s',FakeTransport([{'results':{'p':100,'P':100.02,'t':1767623400000000000}}]));q=c.quote('TEST')
        self.assertEqual(millis(q['at']),1767623400000);self.assertLess(q['spread_bps'],3)
    def test_missing_benchmark_bar_blocks(self):
        args=copy.deepcopy(self.inputs);args['series']['spy']['bars'].pop(-4);r=build_snapshot(**args)
        self.assertFalse(r['complete']);self.assertEqual(r['coverage']['missing_minutes']['spy'],1)
    def test_future_bar_excluded(self):
        args=copy.deepcopy(self.inputs);b=args['series']['security']['bars'][-1]|{'t':millis(args['as_of']),'c':999,'h':999}
        args['series']['security']['bars'].append(b);r=build_snapshot(**args)
        self.assertEqual(r['price'],105);self.assertTrue(r['complete'])
    def test_missing_vwap_not_approximated(self):
        args=copy.deepcopy(self.inputs);args['series']['security']['bars'][-1]['vw']=None;r=build_snapshot(**args)
        self.assertFalse(r['complete']);self.assertIsNone(r['vwap'])
    def test_stale_quote(self):
        args=copy.deepcopy(self.inputs);args['quote']['at']=args['event_at'];r=build_snapshot(**args)
        self.assertFalse(r['complete']);self.assertIn('DATA_QUOTE_STALE_OR_INVALID',r['quality_errors'])
    def test_historical_never_claims_live(self):
        args=copy.deepcopy(self.inputs);args.update(quote=None,data_mode='historical');r=build_snapshot(**args)
        self.assertTrue(r['complete']);self.assertEqual(r['data_mode'],'historical');self.assertGreater(r['spread_bps'],30)
    def test_asof_split_does_not_apply_future_action(self):
        b=self.inputs['series']['security']['bars'][:1]
        adjusted,_=split_adjust(b,[{'execution_date':'2026-01-06','split_from':1,'split_to':2},{'execution_date':'2030-01-01','split_from':1,'split_to':10}],self.inputs['as_of'])
        self.assertEqual(adjusted[0]['c'],50);self.assertEqual(adjusted[0]['v'],200);self.assertEqual(b[0]['c'],100)
    def test_next_open_uses_open_and_no_lookahead(self):
        r=build_snapshot(**self.inputs);self.assertAlmostEqual(r['window_returns']['next_open']['raw_pct'],5)
        args=copy.deepcopy(self.inputs);args['event_at']=args['calendar']['sessions'][22]['open'];r=build_snapshot(**args)
        self.assertTrue(r['complete']);self.assertIsNone(r['window_returns']['next_open'])
    def test_volume_baseline_requires_twenty_complete_sessions(self):
        args=copy.deepcopy(self.inputs);args['series']['security']['bars']=args['series']['security']['bars'][-390*3:];r=build_snapshot(**args)
        self.assertFalse(r['complete']);self.assertIn('DATA_VOLUME_BASELINE_INCOMPLETE',r['quality_errors'])
    def test_outcome_avoids_entry_prefill_extrema(self):
        cal=self.inputs['calendar'];entry=cal['sessions'][0]['open'];row={'t':millis(entry),'o':100,'h':150,'l':50,'c':110,'v':100,'vw':100}
        r=outcome_statistics(100,(dt(entry)+timedelta(minutes=5)).isoformat(),cal['sessions'][0]['close'],[row],[row],cal)
        self.assertIsNone(r['mfe']);self.assertIsNone(r['mae']);self.assertIsNone(r['horizons']['1D']['return_pct'])
    def test_outcome_return_r_fees(self):
        cal=self.inputs['calendar'];entry=cal['sessions'][0]['open'];row={'t':millis(entry),'o':100,'h':112,'l':99,'c':110,'v':100}
        r=outcome_statistics(100,entry,cal['sessions'][0]['close'],[row],[row],cal,10,110,2,50,100)
        self.assertEqual(r['net_pnl'],98);self.assertEqual(r['r_multiple'],1.96);self.assertAlmostEqual(r['horizons']['1D']['benchmark_excess_pct'],0)

class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.security={'security_id':'s','ticker':'TEST','sector':'Technology','ibkr_conid':123}
        self.positions=[{'conid':123,'ticker':'TEST','position':10,'mktPrice':100,'mktValue':1000,'avgCost':99,'currency':'USD','assetClass':'STK'}]
        self.summary={k:{'currency':'USD','amount':v} for k,v in [('netliquidation',10000),('totalcashvalue',9000),('buyingpower',9000)]}
        self.ledger={'BASE':{'currency':'USD'},'USD':{'cashbalance':9000}}
        self.plans={'s':{'invalidation_price':95,'event_family':'GUIDANCE_CHANGE'}}
        self.ticket={'client_order_id':'ticket-1','conid':123,'quantity':5,'limit_price':100,'side':'BUY'}
        self.trade={'execution_id':'e1','order_ref':'ticket-1','conid':123,'side':'B','size':2,'price':'100','commission':'0.5'}
    def portfolio(self,**overrides):
        args={'positions':self.positions,'summary':self.summary,'ledger':self.ledger,'securities':[self.security],'plans':self.plans,'orders':[],'captured_at':'2026-01-05T16:00:00+00:00','account_ref':'redacted'};args.update(overrides);return reconcile_portfolio(**args)
    def test_reconciliation_and_planned_risk(self):
        p=self.portfolio();self.assertTrue(p['reconciled']);self.assertEqual(p['exposure']['open_planned_loss'],50)
    def test_missing_plan_blocks_without_zero_risk(self):
        p=self.portfolio(plans={});self.assertFalse(p['reconciled']);self.assertIsNone(p['exposure']['open_planned_loss'])
    def test_unknown_conid_and_foreign_currency_block(self):
        self.positions[0]['currency']='EUR';p=self.portfolio(securities=[])
        self.assertIn('RISK_SECURITY_MAPPING',p['hard_blocks']);self.assertIn('RISK_UNSUPPORTED_POSITION',p['hard_blocks'])
    def test_cash_or_equity_mismatch_blocks(self):
        self.summary['netliquidation']['amount']=11000;self.assertIn('RISK_EQUITY_RECONCILIATION',self.portfolio()['hard_blocks'])
    def test_active_orders_block_capacity(self):self.assertIn('RISK_OPEN_ORDERS_REVIEW',self.portfolio(orders=[{'status':'Submitted'}])['hard_blocks'])
    def test_partial_duplicate_fill(self):
        r=reconcile_order(self.ticket,[],[self.trade,self.trade]);self.assertEqual(r['filled_quantity'],2);self.assertEqual(r['state'],'PARTIALLY_FILLED')
    def test_partial_cancel(self):
        r=reconcile_order(self.ticket,[{'orderId':9,'order_ref':'ticket-1','status':'Cancelled','filledQuantity':2}],[self.trade]);self.assertEqual(r['state'],'CANCELLED_PARTIAL')
    def test_ack_does_not_create_fill(self):self.assertEqual(normalize_ack([{'order_id':1}],'DU1')['state'],'ACKNOWLEDGED')
    def test_reply_is_not_auto_confirmed(self):self.assertEqual(normalize_ack([{'id':'reply','message':['Warning']}],'DU1')['state'],'AWAITING_REPLY')
    def test_inconsistent_execution_requires_review(self):
        r=reconcile_order(self.ticket,[],[self.trade,self.trade|{'price':'101'}]);self.assertEqual(r['state'],'RECONCILIATION_REQUIRED')
    def test_broker_claim_filled_without_executions_blocks(self):
        r=reconcile_order(self.ticket,[{'order_ref':'ticket-1','status':'Filled','filledQuantity':5}],[]);self.assertEqual(r['state'],'RECONCILIATION_REQUIRED')
    def test_unknown_order_not_matched_by_missing_id(self):self.assertEqual(reconcile_order(self.ticket,[{'status':'Submitted'}],[])['state'],'UNKNOWN')
    def test_invalid_order_payload(self):
        for extra in ({'quantity':True},{'conid':-1},{'quantity':1.5},{'side':'SHORT'},{'order_type':'MKT'}):
            with self.assertRaises(DomainError):order_payload(self.ticket|extra)
    def test_no_paper_enable_no_network(self):
        h=FakeTransport([]);c=IBKRClient('DU1',transport=h)
        with self.assertRaises(DomainError):c.submit(self.ticket,True)
        self.assertEqual(h.calls,[])
    def test_live_account_cannot_submit(self):
        h=FakeTransport([{'authenticated':True,'connected':True},[{'accountId':'U1','type':'INDIVIDUAL'}],{'selectedAccount':'U1'}]);c=IBKRClient('U1',transport=h,paper_enabled=True)
        with self.assertRaises(DomainError):c.submit(self.ticket,True)
        self.assertTrue(all(c[0]=='GET' for c in h.calls))
    def test_competing_session_blocks(self):
        c=IBKRClient('DU1',transport=FakeTransport([{'authenticated':True,'connected':True,'competing':True}]))
        with self.assertRaises(DomainError):c.require_session()
    def test_position_pagination(self):
        first=[{'conid':i} for i in range(100)];h=FakeTransport([first,[{'conid':101}]]);r=IBKRClient('DU1',transport=h).positions();self.assertEqual(len(r),101)
    def test_account_mismatch_orders(self):
        c=IBKRClient('DU1',transport=FakeTransport([{'selectedAccount':'DU1'},{'snapshot':True,'orders':[{'acct':'UOTHER'}]}]))
        with self.assertRaises(DomainError):c.orders()
    def test_tickle_does_not_archive_session(self):
        archive=[];c=IBKRClient('DU1',transport=FakeTransport([{'session':'secret','iserver':{'authStatus':{'authenticated':True}}}]),archive=lambda *x:archive.append(x))
        self.assertNotIn('secret',canonical(c.keepalive()));self.assertEqual(archive,[])

class StreamTests(unittest.TestCase):
    def stream(self):return MarketStream('secret',['TEST'],clock=lambda:'2026-01-05T14:32:00+00:00')
    def test_auth_before_subscription_and_recovery(self):
        s=self.stream();s.on_recovery=lambda symbols:True
        class Socket:
            def __init__(self):self.sent=[];self.receives=0
            def send(self,msg):
                data=json.loads(msg)
                if data['action']=='subscribe':assert self.receives>=2
                self.sent.append(data)
            def recv(self,timeout):
                self.receives+=1
                if self.receives==1:return '[{"ev":"status","status":"connected"}]'
                if self.receives==2:return '[{"ev":"status","status":"auth_success"}]'
                s.stop_event.set();return '[]'
        ws=Socket();s.run_connection(ws);self.assertEqual([x['action'] for x in ws.sent],['auth','subscribe']);self.assertFalse(s.gap)
    def test_auth_failure_does_not_subscribe(self):
        s=self.stream();ws=Mock();ws.recv.return_value='[{"ev":"status","status":"auth_failed"}]'
        with self.assertRaises(SourceUnavailable):s.run_connection(ws)
        self.assertEqual(ws.send.call_count,1)
    def test_aggregate_correction_replaces_volume(self):
        s=self.stream();r={'ev':'AM','sym':'TEST','s':1767623400000,'e':1767623460000,'o':100,'h':102,'l':99,'c':101,'v':100,'vw':100.5}
        s.consume(canonical([r]));s.consume(canonical([r|{'v':200}]))
        self.assertEqual(len(s.bars['TEST']),1);self.assertEqual(next(iter(s.bars['TEST'].values()))['v'],200)
    def test_quote_sequence_gaps_not_interpreted_as_missing(self):
        s=self.stream();r={'ev':'Q','sym':'TEST','bp':100,'ap':101,'t':1767623400000,'q':1};s.consume(canonical([r,r|{'q':10}]))
        self.assertEqual(s.quotes['TEST']['sequence'],10)

class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name+'/test.sqlite3');self.service=Service(self.store,clock=lambda:'2026-01-05T16:00:00+00:00');self.integrations=Integrations(self.service)
    def tearDown(self):self.tmp.cleanup()
    def test_no_configuration_status_no_network(self):
        with patch.dict('os.environ',{},clear=True):
            r=self.integrations.status();self.assertFalse(r['massive']['configured']);self.assertFalse(r['ibkr']['configured']);self.assertFalse(r['ibkr']['live_trading'])
    def test_failure_invalidates_previous_portfolio(self):
        self.service.save_portfolio({'snapshot_id':'old','captured_at':self.service.now(),'equity':10000,'cash':10000,'buying_power':10000,'positions':[],'reconciled':True,'is_demo':False})
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(DomainError):self.integrations.sync_broker()
        self.assertFalse(self.service.portfolio()['reconciled']);self.assertIn('RISK_BROKER_SYNC_FAILED',self.service.portfolio()['hard_blocks'])
    def test_paper_mutation_timeout_not_retried(self):
        broker=Mock(account_ref='account');broker.submit.side_effect=SourceUnavailable('timeout');self.integrations._broker=broker;orders=BrokerOrders(self.integrations)
        body={'opportunity_id':'o','side':'BUY','quantity':1,'limit_price':100};security={'security_id':'s','ticker':'TEST','ibkr_conid':123}
        with patch.object(orders,'_eligibility',return_value=(security,{},'portfolio')):
            t=orders.create(body,'key-00001');t['state']='PREVIEWED'
            with self.store.transaction() as db:orders._save(db,t,'TEST_PREVIEW')
            a=orders.act(t['id'],'submit',{'confirmed':True});b=orders.act(t['id'],'submit',{'confirmed':True})
        self.assertEqual(a['state'],'UNKNOWN');self.assertEqual(b['state'],'UNKNOWN');self.assertEqual(broker.submit.call_count,1)
    def test_draft_idempotency(self):
        self.integrations._broker=Mock(account_ref='account');orders=BrokerOrders(self.integrations)
        body={'opportunity_id':'o','quantity':1,'limit_price':100};security={'security_id':'s','ticker':'TEST','ibkr_conid':123}
        with patch.object(orders,'_eligibility',return_value=(security,{},'p')):
            t=orders.create(body,'key-00001');self.assertEqual(t['id'],orders.create(body,'key-00001')['id'])
            with self.assertRaises(DomainError):orders.create(body|{'quantity':2},'key-00001')
    def test_paper_requires_confirmation(self):
        with self.assertRaises(DomainError):BrokerOrders(self.integrations).act('id','submit',{})
    def test_demo_refuses_live_snapshot(self):
        with self.assertRaises(DomainError):Integrations(Service(self.store,demo=True)).sync_broker()
    def test_receipts_immutable(self):
        import sqlite3
        with self.store.transaction() as db:db.execute('INSERT INTO integration_calculations VALUES (?,?,?,?,?)',('x','OUTCOME','{}','{}',self.service.now()))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.transaction() as db:db.execute("DELETE FROM integration_calculations WHERE id='x'")

class CalendarTests(unittest.TestCase):
    def test_holiday_and_early_close(self):
        try:import exchange_calendars
        except ImportError:self.skipTest('Install requirements-integrations.txt')
        from usoe.calendar import exchange_calendar
        r=exchange_calendar('2026-11-25','2026-11-30');self.assertEqual(len(r['sessions']),3)
        self.assertEqual(r['sessions'][1]['close'],'2026-11-27T18:00:00+00:00')
    def test_dst_open_time(self):
        try:import exchange_calendars
        except ImportError:self.skipTest('Install requirements-integrations.txt')
        from usoe.calendar import exchange_calendar
        r=exchange_calendar('2026-03-06','2026-03-10');self.assertIn('14:30',r['sessions'][0]['open']);self.assertIn('13:30',r['sessions'][1]['open'])

class TransportTests(unittest.TestCase):
    def test_mutation_timeout_has_single_attempt(self):
        import urllib.error
        http=JSONTransport(sleep=lambda _:None);http.opener=Mock();http.opener.open.side_effect=urllib.error.URLError('timeout')
        with self.assertRaises(SourceUnavailable):http.request('POST','https://localhost:5000/v1/api/order',{})
        self.assertEqual(http.opener.open.call_count,1)
    def test_get_retries_429(self):
        import urllib.error
        http=JSONTransport(sleep=lambda _:None);http.opener=Mock();response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.read.return_value=b'{"results":[]}'
        http.opener.open.side_effect=[urllib.error.HTTPError('https://api.massive.com/x',429,'limit',{'Retry-After':'0'},None),response]
        self.assertEqual(http.request('GET','https://api.massive.com/x'),{'results':[]});self.assertEqual(http.opener.open.call_count,2)
    def test_tls_downgrade_rejected(self):
        import urllib.request
        from usoe.integrations.transport import TLSRedirect
        req=urllib.request.Request('https://api.massive.com/x')
        with self.assertRaises(SourceUnavailable):TLSRedirect().redirect_request(req,None,302,'',{},'http://api.massive.com/y')

class ConnectedFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.inputs=fixture();self.s=Service(Store(self.tmp.name+'/shadow.db'),clock=lambda:self.inputs['as_of'])
        self.s.register({'security_id':'test','ticker':'TEST','cik':'0000000001','issuer_name':'Synthetic Fixture Inc','sector':'Technology','ibkr_conid':123})
        self.massive=Mock();bundles={x['ticker']:x for x in self.inputs['series'].values()}
        self.massive.bars.side_effect=lambda ticker,*a,**kw:copy.deepcopy(bundles[ticker]);self.massive.splits.return_value={'results':[],'raw_refs':[]};self.massive.quote.return_value=self.inputs['quote']
        self.i=Integrations(self.s,massive=self.massive,calendar=lambda *a:self.inputs['calendar'])
    def tearDown(self):self.tmp.cleanup()
    def test_full_fetch_calculate_archive(self):
        with patch.dict('os.environ',{'MASSIVE_DATA_MODE':'realtime'}):r=self.i.calculate_market({'security_id':'test','event_at':self.inputs['event_at']})
        self.assertTrue(r['complete']);self.assertEqual(self.massive.bars.call_count,3);self.assertEqual(len(self.s.store.query('SELECT * FROM market_snapshots')),1)
    def test_broker_endpoints_to_reconciled_snapshot(self):
        http=FakeTransport([{'authenticated':True,'connected':True},[{'accountId':'DU1','type':'DEMO'}],[],{k:{'currency':'USD','amount':10000} for k in ('netliquidation','totalcashvalue','buyingpower')},{'BASE':{'currency':'USD'},'USD':{'cashbalance':10000}},{'selectedAccount':'DU1'},{'snapshot':True,'orders':[]},{'selectedAccount':'DU1'},[]])
        self.i._broker=IBKRClient('DU1',transport=http,archive=self.i.archive)
        bundle=self.i.sync_broker();self.assertTrue(bundle['portfolio']['reconciled']);self.assertTrue(self.s.portfolio()['reconciled'])
        archived=self.s.store.query('SELECT content FROM raw_documents');self.assertNotIn('DU1',''.join(bytes(r['content']).decode() for r in archived))
    def test_incomplete_market_evaluates_without_crash(self):
        from usoe.demo import fixtures
        packet,_=fixtures()[0];packet=copy.deepcopy(packet);packet.update(is_demo=False,event_at=self.inputs['event_at']);packet['security'].update(ticker='TEST',security_id='test')
        args=copy.deepcopy(self.inputs);args['series']['security']['bars'][-1]['vw']=None;m=build_snapshot(**args)
        core=evaluate(packet,m,{'equity':0,'positions':[{'planned_loss':None}]},read_rules(),self.inputs['as_of'])
        self.assertNotEqual(core['state'],'READY');self.assertIn('DATA_VWAP_MISSING',core['reason_codes'])
    def test_mapping_plan_change_invalidates_portfolio(self):
        self.s.save_portfolio({'snapshot_id':'p','equity':10000,'cash':10000,'buying_power':10000,'reconciled':True,'is_demo':False,'positions':[],'captured_at':self.s.now()})
        self.i.position_plan({'security_id':'test','event_family':'GUIDANCE_CHANGE','invalidation_price':95})
        self.assertFalse(self.s.portfolio()['reconciled'])

class BrokerAccountIsolationTests(unittest.TestCase):
    setUp=ApplicationTests.setUp
    tearDown=ApplicationTests.tearDown
    def test_old_account_order_not_reconciled_against_new_account(self):
        self.integrations._broker=Mock(account_ref='old-account');orders=BrokerOrders(self.integrations)
        body={'opportunity_id':'o','quantity':1,'limit_price':100};security={'security_id':'s','ticker':'TEST','ibkr_conid':123}
        with patch.object(orders,'_eligibility',return_value=(security,{},'p')):ticket=orders.create(body,'unique-key-1')
        ticket['state']='ACKNOWLEDGED';ticket['broker_order_id']='1'
        with self.store.transaction() as db:orders._save(db,ticket,'TEST')
        orders.reconcile_all({'portfolio':{'account_ref':'new-account'},'orders':[{'orderId':1,'status':'Cancelled'}],'trades':[]})
        self.assertEqual(orders.get(ticket['id'])['state'],'ACKNOWLEDGED')
