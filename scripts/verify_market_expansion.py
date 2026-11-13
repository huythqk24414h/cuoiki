"""Actual raw-file and local HTTP integration verification. NOT browser E2E."""
import sys,json,random
from pathlib import Path
from collections import Counter
from hashlib import sha256
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.universe import ROOT as DATA,read_verified,catalog,canonical_row,coverage
from src.ssi_client import credentials

def main():
    print('Starting raw verification',flush=True);checks=[];cat=catalog();files=sorted((DATA/'symbols').glob('*.json'));symbols={};total=0
    for path in files:
        stored=read_verified(path);rows=stored['rows'];raw={}
        for page in range(1,stored['pages']+1):
            envelope=read_verified(DATA/'raw'/f'{path.stem}_{page}.json')
            for original in envelope['response'].get('data',[]):
                converted=canonical_row(original,path.stem);raw[converted['date']]=converted
        if rows!=sorted(raw.values(),key=lambda r:r['date']):raise ValueError('Raw→normalized mismatch '+path.stem)
        total+=len(rows);symbols[path.stem]=rows
    print('Raw verified',len(files),total,flush=True);checks.append({'name':'every normalized row independently equals checksum-verified raw response','status':'PASS','files':len(files),'rows':total})
    old=ROOT/'data/ssi_snapshots/ohlcv_daily.csv'
    if sha256(old.read_bytes()).hexdigest()!='799e65513c86ad93ddce9349c921b0c93777bfc5880eb580f8529f932ad91d74':raise ValueError('Original snapshot changed')
    checks.append({'name':'original snapshot unchanged','status':'PASS'})
    secrets=[v for k,v in credentials().items() if k in ('SSI_API_KEY','SSI_API_SECRET') and v]
    def get(route):
        with urlopen('http://127.0.0.1:8793'+route,timeout=120) as response:
            body=response.read().decode()
            if any(v in body for v in secrets):raise ValueError('Secret leak (value suppressed)')
            return json.loads(body)
    print('Starting HTTP checks',flush=True);directory=get('/api/market/catalog')
    if len(directory['securities'])!=len(cat['securities']):raise ValueError('Catalog truncated')
    checks.append({'name':'unlimited catalog API','status':'PASS','valid_rows':len(cat['securities'])})
    rng=random.Random(20261104);samples=[]
    for board in ('HOSE','HNX','UPCOM'):
        print('HTTP board',board,flush=True);eligible=[r['symbol'] for r in cat['securities'] if r['board']==board and symbols.get(r['symbol'])]
        if not eligible:checks.append({'name':'actual history '+board,'status':'BLOCKED'});continue
        symbol=rng.choice(eligible)
        payload=get('/api/market/series?symbol='+symbol+'&range=MAX&resolution=1D')
        if payload['rows'][-1]['close_vnd']!=symbols[symbol][-1]['close_vnd']:raise ValueError('API mismatch')
        samples.append({'board':board,'symbol':symbol,'date':payload['rows'][-1]['date'],'raw_match':True})
        for window in ('1D','5D','1W','1M','3M','6M','YTD','1Y','3Y','5Y','MAX'):
            result=get('/api/market/series?symbol='+symbol+'&range='+window)
            if not result['available']:raise ValueError('Range unavailable')
        for resolution in ('1W','1M'):
            result=get('/api/market/series?symbol='+symbol+'&range=MAX&resolution='+resolution)
            if not result['rows']:raise ValueError('Aggregation empty')
        custom=get('/api/market/series?symbol='+symbol+'&range=CUSTOM&from=2026-10-01&to=2026-10-30')
        if not all('2026-10-01'<=r['date']<='2026-10-30' for r in custom['rows']):raise ValueError('Custom dates ignored')
    checks.append({'name':'real HTTP series/ranges/custom/resolutions on three boards','status':'PASS','samples':samples})
    indices=[]
    for code in ('VNINDEX','VN30','HNXINDEX','UPCOMINDEX'):
        stored=read_verified(DATA/'indices'/f'{code}.json');served=get('/api/market/index?symbol='+code+'&range=MAX')
        if len(served['rows'])!=len(stored['rows']) or not served['rows']:raise ValueError('Index mismatch')
        for r in stored['rows']:
            day=r['tradingDate'][:10].replace('/','-');raw=read_verified(DATA/'raw'/f'index_{code}_{day}.json')['response']
            if r not in raw:raise ValueError('Index not raw-backed')
        indices.append({'index':code,'sessions':len(stored['rows'])})
    checks.append({'name':'official index API per-date raw verification','status':'PASS','indices':indices})
    cov=get('/api/market/coverage');rank=get('/api/market/rankings?metric=volume')
    if cov['gate']['allowed'] or rank['rows']:raise ValueError('Unknown historical denominator leaked aggregates')
    checks.append({'name':'unknown historical denominator blocks aggregates','status':'PASS'})
    from src.universe import coverage_gate
    if coverage_gate(79,100,True)['allowed'] or coverage_gate(90,100,True)['status']!='PARTIAL':raise ValueError('Missing-session gate failed')
    checks.append({'name':'known-answer missing-session 79/100 blocked, 90/100 partial','status':'PASS','scope':'isolated test fixture only'})
    report={'status':'PARTIAL_NOT_UI_ACCEPTED','checks':checks,'coverage':cov,'raw_catalog_rows':sum(len(read_verified(DATA/'raw'/f'{b}.json')['response']) for b in ('HOSE','HNX','UPCOM')),'unique_valid_symbols':len({r['symbol'] for r in cat['securities']}),'classification_raw':dict(Counter(r.get('stockType') or 'unknown' for r in cat['securities'])),'browser':'BLOCKED_PERMISSION_POLICY','screenshots':0}
    (ROOT/'docs/MARKET_EXPANSION_EVIDENCE.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'groups':len(checks),'normalized_rows':total,'files':len(files),'coverage_n':cov['gate']['n'],'catalog_denominator_only':cov['gate']['denominator']}))

if __name__=='__main__':main()
