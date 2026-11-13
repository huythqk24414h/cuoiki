"""Actual local HTTP integration checks; explicitly not browser/E2E UI verification."""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.ssi_snapshot import validate_ssi_snapshot
from src.ssi_client import credentials


def main():
    base='http://127.0.0.1:8792';checks=[]
    snapshot=validate_ssi_snapshot(ROOT/'data/ssi_snapshots')
    assert snapshot['passed'],snapshot['issues']
    lookup={(r['symbol'],r['date']):r for r in snapshot['rows']}
    secrets=[v for k,v in credentials().items() if k in ['SSI_API_KEY','SSI_API_SECRET'] and v]
    def read(path):
        with urlopen(base+path,timeout=8) as response:
            body=response.read().decode('utf-8')
            assert response.status==200
            assert "connect-src 'self'" in response.headers['Content-Security-Policy']
            assert response.headers.get('Access-Control-Allow-Origin') is None
        assert all(secret not in body for secret in secrets),'Secret leaked (value suppressed)'
        return body
    def get(path):return json.loads(read(path))
    for asset in ['/','/app.js','/eod-ui.js','/market-ui.js','/depth-chart.js','/style.css','/themes.js','/theme-tokens.css','/calculator-core.js']:
        assert read(asset)
    checks.append({'check':'assets_security_headers_secret_scan','status':'PASS','assets':9})
    meta=get('/api/market/meta')
    assert meta['available'] and meta['source']=='SSI FastConnect V3'
    checks.append({'check':'SSI_metadata','status':'PASS','rows':meta['manifest']['row_count']})
    matches=sum(Decimal(r['source_value_vnd'])==Decimal(r['close_vnd'])*Decimal(r['volume_shares']) for r in snapshot['rows'] if r['source_value_vnd'])
    assert all(r['turnover_vnd']=='' for r in snapshot['rows'])
    assert meta['manifest']['value_diagnostics']['equal_close_times_volume']==matches
    checks.append({'check':'source_value_proxy_not_mislabeled_actual_turnover','status':'PASS',
                   'observed_close_times_volume_matches':matches,'actual_turnover_available':False})
    for symbol in meta['loaded_symbols']:
        counts={}
        for range_id in ['1M','3M','6M','YTD','ALL']:
            payload=get(f'/api/market/ohlcv?symbol={symbol}&range={range_id}')
            assert payload['available'] and payload['rows']
            for row in payload['rows']:
                original=lookup[(symbol,row['date'])]
                for field in ['open_vnd','high_vnd','low_vnd','close_vnd','volume_shares','turnover_vnd','source_value_vnd']:
                    assert row[field]==original[field],f'Invariant failed: {symbol}/{field}'
                assert row['date']<='2026-11-04'
            assert payload['summary']==payload['rows'][-1]
            counts[range_id]=len(payload['rows'])
        assert counts['1M']<=counts['3M']<=counts['6M']<=counts['YTD']==counts['ALL']
        checks.append({'check':'raw_CSV_HTTP_invariant_and_five_ranges','status':'PASS','symbol':symbol,'counts':counts})
    for metric in ['volume','return_pct','relative_volume20']:
        ranking=get('/api/market/rankings?metric='+metric)
        assert len(ranking['rows'])==6 and ranking['scope']=='loaded_symbols'
    checks.append({'check':'three_rankings','status':'PASS'})
    alerts=get('/api/market/alerts')
    assert alerts['status']=='evaluated'
    assert all(Decimal(r['value'])>=Decimal(r['threshold']) and r['timestamp']<='2026-11-04' for r in alerts['rows'])
    checks.append({'check':'historical_alerts','status':'PASS','evaluated':alerts['evaluated_observations'],'events':len(alerts['rows'])})
    status=get('/api/market/status');book=get('/api/market/book?symbol=SSI')
    if not book['available']:assert book['bids']==[] and book['asks']==[] and book.get('reason')
    checks.append({'check':'DATA_runtime_state','status':'PASS','observed_status':status['status'],
                   'stream_active':status['stream_active'],'quote_events':status['quote_events'],
                   'unit_verified':status['unit_verified'],'book_available':book['available'],'reason':book.get('reason')})
    checks[-1]['subscription_status']=status.get('subscription_status',{})
    checks[-1]['last_event_at']=status.get('last_event_at')
    checks[-1]['snapshot_asof']=book['snapshot_asof']
    checks[-1]['parsed_unverified_bid_levels']=len(book.get('unverified_levels',{}).get('bids',[]))
    manual={'contract_version':'1.0','source':'manual','symbol':'TEST','price_unit':'VND','quantity_unit':'share',
            'session':'continuous','event_time':'2026-01-01T10:00:00+07:00','received_at':'2026-01-01T10:00:01+07:00',
            'bids':[{'price':'100','quantity':'20'},{'price':'99','quantity':'10'},{'price':'98','quantity':'1'}],
            'asks':[{'price':'102','quantity':'10'},{'price':'103','quantity':'20'},{'price':'104','quantity':'1'}]}
    req=Request(base+'/api/calculate',data=json.dumps(manual).encode(),headers={'Content-Type':'application/json'})
    result=json.load(urlopen(req,timeout=8))
    assert result['bid_depth_vnd']=='3088' and result['ask_depth_vnd']=='3184' and result['total_depth_vnd']=='6272'
    assert len(result['input_hash'])==64 and result['source']=='manual'
    checks.append({'check':'manual_three_levels_total_and_hash','status':'PASS','total_depth_vnd':result['total_depth_vnd']})
    for route in ['/api/market/ohlcv?symbol=UNKNOWN','/api/market/ohlcv?symbol=SSI&range=1m','/api/market/book?url=https://example.com']:
        try:read(route);raise AssertionError('Invalid query accepted')
        except HTTPError as error:assert error.code==400
    for route in ['/api/trading','/.env','/data/ssi_snapshots/probe_report.json','/../run.py']:
        try:read(route);raise AssertionError('Private route exposed')
        except HTTPError as error:assert error.code==404
    checks.append({'check':'query_private_and_trading_routes_denied','status':'PASS'})
    manifest=snapshot['manifest']
    assert sha256((ROOT/'data/ssi_snapshots/ohlcv_daily.csv').read_bytes()).hexdigest()==manifest['file_sha256']['ohlcv_daily.csv']
    checks.append({'check':'snapshot_unchanged','status':'PASS','sha256':manifest['file_sha256']['ohlcv_daily.csv']})
    report={'executed_at_utc':datetime.now(timezone.utc).isoformat(),'status':'PASS',
            'scope':'Actual running local HTTP server. UI rendering, clicks and screenshot checks NOT performed.',
            'checks':checks}
    (ROOT/'docs/ssi_runtime_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'PASS','checks':len(checks),'DATA_status':status['status'],'quote_events':status['quote_events'],'alerts':len(alerts['rows'])}))


if __name__=='__main__':main()
