import unittest
from datetime import datetime,timedelta,timezone
from src.intraday import normalize,aggregate
from src.depth_watch import outcome

class IntradayWatchTests(unittest.TestCase):
    def test_real_shape_preserves_minutes_and_rejects_conflicts(self):
        raw={'symbol':'SSI','tradingDate':'2026/11/06 09:15:00','open':'10','high':'12','low':'9','close':'11','volume':'100'}
        self.assertEqual(len(normalize([raw,raw],'SSI')),1)
        with self.assertRaises(ValueError):normalize([raw,{**raw,'close':'10'}],'SSI')

    def test_four_hour_does_not_bridge_lunch_or_days(self):
        rows=[dict(timestamp=t,open='10',high='12',low='9',close='11',volume='100') for t in ['2026-11-05T09:15:00+07:00','2026-11-05T13:00:00+07:00','2026-11-06T09:15:00+07:00']]
        bars=aggregate(rows,'4h');self.assertEqual(len(bars),3);self.assertTrue(all(b['partial'] for b in bars));self.assertEqual(bars[0]['volume'],'100')

    def fixture(self):
        start=datetime(2026,11,6,9,15,tzinfo=timezone(timedelta(hours=7)))
        return [dict(timestamp=(start+timedelta(seconds=i)).isoformat(),symbol='SSI',session_id='AM',valid=True,bid_depth='100' if i<100 else '200' if i==100 else '10') for i in range(161)]

    def test_known_sustained_low_outcome_not_prediction(self):
        r=outcome(self.fixture());self.assertEqual(r['label'],1);self.assertFalse(r['forecast']);self.assertEqual(r['baseline_n'],100)

    def test_missing_or_changed_session_is_censored(self):
        for field,value in [('valid',False),('session_id','PM')]:
            rows=self.fixture();rows[-1][field]=value;self.assertEqual(outcome(rows)['state'],'CENSORED')
