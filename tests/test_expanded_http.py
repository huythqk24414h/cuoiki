"""Real HTTP requests against current Handler; no browser or provider connection."""
import unittest,json,threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from src.universe import catalog
from run import Handler
from unittest.mock import patch

@unittest.skipUnless(catalog()['securities'],'Expanded SSI snapshot not installed')
class ExpandedHTTPTests(unittest.TestCase):
    @patch('src.history_store.active',return_value=(None,None))
    def test_latest_catalog_membership_and_rejected_raw_symbols(self,_legacy):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def get(path):
            with urlopen('http://127.0.0.1:'+str(server.server_port)+path,timeout=60) as response:return json.load(response)
        try:
            directory=get('/api/market/catalog')
            self.assertEqual(len(directory['securities']),len(catalog()['securities']))
            for symbol,reason in [('BNW','Invalid OHLCV'),('VIX','Conflict'),('VN50%20GROWTH','400006')]:
                result=get('/api/market/series?symbol='+symbol+'&range=MAX')
                self.assertEqual(result['rows'],[]);self.assertEqual(result['acquisition_state'],'ERROR');self.assertIn(reason,result['message'])
            members=directory.get('index_memberships',{}).get('VN30',[])
            if members:
                cov=get('/api/market/coverage?scope=INDEX:VN30')
                self.assertEqual(cov['catalog_count'],len(set(members)&{r['symbol'] for r in directory['securities']}))
                self.assertFalse(cov['gate']['allowed'])
        finally:server.shutdown();server.server_close();thread.join()
