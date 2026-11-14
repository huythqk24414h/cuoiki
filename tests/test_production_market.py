import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import Mock, patch

from scripts.market_universe import request
from scripts.publish_intraday import closed_candles, merge_candles
from scripts.publish_market_history import backfill
from src.eod_analytics import enrich_rows
from src.ssi_stream import VN, book_metrics


def daily(day, high="11"):
    return dict(symbol="TEST", tradingDate=day, open="10", high=high, low="9",
                close="10", volume="100000")


class ProductionMarketTests(unittest.TestCase):
    def test_retry_on_429_respects_provider_wait(self):
        error = RuntimeError()
        error.status_code = 429
        error.retry_after_ms = 19000
        call = Mock(side_effect=[error, "ok"])
        with patch("scripts.market_universe.time.sleep") as sleep:
            self.assertEqual(request(call), "ok")
            sleep.assert_called_once_with(19)

    def test_daily_quarantine_and_pagination(self):
        client = Mock()
        client.ohlc.side_effect = [
            {"pageIndex":1, "pagesCount":2, "data":[daily("2026/11/13"), daily("2026/11/12","0")]},
            {"pageIndex":2, "pagesCount":2, "data":[daily("2026/11/12","0"), daily("2026/11/11")]},
        ]
        rejected = set()
        rows = backfill(client, "TEST", date(2026,11,10), date(2026,11,13), rejected)
        self.assertEqual(set(rows), {"2026-11-11", "2026-11-13"})
        self.assertEqual(rejected, {"2026-11-12"})
        self.assertEqual(client.ohlc.call_args.kwargs["page"], 2)

    def test_closed_candles_and_partial_session(self):
        def row(hour, minute):
            return dict(timestamp=datetime(2026,11,13,hour,minute,tzinfo=VN).isoformat(),
                        open="10", high="11", low="9", close="10", volume="50")
        rows = [row(11,15), row(12,00), row(13,00)]
        now = datetime(2026,11,13,13,10,tzinfo=VN)
        halfday = closed_candles(rows, "4h", now)
        self.assertEqual([(r["session_minutes"],r["volume"]) for r in halfday], [(135,"50")])
        self.assertEqual(len(closed_candles(rows, "15m", now)), 1)
        first = closed_candles(rows, "15m", now)
        previous = {"15m":first}
        recent = {"15m":[{**first[0],"observed_minutes":0,"volume":"0"}],"1h":[],"4h":[]}
        self.assertEqual(merge_candles(previous,recent,"2026-11-13")["15m"], first)

    def test_liquidation_proxy_excludes_current_volume(self):
        rows = [dict(symbol="TEST", date=f"2026-01-{d:02d}", close_vnd="10",
                     volume_shares="100000" if d<21 else "0", price_adjustment="unknown")
                for d in range(1,22)]
        output = enrich_rows(rows)
        self.assertIsNone(output[19]["liquidation_days_100k_5pct"])
        self.assertEqual(Decimal(output[-1]["liquidation_days_100k_5pct"]),20)
        output = enrich_rows([{**row,"volume_shares":"0"} for row in rows])
        self.assertIsNone(output[-1]["liquidation_days_100k_5pct"])

    def test_ssi_spread_depth_and_imbalance(self):
        now = datetime(2026,11,13,10,0,tzinfo=VN)
        candidate = {"symbol":"TEST", "event_time":now.isoformat(), "received_at":now.isoformat(),
                     "bids":[("100","3"),("99","4"),("98","5")],
                     "asks":[("102","1"),("103","2"),("104","3")]}
        metrics = book_metrics(candidate, Decimal(1), "LO", now)
        self.assertEqual(Decimal(metrics["spread_vnd_per_share"]), 2)
        self.assertAlmostEqual(float(metrics["spread_bps"]), 20000/101)
        self.assertEqual(Decimal(metrics["bid_depth_vnd"]), 1186)
        self.assertEqual(Decimal(metrics["ask_depth_vnd"]), 620)
        self.assertEqual(Decimal(metrics["bid_displayed_shares"]), 12)
        self.assertAlmostEqual(float(metrics["imbalance"]), 566/1806)
        with self.assertRaises(ValueError):
            book_metrics(candidate, None, "LO", now)
