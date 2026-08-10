from datetime import datetime, timezone
from unittest.mock import patch

from base import api_monitor


def test_daily_limit_is_higher_on_beijing_monday():
    monitor = api_monitor.ApiCallMonitor.__new__(api_monitor.ApiCallMonitor)
    with patch.object(
        api_monitor,
        "_bj_now",
        return_value=datetime(2026, 8, 10, tzinfo=timezone.utc),
    ):
        assert monitor._daily_limit() == 10000


def test_daily_limit_is_5000_on_non_monday():
    monitor = api_monitor.ApiCallMonitor.__new__(api_monitor.ApiCallMonitor)
    with patch.object(
        api_monitor,
        "_bj_now",
        return_value=datetime(2026, 8, 11, tzinfo=timezone.utc),
    ):
        assert monitor._daily_limit() == 5000


def test_only_explicit_bypass_ignores_hard_limit():
    with patch.object(api_monitor.monitor, "check_allowed", return_value=False):
        assert not api_monitor.check_api_allowed()
        assert api_monitor.check_api_allowed(ignore_hard_limit=True)
