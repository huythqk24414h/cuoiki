import unittest
from datetime import datetime,timedelta
from src.quote_board import board_row,numeric
from src.ssi_stream import DataStream,VN
class BoardTests(unittest.TestCase):
 def test_book_and_board_watchlists_do_not_overwrite_each_other(self):
  s=DataStream();s.watch('SSI');s.watch_board(['FPT','HPG','VN50 GROWTH']);s.watch('MBB')
  self.assertEqual(s.wanted,{'FPT','HPG','MBB'});s.board_lease_until=0;s._wanted_now();self.assertEqual(s.wanted,{'MBB'})
 def test_stale_is_not_live_and_change_not_inferred(self):
  now=datetime(2026,11,5,13,tzinfo=VN);q={'event_time':(now-timedelta(minutes=2)).isoformat(),'received_at':(now-timedelta(minutes=2)).isoformat(),'bids':[['20000','100']],'asks':[]}
  r=board_row({'symbol':'SSI','board':'HOSE'},q,None,None,None,now,'connected_unverified')
  self.assertEqual(r['status'],'stale');self.assertIsNone(r['change_pct']);self.assertEqual(r['bids'][0]['price'],'20000')
 def test_invalid_values_do_not_leak_nonfinite_json(self):
  self.assertIsNone(numeric('NaN'));self.assertIsNone(numeric('Infinity'));self.assertIsNone(numeric('-1'));self.assertEqual(numeric('ATO',True),'ATO')
