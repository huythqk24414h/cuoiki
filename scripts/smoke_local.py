"""Explicit local HTTP smoke test. Does not automate a browser or fetch providers."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def smoke(port):
    base = f'http://127.0.0.1:{port}'
    checks = []

    def get(path):
        with urlopen(base + path, timeout=5) as response:
            assert response.status == 200
            assert "connect-src 'self'" in response.headers['Content-Security-Policy']
            assert response.headers.get('Access-Control-Allow-Origin') is None
            return json.load(response)

    before = sha256((ROOT / 'data/demo/ohlcv.csv').read_bytes()).hexdigest()
    meta = get('/api/demo/meta')
    assert meta['available'] and meta['quality_gate']['passed']
    assert meta['asof_date'] == '2026-11-04'
    checks.append({'check': 'runtime_metadata', 'status': 'PASS', 'symbols': meta['loaded_symbols'],
                   'row_count': meta['manifest']['row_count']})
    for symbol in meta['loaded_symbols']:
        counts = {}
        for range_id in ('1M', '3M', 'ALL'):
            payload = get(f'/api/demo/ohlcv?symbol={symbol}&range={range_id}')
            assert payload['available'] and payload['rows']
            assert all(row['date'] <= '2026-11-04' and row['symbol'] == symbol for row in payload['rows'])
            assert payload['summary'] == payload['rows'][-1]
            counts[range_id] = len(payload['rows'])
        assert counts['1M'] <= counts['3M'] <= counts['ALL']
        checks.append({'check': 'runtime_filters', 'status': 'PASS', 'symbol': symbol, 'counts': counts})
    for metric in ('volume', 'return_pct', 'relative_volume20'):
        ranking = get(f'/api/demo/rankings?metric={metric}')
        assert len(ranking['rows']) == len(meta['loaded_symbols'])
    checks.append({'check': 'runtime_rankings', 'status': 'PASS', 'metrics': 3})
    status = get('/api/status')
    assert status['connection'] == 'not_configured' and status['database'] == 'disabled'
    assert status['market_metrics'] is None
    checks.append({'check': 'ssi_database_stay_disabled', 'status': 'PASS'})
    # Known-answer manual fixture, never inserted into the historical snapshot.
    manual = {'contract_version': '1.0', 'source': 'manual', 'symbol': 'TEST',
              'price_unit': 'VND', 'quantity_unit': 'share', 'session': 'continuous',
              'event_time': '2026-01-01T10:00:00+07:00', 'received_at': '2026-01-01T10:00:01+07:00',
              'bids': [{'price': '100', 'quantity': '20'}, {'price': '99', 'quantity': '10'}],
              'asks': [{'price': '102', 'quantity': '10'}, {'price': '103', 'quantity': '20'}]}
    request = Request(base + '/api/calculate', data=json.dumps(manual).encode(),
                      headers={'Content-Type': 'application/json'})
    result = json.load(urlopen(request, timeout=5))
    assert result['bid_depth_vnd'] == '2990' and result['ask_depth_vnd'] == '3080'
    checks.append({'check': 'runtime_manual_known_answer', 'status': 'PASS', 'source': result['source'],
                   'bid_depth_vnd': result['bid_depth_vnd'], 'ask_depth_vnd': result['ask_depth_vnd']})
    for route in ('/api/demo/ohlcv?symbol=UNKNOWN&range=ALL', '/api/demo/ohlcv?symbol=FPT&range=1m'):
        try:
            urlopen(base + route, timeout=5)
            raise AssertionError('Bad query accepted')
        except HTTPError as error:
            assert error.code == 400
    checks.append({'check': 'runtime_bad_queries_rejected', 'status': 'PASS'})
    after = sha256((ROOT / 'data/demo/ohlcv.csv').read_bytes()).hexdigest()
    assert before == after == meta['manifest']['file_sha256']['ohlcv.csv']
    checks.append({'check': 'snapshot_unchanged_after_runtime_reads', 'status': 'PASS', 'sha256': after})
    return {'executed_at_utc': datetime.now(timezone.utc).isoformat(), 'base_url': base,
            'scope': 'Actual running HTTP server and APIs; no browser/render/screenshot verification.',
            'status': 'PASS', 'checks': checks}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8792)
    args = parser.parse_args()
    report = smoke(args.port)
    path = ROOT / 'docs/runtime_smoke.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"PASS: {len(report['checks'])} local HTTP checks; {path}")
