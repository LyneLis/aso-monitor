from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import gspread
import pandas as pd
import pytest
import requests

from sheets.serialization import APP_HEADERS, storage_key, tracked_info_from_row, tracked_info_to_apps_row
from sheets.streamlit_repo import StreamlitAppsRepository


def make_info(package_id="com.example.app", title="Original"):
    return tracked_info_from_row(package_id, "en-US", "123", title=title, summary="Summary")


def as_data(*infos):
    return {storage_key(info): info for info in infos}


class MemoryConnection:
    """Simulate the value-only Sheets batch contract, including an ambiguous timeout."""

    def __init__(self, *infos, row_count=20, col_count=20):
        self.id = 17
        self.row_count = row_count
        self.col_count = col_count
        rows = [tracked_info_to_apps_row(info) for info in infos]
        self.values = [list(APP_HEADERS)] + [list(row.values()) for row in rows]
        self.client = self
        self.spreadsheet = self
        self.batches = []
        self.read_count = 0
        self.fail_before_commit = False
        self.fail_after_commit = False
        self.formatting = {"A1": {"bold": True}, "D2": {"wrap": True}}

    def _select_worksheet(self, *, worksheet):
        assert worksheet == "apps"
        return self

    def read(self, *, worksheet, ttl):
        if worksheet == "users":
            return pd.DataFrame([{"name": "Test user", "chat_id": "123"}])
        assert worksheet == "apps"
        assert ttl == 0
        self.read_count += 1
        headers = self.values[0]
        return pd.DataFrame(self.values[1:], columns=headers)

    def clear(self, *args, **kwargs):
        raise AssertionError("Standalone clearing must never be used")

    def update(self, *args, **kwargs):
        raise AssertionError("The connector's destructive update must never be used")

    def batch_update(self, body):
        self.batches.append(deepcopy(body))
        if self.fail_before_commit:
            self.fail_before_commit = False
            raise RuntimeError("429 Quota exceeded")

        row_count, col_count = self.row_count, self.col_count
        values = deepcopy(self.values)
        for operation in body["requests"]:
            if "appendDimension" in operation:
                request = operation["appendDimension"]
                assert request["sheetId"] == self.id
                assert request["length"] > 0
                if request["dimension"] == "ROWS":
                    row_count += request["length"]
                else:
                    assert request["dimension"] == "COLUMNS"
                    col_count += request["length"]
            else:
                request = operation["updateCells"]
                assert request["range"] == {"sheetId": self.id}
                assert request["fields"] == "userEnteredValue"
                assert "start" not in request
                values = [
                    [cell["userEnteredValue"]["stringValue"] for cell in row["values"]]
                    for row in request["rows"]
                ]
                assert len(values) <= row_count
                assert all(len(row) <= col_count for row in values)

        self.values = values
        self.row_count, self.col_count = row_count, col_count
        if self.fail_after_commit:
            self.fail_after_commit = False
            raise requests.Timeout("Response lost after the commit")
        return {"replies": [{} for _ in body["requests"]]}


def test_full_save_is_one_atomic_batch_and_roundtrips_all_fields():
    info = make_info()
    info["current"].update({
        "publisher": "Example Studio", "description": "Full description\nSecond line",
        "icon": "https://example.invalid/icon.png", "icon_hash": "pxsha256:abc",
        "header_image": "https://example.invalid/fg.png", "header_image_hash": "vhash64:abc",
        "screenshots": ["https://example.invalid/1.png"], "screenshot_hashes": ["vhash64:def"],
    })
    info["history"] = [{"title": "Previous"}]
    info["check_log"] = [{"time": "16.09.2026 12:00:00", "status": "Checked"}]
    info["ai_audit"] = "Saved audit"
    conn = MemoryConnection()
    repo = StreamlitAppsRepository(conn, True)

    assert repo.save_apps(as_data(info))
    assert len(conn.batches) == 1
    assert len(conn.batches[0]["requests"]) == 1
    saved = repo.load_apps()[storage_key(info)]
    assert tracked_info_to_apps_row(saved) == tracked_info_to_apps_row(info)


def test_deleting_middle_locale_removes_it_and_the_old_tail():
    first, second, third = [make_info(f"com.example.{index}") for index in range(3)]
    conn = MemoryConnection(first, second, third)
    repo = StreamlitAppsRepository(conn, True)

    assert repo.save_apps(as_data(first, third), deleted_keys={storage_key(second)})
    assert list(repo.load_apps()) == [storage_key(first), storage_key(third)]
    assert len(conn.values) == 3
    assert len(conn.batches) == 1


def test_full_replacement_removes_obsolete_columns_and_trailing_rows():
    first, second = make_info(), make_info("com.example.other")
    conn = MemoryConnection(first, second)
    conn.values[0].append("obsolete_column")
    conn.values[1].append("old value")
    conn.values[2].append("old value")
    formatting = deepcopy(conn.formatting)
    repo = StreamlitAppsRepository(conn, True)

    assert repo.save_apps(as_data(first))
    assert conn.values == [list(APP_HEADERS), list(tracked_info_to_apps_row(first).values())]
    assert conn.formatting == formatting


