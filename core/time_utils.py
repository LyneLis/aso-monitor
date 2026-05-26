from datetime import datetime, timedelta


def get_minsk_time() -> str:
    return (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
