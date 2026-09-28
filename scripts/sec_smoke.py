#!/usr/bin/env python3
"""Optional read-only live SEC smoke check. Isolated from the user's workspaces."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from usoe.util import ROOT,load_env,canonical
from usoe.storage import Store
from usoe.service import Service
from usoe.sources import Sources,SourceUnavailable

load_env()
service=Service(Store(ROOT/'data/sec-smoke.sqlite3'))
service.register({'security_id':'sec-msft-smoke','ticker':'MSFT','cik':'0000789019','issuer_name':'Microsoft Corporation','sector':'Technology'})
try:
    r=Sources(service).sec_sync('sec-msft-smoke',limit=1)
    print(canonical({'status':r['status'],'filings_archived':r['filings_archived'],'companyfacts_archived':bool(r['companyfacts_raw_id']),'opportunities_created':len(service.list()),'audit':service.store.verify_audit()['valid']}))
except SourceUnavailable as e:
    print(canonical({'status':'DEGRADED','reason':str(e),'opportunities_created':len(service.list())}))
    raise SystemExit(1)
