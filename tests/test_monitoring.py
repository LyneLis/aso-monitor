from core.compare import AppSnapshot
from core.monitoring import add_changed_locale_to_batch, check_item_snapshots


def test_check_item_snapshots_uses_fetcher_and_detects_change():
    old = AppSnapshot(title="Old", summary="S", description="D")

    def fetcher(package_id, geo):
        assert package_id == "com.test.app"
        assert geo == "us"
        return {
            "title": "New",
            "summary": "S",
            "description": "D",
            "icon": "",
            "headerImage": "",
            "screenshots": [],
        }

    outcome = check_item_snapshots(
        "com.test.app",
        "us",
        old,
        [],
        False,
        label_style="web",
        fetcher=fetcher,
    )

    assert outcome.updates == 1
    assert outcome.changed == ["Title"]
    assert outcome.text_payload["old_t"] == "Old"
    assert outcome.new_snapshot.title == "New"


def test_add_changed_locale_to_batch_collects_texts_and_visuals():
    batched = {}
    old = AppSnapshot(icon="old-icon", header_image="old-header", screenshots=["old-screen"])
    new = AppSnapshot(icon="new-icon", header_image="new-header", screenshots=["new-screen"])
    text_payload = {"old_t": "Old", "new_t": "New"}

    add_changed_locale_to_batch(
        batched,
        "com.test.app",
        "123",
        "us",
        old,
        new,
        ["Иконка", "Feature Graphic", "Скриншоты"],
        text_payload,
        is_rollback=True,
    )

    batch = batched[("com.test.app", "123", False)]
    assert batch["changes"]["us"] == ["Иконка", "Feature Graphic", "Скриншоты"]
    assert batch["texts"]["us"] == text_payload
    assert batch["is_rollback"] is True
    assert batch["visuals"] == [
        {"type": "diff", "name": "Иконка", "old": "old-icon", "new": "new-icon", "geo": "us"},
        {
            "type": "diff",
            "name": "Feature Graphic",
            "old": "old-header",
            "new": "new-header",
            "geo": "us",
        },
        {"type": "screens", "screens": ["new-screen"], "geo": "us"},
    ]


def test_add_changed_locale_to_batch_skips_empty_screenshot_visuals():
    batched = {}

    add_changed_locale_to_batch(
        batched,
        "com.test.app",
        "123",
        "us",
        AppSnapshot(),
        AppSnapshot(screenshots=[]),
        ["Скриншоты"],
    )

    assert batched[("com.test.app", "123", False)]["visuals"] == []
