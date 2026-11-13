"""Known-answer financial checks; synthetic fixtures never enter production data."""
import unittest
from unittest.mock import patch
from decimal import Decimal
from src.universe import coverage_gate, canonical_row, resample
from src.eod_analytics import enrich_rows,select_range

class UniverseTests(unittest.TestCase):
    def test_gate_incomplete_session_and_unknown_membership(self):
        self.assertFalse(coverage_gate(79,100,True)['allowed'])
        self.assertEqual(coverage_gate(80,100,True)['status'],'PARTIAL')
        self.assertEqual(coverage_gate(95,100,True)['status'],'FULL')
        self.assertFalse(coverage_gate(100,100,False)['allowed'])
        self.assertFalse(coverage_gate(101,100,True)['allowed'])
        self.assertFalse(coverage_gate(0,0,True)['allowed'])

    def test_native_ohlc_not_rescaled_and_no_turnover_invention(self):
        r=canonical_row(dict(symbol='ABC',tradingDate='2026/11/04',open=10,high=12,low=9,close=11,volume=100,value=1100),'ABC')
        self.assertEqual(r['close_vnd'],'11');self.assertEqual(r['turnover_vnd'],'')
        self.assertEqual(r['unit_status'],'source_native_unverified')
        with self.assertRaises(ValueError):canonical_row(dict(symbol='ABC',tradingDate='2026/11/05'), 'ABC')

    def test_weekly_ohlcv_known_answer(self):
        rows=[canonical_row(dict(symbol='ABC',tradingDate=d,open=o,high=h,low=l,close=c,volume=v),'ABC') for d,o,h,l,c,v in [('2026/11/02',10,12,9,11,100),('2026/11/03',11,14,10,13,200),('2026/11/04',13,15,8,9,300)]]
        weekly=resample(rows,'1W')[0]
        self.assertEqual([weekly[k] for k in ('open_vnd','high_vnd','low_vnd','close_vnd','volume_shares')],['10','15','8','9','600'])
        self.assertEqual(weekly['source_value_vnd'],'')
        self.assertTrue(weekly['partial_period_possible'])
        with self.assertRaises(ValueError):resample(rows,'1m')

    def test_short_observation_ranges(self):
        rows=[{'date':f'2026-10-{d:02}'} for d in range(1,30)]
        self.assertEqual(len(select_range(rows,'1D')[0]),1)
        self.assertEqual(len(select_range(rows,'5D')[0]),5)
        self.assertEqual(len(select_range(rows,'MAX')[0]),29)

    def test_transient_backoff(self):
        from scripts.expand_ssi_market import request
        class Transient(Exception):status_code=429
        class Client:
            calls=0
            def get(self,*args):
                self.calls+=1
                if self.calls<3:raise Transient()
                return {'data':[]}
        c=Client()
        with patch('scripts.expand_ssi_market.time.sleep') as sleep:
            self.assertEqual(request(c,'endpoint',{}),{'data':[]})
            self.assertEqual([x.args[0] for x in sleep.call_args_list],[1,2])

    def test_checkpoint_checksum_rejects_tampering(self):
        from scripts.expand_ssi_market import save,read
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'page.json';save(path,{'response':[1]})
            self.assertEqual(read(path),{'response':[1]})
            path.write_text('{}')
            with self.assertRaises(ValueError):read(path)
