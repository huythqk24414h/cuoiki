"""Real saved SSI history and HTTP integration; no upstream requests, no invented prices."""
import json,threading,unittest,tempfile
from pathlib import Path
from hashlib import sha256
from urllib.request import urlopen
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from src import history_store,universe
from src.market import market_payload
from run import Handler

requires_history = unittest.skipUnless(
    (history_store.PROJECT / "data/ssi_history_20220101_20261105/quality.json").exists(),
    "Saved expanded SSI history unavailable")


class HistoricalRevisionTests(unittest.TestCase):
    @requires_history
    def test_active_revision_bounds_and_partial_rows_exclude_quarantine(self):
        folder,q=history_store.active()
        self.assertEqual(q['validation_status'],'PASS')
        self.assertEqual(q['query_start'],'2022-01-01')
        self.assertEqual(q['query_end'],'2026-11-05')
        self.assertGreater(q['rows'],1000000)
        for symbol in ('SSI','FPT','BNW','VIX'):
            rows=history_store.rows(symbol)
            self.assertTrue(rows,symbol)
            self.assertEqual(len(rows),len({r['date'] for r in rows}))
            self.assertTrue(all('2022-01-01'<=r['date']<='2026-11-05' for r in rows))
        self.assertEqual(history_store.rows('VN50 GROWTH'),[])
        original=history_store.PROJECT/'data/ssi_snapshots/ohlcv_daily.csv'
        self.assertEqual(sha256(original.read_bytes()).hexdigest(),'799e65513c86ad93ddce9349c921b0c93777bfc5880eb580f8529f932ad91d74')

    def test_anchored_digest_rejects_changed_file_even_with_updated_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'example.json';raw=b'{"rows":[]}'
            path.write_bytes(raw);digest=sha256(raw).hexdigest();path.with_suffix('.sha256').write_text(digest)
            self.assertEqual(history_store.read_verified(path,digest),{'rows':[]})
            path.write_bytes(raw+b' ');path.with_suffix('.sha256').write_text(sha256(path.read_bytes()).hexdigest())
            with self.assertRaises(ValueError):history_store.read_verified(path,digest)

    def test_missing_active_quality_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'config').mkdir();(root/'data').mkdir()
            (root/'config/history_active.json').write_text(json.dumps({'folder':'data/missing','quality_sha256':'invalid'}))
            with patch.object(history_store,'PROJECT',root):
                with self.assertRaises(ValueError):history_store.active()
        history_store._cache.clear()

    @requires_history
    def test_real_http_welcome_assets_5y_series_and_index(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        def get(path):
            with urlopen(base+path,timeout=30) as response:return response.read()
        try:
            html=get('/').decode();self.assertIn('class="guest"',html);self.assertIn('id="demo-login-open"',html)
            self.assertEqual(get('/assets/landing.png'),(history_store.PROJECT/'web/assets/landing.png').read_bytes())
            self.assertIn(b'assembly',get('/welcome-fx.js'))
            meta=json.loads(get('/api/market/meta'));self.assertEqual(meta['historical_range']['start'],'2022-01-01')
            for window in ('3Y','5Y','MAX'):
                data=json.loads(get('/api/market/series?symbol=SSI&range='+window))
                self.assertGreater(len(data['rows']),600)
                self.assertEqual(data['rows'][-1]['date'],'2026-11-05')
            data=json.loads(get('/api/market/series?symbol=SSI&range=CUSTOM&from=2022-01-01&to=2022-12-31'))
            self.assertTrue(data['rows']);self.assertTrue(all(r['date'].startswith('2022') for r in data['rows']))
            for code in ('VNINDEX','VN30','HNXINDEX','UPCOMINDEX'):
                data=json.loads(get('/api/market/index?symbol='+code+'&range=MAX'))
                self.assertGreater(len(data['rows']),1100)
                self.assertEqual(data['source'],'SSI official daily index OHLC')
            self.assertFalse(json.loads(get('/api/market/coverage?to=2022-06-01'))['gate']['allowed'])
        finally:server.shutdown();server.server_close();thread.join()