def test_deleting_last_locale_preserves_headers_and_allows_addition():
    first, added = make_info(), make_info("com.example.added")
    conn = MemoryConnection(first)
    repo = StreamlitAppsRepository(conn, True)

    assert repo.save_apps({}, deleted_keys={storage_key(first)})
    assert conn.values == [list(APP_HEADERS)]
    assert repo.load_apps() == {}
    assert repo.save_apps(as_data(added), updated_keys={storage_key(added)})
    assert list(repo.load_apps()) == [storage_key(added)]


def test_empty_full_save_clears_old_values_but_preserves_schema():
    conn = MemoryConnection(make_info())
    repo = StreamlitAppsRepository(conn, True)

    assert repo.save_apps({})
    assert conn.values == [list(APP_HEADERS)]
    assert len(conn.batches) == 1


def test_sheet_growth_is_in_the_same_batch_as_values():
    conn = MemoryConnection(row_count=1, col_count=2)
    conn.values = []
    repo = StreamlitAppsRepository(conn, True)
    infos = [make_info(f"com.example.{index}") for index in range(3)]

    assert repo.save_apps(as_data(*infos))
    assert len(conn.batches) == 1
    assert conn.row_count == 4
    assert conn.col_count == len(APP_HEADERS)
    assert len(conn.batches[0]["requests"]) == 3


@pytest.mark.parametrize("cached", [False, True])
def test_rate_limit_preserves_old_sheet_and_retry_keeps_other_rows(cached):
    first, other = make_info(), make_info("com.example.other")
    conn = MemoryConnection(first, other)
    repo = StreamlitAppsRepository(conn, True)
    if cached:
        repo.begin_cached_save(as_data(first, other))
    updated = deepcopy(first)
    updated["current"]["title"] = "Updated"
    old_values = deepcopy(conn.values)
    old_cache = deepcopy(repo._apps_save_cache)
    conn.fail_before_commit = True

    assert not repo.save_apps(as_data(updated), updated_keys={storage_key(updated)})
    assert repo.last_error == "429 Quota exceeded"
    assert conn.values == old_values
    assert repo._apps_save_cache == old_cache
    assert repo.save_apps(as_data(updated), updated_keys={storage_key(updated)})
    assert repo.last_error is None
    saved = repo.load_apps()
    assert saved[storage_key(first)]["current"]["title"] == "Updated"
    assert saved[storage_key(other)]["current"]["title"] == "Original"


@pytest.mark.parametrize("operation", ["add", "delete", "update"])
def test_retry_after_lost_response_is_idempotent(operation):
    first, other = make_info(), make_info("com.example.other")
    conn = MemoryConnection(first, other)
    repo = StreamlitAppsRepository(conn, True)
    data = as_data(first, other)
    if operation == "add":
        added = make_info("com.example.added")
        data.update(as_data(added))
        options = {"updated_keys": {storage_key(added)}}
    elif operation == "delete":
        data.pop(storage_key(first))
        options = {"deleted_keys": {storage_key(first)}}
    else:
        first["current"]["title"] = "Updated"
        options = {"updated_keys": {storage_key(first)}}
    conn.fail_after_commit = True

    assert not repo.save_apps(data, **options)
    committed = deepcopy(conn.values)
    assert repo.save_apps(data, **options)
    assert conn.values == committed
    assert set(repo.load_apps()) == set(data)


def test_growth_failure_does_not_resize_or_clear_existing_data():
    old = make_info()
    conn = MemoryConnection(old, row_count=2, col_count=len(APP_HEADERS))
    repo = StreamlitAppsRepository(conn, True)
    old_values = deepcopy(conn.values)
    conn.fail_before_commit = True

    assert not repo.save_apps(as_data(old, make_info("com.example.new")))
    assert conn.values == old_values
    assert conn.row_count == 2


def test_store_text_is_written_as_literal_text_including_formula_prefixes():
    info = make_info(title='=HYPERLINK("https://example.invalid", "Title")')
    info["chat_id"] = "-1001234567890123"
    info["current"]["description"] = "+text\n00123"
    conn = MemoryConnection()
    repo = StreamlitAppsRepository(conn, True)

    assert repo.save_apps(as_data(info))
    payload = conn.batches[0]["requests"][-1]["updateCells"]["rows"][1]["values"]
    assert all(set(cell["userEnteredValue"]) == {"stringValue"} for cell in payload)
    assert repo.load_apps()[storage_key(info)]["current"]["title"] == info["current"]["title"]
    assert conn.values[1][2] == info["chat_id"]


def test_incompatible_connection_fails_without_destructive_fallback():
    conn = SimpleNamespace(update=lambda **kwargs: pytest.fail("Unsafe fallback"))
    repo = StreamlitAppsRepository(conn, True)

    assert not repo.save_apps(as_data(make_info()))
    assert repo.last_error


def test_serialization_failure_does_not_issue_a_write():
    info = make_info()
    info["history"] = [object()]
    conn = MemoryConnection()
    repo = StreamlitAppsRepository(conn, True)

    assert not repo.save_apps(as_data(info))
    assert conn.batches == []


