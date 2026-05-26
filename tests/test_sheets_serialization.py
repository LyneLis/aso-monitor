from sheets.serialization import parse_json_list, storage_key, tracked_info_from_row, tracked_info_to_apps_row
from sheets.streamlit_repo import StreamlitAppsRepository


def test_parse_json_list_default():
    assert parse_json_list(None) == []
    assert parse_json_list('["a"]') == ["a"]


def test_tracked_info_from_row():
    info = tracked_info_from_row("com.app", "en-US", "123", title="T")
    assert info is not None
    assert info["package_id"] == "com.app"
    assert storage_key(info) == "com.app_en-US_123"


def test_tracked_info_skips_invalid():
    assert tracked_info_from_row("", "en-US") is None
    assert tracked_info_from_row("com.app", "nan") is None


def test_tracked_info_to_apps_row_roundtrip():
    info = tracked_info_from_row("com.app", "us", "1", title="A", screenshots='["s"]')
    row = tracked_info_to_apps_row(info)
    assert row["package_id"] == "com.app"
    assert '"s"' in row["screenshots"]


def test_streamlit_repo_save_records_error():
    class BadConnection:
        def update(self, worksheet, data):
            raise RuntimeError("save failed")

    repo = StreamlitAppsRepository(BadConnection(), True)
    info = tracked_info_from_row("com.app", "us", "1", title="A")

    assert repo.save_apps({"com.app_us_1": info}) is False
    assert repo.last_error == "save failed"


def test_streamlit_repo_save_records_missing_connection():
    repo = StreamlitAppsRepository(None, False)

    assert repo.save_apps({}) is False
    assert repo.last_error == "Нет подключения к Google Sheets."
