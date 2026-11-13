"""Independently compare every stored historical row against raw; activate only after PASS."""
import sys,json
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
from hashlib import sha256
from decimal import Decimal
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.fetch_history_2022 import OUT,START,END
from scripts.expand_ssi_market import read,save
from src.universe import canonical_row

def main():
    catalog=read(OUT/'catalog.json');states=read(OUT/'checkpoint.json')
    symbols=sorted({r['symbol'] for r in catalog['securities']})
    if any(s not in states for s in symbols):raise ValueError('Acquisition incomplete; no activation')
    extra={read(p)['symbol'] for p in (OUT/'index_ohlc').glob('*.json')}-set(symbols)
    validation_symbols=sorted(set(symbols)|extra)
    allrows={};files={};quarantined=0;errors={}
    for i,symbol in enumerate(validation_symbols,1):
        path=OUT/'symbols'/f'{symbol}.json'
        if not path.exists():
            if states[symbol]['state']!='ERROR':raise ValueError('Missing unreported symbol')
            errors[symbol]=states[symbol];continue
        result=read(path);expected={};conflicts=set();bad_count=0
        for page in range(1,result['pages']+1):
            rawpath=OUT/'raw'/f'{symbol}_{page}.json';envelope=read(rawpath);params=envelope['params']
            if params['symbol']!=symbol or params['timeFrame']!='1d' or params['pageIndex']!=page or params['from']!=START.replace('-','/')+' 00:00:00' or params['to']!=END.replace('-','/')+' 23:59:59':raise ValueError('Query mismatch')
            files[str(rawpath.relative_to(OUT))]=sha256(rawpath.read_bytes()).hexdigest()
            for raw in envelope['response'].get('data',[]):
                try:r=canonical_row(raw,symbol,START,END)
                except (ValueError,KeyError,TypeError,ArithmeticError):bad_count+=1;continue
                day=r['date']
                if day in conflicts:continue
                if day in expected and expected[day]!=r:
                    expected.pop(day);conflicts.add(day);bad_count+=1
                else:expected[day]=r
        if result['rows']!=sorted(expected.values(),key=lambda r:r['date']):raise ValueError('Raw/normalized mismatch: '+symbol)
        if bad_count!=len(result['quarantine']):raise ValueError('Unreported quarantine')
        files[str(path.relative_to(OUT))]=sha256(path.read_bytes()).hexdigest();quarantined+=bad_count
        allrows[symbol]=result['rows']
        if i%250==0:print('VALIDATED',i,'/',len(symbols),flush=True)
    if not any(allrows.values()):raise ValueError('Empty dataset')
    coverage={s:{'rows':len(rs),'first_available_session':rs[0]['date'],'last_available_session':rs[-1]['date']} for s,rs in allrows.items() if rs and s in symbols}
    memberships=read(ROOT/'data/ssi_universe_20261104/memberships.json')['current_members']
    scopes={'ALL':set(symbols),**{b:{r['symbol'] for r in catalog['securities'] if r['board']==b} for b in ('HOSE','HNX','UPCOM')},**{'INDEX:'+code:set(members)&set(symbols) for code,members in memberships.items()}}
    summaries={}
    for scope,ids in scopes.items():
        dates=Counter(r['date'] for s in ids for r in allrows.get(s,[]));loaded=[s for s in ids if allrows.get(s)]
        summaries[scope]={'catalog_count':len(ids),'loaded_symbols':len(loaded),'missing_or_empty':len(ids)-len(loaded),'invalid_symbols':sum(s in errors for s in ids),'processing_states':dict(Counter(states[s]['state'] for s in ids)),
                          'first':min(dates,default=None),'last':max(dates,default=None),'sessions':len(dates),'by_session':dict(sorted(dates.items()))}
    overlaps={}
    for code in ('VNINDEX','VN30','HNXINDEX','UPCOMINDEX'):
        path=OUT/'index_ohlc'/f'{code}.json'
        if not path.exists():continue
        data=read(path);actual_symbol=data['symbol'];original=read(OUT/'symbols'/f'{actual_symbol}.json')
        if data['rows']!=original['rows']:raise ValueError('Index projection not raw-backed')
        files[str(path.relative_to(OUT))]=sha256(path.read_bytes()).hexdigest()
        previous=read(ROOT/'data/ssi_universe_20261104/indices'/f'{code}.json')['rows'];lookup={r['date']:r for r in data['rows']}
        checks=[Decimal(r['indexValue'])==Decimal(lookup[r['tradingDate'][:10].replace('/','-')]['close_vnd']) for r in previous if r['tradingDate'][:10].replace('/','-') in lookup]
        overlaps[code]={'rows':len(data['rows']),'same_date_summary_checks':len(checks),'matches':sum(checks),'provider_symbol':actual_symbol}
    q={'validation_status':'PASS','query_start':START,'query_end':END,'verified_at':datetime.now(timezone.utc).isoformat(),
       'rows':sum(len(allrows.get(s,[])) for s in symbols),'symbols_requested':symbols,'symbols_loaded':list(coverage),'coverage_by_symbol':coverage,
       'first':min(c['first_available_session'] for c in coverage.values()),'last':max(c['last_available_session'] for c in coverage.values()),
       'quarantined_rows_or_conflicts':quarantined,'errors':errors,'states':dict(Counter(states[s]['state'] for s in symbols)),
       'by_year':dict(Counter(r['date'][:4] for s,rs in allrows.items() if s in symbols for r in rs)),'coverage_by_scope':summaries,'file_sha256':files,'indices':overlaps,
       'units':'source native; no automatic scaling','adjustment':'unknown','historical_eligibility':'unverified; do not publish market aggregates'}
    save(OUT/'quality.json',q)
    old=ROOT/'data/ssi_snapshots/ohlcv_daily.csv'
    if sha256(old.read_bytes()).hexdigest()!='799e65513c86ad93ddce9349c921b0c93777bfc5880eb580f8529f932ad91d74':raise ValueError('Original snapshot changed')
    save(ROOT/'config/history_active.json',{'folder':str(OUT.relative_to(ROOT)),'quality_sha256':sha256((OUT/'quality.json').read_bytes()).hexdigest()})
    public={k:v for k,v in q.items() if k not in ('coverage_by_symbol','coverage_by_scope','file_sha256','symbols_requested','symbols_loaded')}
    (ROOT/'docs/HISTORY_2022_REPORT.json').write_text(json.dumps(public,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(public,ensure_ascii=False))

if __name__=='__main__':main()
