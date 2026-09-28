"""Opt-in read-only account/market polling; never submits or confirms broker orders."""
import os
import threading
from ..util import DomainError,utcnow
from .stream import MarketStream

class IntegrationWorker:
    def __init__(self,integrations,interval=60,stream_symbols=None):
        if interval<60:raise ValueError('Integration polling minimum is 60 seconds')
        integrations.shadow();self.i=integrations;self.interval=interval;self.stop_event=threading.Event();self.thread=None
        if stream_symbols:
            mode=os.environ.get('MASSIVE_DATA_MODE','historical')
            self.i.stream=MarketStream(os.environ.get('MASSIVE_API_KEY'),stream_symbols,mode,on_recovery=self.recover)

    def recover(self,symbols):
        client=self.i.massive();day=utcnow()[:10]
        # Refetch current trading day after each reconnect. This alone never creates READY.
        for ticker in symbols:client.bars(ticker,day,day,adjusted=False)
        return True

    def cycle(self):
        if os.environ.get('IBKR_ACCOUNT_ID'):
            try:
                try:self.i.broker().keepalive()
                except Exception:pass
                self.i.sync_broker()
            except Exception:pass # sync records a failed source and blocks the portfolio
        for row in self.i.store.query("SELECT id FROM opportunities WHERE state IN ('WATCH','READY','ENTERED')"):
            try:
                if os.environ.get('MASSIVE_API_KEY'):self.i.refresh_market(row['id'])
                else:self.i.service.refresh(row['id']) # age out old snapshots even without a key
            except Exception:pass

    def _run(self):
        while not self.stop_event.is_set():
            self.cycle()
            if self.stop_event.wait(self.interval):break

    def start(self):
        if self.i.stream:self.i.stream.start()
        self.thread=threading.Thread(target=self._run,name='integration-poll',daemon=True);self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.i.stream:self.i.stream.stop()
        if self.thread:self.thread.join(timeout=3)
