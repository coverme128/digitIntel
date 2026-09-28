#!/usr/bin/env python3
"""Local maintenance, no network unless sync-sec is explicitly requested."""
import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from usoe.storage import Store
from usoe.service import Service
from usoe.util import ROOT,load_env,canonical,digest


def main():
    load_env();p=argparse.ArgumentParser()
    p.add_argument('--db',default=str(ROOT/'data/shadow.sqlite3'))
    commands=p.add_subparsers(dest='command',required=True)
    backup=commands.add_parser('backup');backup.add_argument('destination')
    commands.add_parser('verify')
    commands.add_parser('replay')
    membership=commands.add_parser('universe');membership.add_argument('csv_file')
    ingest=commands.add_parser('import');ingest.add_argument('json_file')
    commands.add_parser('sync-sec')
    args=p.parse_args();store=Store(args.db);service=Service(store,demo=store.setting('workspace_mode')=='demo')
    if args.command=='backup':
        target=Path(args.destination)
        if target.exists():p.error('Backup destination already exists; use a new filename')
        source=store.connect();destination=sqlite3.connect(target)
        try:source.backup(destination)
        finally:source.close();destination.close()
        print(canonical({'backup':str(target.resolve()),'sha256':digest(target.read_bytes())}))
    elif args.command=='verify':
        db=store.connect()
        try:integrity=db.execute('PRAGMA integrity_check').fetchone()[0];fk=[tuple(x) for x in db.execute('PRAGMA foreign_key_check')]
        finally:db.close()
        audit=store.verify_audit();print(canonical({'database':integrity,'foreign_keys':fk,'audit':audit}));return 0 if integrity=='ok' and not fk and audit['valid'] else 1
    elif args.command=='replay':
        results=[service.replay(c['opportunity_id']) for c in service.list()];print(canonical({'count':len(results),'results':results}));return 0 if all(x['match'] for x in results) else 1
    elif args.command=='universe':
        with open(args.csv_file,newline='') as f:
            rows=list(csv.DictReader(f))
        for row in rows:
            s={k:row[k] for k in ('security_id','ticker','cik','issuer_name','sector')}
            service.register(s,row['universe'],row['valid_from'])
        print(canonical({'registered':len(rows)}))
    elif args.command=='import':
        payload=json.loads(Path(args.json_file).read_text());result=service.ingest(payload['event'],payload['market_snapshot']);print(canonical({'opportunity_id':result['opportunity_id'],'state':result['state']}))
    elif args.command=='sync-sec':
        from usoe.jobs import SECWorker
        print(canonical(SECWorker(service).run_once()))
    return 0

if __name__=='__main__':raise SystemExit(main())
