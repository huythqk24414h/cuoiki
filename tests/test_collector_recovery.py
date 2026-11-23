import unittest
from datetime import datetime
from unittest.mock import patch
from scripts.reconcile_collectors import VN, active, reconcile


class CollectorRecoveryTests(unittest.TestCase):
    def test_missing_afternoon_starts_capture_and_both_chart_collectors(self):
        with patch("scripts.reconcile_collectors.active", return_value=False), patch("scripts.reconcile_collectors.github", return_value={"workflow_runs":[]}) as dispatch:
            started = reconcile(datetime(2026,11,18,13,20,tzinfo=VN))
        self.assertEqual(started, ["ssi-live-capture.yml", "ssi-intraday.yml", "ssi-intraday-index-board.yml"])
        requests = [call for call in dispatch.call_args_list if len(call.args) == 2]
        self.assertEqual(requests[0].args[1]["inputs"], {"session":"afternoon"})
        self.assertTrue(requests[1].args[1]["inputs"]["follow_session"])

    def test_active_collectors_are_preserved(self):
        with patch("scripts.reconcile_collectors.active", return_value=True), patch("scripts.reconcile_collectors.github", return_value={"workflow_runs":[]}) as dispatch:
            self.assertEqual(reconcile(datetime(2026,11,18,10,20,tzinfo=VN)), [])
            dispatch.assert_not_called()

    def test_skip_nights_weekends_and_morning_charts_before_open(self):
        with patch("scripts.reconcile_collectors.active", return_value=False), patch("scripts.reconcile_collectors.github", return_value={"workflow_runs":[]}) as dispatch:
            self.assertEqual(reconcile(datetime(2026,11,21,10,tzinfo=VN)), [])
            self.assertEqual(reconcile(datetime(2026,11,18,20,tzinfo=VN)), [])
            self.assertEqual(reconcile(datetime(2026,11,18,8,tzinfo=VN)), ["ssi-live-capture.yml"])
            self.assertEqual(sum(len(call.args) == 2 for call in dispatch.call_args_list), 1)

    def test_an_afternoon_waiter_does_not_hide_a_missing_morning_capture(self):
        def reply(path):
            if "status=in_progress" in path:
                return {"workflow_runs":[{"id":1}]}
            if "/jobs?" in path:
                return {"jobs":[{"name":"morning","status":"completed"},{"name":"afternoon","status":"in_progress"}]}
            return {"workflow_runs":[]}
        with patch("scripts.reconcile_collectors.github", side_effect=reply):
            self.assertFalse(active("ssi-live-capture.yml", "morning"))
            self.assertTrue(active("ssi-live-capture.yml", "afternoon"))

    def test_failed_collector_has_a_ten_minute_retry_delay(self):
        failed={"workflow_runs":[{"conclusion":"failure","updated_at":"2026-11-18T01:59:00Z"}]}
        with patch("scripts.reconcile_collectors.active", return_value=False), patch("scripts.reconcile_collectors.github", return_value=failed) as dispatch:
            self.assertEqual(reconcile(datetime(2026,11,18,9,0,tzinfo=VN)), [])
            self.assertTrue(all(len(call.args) == 1 for call in dispatch.call_args_list))

    def test_chart_watch_recovers_charts_without_dispatching_order_book(self):
        with patch("scripts.reconcile_collectors.active", return_value=False), patch("scripts.reconcile_collectors.github", return_value={"workflow_runs":[]}) as request:
            started = reconcile(datetime(2026,11,24,9,20,tzinfo=VN), charts_only=True)
        self.assertEqual(started, ["ssi-intraday.yml", "ssi-intraday-index-board.yml"])
        self.assertTrue(all("ssi-live-capture" not in call.args[0] for call in request.call_args_list))
