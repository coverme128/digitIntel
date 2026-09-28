from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager, closing
from pathlib import Path
from .util import ROOT, canonical, digest, utcnow, DomainError

IMMUTABLE = ('raw_documents','filings','evidence_spans','facts','events','market_snapshots','portfolio_snapshots','evaluations','transitions','outcomes','audit','broker_receipts','broker_executions','integration_calculations','ai_artifacts')

class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.executescript((ROOT / 'usoe/schema.sql').read_text())
            db.execute('INSERT OR IGNORE INTO schema_migrations VALUES (1,?)', (utcnow(),))
            for table in IMMUTABLE:
                for op in ('UPDATE','DELETE'):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS no_{op.lower()}_{table} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT,'immutable record'); END")
            for source, kind in [('sec','SEC_EDGAR'), ('massive','MARKET'), ('ibkr','BROKER'), ('demo','SYNTHETIC')]:
                db.execute('INSERT OR IGNORE INTO sources VALUES (?,?,?,NULL,NULL,?)', (source,kind,'NOT_CONFIGURED','REVIEW_REQUIRED' if source != 'demo' else 'SYNTHETIC_ONLY'))

    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=WAL')
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def query(self, query, params=()):
        db = self.connect()
        try:
            return [dict(x) for x in db.execute(query, params).fetchall()]
        finally:
            db.close()

    def setting(self, key, default=None):
        rows = self.query('SELECT value FROM settings WHERE key=?',(key,))
        return json.loads(rows[0]['value']) if rows else default

    @staticmethod
    def set_setting(db, key, value):
        db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,canonical(value)))

    @staticmethod
    def audit(db, action, entity_id, details):
        prev = db.execute('SELECT hash FROM audit ORDER BY id DESC LIMIT 1').fetchone()
        previous = prev['hash'] if prev else 'GENESIS'
        body = {'at':utcnow(),'action':action,'entity_id':entity_id,'details_json':canonical(details),'previous_hash':previous}
        h = digest(body)
        db.execute('INSERT INTO audit(at,action,entity_id,details_json,previous_hash,hash) VALUES (?,?,?,?,?,?)', (*body.values(),h))

    def verify_audit(self):
        previous = 'GENESIS'
        rows = self.query('SELECT * FROM audit ORDER BY id')
        for row in rows:
            body = {k:row[k] for k in ('at','action','entity_id','details_json','previous_hash')}
            if row['previous_hash'] != previous or digest(body) != row['hash']:
                return {'valid':False,'broken_at':row['id'],'count':len(rows)}
            previous = row['hash']
        return {'valid':True,'count':len(rows),'head':previous}

    @staticmethod
    def raw(db, source, external_id, content, published_at, url, demo=False):
        if isinstance(content,str): content = content.encode()
        raw_hash = digest(content)
        rid = 'raw_' + digest([source,external_id,raw_hash])[:24]
        db.execute('INSERT OR IGNORE INTO raw_documents VALUES (?,?,?,?,?,?,?,?,?)', (rid,source,external_id,raw_hash,published_at,utcnow(),url,content,int(demo)))
        return rid, raw_hash

    @staticmethod
    def require(db, table, identity):
        if table not in {'opportunities','events','evaluations','positions','order_intents','exit_intents'}:
            raise ValueError('Unknown entity')
        row = db.execute(f'SELECT * FROM {table} WHERE id=?',(identity,)).fetchone()
        if row is None: raise DomainError('Record not found','NOT_FOUND',404)
        return dict(row)
