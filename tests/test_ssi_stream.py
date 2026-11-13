"""Known-answer quote fixtures only; never served as market data."""
from datetime import datetime, timedelta
from decimal import Decimal
import copy
import unittest
from src.ssi_stream import book_metrics, DataStream, VN


def fixture():
    return {'symbol':'TEST','event_time':'2026-11-05T10:00:00+07:00','received_at':'2026-11-05T10:00:01+07:00',
            'bids':[['100','20'],['99','10'],['98','1']],
            'asks':[['102','10'],['103','20'],['104','1']]}


class StreamGateTests(unittest.TestCase):
    def test_verified_known_answer_and_no_mutation(self):
        book=fixture();before=copy.deepcopy(book)
        result=book_metrics(book,Decimal(1),'LO',datetime(2026,11,5,10,0,2,tzinfo=VN))
        self.assertEqual(result['bid_depth_vnd'],'3088');self.assertEqual(result['ask_depth_vnd'],'3184')
        self.assertEqual(result['total_depth_vnd'],'6272');self.assertEqual(book,before)
        self.assertAlmostEqual(float(result['spread_bps']),2/101*10000)

    def test_unverified_units_session_and_stale_rejected(self):
        now=datetime(2026,11,5,10,0,2,tzinfo=VN)
        for scale,session,time in [(None,'LO',now),(Decimal(1),'ATO',now),(Decimal(1),'LO',now+timedelta(seconds=31))]:
            with self.assertRaises(ValueError):book_metrics(fixture(),scale,session,time)

    def test_partial_delta_crossed_nonfinite_or_bad_order_rejected(self):
        now=datetime(2026,11,5,10,0,2,tzinfo=VN)
        variants=[]
        for side in ['bids','asks']:
            b=fixture();b[side]=b[side][:2];variants.append(b)
        for value in ['NaN','Infinity','bad','0','-1']:
            b=fixture();b['bids'][0][0]=value;variants.append(b)
        b=fixture();b['bids'][0][0]='102';variants.append(b)
        b=fixture();b['bids'].reverse();variants.append(b)
        b=fixture();b['asks'][0][1]='1.5';variants.append(b)
        for book in variants:
            with self.assertRaises(ValueError):book_metrics(book,Decimal(1),'LO',now)

    def test_off_hours_and_future_receive_rejected(self):
        b=fixture();b['event_time']='2026-11-05T08:59:00+07:00'
        with self.assertRaises(ValueError):book_metrics(b,Decimal(1),'LO',datetime(2026,11,5,9,tzinfo=VN))
        b=fixture();b['received_at']='2026-11-05T09:59:59+07:00'
        with self.assertRaises(ValueError):book_metrics(b,Decimal(1),'LO',datetime(2026,11,5,10,0,2,tzinfo=VN))

    def test_disconnected_service_contains_no_invented_book(self):
        stream=DataStream()
        self.assertEqual(stream.status()['status'],'disconnected')
        book=stream.book('SSI');self.assertFalse(book['available']);self.assertEqual(book['bids'],[])

    def test_disconnect_and_reconnect_clear_previous_book_and_session(self):
        from types import SimpleNamespace
        stream=DataStream();stream.quotes={'SSI':fixture()};stream.flag='LO'
        stream._connection(SimpleNamespace(state='disconnected'))
        self.assertEqual(stream.quotes,{});self.assertIsNone(stream.flag)
        stream._connection(SimpleNamespace(state='reconnected'))
        self.assertEqual(stream.state,'connected_no_ticks');self.assertFalse(stream.book('SSI')['available'])

    def test_unverified_quote_exposes_diagnostic_levels_without_metrics(self):
        stream=DataStream();stream.state='connected_unverified';stream.quotes={'SSI':fixture()}
        result=stream.book('SSI')
        self.assertFalse(result['available']);self.assertEqual(result['bids'],[])
        self.assertEqual(result['unverified_levels']['bids'][0],['100','20'])
        self.assertEqual(result['unverified_levels']['price_unit'],'unverified')
        self.assertNotIn('bid_depth_vnd',result)

    def test_subscription_ack_is_not_quote_and_rejection_is_explicit(self):
        stream=DataStream();stream.state='connected_no_ticks'
        stream._ack('quote',{'status':'ok','message':'not logged'})
        self.assertEqual(stream.status()['subscription_status']['quote'],'accepted')
        self.assertEqual(stream.quote_count,0)
        stream._ack('quote',{'status':'error','message':'sensitive body ignored'})
        self.assertEqual(stream.state,'connected_scope_rejected')
        self.assertEqual(stream.error['code'],'QUOTE_REJECTED')
        self.assertNotIn('message',stream.error)
