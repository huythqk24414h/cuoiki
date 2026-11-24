"""Known-answer tests, HTTP/SSE transport tests; not browser screenshots."""
import unittest,json,threading,time
from datetime import datetime
from decimal import Decimal,localcontext
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from pathlib import Path
from unittest.mock import patch
from src.eod_analytics import enrich_rows
from src.ssi_stream import book_metrics,VN
from src.quote_board import board_row
from run import Handler

class FinancePromptTests(unittest.TestCase):
    def row(self,day,close,volume):
        return {'symbol':'TEST','date':day,'close_vnd':str(close),'volume_shares':str(volume),'price_adjustment':'unknown'}
    def test_rv20_excludes_current_and_missing_stays_null(self):
        rows=[self.row(f'2026-10-{i:02}',100,100) for i in range(1,21)]+[self.row('2026-10-21',100,250)]
        self.assertEqual(Decimal(enrich_rows(rows)[-1]['relative_volume20']),Decimal('2.5'))
        self.assertIsNone(enrich_rows(rows[:20])[-1]['relative_volume20'])
    def test_sample_stddev_hand_answer(self):
        with localcontext() as c:
            c.prec=60;price=Decimal(100);rows=[self.row('2026-10-01',price,100)]
            for i in range(1,21):
                price*=Decimal('1.01') if i%2 else Decimal('.99');rows.append(self.row(f'2026-10-{i+1:02}',price,100))
            actual=Decimal(enrich_rows(rows)[-1]['volatility20_pct']);expected=(Decimal(20)/19).sqrt()
            self.assertLess(abs(actual-expected),Decimal('1e-9'))
    def test_prompt_spread_and_no_implicit_thousand_scaling(self):
        candidate={'symbol':'TEST','event_time':'2026-11-05T10:00:00+07:00','received_at':'2026-11-05T10:00:01+07:00','bids':[['20.50','1000'],['20.49','1000'],['20.48','1000']],'asks':[['20.55','1000'],['20.56','1000'],['20.57','1000']]}
        metrics=book_metrics(candidate,Decimal(1),'LO',datetime(2026,11,5,10,0,2,tzinfo=VN))
        self.assertAlmostEqual(float(metrics['spread_bps']),24.3605359318,places=8)
        self.assertEqual(Decimal('20.55')*1000,Decimal(20550))
    def test_price_color_requires_verified_compatible_units(self):
        t='2026-11-05T10:00:00+07:00';quote={'event_time':t,'received_at':t,'bids':[['101','100']],'asks':[]};master={'event_time':t,'received_at':t,'data':{'ce':'107','fl':'93','ref':'100'}}
        meta={'symbol':'TEST','board':'HOSE'};now=datetime.fromisoformat(t)
        self.assertEqual(board_row(meta,quote,None,master,None,now,'connected_unverified')['colors'],{})
        c={'status':'VERIFIED','symbols':['TEST'],'price_scale':1,'reference_price_scale':1}
        self.assertEqual(board_row(meta,quote,None,master,None,now,'connected_unverified',c)['colors']['bids'][0],'market-up')

class SSELocalTests(unittest.TestCase):
    def test_real_local_sse_first_frame_and_assets_no_provider_connection(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            sample = Path(__file__).resolve().parents[1] / "data_sample/catalog_fixture.json"
            catalog = json.loads(sample.read_text(encoding="utf-8"))
            self.assertEqual(catalog["fixture_type"], "synthetic_test_only")
            with patch("src.universe.catalog", return_value=catalog), urlopen(
                base + "/api/market/board-stream?scope=INDEX:VN30&size=30", timeout=15
            ) as r:
                self.assertIn('text/event-stream',r.headers['Content-Type']);self.assertEqual(r.readline().decode().strip(),'event: board')
                data=json.loads(r.readline().decode()[6:]);self.assertEqual([row['symbol'] for row in data['rows']], ['TEST']);self.assertEqual(data['scope'],'INDEX:VN30')
            for path in ('/formula.js','/vendor/katex/katex.js'):
                with urlopen(base+path) as r:self.assertEqual(r.status,200)
        finally:server.shutdown();server.server_close();thread.join()
