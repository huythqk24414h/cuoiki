"""SSI contract/integrity integration tests. No provider or browser requests."""
import copy
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.ssi_client import SSIReadonly, date_range, safe_error, ALLOWED
from src.ssi_snapshot import validate_ssi_snapshot
from src import history_store
from src.market import market_payload, historical_alerts, FOLDER


class SSIClientTests(unittest.TestCase):
    def test_v3_date_serialization_and_timezone(self):
        start,end='2026-10-01T00:00:00+07:00','2026-11-04T23:59:59+07:00'
        self.assertEqual(date_range(start,end),('2026/10/01 00:00:00','2026/11/04 23:59:59'))
        self.assertEqual(date_range(start,end,True),('2026/10/01','2026/11/04'))
        for first,last in [(end,start),('2026-10-01',end),('2026-10-01T00:00:00Z',end)]:
            with self.assertRaises(ValueError):date_range(first,last)

    def test_ohlc_named_params_and_whitelist(self):
        client=SSIReadonly.__new__(SSIReadonly);client.get=MagicMock(return_value={'data':[]})
        client.ohlc('SSI','2026-10-01T00:00:00+07:00','2026-11-04T23:59:59+07:00',page=2)
        path,params=client.get.call_args.args
        self.assertEqual(path,'/api/v3/data/ohlc');self.assertEqual(params['pageIndex'],2)
        self.assertEqual(params['from'],'2026/10/01 00:00:00');self.assertEqual(params['timeFrame'],'1d')
        for symbol in ['../SSI','https://example.com','SSI?x=1']:
            with self.assertRaises(ValueError):client.ohlc(symbol,'bad','bad')
            self.assertEqual(ALLOWED,{'/api/v3/data/ohlc','/api/v3/data/securitiesByBoard','/api/v3/data/indexList',
                                      '/api/v3/data/indexSummary','/api/v3/data/securitiesSummary'})
        with self.assertRaises(ValueError):SSIReadonly.get(client,'/api/v3/trading/order',{})

    def test_error_output_has_no_message_body_or_token(self):
        error=RuntimeError('secret-string bearer token')
        error.response_body={'accessToken':'sensitive'}
        self.assertNotIn('secret',json.dumps(safe_error(error)))
        self.assertNotIn('sensitive',json.dumps(safe_error(error)))


require_snapshot = unittest.skipUnless(
    (FOLDER / "manifest.json").exists(), "Saved SSI snapshot unavailable; synthetic tests still run")


