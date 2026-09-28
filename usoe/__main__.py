import argparse
import os
from .util import ROOT,load_env,canonical
from .storage import Store
from .service import Service
from .server import AppServer


def main():
    load_env()
    parser=argparse.ArgumentParser(description='US Opportunity Engine — local-only research and paper simulation')
    parser.add_argument('--demo',action='store_true',help='Use isolated fictional demo replay database')
    parser.add_argument('--port',type=int,default=int(os.environ.get('USOE_PORT','8787')))
    parser.add_argument('--poll-sec',type=int,metavar='SECONDS',help='Opt-in SEC polling in shadow mode, minimum 60 seconds')
    parser.add_argument('--poll-integrations',type=int,metavar='SECONDS',help='Opt-in read-only Massive/IBKR polling, minimum 60 seconds')
    parser.add_argument('--stream-symbols',help='Optional comma-separated Massive AM/Q subscriptions; requires --poll-integrations')
    parser.add_argument('--db',help='Optional database path; never share across demo and shadow')
    args=parser.parse_args()
    db=args.db or ROOT/'data'/('demo.sqlite3' if args.demo else 'shadow.sqlite3')
    store=Store(db)
    existing=store.setting('workspace_mode')
    mode='demo' if args.demo else 'shadow'
    if existing and existing!=mode:parser.error('Cannot switch workspace mode for an existing database')
    with store.transaction() as conn:
        Store.set_setting(conn,'workspace_mode',mode)
        if store.setting('ai_mode') is None:Store.set_setting(conn,'ai_mode',os.environ.get('AI_MODE','off') if os.environ.get('AI_MODE','off') in ('off','assist') else 'off')
    service=Service(store,demo=args.demo)
    if args.demo:service.seed_demo()
    worker=None
    if args.poll_sec:
        from .jobs import SECWorker
        try:worker=SECWorker(service,args.poll_sec)
        except ValueError as e:parser.error(str(e))
    server=AppServer(('127.0.0.1',args.port),service)
    integration_worker=None
    if args.stream_symbols and not args.poll_integrations:parser.error('--stream-symbols requires --poll-integrations')
    if args.poll_integrations:
        from .integrations.worker import IntegrationWorker
        try:integration_worker=IntegrationWorker(server.integrations,args.poll_integrations,args.stream_symbols.split(',') if args.stream_symbols else None)
        except Exception as e:parser.error(str(e))
    print(canonical({'event':'server_started','url':f'http://127.0.0.1:{args.port}','mode':mode,'status':'PRODUCTION_BLOCKED'}),flush=True)
    if worker:worker.start()
    if integration_worker:integration_worker.start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        if worker:worker.stop()
        if integration_worker:integration_worker.stop()
        server.server_close()

if __name__=='__main__':main()
