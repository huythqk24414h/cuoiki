"""Manual, resumable SSI-only acquisition. Never runs on page load."""
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.ssi_client import SSIReadonly, safe_error

START='2026-01-01T00:00:00+07:00'
END='2026-11-04T23:59:59+07:00'
SYMBOLS=['SSI','FPT','HPG','VNM','VCB','MBB']
FIELDS=['symbol','trading_date','open','high','low','close','volume','value','source','timeframe','timezone','raw_unit','normalized_unit','adjustment_status']


def main():
    out=ROOT/'data/ssi_snapshots';rawdir=out/'raw';rawdir.mkdir(parents=True,exist_ok=True)
    records=[];errors=[];pages={};cross=[]
    client=None
    try:
        client=SSIReadonly()
        client.authenticate()
        securities=client.get('/api/v3/data/securitiesByBoard',{'board':'HOSE'})
        if not isinstance(securities,list):raise ValueError('Invalid securities schema')
        names={row.get('symbol') for row in securities}
        for symbol in SYMBOLS:
            if symbol not in names:
                errors.append({'symbol':symbol,'reason':'not returned by HOSE list'});continue
            collected={}
            try:
                for page in range(1,11):
                    path=rawdir/f'{symbol}_{page}.json'
                    checksum=path.with_suffix('.sha256')
                    if path.exists() and checksum.exists() and sha256(path.read_bytes()).hexdigest()==checksum.read_text():
                        envelope=json.loads(path.read_text(encoding='utf-8'))
                        if envelope.get('range')!=[START,END]:raise ValueError('Cached query differs')
                        raw=envelope['response']
                    else:
                        raw=client.ohlc(symbol,START,END,page=page,size=100)
                        # Only public market rows, never auth responses or headers.
                        envelope={'range':[START,END],'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'response':raw}
                        path.write_text(json.dumps(envelope,ensure_ascii=False),encoding='utf-8')
                        checksum.write_text(sha256(path.read_bytes()).hexdigest())
                    rows=raw.get('data') if isinstance(raw,dict) else None
                    if not isinstance(rows,list):raise ValueError('Invalid OHLC envelope')
                    for row in rows:
                        if row.get('symbol')!=symbol:raise ValueError('Mixed symbol response')
                        day=datetime.strptime(row['tradingDate'][:10],'%Y/%m/%d').date().isoformat()
                        if not '2026-01-01'<=day<='2026-11-04':raise ValueError('Out of range SSI row')
                        item={'symbol':symbol,'trading_date':day,**{k:str(row[k]) for k in ['open','high','low','close','volume']},
                              'value':'' if row.get('value') is None else str(row['value']),
                              'source':'SSI FastConnect V3','timeframe':'1d','timezone':'Asia/Ho_Chi_Minh',
                              'raw_unit':'VND/share','normalized_unit':'VND/share','adjustment_status':'unknown'}
                        if day in collected and collected[day]!=item:raise ValueError('Conflicting duplicate')
                        collected[day]=item
                    pages[symbol]=page
                    if len(rows)<100:break
                else:raise ValueError('Paging cap reached')
                records.extend(collected.values())
                print(f'{symbol}: {len(collected)} rows',flush=True)
            except Exception as error:
                errors.append({'symbol':symbol,**safe_error(error)})
        # Existing, independently validated VCI reference is ONLY a crosscheck, never SSI filler.
        from src.eod_snapshot import validate_snapshot
        reference=validate_snapshot(ROOT/'data/demo')
        if reference['passed']:
            lookup={(r['symbol'],r['date']):r for r in reference['rows']}
            for row in records:
                if row['trading_date']!='2026-11-04':continue
                other=lookup.get((row['symbol'],row['trading_date']))
                if other:
                    from decimal import Decimal
                    same=all(Decimal(row[k])==Decimal(other[k+'_vnd']) for k in ['open','high','low','close']) and Decimal(row['volume'])==Decimal(other['volume_shares'])
                    cross.append({'symbol':row['symbol'],'date':row['trading_date'],'OHLCV_matches_VCI_VND':same})
        if not cross or not all(r['OHLCV_matches_VCI_VND'] for r in cross):
            raise ValueError('Unit crosscheck incomplete or mismatch; no normalized snapshot published')
        records.sort(key=lambda r:(r['symbol'],r['trading_date']))
        with (out/'ohlcv_daily.csv').open('w',encoding='utf-8',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=FIELDS);writer.writeheader();writer.writerows(records)
        coverage={}
        for symbol in SYMBOLS:
            ds=[r['trading_date'] for r in records if r['symbol']==symbol]
            if ds:coverage[symbol]={'rows':len(ds),'first_available_session':min(ds),'last_available_session':max(ds)}
        manifest={'dataset_type':'ssi_historical_eod','asof_date':'2026-11-04','asof_timezone':'Asia/Ho_Chi_Minh',
                  'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'query_range':[START,END],
                  'sdk_version':'3.3.2','source':'SSI FastConnect V3','endpoint':'https://api.ssi.com.vn/api/v3/data/ohlc',
                  'documentation_url':'https://developers.ssi.com.vn/docs/api-reference/data-ohlc',
                  'symbols_requested':SYMBOLS,'symbols_loaded':list(coverage),'coverage_by_symbol':coverage,'row_count':len(records),
                  'units':{'price':'VND/share','volume':'share','turnover':'VND'},'adjustment_policy':'unknown',
                  'unit_evidence':{'method':'No scaling. Actual 04Nov OHLCV compared against independently verified VCI VND snapshot.',
                                   'checks':cross,'limitation':'SSI OHLC reference does not explicitly document adjustment; unknown retained. Value unit VND checked with value/volume against VND OHLC.'},
                  'value_semantics':'Source-reported value; actual cash turnover unverified. Publish as source_value_vnd proxy, not actual turnover.',
                  'pages_by_symbol':pages,'errors':errors,'file_sha256':{'ohlcv_daily.csv':sha256((out/'ohlcv_daily.csv').read_bytes()).hexdigest()},
                  'raw_sha256':{p.name:sha256(p.read_bytes()).hexdigest() for p in rawdir.glob('*.json') if p.stem.split('_')[0] in coverage},
                  'refresh_policy':'manual_one_shot','usage_note':'Local personal academic use; SSI entitlements apply. Do not publish credentials or raw data without permission.'}
        (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        from src.ssi_snapshot import validate_ssi_snapshot
        result=validate_ssi_snapshot(out)
        (out/'quality_report.json').write_text(json.dumps({k:v for k,v in result.items() if k not in ('rows','manifest')},indent=2),encoding='utf-8')
        print(json.dumps({'passed':result['passed'],'rows':len(records),'coverage':coverage,'errors':errors}))
    except Exception as error:
        report={'status':'BLOCKED','stage':'acquisition',**safe_error(error)}
        (out/'acquisition_error.json').write_text(json.dumps(report),encoding='utf-8')
        print(json.dumps(report));return 1
    finally:
        if client:client.close()


if __name__=='__main__':
    # Superseded six-symbol collector retained for provenance only. Default acquisition is dynamic.
    from expand_ssi_market import main as expand
    sys.exit(expand() or 0)
