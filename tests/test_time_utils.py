from datetime import UTC, datetime

from core.time_utils import current_minsk_datetime


def test_current_minsk_datetime_uses_utc_plus_three():
    now_utc = datetime(2026, 5, 31, 21, 15, 30, tzinfo=UTC)

    assert current_minsk_datetime(now_utc) == datetime(2026, 6, 1, 0, 15, 30)
