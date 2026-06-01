from datetime import UTC, datetime, timedelta


MINSK_UTC_OFFSET = timedelta(hours=3)
DISPLAY_TIME_FORMAT = "%d.%m.%Y %H:%M:%S"


def current_minsk_datetime(now_utc: datetime | None = None) -> datetime:
    base_time = now_utc or datetime.now(UTC)
    if base_time.tzinfo is None:
        base_time = base_time.replace(tzinfo=UTC)
    return (base_time.astimezone(UTC) + MINSK_UTC_OFFSET).replace(tzinfo=None)


def get_minsk_time() -> str:
    return current_minsk_datetime().strftime(DISPLAY_TIME_FORMAT)