def test_real_gspread_adapter_sends_a_single_batch_request():
    api = SimpleNamespace(request=Mock(return_value=SimpleNamespace(json=lambda: {"replies": [{}]})))
    spreadsheet = gspread.Spreadsheet.__new__(gspread.Spreadsheet)
    spreadsheet.client = api
    spreadsheet._properties = {"id": "review-sheet"}
    worksheet = gspread.Worksheet(spreadsheet, {
        "sheetId": 17, "title": "apps", "gridProperties": {"rowCount": 100, "columnCount": 20},
    })
    select = Mock(return_value=worksheet)
    conn = SimpleNamespace(client=SimpleNamespace(_select_worksheet=select))
    repo = StreamlitAppsRepository(conn, True)

    assert repo.save_apps(as_data(make_info()))
    select.assert_called_once_with(worksheet="apps")
    api.request.assert_called_once()
    call = api.request.call_args
    assert call.args == ("post", "https://sheets.googleapis.com/v4/spreadsheets/review-sheet:batchUpdate")
    assert call.kwargs["json"]["requests"][0]["updateCells"]["range"] == {"sheetId": 17}


def test_pinned_streamlit_connector_selects_the_configured_apps_worksheet():
    connector = pytest.importorskip("streamlit_gsheets.gsheets_connection")
    worksheet = MemoryConnection()
    select = Mock(return_value=worksheet)
    spreadsheet = SimpleNamespace(worksheet=select)
    service_client = connector.GSheetsServiceAccountClient.__new__(connector.GSheetsServiceAccountClient)
    service_client._spreadsheet = "https://docs.google.com/spreadsheets/d/review-sheet/edit"
    service_client._worksheet = None
    service_client._client = SimpleNamespace(open_by_url=Mock(return_value=spreadsheet))
    repo = StreamlitAppsRepository(SimpleNamespace(client=service_client), True)

    assert repo.save_apps(as_data(make_info()))
    service_client._client.open_by_url.assert_called_once_with(url=service_client._spreadsheet)
    select.assert_called_once_with("apps")
    assert len(worksheet.batches) == 1


def test_site_buttons_add_check_and_delete_without_losing_other_apps(monkeypatch):
    testing = pytest.importorskip("streamlit.testing.v1")
    import core
    import core.parsing

    existing = make_info("com.example.existing")
    conn = MemoryConnection(existing)
    repo = StreamlitAppsRepository(conn, True)
    monkeypatch.setattr(core.Settings, "from_streamlit_secrets", lambda _: core.Settings())
    monkeypatch.setattr(StreamlitAppsRepository, "connect", lambda: repo)

    def fetcher(package_id, geo):
        return {"title": "New app", "summary": "Summary", "description": "", "screenshots": []}

    monkeypatch.setattr(core, "fetch_app_data", fetcher)
    monkeypatch.setattr(core.parsing, "fetch_app_data", fetcher)
    app = testing.AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15)
    app.run()
    assert not app.exception

    next(item for item in app.text_input if item.label == "Package ID / App ID").set_value("com.example.added")
    next(item for item in app.button if (item.key or "").startswith("FormSubmitter:add_app_preview_form-")).click().run()
    assert not app.exception
    app.selectbox[-1].select("Test user").run()
    next(item for item in app.button if item.label == "Добавить в мониторинг").click().run()
    assert not app.exception
    added_key = "com.example.added_en-US_123"
    assert set(repo.load_apps()) == {storage_key(existing), added_key}

    # Reload from Sheets after the add form removes its preview widgets on rerun.
    app = testing.AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    assert not app.exception
    app.button(key=f"btn_sng_{added_key}").click().run()
    assert not app.exception
    assert len(conn.batches) == 2
    assert repo.load_apps()[added_key]["check_log"]

    app.button(key=f"del_{added_key}").click().run()
    assert not app.exception
    assert added_key in repo.load_apps()
    app.button(key=f"del_yes_{added_key}").click().run()
    assert not app.exception
    assert list(repo.load_apps()) == [storage_key(existing)]


def test_site_group_check_saves_all_locales_in_one_batch(monkeypatch):
    testing = pytest.importorskip("streamlit.testing.v1")
    import core
    import core.parsing

    first, second, other = make_info(), make_info(), make_info("com.example.other")
    second["geo"] = "fr-CA"
    conn = MemoryConnection(first, second, other)
    repo = StreamlitAppsRepository(conn, True)
    monkeypatch.setattr(core.Settings, "from_streamlit_secrets", lambda _: core.Settings())
    monkeypatch.setattr(StreamlitAppsRepository, "connect", lambda: repo)
    fetcher = lambda *_: {"title": "Original", "summary": "Summary", "description": "", "screenshots": []}
    monkeypatch.setattr(core.parsing, "fetch_app_data", fetcher)
    app = testing.AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15)

    app.run()
    assert not app.exception
    app.button(key="ch_grp_com.example.app_123").click().run()
    assert not app.exception
    assert len(conn.batches) == 1
    saved = repo.load_apps()
    assert saved[storage_key(first)]["check_log"]
    assert saved[storage_key(second)]["check_log"]
    assert not saved[storage_key(other)]["check_log"]
