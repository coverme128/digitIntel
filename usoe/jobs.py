"""Opt-in local SEC polling; durable job state, no network calls on normal startup."""
import json
import threading
from .sources import Sources,SourceUnavailable
from .util import utcnow,canonical,DomainError
from .storage import Store

class SECWorker:
    def __init__(self,service,interval=300):
        if interval<60:raise ValueError('SEC polling interval must be at least 60 seconds')
        if service.demo:raise ValueError('SEC polling cannot run in demo workspace')
        self.service=service;self.interval=interval;self.stop_event=threading.Event()
        self.sources=Sources(service);self.thread=None
        with service.store.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,state TEXT NOT NULL,started_at TEXT NOT NULL,finished_at TEXT,details_json TEXT NOT NULL)')
            db.execute("UPDATE jobs SET state='INTERRUPTED',finished_at=? WHERE state='RUNNING'",(utcnow(),))

    def run_once(self,security_ids=None):
        s=self.service
        with s.store.transaction() as db:
            cursor=db.execute("INSERT INTO jobs(kind,state,started_at,details_json) VALUES ('SEC_POLL','RUNNING',?,'{}')",(utcnow(),));job=cursor.lastrowid
        result={'synced':0,'filings_archived':0,'failures':[]}
        try:
            # Membership is date-effective; historical index membership is never inferred.
            day=s.now()[:10]
            rows=s.store.query('SELECT DISTINCT security_id FROM universe_memberships WHERE valid_from<=? AND (valid_to IS NULL OR valid_to>?)',(day,day))
            if security_ids is not None:rows=[r for r in rows if r['security_id'] in security_ids]
            for row in rows:
                if self.stop_event.is_set():break
                try:
                    response=self.sources.sec_sync(row['security_id']);result['synced']+=1;result['filings_archived']+=response['filings_archived']
                except (SourceUnavailable,DomainError) as e:result['failures'].append({'security_id':row['security_id'],'error':str(e)})
            for c in s.list():
                if c['state'] not in ('IGNORED','EXITED','INVALIDATED'):
                    s.refresh(c['opportunity_id'])
            state='DEGRADED' if result['failures'] else 'SUCCEEDED'
        except Exception as e:
            result['error_type']=type(e).__name__;state='FAILED'
        with s.store.transaction() as db:
            db.execute('UPDATE jobs SET state=?,finished_at=?,details_json=? WHERE id=?',(state,utcnow(),canonical(result),job))
            Store.audit(db,'SEC_POLL_COMPLETED',str(job),{'state':state,**result})
        return {'job_id':job,'state':state,**result}

    def start(self):
        def work():
            while not self.stop_event.is_set():
                self.run_once()
                self.stop_event.wait(self.interval)
        self.thread=threading.Thread(target=work,name='sec-poll',daemon=True);self.thread.start()

    def stop(self):self.stop_event.set()
