"""SSI-only history revision; old04Nov snapshot stays immutable. Sequential/resumable."""
import sys,json,time,re
from pathlib import Path
from datetime import datetime,timezone,timedelta
from hashlib import sha256
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.ssi_client import SSIReadonly,safe_error
from src.universe import canonical_row
from scripts.expand_ssi_market import save,read,request
START='2022-01-01';END='2026-11-05'
OUT=ROOT/'data'/('ssi_history_'+START.replace('-','')+'_'+END.replace('-',''))

def fetch(client,name,endpoint,params):
    path=OUT/'raw'/f'{name}.json'
    if path.exists():
        envelope=read(path)
        if envelope['params']!=params:raise ValueError('Cached query differs')
        return envelope['response']
    result=request(client,endpoint,params)
    save(path,{'endpoint':endpoint,'params':params,'retrieved_at':datetime.now(timezone.utc).isoformat(),'response':result})
    return result

def symbol_history(client,symbol):
    target=OUT/'symbols'/f'{symbol}.json'
    if target.exists():return read(target),True
    rows={};bad={};quarantine=[];page=1;seen=set();duplicates=0
    while True:
        params={'symbol':symbol,'from':START.replace('-','/')+' 00:00:00','to':END.replace('-','/')+' 23:59:59','timeFrame':'1d','pageIndex':page,'pageSize':5000}
        response=fetch(client,f'{symbol}_{page}','/api/v3/data/ohlc',params)
        if not isinstance(response,dict) or not isinstance(response.get('data'),list):
            if isinstance(response,dict) and response.get('code')==204:raw=[]
            else:raise ValueError('OHLC schema unsupported')
        else:raw=response['data']
        fingerprint=sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()
        if raw and fingerprint in seen:raise ValueError('Repeated page')
        seen.add(fingerprint)
        for position,r in enumerate(raw):
            try:
                row=canonical_row(r,symbol,START,END);day=row['date']
                if day in bad:continue
                if day in rows:
                    if row!=rows[day]:
                        rows.pop(day);bad[day]=True;quarantine.append({'page':page,'position':position,'date':day,'reason':'Conflicting duplicate; entire date excluded'})
                    else:duplicates+=1
                else:rows[day]=row
            except (ValueError,KeyError,TypeError,ArithmeticError) as e:
                quarantine.append({'page':page,'position':position,'reason':str(e) if isinstance(e,ValueError) else type(e).__name__})
        count=response.get('pagesCount',response.get('pageCount')) if isinstance(response,dict) else None
        if not raw or (count is not None and page>=int(count)) or (count is None and len(raw)<5000):break
        page+=1
    result={'symbol':symbol,'rows':sorted(rows.values(),key=lambda r:r['date']),'source':'SSI FastConnect V3','query_range':[START,END],
            'pages':page,'quarantine':quarantine,'identical_duplicates':duplicates,'adjustment':'unknown','units':'source native; no scaling'}
    save(target,result)
    return result,False

def main():
    OUT.mkdir(parents=True,exist_ok=True);client=None;states={};catalog=[];index_list=[]
    try:
        client=SSIReadonly();client.authenticate();print('Authenticated (no token recorded)',flush=True)
        for board in ('HOSE','HNX','UPCOM'):
            result=fetch(client,board,'/api/v3/data/securitiesByBoard',{'board':board})
            if not isinstance(result,list):raise ValueError('Invalid catalog')
            catalog.extend({**r,'board':board} for r in result if re.fullmatch('[A-Z0-9 _-]{1,40}',str(r.get('symbol',''))))
        index_list=fetch(client,'index_list','/api/v3/data/indexList',{})
        save(OUT/'catalog.json',{'securities':catalog,'indexes':index_list,'source':'SSI FastConnect V3','retrieved_at':datetime.now(timezone.utc).isoformat(),'historical_eligibility_verified':False})
        # One legitimate OHLC request tests provider index support; never manufacture index values.
        for code in ('VNINDEX','VN30','HNXINDEX','UPCOMINDEX'):
            try:
                result,_=symbol_history(client,code)
                if code=='UPCOMINDEX' and not result['rows']:
                    result,_=symbol_history(client,'HNXUPCOMINDEX')
                    result={**result,'display_index':'UPCOMINDEX','provider_symbol':'HNXUPCOMINDEX'}
                save(OUT/'index_ohlc'/f'{code}.json',result)
                print('INDEX',code,len(result['rows']),flush=True)
            except Exception as e:states['index:'+code]={'state':'ERROR',**safe_error(e)}
        # Prioritize selected series for usable UI while continuing the whole current directory.
        prior=json.loads((ROOT/'data/ssi_universe_20261104/memberships.json').read_text())['current_members'].get('VN30',[])
        unique={r['symbol'] for r in catalog};ordered=sorted(unique,key=lambda s:(s not in set(prior),s))
        for number,symbol in enumerate(ordered,1):
            try:
                result,resumed=symbol_history(client,symbol)
                rows=result['rows'];states[symbol]={'state':'PARTIAL' if result['quarantine'] else 'SUCCESS' if rows else 'NO_HISTORY','rows':len(rows),'quarantined':len(result['quarantine']),'resumed':resumed}
            except Exception as e:states[symbol]={'state':'ERROR',**safe_error(e),'reason':str(e) if isinstance(e,ValueError) else None}
            save(OUT/'checkpoint.json',states)
            if number<=5 or number%100==0:print('PROGRESS',number,'/',len(ordered),'states',dict(Counter(r['state'] for r in states.values())),flush=True)
        save(OUT/'request_evidence.json',{'http':dict(Counter(str(r['http_status'])+' '+r['endpoint'] for r in client.evidence))})
        print('ACQUISITION COMPLETE',len(ordered),flush=True)
    except Exception as e:
        save(OUT/'error.json',safe_error(e));print(json.dumps(safe_error(e)),flush=True);return 1
    finally:
        if client:client.close()
    return 0

if __name__=='__main__':sys.exit(main())
