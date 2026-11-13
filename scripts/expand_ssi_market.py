"""SSI-only, sequential, resumable immutable EOD extension. No database or trading."""
import sys, json, time, re
from pathlib import Path
from datetime import datetime, timedelta, date, timezone
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.ssi_client import SSIReadonly, safe_error
OUT=ROOT/'data/ssi_universe_20261104'
START='2026-01-01T00:00:00+07:00';END='2026-11-04T23:59:59+07:00'

def save(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(data,ensure_ascii=False,sort_keys=True).encode()
    tmp=path.with_suffix('.tmp');tmp.write_bytes(raw);tmp.replace(path)
    path.with_suffix('.sha256').write_text(sha256(raw).hexdigest())

def read(path):
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=path.with_suffix('.sha256').read_text():raise ValueError('Checksum mismatch')
    return json.loads(raw)

def request(client, endpoint, params):
    for attempt in range(5):
        try:return client.get(endpoint,params)
        except Exception as error:
            status=getattr(error,'status_code',None)
            if status not in (429,500,502,503,504) or attempt==4:raise
            time.sleep(2**attempt)

def cached(client, name, endpoint, params):
    path=OUT/'raw'/f'{name}.json'
    if path.exists():return read(path)['response']
    data=request(client,endpoint,params)
    save(path,{'endpoint':endpoint,'params':params,'retrieved_at':datetime.now(timezone.utc).isoformat(),'response':data})
    return data

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    client=SSIReadonly();status={};catalog=[];indexes=[]
    try:
        client.authenticate()
        for board in ('HOSE','HNX','UPCOM'):
            try:
                rows=cached(client,board,'/api/v3/data/securitiesByBoard',{'board':board})
                if not isinstance(rows,list):raise ValueError('Catalog not array')
                for row in rows:
                    if re.fullmatch('[A-Z0-9 _-]{1,40}',str(row.get('symbol',''))):catalog.append({**row,'board':board})
                print(board,len(rows),flush=True)
            except Exception as e:status[board]={'state':'ERROR',**safe_error(e)}
        try:
            indexes=cached(client,'indexes','/api/v3/data/indexList',{})
            if not isinstance(indexes,list):raise ValueError('Index list not array')
        except Exception as e:indexes=[];status['indexes']={'state':'ERROR',**safe_error(e)}
        save(OUT/'catalog.json',{'source':'SSI FastConnect V3','retrieved_at':datetime.now(timezone.utc).isoformat(),'securities':catalog,'indexes':indexes,'errors':status.copy(),'classification':'Raw SSI stockType; no inferred labels','historical_eligibility_verified':False})
        # Official daily summaries: never manufacture index OHLC from securities.
        for item in indexes:
            code=item.get('indexCode') or item.get('index') or item.get('symbol')
            if code not in ('VNINDEX','VN30','HNXINDEX','UPCOMINDEX'):continue
            day=date(2026,1,1);collected=[]
            while day<=date(2026,11,4):
                if day.weekday()<5:
                    try:
                        result=cached(client,f'index_{code}_{day}', '/api/v3/data/indexSummary',{'index':code,'tradingDate':day.strftime('%Y/%m/%d')})
                        if isinstance(result,list):
                            for r in result:
                                actual=str(r.get('tradingDate',''))[:10].replace('/','-')
                                if actual==day.isoformat():collected.append(r)
                    except Exception as e:status['index:'+code]={'state':'ERROR',**safe_error(e)};break
                day+=timedelta(days=1)
            save(OUT/'indices'/f'{code}.json',{'code':code,'rows':collected,'source':'SSI indexSummary','units':'index points; other units unverified'})
            print('index',code,len(collected),flush=True)
        unique={r['symbol']:r for r in catalog}
        for number,symbol in enumerate(sorted(unique),1):
            target=OUT/'symbols'/f'{symbol}.json'
            try:
                if target.exists():
                    previous=read(target);status[symbol]={'state':'SUCCESS' if previous['rows'] else 'NO_HISTORY','resumed':True,'rows':len(previous['rows'])};continue
                records={};page=1;previous=None
                while True:
                    first,last=START[:10].replace('-','/')+' 00:00:00',END[:10].replace('-','/')+' 23:59:59'
                    raw=cached(client,f'{symbol}_{page}','/api/v3/data/ohlc',{'symbol':symbol,'from':first,'to':last,'timeFrame':'1d','pageIndex':page,'pageSize':1000})
                    rows=raw.get('data',[]) if isinstance(raw,dict) else None
                    if rows is None:raise ValueError('OHLC schema')
                    fingerprint=sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
                    if rows and previous==fingerprint:raise ValueError('Repeated page')
                    previous=fingerprint
                    from src.universe import canonical_row
                    for r in rows:
                        item=canonical_row(r,symbol)
                        if item['date'] in records and records[item['date']]!=item:raise ValueError('Conflict')
                        records[item['date']]=item
                    pages=raw.get('pagesCount',raw.get('pageCount')) if isinstance(raw,dict) else None
                    if not rows or (pages is not None and page>=int(pages)) or (pages is None and len(rows)<1000):break
                    page+=1
                ordered=sorted(records.values(),key=lambda r:r['date'])
                save(target,{'symbol':symbol,'rows':ordered,'source':'SSI FastConnect V3','range':[START,END],'pages':page,'adjustment':'unknown','units':'source native; price VND convention unverified for expanded securities'})
                status[symbol]={'state':'SUCCESS' if ordered else 'NO_HISTORY','rows':len(ordered)}
            except Exception as e:status[symbol]={'state':'ERROR',**safe_error(e),'validation_reason':str(e) if isinstance(e,ValueError) else None}
            save(OUT/'checkpoint.json',status)
            if number%50==0:print('progress',number,'/',len(unique),flush=True)
        save(OUT/'checkpoint.json',status)
        print('DONE',len(unique),flush=True)
    except Exception as e:
        save(OUT/'acquisition_error.json',safe_error(e));print(json.dumps(safe_error(e)),flush=True)
    finally:
        from collections import Counter
        save(OUT/'request_evidence.json',{'observed_http':dict(Counter(str(e.get('http_status'))+' '+e.get('endpoint','') for e in client.evidence)),'scope':'This invocation only; no authentication response or secrets recorded'})
        client.close()

if __name__=='__main__':main()
