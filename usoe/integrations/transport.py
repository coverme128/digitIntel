"""Persistent TLS HTTP transport. Retries only safe reads, never order mutations."""
import http.cookiejar
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from email.utils import parsedate_to_datetime
from datetime import datetime,timezone
from ..sources import SafeRedirect,SourceUnavailable
from ..util import canonical

class TLSRedirect(SafeRedirect):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if req.get_method()!='GET' or urlparse(newurl).scheme!='https':
            raise SourceUnavailable('Mutation redirect or TLS downgrade rejected')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

class JSONTransport:
    def __init__(self,timeout=20,sleep=time.sleep):
        self.timeout=timeout;self.sleep=sleep;self.lock=threading.Lock();self.last=0
        context=ssl.create_default_context(cafile=os.environ.get('USOE_CA_BUNDLE') or None)
        self.opener=urllib.request.build_opener(TLSRedirect(),urllib.request.HTTPSHandler(context=context),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self,method,url,body=None,headers=None):
        attempts=3 if method=='GET' else 1
        for attempt in range(attempts):
            try:
                with self.lock:
                    self.sleep(max(0,0.25-(time.monotonic()-self.last)));self.last=time.monotonic()
                    req=urllib.request.Request(url,data=canonical(body).encode() if body is not None else None,method=method,headers={'Accept':'application/json',**({'Content-Type':'application/json'} if body is not None else {}),**(headers or {})})
                    with self.opener.open(req,timeout=self.timeout) as response:
                        data=response.read(16*1024*1024+1)
                if len(data)>16*1024*1024:raise SourceUnavailable('Response size limit exceeded')
                return json.loads(data)
            except urllib.error.HTTPError as exc:
                if exc.code not in (429,500,502,503,504) or attempt+1==attempts:
                    raise SourceUnavailable(f'Upstream HTTP {exc.code}; {"authentication/entitlement required" if exc.code in (401,403) else "request not completed"}') from None
                delay=2**attempt
                retry=exc.headers.get('Retry-After','')
                try:delay=max(delay,float(retry))
                except ValueError:
                    try:delay=max(delay,(parsedate_to_datetime(retry)-datetime.now(timezone.utc)).total_seconds())
                    except (ValueError,TypeError):pass
                if delay>30:raise SourceUnavailable('Upstream rate limit; retry later') from None
                self.sleep(delay)
            except (urllib.error.URLError,OSError):
                if attempt+1==attempts:raise SourceUnavailable('Connection failed; mutation result may be unknown' if method!='GET' else 'Source connection failed') from None
                self.sleep(2**attempt)
            except (ValueError,UnicodeError):raise SourceUnavailable('Malformed upstream JSON') from None
