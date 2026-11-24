from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from src.finance import calculate, ContractError
from src.research_core import displayed_depth
from src.ssi_stream import book_metrics


NOW = datetime(2026, 11, 19, 10, tzinfo=timezone(timedelta(hours=7)))
CONTRACT = {"price_scale": 1, "quantity_scale": 1, "zero_pair_means_absent_level": True}


def inputs(bids, asks):
    quote = {"symbol": "TEST", "event_time": NOW.isoformat(), "received_at": NOW.isoformat(),
             "bids": bids, "asks": asks}
    manual = {**quote, "contract_version": "1.0", "source": "manual", "session": "continuous",
              "price_unit": "VND", "quantity_unit": "share"}
    for side in ("bids", "asks"):
        manual[side] = [{"price": p, "quantity": q} for p, q in quote[side]]
    return quote, manual


class DepthParityTests(unittest.TestCase):
    def test_agreement_on_twenty_valid_three_level_books(self):
        for i in range(1, 21):
            bids = [[1000+i-j*10, i*10+j] for j in range(3)]
            asks = [[1020+i+j*10, (22-i)*10+j] for j in range(3)]
            with self.subTest(case=i):
                quote, manual = inputs(bids, asks)
                a = calculate(manual)
                b = book_metrics(quote, Decimal(1), "LO", NOW)
                c = displayed_depth(bids, asks, CONTRACT)
                for field, research_field in (("bid_depth_vnd", "bid_depth"), ("ask_depth_vnd", "ask_depth"),
                                              ("imbalance", "imbalance"), ("spread_bps", "spread_bps")):
                    self.assertAlmostEqual(Decimal(a[field]), Decimal(b[field]), places=23)
                    self.assertAlmostEqual(Decimal(a[field]), Decimal(c[research_field]), places=23)

    def test_different_policies_for_verified_absence_and_crossed_books(self):
        cases = [([], [[110, 1], [111, 1], [112, 1]]),
                 ([[120, 1], [119, 1], [118, 1]], [[110, 1], [111, 1], [112, 1]])]
        for bids, asks in cases:
            quote, manual = inputs(bids, asks)
            with self.assertRaises(ContractError):
                calculate(manual)
            with self.assertRaises(ValueError):
                book_metrics(quote, Decimal(1), "LO", NOW)
            with self.assertRaises(ValueError):
                displayed_depth(bids, asks, CONTRACT)
        bids, asks = [[0, 0]] * 3, [[110, 1], [111, 1], [112, 1]]
        quote, manual = inputs(bids, asks)
        with self.assertRaises(ContractError):
            calculate(manual)
        with self.assertRaises(ValueError):
            book_metrics(quote, Decimal(1), "LO", NOW)
        self.assertTrue(displayed_depth(bids, asks, CONTRACT)["empty_bid"])
        self.assertIsNone(displayed_depth(bids, asks, CONTRACT)["spread_bps"])
