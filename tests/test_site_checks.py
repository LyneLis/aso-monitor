from core.site_checks import run_site_check_for_item


def make_info():
    return {
        "package_id": "com.test.app",
        "geo": "en-US",
        "current": {
            "title": "Old title",
            "summary": "Summary",
            "description": "Description",
            "developer": "Test Publisher",
            "icon": "",
            "header_image": "",
            "screenshots": [],
        },
        "history": [],
        "check_log": [],
    }


def test_run_site_check_for_item_updates_current_history_and_log():
    info = make_info()

    def fetcher(package_id, geo):
        assert package_id == "com.test.app"
        assert geo == "en-US"
        return {
            "title": "New title",
            "summary": "Summary",
            "description": "Description",
            "developer": "Test Publisher",
            "icon": "",
            "headerImage": "",
            "screenshots": [],
        }

    updates, changed, text_payload, outcome = run_site_check_for_item(info, item_key="row-1", fetcher=fetcher)

    assert updates == 1
    assert changed == ["Title"]
    assert text_payload["old_t"] == "Old title"
    assert outcome.new_snapshot.title == "New title"
    assert info["current"]["title"] == "New title"
    assert info["current"]["publisher"] == "Test Publisher"
    assert info["history"][0]["title"] == "Old title"
    assert "Изменение" in info["check_log"][-1]["status"]


def test_run_site_check_for_item_records_error_without_raising():
    info = make_info()

    def fetcher(package_id, geo):
        raise RuntimeError("network failed")

    updates, changed, text_payload, outcome = run_site_check_for_item(info, item_key="row-1", fetcher=fetcher)

    assert updates == 0
    assert changed == []
    assert text_payload is None
    assert outcome is None
    assert info["current"]["title"] == "Old title"
    assert info["check_log"][-1]["status"] == "❌ Ошибка"
