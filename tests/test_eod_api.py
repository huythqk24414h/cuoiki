"""Local HTTP/API checks; test fixtures are isolated from data/demo."""
import csv
from decimal import Decimal
from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import statistics
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from run import Handler
from src.eod_analytics import demo_payload
from src.eod_snapshot import COLUMNS
from test_eod_analytics import rows


def write_snapshot(folder):
    data = sorted(rows(25, 'AAA') + rows(25, 'BBB'), key=lambda r: (r['symbol'], r['date']))
    with (folder / 'ohlcv.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(data)
    coverage = {s: {'rows': 25, 'first_available_session': data[0]['date'],
                    'last_available_session': data[24]['date']} for s in ('AAA', 'BBB')}
    manifest = {'dataset_type': 'historical_eod_snapshot', 'asof_date': '2026-11-04',
                'asof_timezone': 'Asia/Ho_Chi_Minh', 'retrieved_at_utc': '2026-11-05T00:00:00Z',
                'symbols_requested': ['AAA', 'BBB'], 'symbols_loaded': ['AAA', 'BBB'],
                'lookback_sessions_requested': 25, 'refresh_policy': 'manual_one_shot',
                'units': {'price': 'VND/share', 'volume': 'share', 'turnover': 'VND'},
                'adjustment_policy': 'provider_adjusted', 'coverage_by_symbol': coverage,
                'row_count': 50, 'file_sha256': {'ohlcv.csv': sha256((folder / 'ohlcv.csv').read_bytes()).hexdigest()},
                'upstream_sources': [{'id': 'test', 'usage_note': 'Unit test fixture only.',
                                     'source_url': 'https://example.org/test',
                                     'documentation_url': 'https://example.org/documentation'}], 'issues': []}
    (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return manifest


class EODPayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.folder = Path(self.temp.name)
        self.manifest = write_snapshot(self.folder)

    def tearDown(self):
        self.temp.cleanup()

    def test_metadata_coverage_and_no_network(self):
        with patch('socket.create_connection', side_effect=AssertionError('No network allowed')):
            payload, code = demo_payload('/api/demo/meta', '', self.folder)
        self.assertEqual(code, 200)
        self.assertTrue(payload['available'])
        self.assertEqual(payload['loaded_symbols'], ['AAA', 'BBB'])
        self.assertEqual(payload['manifest']['file_sha256'], self.manifest['file_sha256'])
        self.assertEqual(payload['last_available_session'], self.manifest['coverage_by_symbol']['AAA']['last_available_session'])

    def test_prices_exact_and_summary_matches_last_csv_row(self):
        result, code = demo_payload('/api/demo/ohlcv', 'symbol=AAA&range=1M', self.folder)
        self.assertEqual(code, 200)
        self.assertEqual(result['summary']['close_vnd'], '124')
        self.assertEqual(result['rows'][-1]['volume_shares'], '25')
        summary, _ = demo_payload('/api/demo/summary', 'symbol=AAA&range=1M', self.folder)
        self.assertEqual(summary['summary'], result['summary'])
        self.assertTrue(all(r['date'] <= '2026-11-04' for r in result['rows']))
        self.assertIn('missing_reasons', result['summary'])

    def test_rankings_scope_and_allowed_metrics(self):
        for metric in ('volume', 'return_pct', 'relative_volume20'):
            result, code = demo_payload('/api/demo/rankings', 'metric=' + metric, self.folder)
            self.assertEqual(code, 200)
            self.assertEqual(result['scope'], 'loaded_symbols')
            self.assertEqual({r['symbol'] for r in result['rows']}, {'AAA', 'BBB'})

    def test_invalid_and_duplicate_queries_rejected(self):
        for route, query in [('/api/demo/ohlcv', 'symbol=../../.env'),
                             ('/api/demo/ohlcv', 'symbol=AAA&symbol=BBB'),
                             ('/api/demo/ohlcv', 'symbol=UNKNOWN'),
                             ('/api/demo/ohlcv', 'range=15m'),
                             ('/api/demo/ohlcv', 'symbol='),
                             ('/api/demo/meta', 'file=../../run.py'),
                             ('/api/demo/rankings', 'metric=turnover'),
                             ('/api/demo/meta', 'broken')]:
            with self.subTest(query=query):
                self.assertEqual(demo_payload(route, query, self.folder)[1], 400)
        self.assertEqual(demo_payload('/api/demo/no-such-route', '', self.folder)[1], 404)

    def test_corrupt_missing_or_malformed_snapshot_unavailable(self):
        (self.folder / 'ohlcv.csv').write_text('corrupted', encoding='utf-8')
        result, code = demo_payload('/api/demo/ohlcv', 'symbol=AAA', self.folder)
        self.assertEqual(code, 200)
        self.assertFalse(result['available'])
        self.assertEqual(result['rows'], [])
        (self.folder / 'manifest.json').write_text('{', encoding='utf-8')
        self.assertFalse(demo_payload('/api/demo/health', '', self.folder)[0]['available'])
        (self.folder / 'manifest.json').unlink()
        self.assertFalse(demo_payload('/api/demo/meta', '', self.folder)[0]['available'])

    def test_unvalidated_manifest_not_exposed(self):
        self.manifest['retrieved_at_utc'] = 123
        (self.folder / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        result, code = demo_payload('/api/demo/meta', '', self.folder)
        self.assertEqual(code, 200)
        self.assertFalse(result['available'])
        self.assertEqual(result['manifest'], {})

    def test_nonfinite_extra_metadata_unavailable_not_500(self):
        self.manifest['unexpected_nonfinite'] = float('nan')
        (self.folder / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        result, code = demo_payload('/api/demo/meta', '', self.folder)
        self.assertEqual(code, 200)
        self.assertFalse(result['available'])

    def test_actual_frozen_snapshot_against_independent_csv_math(self):
        folder = Path(__file__).resolve().parents[1] / 'data' / 'demo'
        if not (folder / 'ohlcv.csv').is_file():
            self.skipTest('No local historical snapshot; fixture tests remain available.')
        with (folder / 'ohlcv.csv').open(encoding='utf-8-sig', newline='') as handle:
            data = [r for r in csv.DictReader(handle) if r['symbol'] == 'FPT']
        result, code = demo_payload('/api/demo/ohlcv', 'symbol=FPT&range=ALL', folder)
        self.assertEqual(code, 200)
        self.assertTrue(result['available'])
        self.assertEqual(len(result['rows']), len(data))
        self.assertEqual(result['summary']['close_vnd'], data[-1]['close_vnd'])
        self.assertEqual(result['last_available_session'], max(r['date'] for r in data))
        expected_average = sum(Decimal(r['volume_shares']) for r in data[-21:-1]) / 20
        self.assertEqual(Decimal(result['summary']['volume_avg20_previous']), expected_average)
        expected_returns = [float(Decimal(b['close_vnd']) / Decimal(a['close_vnd']) - 1) * 100
                            for a, b in zip(data[-21:-1], data[-20:])]
        self.assertAlmostEqual(float(result['summary']['volatility20_pct']), statistics.stdev(expected_returns), places=11)
        self.assertTrue(all(r['date'] <= '2026-11-04' for r in result['rows']))


class EODHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        cls.folder = Path(cls.temp.name)
        write_snapshot(cls.folder)
        cls.patch = patch('run.DEMO', cls.folder)
        cls.patch.start()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.patch.stop()
        cls.temp.cleanup()

    def test_local_routes_and_csp_preserved(self):
        for route in ('/api/demo/meta', '/api/demo/health', '/api/demo/ohlcv?symbol=AAA&range=ALL',
                      '/api/demo/summary?symbol=AAA', '/api/demo/rankings?metric=volume'):
            with self.subTest(route=route), urlopen(self.base + route) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(json.load(response)['available'])
                self.assertIn("connect-src 'self'", response.headers['Content-Security-Policy'])
                self.assertIsNone(response.headers.get('Access-Control-Allow-Origin'))
        status = json.load(urlopen(self.base + '/api/status'))
        self.assertEqual(status['connection'], 'not_configured')
        self.assertEqual(status['database'], 'disabled')

    def test_reject_bad_query_at_http_boundary(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.base + '/api/demo/ohlcv?symbol=AAA&range=1m')
        self.assertEqual(caught.exception.code, 400)


if __name__ == '__main__':
    unittest.main()
