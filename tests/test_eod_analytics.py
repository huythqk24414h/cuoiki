"""Synthetic known answers live only in tests, never in the demo snapshot."""
import copy
from datetime import date, timedelta
from decimal import Decimal
import statistics
import unittest

from src.eod_analytics import enrich_rows, select_range


def rows(count=25, symbol='TEST', zero_volume=False):
    result, session = [], date(2026, 1, 1)
    while len(result) < count:
        if session.weekday() < 5:
            i = len(result)
            price = str(100 + i)
            result.append({'symbol': symbol, 'date': session.isoformat(), 'open_vnd': price,
                           'high_vnd': price, 'low_vnd': price, 'close_vnd': price,
                           'volume_shares': '0' if zero_volume else str(i + 1),
                           'turnover_vnd': '', 'price_adjustment': 'provider_adjusted',
                           'upstream_source': 'test', 'source_url': 'https://example.org/test'})
        session += timedelta(days=1)
    return result


class EODAnalyticsTests(unittest.TestCase):
    def test_prior20_volume_excludes_current(self):
        sample = rows(21)
        sample[-1]['volume_shares'] = '2100'
        result = enrich_rows(sample)
        self.assertIsNone(result[19]['volume_avg20_previous'])
        self.assertEqual(Decimal(result[20]['volume_avg20_previous']), Decimal('10.5'))
        self.assertEqual(Decimal(result[20]['relative_volume20']), Decimal('200'))

    def test_return_and_volatility_known_answer(self):
        sample = rows(21)
        result = enrich_rows(sample)
        self.assertIsNone(result[0]['return_pct'])
        self.assertEqual(Decimal(result[1]['return_pct']), Decimal(1))
        self.assertIsNone(result[19]['volatility20_pct'])
        expected = statistics.stdev([(100 + i) / (99 + i) * 100 - 100 for i in range(1, 21)])
        self.assertAlmostEqual(float(result[20]['volatility20_pct']), expected, places=11)

    def test_no_lookahead_and_no_mutation(self):
        sample = rows(25)
        before = copy.deepcopy(sample)
        prefix = enrich_rows(sample[:21])
        full = enrich_rows(sample)
        self.assertEqual(prefix, full[:21])
        self.assertEqual(sample, before)
        sample[-1]['close_vnd'] = '999999'
        sample[-1]['volume_shares'] = '888888'
        self.assertEqual(prefix, enrich_rows(sample)[:21])

    def test_zero_volume_and_short_samples_are_explicit(self):
        result = enrich_rows(rows(21, zero_volume=True))
        self.assertEqual(result[-1]['volume_avg20_previous'], '0')
        self.assertIsNone(result[-1]['relative_volume20'])
        self.assertIn('bằng 0', result[-1]['missing_reasons']['relative_volume20'])
        self.assertIn('21', result[0]['missing_reasons']['volatility20_pct'])
        self.assertEqual(enrich_rows([]), [])

    def test_calendar_ranges_anchor_actual_last_session(self):
        sample = enrich_rows(rows(150))
        selected, start, end = select_range(sample, '1M')
        self.assertEqual(end, sample[-1]['date'])
        self.assertTrue(all(r['date'] >= start for r in selected))
        self.assertLess(len(selected), len(sample))
        self.assertEqual(select_range(sample, 'ALL')[0], sample)
        self.assertEqual(select_range([], '3M'), ([], None, None))
        with self.assertRaises(ValueError):
            select_range(sample, '1m')

    def test_mixed_policy_or_symbol_rejected(self):
        sample = rows(2)
        sample[-1]['price_adjustment'] = 'unadjusted'
        with self.assertRaises(ValueError):
            enrich_rows(sample)
        sample[-1]['price_adjustment'] = 'provider_adjusted'
        sample[-1]['symbol'] = 'OTHER'
        with self.assertRaises(ValueError):
            enrich_rows(sample)


if __name__ == '__main__':
    unittest.main()
