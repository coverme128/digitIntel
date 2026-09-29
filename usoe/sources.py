"""Read-only official-source clients; raw responses are archived, never fabricated.
Transport may be injected for contract tests. Unknown filings enter REVIEW_REQUIRED.
"""
from __future__ import annotations
import json
import os
import re
import ssl
import time
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from .util import canonical,digest,utcnow,dt,DomainError
from .storage import Store

class SourceUnavailable(Exception): pass

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if urllib.parse.urlparse(newurl).netloc!=urllib.parse.urlparse(req.full_url).netloc:
            raise SourceUnavailable('Cross-host redirect rejected')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

class HTTP:
    def __init__(self): self.last_request=0
    def get(self,url,headers=None):
        for attempt in range(3):
            delay=max(0,0.25-(time.monotonic()-self.last_request))
            if delay:time.sleep(delay)
            self.last_request=time.monotonic()
            try:
                req=urllib.request.Request(url,headers=headers or {})
                context=ssl.create_default_context(cafile=os.environ.get('USOE_CA_BUNDLE') or None)
                opener=urllib.request.build_opener(SafeRedirect(),urllib.request.HTTPSHandler(context=context))
                with opener.open(req,timeout=15) as response:
                    content=response.read(16*1024*1024+1)
                    if len(content)>16*1024*1024:raise SourceUnavailable('Source document exceeds 16 MiB limit')
                    return content
            except urllib.error.HTTPError as exc:
                if exc.code not in (429,500,502,503,504) or attempt==2:raise SourceUnavailable(f'Upstream HTTP {exc.code}') from None
                time.sleep(min(2**attempt,4))
            except (OSError,urllib.error.URLError) as exc:
                if attempt==2:raise SourceUnavailable('Source connection failed; check network, TLS and credentials') from None
                time.sleep(2**attempt)
        raise SourceUnavailable('Source unavailable')

