from sheets.serialization import parse_json_list, storage_key, tracked_info_from_row, tracked_info_to_apps_row


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
