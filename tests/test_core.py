"""Known-answer fixtures are test inputs, never application market data."""
import copy
import json
import threading
import unittest
from decimal import Decimal
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from src.finance import calculate, ContractError, available_asof
from src.sources import get_source
from run import Handler


def fixture():
    return dict(contract_version='1.0', source='manual', symbol='TEST', price_unit='VND',
                quantity_unit='share', session='continuous', event_time='2026-01-01T10:00:00+07:00',
                received_at='2026-01-01T10:00:01+07:00',
                bids=[dict(price=100,quantity=20),dict(price=99,quantity=10)],
                asks=[dict(price=102,quantity=10),dict(price=103,quantity=20)])


class FinanceTests(unittest.TestCase):
    def test_known_answer(self):
        result = calculate(fixture())
        self.assertEqual(result['bid_depth_vnd'], '2990')
        self.assertEqual(result['ask_depth_vnd'], '3080')
        self.assertEqual(Decimal(result['imbalance']), Decimal(-90)/6070)
        self.assertAlmostEqual(float(result['spread_bps']), 2/101*10000)

    def test_scale_invariance(self):
        original = fixture()
        scaled = copy.deepcopy(original)
        for side in ('bids','asks'):
            for level in scaled[side]: level['price'] *= 1000
        a,b = calculate(original),calculate(scaled)
        self.assertEqual(a['imbalance'],b['imbalance'])
        self.assertEqual(a['spread_bps'],b['spread_bps'])
        self.assertEqual(Decimal(b['bid_depth_vnd']),Decimal(a['bid_depth_vnd'])*1000)

    def test_no_mutation_and_reproducible(self):
        payload = fixture(); saved = copy.deepcopy(payload)
        self.assertEqual(calculate(payload),calculate(payload))
        self.assertEqual(payload,saved)

    def test_reject_invalid_contract(self):
        for field,value in [('contract_version','2'),('source','ssi'),('price_unit','1000VND'),
                            ('session','auction'),('symbol',''),('event_time','2026-01-01T10:00:00'),
                            ('received_at','2026-01-01T09:00:00+07:00')]:
            with self.subTest(field=field):
                payload=fixture();payload[field]=value
                with self.assertRaises(ContractError):calculate(payload)

    def test_reject_invalid_levels(self):
        for value in [None,True,-1,'NaN','Infinity','1e999999',{},0,1.5]:
            with self.subTest(value=value):
                payload=fixture();payload['bids'][0]['quantity']=value
                with self.assertRaises(ContractError):calculate(payload)
        for bids in [[],[dict(price=100,quantity=1)]*4,
                     [dict(price=99,quantity=1),dict(price=100,quantity=1)],
                     [dict(price=102,quantity=1)]]:
            payload=fixture();payload['bids']=bids
            with self.assertRaises(ContractError):calculate(payload)

    def test_point_in_time_late_arrival(self):
        first = dict(event_time='2026-01-01T10:00:00+07:00',received_at='2026-01-01T10:00:01+07:00')
        late = dict(event_time='2026-01-01T09:59:00+07:00',received_at='2026-01-01T10:01:00+07:00')
        self.assertEqual(available_asof([first,late],'2026-01-01T10:00:30+07:00'),[first])
        self.assertEqual(available_asof([first,late],'2026-01-01T10:01:00+07:00'),[first,late])

    def test_sources_disabled(self):
        self.assertEqual(list(get_source().events()),[])
        self.assertEqual(get_source().health()['database'],'disabled')
        self.assertEqual(get_source('replay').health()['connection'],'offline_replay')
        for name in ('ssi','mock'):
            with self.assertRaises(ValueError):get_source(name)


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def test_static_and_no_storage_imports(self):
        import sys
        self.assertNotIn('sqlite3',sys.modules)
        for path in ('/','/style.css','/app.js','/themes.js','/calculator-core.js','/book.svg'):
            with urlopen(self.base+path) as response:
                self.assertEqual(response.status,200)
                self.assertTrue(response.read())
                self.assertIn("default-src 'self'",response.headers['Content-Security-Policy'])

    def test_status_has_no_market_numbers(self):
        status=json.load(urlopen(self.base+'/api/status'))
        self.assertIsNone(status['market_metrics'])
        self.assertEqual(status['database'],'disabled')
        protocol=json.load(urlopen(self.base+'/api/protocol'))
        self.assertFalse(protocol['study_started'])
        self.assertIsNone(protocol['thresholds'])

    def test_post_valid_and_error(self):
        data=json.dumps(fixture()).encode()
        req=Request(self.base+'/api/calculate',data=data,headers={'Content-Type':'application/json'})
        self.assertEqual(json.load(urlopen(req))['bid_depth_vnd'],'2990')
        for body in (b'{',b'NaN',b'[]',b'{}'):
            with self.subTest(body=body):
                req=Request(self.base+'/api/calculate',data=body,headers={'Content-Type':'application/json'})
                with self.assertRaises(HTTPError) as ctx:urlopen(req)
                self.assertEqual(ctx.exception.code,422)

    def test_reject_cross_origin_and_wrong_type(self):
        for headers,code in [({'Content-Type':'application/json','Origin':'https://example.com'},403),
                             ({'Content-Type':'text/plain'},415)]:
            with self.subTest(code=code):
                with self.assertRaises(HTTPError) as ctx:
                    urlopen(Request(self.base+'/api/calculate',data=b'{}',headers=headers))
                self.assertEqual(ctx.exception.code,code)

    def test_no_file_or_database_routes(self):
        for route in ('/../run.py','/.env','/api/database','/api/trading'):
            with self.subTest(route=route):
                with self.assertRaises(HTTPError) as ctx:urlopen(self.base+route)
                self.assertEqual(ctx.exception.code,404)


if __name__=='__main__':unittest.main()
