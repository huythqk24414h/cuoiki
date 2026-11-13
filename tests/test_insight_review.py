"""Financial review regressions: identical dates alone do not imply identical return horizons."""
import unittest
from src.insights import fact_sheet

class InsightReviewTests(unittest.TestCase):
    def rows(self):
        return [{'symbol':'TEST','date':'2026-10-29','volume_shares':'10'}, {'symbol':'TEST','date':'2026-11-04','volume_shares':'100','return_pct':'2'}]

    def test_same_date_benchmark_with_different_base_session_is_not_excess(self):
        result=fact_sheet(self.rows(),[{'tradingDate':'2026/11/03','indexChangePercentage':'1'}, {'tradingDate':'2026/11/04','indexChangePercentage':'0.5'}])
        self.assertEqual(result['facts']['vnindex_return_pct'],'0.5')
        self.assertFalse(result['facts']['benchmark_interval_verified'])
        self.assertIsNone(result['facts']['excess_return_pp'])

    def test_missing_previous_index_date_is_not_verified(self):
        result=fact_sheet(self.rows(),[{'tradingDate':'2026/11/04','indexChangePercentage':'0.5'}])
        self.assertFalse(result['facts']['benchmark_interval_verified'])
        self.assertIsNone(result['facts']['excess_return_pp'])

    def test_same_return_horizon_can_be_compared(self):
        result=fact_sheet(self.rows(),[{'tradingDate':'2026/10/29','indexChangePercentage':'0'}, {'tradingDate':'2026/11/04','indexChangePercentage':'0.5'}])
        self.assertTrue(result['facts']['benchmark_interval_verified'])
        self.assertEqual(result['facts']['excess_return_pp'],'1.5')

    def test_current_volume_does_not_change_baseline_statistics(self):
        prior=[{'symbol':'TEST','date':f'2026-10-{day:02}','volume_shares':str(day)} for day in range(1,25)]
        first=fact_sheet(prior+[{'symbol':'TEST','date':'2026-11-04','volume_shares':'100'}])['facts']
        second=fact_sheet(prior+[{'symbol':'TEST','date':'2026-11-04','volume_shares':'10000'}])['facts']
        self.assertEqual(first['median_volume'],second['median_volume'])
        self.assertEqual(first['mad_volume'],second['mad_volume'])
        self.assertEqual(first['prior_observations'],24)
