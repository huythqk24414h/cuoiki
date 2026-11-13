"""Launcher tests never open a browser or create a real server."""
import unittest
from unittest.mock import patch, MagicMock
import launch


class LauncherTests(unittest.TestCase):
    def test_starts_before_opening_and_cleans_up(self):
        events = []
        server, thread = MagicMock(), MagicMock()
        thread.start.side_effect = lambda: events.append('started')
        with patch.object(launch, 'ThreadingHTTPServer', return_value=server), \
             patch.object(launch, 'start_live_stream'), patch.object(launch.LIVE, 'stop'), \
             patch.object(launch.threading, 'Thread', return_value=thread), \
             patch.object(launch.webbrowser, 'open', side_effect=lambda url: events.append(url) or True):
            launch.launch()
        self.assertEqual(events, ['started', launch.URL])
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()

    def test_second_click_opens_existing_app(self):
        with patch.object(launch, 'ThreadingHTTPServer', side_effect=OSError), \
             patch.object(launch, 'existing_app', return_value=True), \
             patch.object(launch.webbrowser, 'open') as browser:
            launch.launch()
        browser.assert_called_once_with(launch.URL)

    def test_occupied_port_never_opens_unknown_app(self):
        with patch.object(launch, 'ThreadingHTTPServer', side_effect=OSError), \
             patch.object(launch, 'existing_app', return_value=False), \
             patch.object(launch.webbrowser, 'open') as browser:
            with self.assertRaises(RuntimeError):
                launch.launch()
        browser.assert_not_called()
