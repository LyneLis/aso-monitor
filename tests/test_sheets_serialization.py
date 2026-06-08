import pandas as pd

from sheets.serialization import parse_json_list, storage_key, tracked_info_from_row, tracked_info_to_apps_row
from sheets.streamlit_repo import StreamlitAppsRepository


def test_parse_json_list_default():
    assert parse_json_list(None) == []
    assert parse_json_list('["a"]') == ["a"]


def test_tracked_info_from_row():
    info = tracked_info_from_row(
        "com.app",
        "en-US",
        "123",
        title="T",
        publisher="Studio",
        icon_hash="pxsha256:abc",
    )
    assert info is not None
    assert info["package_id"] == "com.app"
    assert info["current"]["publisher"] == "Studio"
    assert info["current"]["icon_hash"] == "pxsha256:abc"
    assert storage_key(info) == "com.app_en-US_123"


def test_tracked_info_from_row_normalizes_package_id():
    info = tracked_info_from_row(
        "com.playrix.gardenscapes&pcampaignid=promo&hl=ru",
        "en-US",
        "123",
    )

    assert info["package_id"] == "com.playrix.gardenscapes"
    assert storage_key(info) == "com.playrix.gardenscapes_en-US_123"


def test_tracked_info_skips_invalid():
    assert tracked_info_from_row("", "en-US") is None
    assert tracked_info_from_row("com.app", "nan") is None


def test_tracked_info_to_apps_row_roundtrip():
    info = tracked_info_from_row("com.app", "us", "1", title="A", screenshots='["s"]')
    row = tracked_info_to_apps_row(info)
    assert row["package_id"] == "com.app"
    assert "publisher" in row
    assert "icon_hash" in row
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


def test_streamlit_repo_load_users_records_error():
    class BadConnection:
        def read(self, worksheet, ttl):
            assert worksheet == "users"
            raise RuntimeError("users read failed")

    repo = StreamlitAppsRepository(BadConnection(), True)

    assert repo.load_users() == {}
    assert repo.load_errors == {"users": "users read failed"}
    assert repo.load_error_message() == "users: users read failed"


def test_streamlit_repo_load_apps_records_error():
    class BadConnection:
        def read(self, worksheet, ttl):
            assert worksheet == "apps"
            raise RuntimeError("apps read failed")

    repo = StreamlitAppsRepository(BadConnection(), True)

    assert repo.load_apps() == {}
    assert repo.load_errors == {"apps": "apps read failed"}
    assert repo.load_error_message() == "apps: apps read failed"


def test_streamlit_repo_load_apps_clears_previous_error():
    info = tracked_info_from_row("com.app", "us", "1", title="A")

    class Connection:
        def __init__(self):
            self.fail = True

        def read(self, worksheet, ttl):
            assert worksheet == "apps"
            if self.fail:
                raise RuntimeError("temporary read failed")
            return pd.DataFrame([tracked_info_to_apps_row(info)])

    conn = Connection()
    repo = StreamlitAppsRepository(conn, True)

    assert repo.load_apps() == {}
    assert "apps" in repo.load_errors

    conn.fail = False
    assert repo.load_apps()["com.app_us_1"]["current"]["title"] == "A"
    assert repo.load_errors == {}


def test_streamlit_repo_save_merges_updated_keys_with_latest_sheet():
    remote_existing = tracked_info_from_row("com.app", "us", "1", title="Remote title", summary="Fresh")
    stale_existing = tracked_info_from_row("com.app", "us", "1", title="Local stale", summary="Old")
    added = tracked_info_from_row("com.new", "us", "1", title="New app")

    class Connection:
        def __init__(self):
            self.updated = None

        def read(self, worksheet, ttl):
            assert worksheet == "apps"
            assert ttl == 0
            return pd.DataFrame([tracked_info_to_apps_row(remote_existing)])

        def update(self, worksheet, data):
            assert worksheet == "apps"
            self.updated = data

    conn = Connection()
    repo = StreamlitAppsRepository(conn, True)

    assert repo.save_apps(
        {
            "com.app_us_1": stale_existing,
            "com.new_us_1": added,
        },
        updated_keys={"com.new_us_1"},
    )

    rows = conn.updated.to_dict("records")
    by_package = {row["package_id"]: row for row in rows}
    assert by_package["com.app"]["title"] == "Remote title"
    assert by_package["com.app"]["summary"] == "Fresh"
    assert by_package["com.new"]["title"] == "New app"


def test_streamlit_repo_cached_save_merges_updates_without_reads():
    existing = tracked_info_from_row("com.app", "us", "1", title="Existing app")
    first_update = tracked_info_from_row("com.one", "us", "1", title="First update")
    second_update = tracked_info_from_row("com.two", "us", "1", title="Second update")

    class Connection:
        def __init__(self):
            self.read_count = 0
            self.updates = []

        def read(self, worksheet, ttl):
            self.read_count += 1
            raise AssertionError("cached save should not read apps")

        def update(self, worksheet, data):
            assert worksheet == "apps"
            self.updates.append(data.to_dict("records"))

    conn = Connection()
    repo = StreamlitAppsRepository(conn, True)
    initial_data = {"com.app_us_1": existing}

    with repo.cached_save(initial_data):
        first_data = {
            "com.app_us_1": existing,
            "com.one_us_1": first_update,
        }
        second_data = {
            "com.app_us_1": existing,
            "com.one_us_1": first_update,
            "com.two_us_1": second_update,
        }

        assert repo.save_apps(first_data, updated_keys={"com.one_us_1"})
        assert repo.save_apps(second_data, updated_keys={"com.two_us_1"})

    final_rows = {row["package_id"]: row for row in conn.updates[-1]}
    assert conn.read_count == 0
    assert final_rows["com.app"]["title"] == "Existing app"
    assert final_rows["com.one"]["title"] == "First update"
    assert final_rows["com.two"]["title"] == "Second update"