class Sources:
    def __init__(self,service,transport=None):
        self.service=service;self.store=service.store;self.http=transport or HTTP()

    def _state(self,source,state,error=None):
        with self.store.transaction() as db:
            db.execute('UPDATE sources SET state=?,last_success=CASE WHEN ?=\'HEALTHY\' THEN ? ELSE last_success END,last_error=? WHERE id=?',(state,state,utcnow(),error,source))
            Store.audit(db,'SOURCE_STATUS',source,{'state':state,'error':error})

    def _fetch(self,source,path,base,headers,published=None):
        try:
            content=self.http.get(base+path,headers)
            with self.store.transaction() as db:
                rid,sha=Store.raw(db,source,path,content,published or utcnow(),base+path)
            return content,rid,sha
        except SourceUnavailable as exc:
            self._state(source,'DEGRADED',str(exc));raise

    def sec_sync(self,security_id,limit=5,catchup=False):
        if self.service.demo:raise DomainError('SEC sync is available in shadow workspace only')
        ua=os.environ.get('SEC_USER_AGENT','')
        if '@' not in ua:raise DomainError('Configure SEC_USER_AGENT with contact email','SOURCE_NOT_CONFIGURED',409)
        securities=self.store.query('SELECT * FROM securities WHERE id=?',(security_id,))
        if not securities:raise DomainError('Register a verified ticker/CIK mapping first')
        sec=securities[0];cik=sec['cik'];headers={'User-Agent':ua,'Accept':'application/json,text/html,application/xml'}
        content,rid,_=self._fetch('sec',f'/submissions/CIK{cik}.json','https://data.sec.gov',headers)
        try:data=json.loads(content)
        except ValueError:self._state('sec','DEGRADED','Malformed submissions JSON');raise SourceUnavailable('Malformed submissions JSON')
        if str(data.get('cik','')).zfill(10)!=cik or sec['ticker'] not in data.get('tickers',[]):
            self._state('sec','DEGRADED','Ticker / CIK identity mismatch');raise DomainError('SEC security mapping mismatch','IDENTITY_CONFLICT',409)
        recent=data.get('filings',{}).get('recent',{})
        checked_at=utcnow()
        cursor_key='sec_cursor_'+security_id
        pending_more=False
        if catchup:
            from datetime import timedelta
            since=self.store.setting(cursor_key) or (dt(checked_at)-timedelta(days=30)).isoformat()
            since=(dt(since)-timedelta(days=1)).isoformat() # overlap for delayed SEC indexing
            # SEC older submissions files extend coverage when recent no longer spans the cursor.
            for file in data.get('filings',{}).get('files',[]):
                if file.get('filingTo','')<since[:10]:continue
                name=file.get('name','')
                if not re.fullmatch(r'CIK[0-9]+-submissions-[0-9]+\.json',name):raise SourceUnavailable('Invalid historical submissions path')
                raw,_,_=self._fetch('sec','/submissions/'+name,'https://data.sec.gov',headers)
                older=json.loads(raw)
                for k in ('accessionNumber','primaryDocument','form','acceptanceDateTime'):
                    recent.setdefault(k,[]).extend(older.get(k,[]))
            eligible=[i for i,a in enumerate(recent.get('acceptanceDateTime',[])) if dt(a)>=dt(since) and not self.store.query('SELECT id FROM filings WHERE accession=?',(recent['accessionNumber'][i],))]
            indices=eligible[:50];pending_more=len(eligible)>50
        else:indices=range(min(max(int(limit),1),20,len(recent.get('accessionNumber',[]))))
        inserted=[]
        for i in indices:
            accession=recent['accessionNumber'][i]
            if not re.fullmatch(r'\d{10}-\d{2}-\d{6}',accession):raise SourceUnavailable('Invalid accession in SEC submissions')
            if self.store.query('SELECT id FROM filings WHERE accession=?',(accession,)):continue
            name=recent['primaryDocument'][i]
            if not re.fullmatch(r'[A-Za-z0-9_./\-]+',name) or '..' in name:raise SourceUnavailable('Invalid primary document in SEC submissions')
            if recent['form'][i] in ('4','4/A') and name.startswith('xsl'):name=name.rsplit('/',1)[-1]
            accepted=recent['acceptanceDateTime'][i];dt(accepted)
            path=f'/Archives/edgar/data/{int(cik)}/{accession.replace("-","")}/{name}'
            raw,docid,sha=self._fetch('sec',path,'https://www.sec.gov',headers,accepted)
            fid='filing-'+digest(accession)[:20]
            review={'accession':accession,'security_id':security_id,'form':recent['form'][i],'accepted_at':accepted,'primary_document_id':docid,'raw_sha256':sha,'normalized_candidates':parse_form4(raw) if recent['form'][i] in ('4','4/A') else []}
            with self.store.transaction() as db:
                db.execute('INSERT OR IGNORE INTO filings VALUES (?,?,?,?,?,?)',(fid,security_id,accession,recent['form'][i],accepted,docid))
                db.execute('INSERT OR IGNORE INTO review_queue VALUES (?,?,?,?,?,?)',('review-'+fid,fid,'REVIEW_REQUIRED','Canonical facts and market window require deterministic validation',canonical(review),utcnow()))
                Store.audit(db,'SEC_FILING_ARCHIVED',fid,{'raw_document_id':docid,'sha256':sha})
            inserted.append(review)
        facts_raw,frid,_=self._fetch('sec',f'/api/xbrl/companyfacts/CIK{cik}.json','https://data.sec.gov',headers)
        try:
            facts=json.loads(facts_raw)
            if str(facts.get('cik','')).zfill(10)!=cik:raise ValueError('CIK mismatch')
        except ValueError:self._state('sec','DEGRADED','Company facts identity / schema invalid');raise SourceUnavailable('Company facts identity / schema invalid')
        if catchup and not pending_more:
            with self.store.transaction() as db:Store.set_setting(db,cursor_key,checked_at)
        self._state('sec','HEALTHY')
        return {'pending_more':pending_more,'checked_at':checked_at,'filings_archived':len(inserted),'items':inserted,'companyfacts_raw_id':frid,'status':'REVIEW_REQUIRED','message':'Raw SEC documents archived. No unverified trading opportunity was created.'}

    def sec_exhibits(self,filing_id):
        """Archive bounded EX-99 HTML/text attachments from the SEC accession index."""
        if self.service.demo:raise DomainError('Exhibits require shadow workspace')
        rows=self.store.query('SELECT f.*,r.url FROM filings f JOIN raw_documents r ON r.id=f.raw_document_id WHERE f.id=?',(filing_id,))
        if not rows:raise DomainError('Filing not found')
        filing=rows[0];ua=os.environ.get('SEC_USER_AGENT','')
        if '@' not in ua:raise DomainError('Configure SEC_USER_AGENT','SOURCE_NOT_CONFIGURED',409)
        parsed=urllib.parse.urlparse(filing['url'])
        if parsed.scheme!='https' or parsed.netloc!='www.sec.gov' or not parsed.path.startswith('/Archives/edgar/data/'):raise DomainError('Untrusted filing archive')
        directory=parsed.path.rsplit('/',1)[0]+'/'
        content,_,_=self._fetch('sec',directory+'index.json','https://www.sec.gov',{'User-Agent':ua},filing['accepted_at'])
        data=json.loads(content);items=data.get('directory',{}).get('item',[]);saved=[]
        for item in items:
            name=item.get('name','')
            if not re.fullmatch(r'[A-Za-z0-9_.-]+\.(?:htm|html|txt)',name,re.I) or not re.search(r'ex(?:hibit)?[-_]?99|(?:^|[-_])99[12]|earnings|press[-_]?release',name,re.I):continue
            if len(saved)>=5:break
            url='https://www.sec.gov'+directory+name
            previous=self.store.query('SELECT r.id FROM filing_documents d JOIN raw_documents r ON r.id=d.raw_document_id WHERE d.filing_id=? AND r.url=?',(filing_id,url))
            if previous:saved.append(previous[0]['id']);continue
            _,rid,_=self._fetch('sec',directory+name,'https://www.sec.gov',{'User-Agent':ua},filing['accepted_at'])
            with self.store.transaction() as db:
                db.execute('INSERT OR IGNORE INTO filing_documents VALUES (?,?,?)',(filing_id,rid,'EX99'))
                Store.audit(db,'SEC_EXHIBIT_ARCHIVED',filing_id,{'raw_document_id':rid})
            saved.append(rid)
        return {'filing_id':filing_id,'documents':saved,'note':'Only matching EX-99 HTML/text attachments; unmatched/PDF exhibits require manual review.'}

    def massive_bars(self,symbol,start,end):
        """Legacy import compatibility only. Application routes use integrations.MassiveClient."""
        key=os.environ.get('MASSIVE_API_KEY','')
        if not key:raise DomainError('Configure MASSIVE_API_KEY','SOURCE_NOT_CONFIGURED',409)
        if not re.fullmatch(r'[A-Z0-9.\-]{1,16}',symbol) or not all(re.fullmatch(r'\d{4}-\d{2}-\d{2}',d) for d in (start,end)):raise DomainError('Invalid symbol/date')
        content,rid,sha=self._fetch('massive',f'/v2/aggs/ticker/{symbol}/range/1/minute/{start}/{end}?adjusted=true&sort=asc&limit=50000','https://api.massive.com',{'Authorization':'Bearer '+key})
        try:
            data=json.loads(content);rows=data.get('results',[])
            if data.get('status') in ('ERROR','NOT_AUTHORIZED') or not rows:raise ValueError('Empty / denied market window')
            previous=-1
            for row in rows:
                if any(k not in row for k in ('t','o','h','l','c','v')) or row['t']<=previous:raise ValueError('Corrupt market timestamps')
                previous=row['t']
                if row['h']<row['l'] or row['c']<=0:raise ValueError('Invalid OHLC')
        except (ValueError,TypeError,KeyError):
            self._state('massive','DEGRADED','Market window failed validation');raise SourceUnavailable('Market window failed validation')
        self._state('massive','HEALTHY')
        return {'raw_document_id':rid,'sha256':sha,'adjusted':True,'data_mode':'historical','window_complete':False,'pagination_pending':bool(data.get('next_url')),'bars':rows,'note':'Historical bars only. Exchange calendar, benchmark/sector alignment and realtime freshness must be validated separately.'}

    def ibkr_read(self):
        """Legacy unverified archive helper. Application routes use Integrations.sync_broker."""
        base=os.environ.get('IBKR_BASE_URL','https://localhost:5000/v1/api').rstrip('/')
        parsed=urllib.parse.urlparse(base)
        if parsed.scheme!='https' or parsed.hostname not in ('localhost','127.0.0.1','api.ibkr.com'):raise DomainError('IBKR must use TLS on an approved local gateway or api.ibkr.com')
        account=os.environ.get('IBKR_ACCOUNT_ID','')
        if not re.fullmatch(r'[A-Za-z0-9]+',account):raise DomainError('Configure IBKR_ACCOUNT_ID','SOURCE_NOT_CONFIGURED',409)
        # GET only; no order or brokerage session mutation endpoint exists here.
        try:
            accounts=json.loads(self.http.get(base+'/portfolio/accounts'))
            if not isinstance(accounts,list) or account not in [a.get('accountId') or a.get('id') for a in accounts]:raise SourceUnavailable('IBKR account mapping mismatch')
            positions=[]
            for page in range(100):
                batch=json.loads(self.http.get(base+f'/portfolio/{account}/positions/{page}'))
                if not isinstance(batch,list):raise SourceUnavailable('Invalid IBKR positions payload')
                positions.extend(batch)
                if len(batch)<100:break
            else:raise SourceUnavailable('IBKR pagination incomplete')
            summary=json.loads(self.http.get(base+f'/portfolio/{account}/summary'))
            # Account number is omitted from storage and responses.
            redacted={'account_ref':digest(account)[:12],'positions':[{'conid':p.get('conid'),'ticker':p.get('ticker') or p.get('contractDesc'),'quantity':p.get('position'),'market_value':p.get('mktValue'),'avg_price':p.get('avgCost')} for p in positions],'summary':{k:{'amount':v.get('amount'),'currency':v.get('currency')} for k,v in summary.items() if isinstance(v,dict) and k in ('netliquidation','totalcashvalue','buyingpower')},'captured_at':utcnow(),'reconciled':False}
            with self.store.transaction() as db:
                rid,_=Store.raw(db,'ibkr','read-only-portfolio',canonical(redacted),utcnow(),'ibkr://portfolio/redacted')
                db.execute('INSERT INTO review_queue VALUES (?,NULL,?,?,?,?)',('ibkr-'+digest(redacted)[:24],'REVIEW_REQUIRED','Security mapping and account reconciliation required',canonical(redacted),utcnow()))
            self._state('ibkr','HEALTHY')
            return {'status':'REVIEW_REQUIRED','raw_document_id':rid,'portfolio':redacted}
        except (SourceUnavailable,ValueError,TypeError):
            self._state('ibkr','DEGRADED','Read-only broker sync failed');raise SourceUnavailable('IBKR read failed; verify gateway session, TLS and account mapping') from None


