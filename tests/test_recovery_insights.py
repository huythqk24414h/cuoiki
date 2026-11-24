"""Regression for observed connection failure and independent finance known answers."""
import unittest
from unittest.mock import patch
from decimal import Decimal
from src.ssi_stream import DataStream,stream_symbols
from src.insights import fact_sheet

class RecoveryTests(unittest.TestCase):
    def test_rest_alias_cannot_break_stream_subscription(self):
        directory = {"securities": [{"symbol": "SSI"}, {"symbol": "VN50 GROWTH"}]}
        with patch.dict("os.environ", {"SSI_STREAM_SYMBOLS": "SSI,VN50 GROWTH"}):
            with patch("src.universe.catalog", return_value=directory):
                self.assertEqual(stream_symbols(), ["SSI"])
            with patch("src.universe.catalog", return_value={"securities": []}):
                self.assertEqual(stream_symbols(), [])
        stream=DataStream();self.assertFalse(stream.watch('VN50 GROWTH'));self.assertTrue(stream.watch('SSI'))

    def test_partial_payload_replaces_previous_book_and_stays_unverified(self):
        stream=DataStream();stream.watch('SSI')
        stream._raw({'topic':'quote.SSI','data':{'s':'SSI','t':'2026/11/05 10:00:00','bids':[['100','20']],'asks':[],'token':'must not persist'}})
        self.assertEqual(stream.quote_count,1);self.assertFalse(stream.book('SSI')['available'])
        saved=stream.pending.get_nowait();self.assertNotIn('token',saved['data'])
        self.assertEqual(stream.quotes['SSI']['asks'],[])
        stream._raw({'topic':'quote.SSI','data':{'s':'SSI','t':'2026/11/05 10:00:01','bids':[['100']],'asks':[]}})
        self.assertEqual(stream.quotes['SSI']['bids'],[])

    def test_failed_session_is_retried(self):
        stream=DataStream()
        def attempt():
            if stream.attempts==2:stream.stop_event.set()
        with patch.object(stream,'_session',side_effect=attempt),patch.object(stream,'_rest_refresh'),patch.object(stream.stop_event,'wait',return_value=False):stream._run()
        self.assertEqual(stream.attempts,2)

class InsightTests(unittest.TestCase):
    def test_percentile_mad_and_prior_exclusion(self):
        prior=[{'symbol':'TEST','date':'2026-10-01','volume_shares':str(v)} for v in range(1,22)]
        current={'symbol':'TEST','date':'2026-11-04','volume_shares':'100','relative_volume20':'10','return_pct':'2'}
        sheet=fact_sheet(prior+[current],[{'tradingDate':'2026/10/01','indexChangePercentage':'0'},{'tradingDate':'2026/11/04','indexChangePercentage':'0.5'}])
        f=sheet['facts'];self.assertEqual(f['volume_percentile'],100);self.assertEqual(f['median_volume'],'11');self.assertEqual(f['mad_volume'],'5');self.assertEqual(f['excess_return_pp'],'1.5')
        self.assertEqual(Decimal(f['robust_z']),Decimal('0.67448975')*89/5)

    def test_zero_mad_is_missing_not_zero_signal(self):
        rows=[{'symbol':'TEST','date':'2026-11-04','volume_shares':'10'} for _ in range(25)]
        sheet=fact_sheet(rows);self.assertIsNone(sheet['facts']['robust_z']);self.assertIsNone(sheet['facts']['vnindex_return_pct'])