@require_snapshot
class SSISnapshotTests(unittest.TestCase):
    def test_actual_snapshot_and_every_raw_invariant(self):
        result=validate_ssi_snapshot(FOLDER)
        self.assertTrue(result['passed'],result['issues']);self.assertEqual(result['status'],'VALID')
        self.assertEqual(len(result['rows']),result['manifest']['row_count'])
        self.assertEqual(len(result['coverage_by_symbol']),6)
        self.assertTrue(all(r['date']<='2026-11-04' for r in result['rows']))
        self.assertEqual(len({(r['symbol'],r['date']) for r in result['rows']}),len(result['rows']))
        self.assertTrue(all(r['price_adjustment']=='unknown' for r in result['rows']))

    def test_tampering_raw_or_csv_is_rejected(self):
        for target in ['ohlcv_daily.csv','raw/SSI_1.json']:
            with tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp)/'snapshot';shutil.copytree(FOLDER,folder)
                with (folder/target).open('ab') as handle:handle.write(b' ')
                result=validate_ssi_snapshot(folder)
                self.assertFalse(result['passed']);self.assertEqual(result['rows'],[])

    def test_unknown_units_and_empty_snapshot_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'snapshot';shutil.copytree(FOLDER,folder)
            m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'));m['units']['price']='1000VND'
            (folder/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
            self.assertFalse(validate_ssi_snapshot(folder)['passed'])
        with tempfile.TemporaryDirectory() as tmp:self.assertFalse(validate_ssi_snapshot(tmp)['passed'])


@require_snapshot
@unittest.skipUnless(
    (history_store.PROJECT / "data/ssi_history_20220101_20261105/quality.json").exists(),
    "Saved expanded SSI history unavailable")
class MarketIntegrationTests(unittest.TestCase):
    def test_ssi_api_same_last_raw_prices_and_value(self):
        payload,code=market_payload('/api/market/ohlcv','symbol=SSI&range=ALL')
        self.assertEqual(code,200);self.assertTrue(payload['available'])
        self.assertEqual(payload['source'],'SSI FastConnect V3')
        last=payload['rows'][-1]
        self.assertEqual(last['date'],'2026-11-04');self.assertEqual(last['close_vnd'],'20400')
        self.assertEqual(last['volume_shares'],'47036100');self.assertEqual(last['source_value_vnd'],'959536440000');self.assertEqual(last['turnover_vnd'],'')
        self.assertEqual(last,payload['summary'])

    def test_ranges_and_rankings_are_snapshot_scoped(self):
        counts=[]
        for window in ['1M','3M','6M','YTD','ALL']:
            p,c=market_payload('/api/market/ohlcv','symbol=FPT&range='+window)
            self.assertEqual(c,200);counts.append(len(p['rows']))
            self.assertTrue(all(r['date']<='2026-11-04' for r in p['rows']))
        self.assertEqual(counts,sorted(counts))
        p,c=market_payload('/api/market/rankings','metric=volume')
        self.assertEqual(p['rows'],[]);self.assertFalse(p['coverage']['gate']['allowed'])

    def test_alert_evidence_recomputes_from_baseline(self):
        p,c=market_payload('/api/market/alerts','')
        self.assertEqual(c,200);self.assertEqual(p['status'],'evaluated')
        self.assertEqual(p['snapshot_sha256'],validate_ssi_snapshot(FOLDER)['manifest']['file_sha256']['ohlcv_daily.csv'])
        self.assertGreater(p['evaluated_observations'],0)
        for event in p['rows']:
            self.assertGreaterEqual(Decimal(event['value']),2)
            self.assertEqual(Decimal(event['volume'])/Decimal(event['baseline']),Decimal(event['value']))
            self.assertEqual(event['priority'],'cao' if Decimal(event['value'])>=3 else 'theo_doi')
            self.assertLessEqual(event['timestamp'],'2026-11-04')
        empty=historical_alerts({'passed':False,'manifest':{}})
        self.assertEqual(empty['status'],'unavailable');self.assertEqual(empty['message'],'Chưa đánh giá')

    def test_book_never_invents_quote_from_eod(self):
        p,c=market_payload('/api/market/book','symbol=SSI')
        self.assertEqual(c,200);self.assertFalse(p['available']);self.assertEqual(p['bids'],[])
        self.assertEqual(p['status'],'disconnected');self.assertIsNone(p['event_time'])

    def test_query_injection_and_unknown_symbol_rejected(self):
        for route,query in [('/api/market/ohlcv','symbol=../../../.env'),('/api/market/ohlcv','symbol=UNKNOWN'),('/api/market/ohlcv','symbol=SSI&symbol=FPT'),('/api/market/book','url=https://example.com'),('/api/market/alerts','x=y')]:
            self.assertEqual(market_payload(route,query)[1],400)

    def test_no_network_for_page_requests_and_fail_closed_missing_ssi(self):
        with patch('socket.socket',side_effect=AssertionError('Provider network forbidden')):
            self.assertTrue(market_payload('/api/market/meta','')[0]['available'])
        with tempfile.TemporaryDirectory() as tmp,patch('src.market.FOLDER',Path(tmp)):
            p,c=market_payload('/api/market/ohlcv','symbol=SSI&range=ALL')
            self.assertFalse(p['available']);self.assertEqual(p['rows'],[])

    def test_public_api_never_contains_credentials(self):
        from src.ssi_client import credentials
        secrets=credentials()
        for route in ['/api/market/meta','/api/market/status','/api/market/provenance']:
            body=json.dumps(market_payload(route,'')[0])
            self.assertNotIn('accessToken',body);self.assertNotIn('refreshToken',body)
            for key in ['SSI_API_KEY','SSI_API_SECRET']:
                if secrets[key]:self.assertNotIn(secrets[key],body)