def parse_form4(raw):
    """Returns candidates only. Transaction code P alone does not establish a trade thesis."""
    try:root=ET.fromstring(raw)
    except ET.ParseError:return []
    result=[]
    for node in root.findall('.//nonDerivativeTransaction'):
        def text(path):return node.findtext(path)
        if text('transactionCoding/transactionCode')!='P' or text('transactionAmounts/transactionAcquiredDisposedCode/value')!='A':continue
        try:
            shares=float(text('transactionAmounts/transactionShares/value'));price=float(text('transactionAmounts/transactionPricePerShare/value'))
            result.append({'code':'P','acquired_disposed':'A','derivative':False,'shares':shares,'price':price,'value':shares*price,'transaction_date':text('transactionDate/value'),'status':'CANDIDATE_REQUIRES_OWNER_AND_EVIDENCE_VALIDATION'})
        except (ValueError,TypeError):continue
    return result


def xbrl_candidates(data,as_of,accepted_by_accession):
    """Only known accepted-at filings, explicit units and periods; no future restatements."""
    registry={'Revenues':'revenue','RevenueFromContractWithCustomerExcludingAssessedTax':'revenue','GrossProfit':'gross_profit','OperatingIncomeLoss':'operating_income','NetIncomeLoss':'net_income','EarningsPerShareDiluted':'diluted_eps','NetCashProvidedByUsedInOperatingActivities':'operating_cash_flow','PaymentsToAcquirePropertyPlantAndEquipment':'capex','CashAndCashEquivalentsAtCarryingValue':'cash'}
    out=[]
    for tag,metric in registry.items():
        for unit,rows in data.get('facts',{}).get('us-gaap',{}).get(tag,{}).get('units',{}).items():
            for row in rows:
                accepted=accepted_by_accession.get(row.get('accn'))
                if not accepted or dt(accepted)>dt(as_of):continue
                out.append({'metric_id':metric,'value':row['val'],'unit':unit,'period_start':row.get('start',row['end']),'period_end':row['end'],'accession':row['accn'],'accepted_at':accepted,'locator':f'/facts/us-gaap/{tag}/units/{unit}','status':'CANDIDATE_REQUIRES_RECONCILIATION'})
    return out
