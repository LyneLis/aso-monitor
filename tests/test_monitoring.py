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


def test_check_item_snapshots_uses_icon_hash_to_ignore_cdn_url_noise():
    old = AppSnapshot(
        title="App",
        summary="S",
        description="D",
        icon="https://cdn.example.com/icon-v1.jpg",
        icon_hash="pxsha256:same",
    )

    def fetcher(package_id, geo):
        return {
            "title": "App",
            "summary": "S",
            "description": "D",
            "icon": "https://cdn.example.com/icon-v2.jpg",
            "iconHash": "pxsha256:same",
            "headerImage": "",
            "screenshots": [],
        }

    outcome = check_item_snapshots(
        "com.test.app",
        "us",
        old,
        [],
        False,
        label_style="bot",
        fetcher=fetcher,
    )

    assert outcome.changed == []
    assert outcome.new_snapshot.icon_hash == "pxsha256:same"


def test_check_item_snapshots_preserves_ios_summary_when_web_subtitle_unavailable():
    old = AppSnapshot(title="App", summary="Sous-titre", description="Description")

    def fetcher(package_id, geo):
        return {
            "title": "App",
            "summary": "",
            "summary_unavailable": True,
            "description": "Description",
            "icon": "",
            "headerImage": "",
            "screenshots": [],
        }

    outcome = check_item_snapshots(
        "123456789",
        "fr-CA",
        old,
        [],
        False,
        label_style="bot",
        fetcher=fetcher,
    )

    assert outcome.new_snapshot.summary == "Sous-titre"
    assert outcome.changed == []


def test_check_item_snapshots_clears_invalid_ios_summary_when_web_subtitle_unavailable():
    old = AppSnapshot(title="App", summary="कार्ड", description="Description")

    def fetcher(package_id, geo):
        return {
            "title": "App",
            "summary": "",
            "summary_unavailable": True,
            "description": "Description",
            "icon": "",
            "headerImage": "",
            "screenshots": [],
        }

    outcome = check_item_snapshots(
        "123456789",
        "hi-IN",
        old,
        [],
        False,
        label_style="bot",
        fetcher=fetcher,
    )

    assert outcome.new_snapshot.summary == ""
    assert outcome.changed == ["Subtitle"]


def test_check_item_snapshots_preserves_ios_screenshots_when_web_assets_unavailable():
    old = AppSnapshot(
        title="App",
        summary="Subtitle",
        description="Description",
        screenshots=["https://example.com/old-screen.jpg"],
    )

    def fetcher(package_id, geo):
        return {
            "title": "App",
            "summary": "Subtitle",
            "description": "Description",
            "icon": "",
            "headerImage": "",
            "screenshots": ["https://example.com/fallback-screen.jpg"],
            "screenshots_unavailable": True,
        }

    outcome = check_item_snapshots(
        "123456789",
        "en-US",
        old,
        [],
        False,
        label_style="bot",
        fetcher=fetcher,
    )

    assert outcome.new_snapshot.screenshots == ["https://example.com/old-screen.jpg"]
    assert "Скриншоты" not in outcome.changed


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
        {"type": "screens", "old": ["old-screen"], "new": ["new-screen"], "geo": "us"},
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


def test_add_changed_locale_to_batch_stores_display_name():
    batched = {}

    add_changed_locale_to_batch(
        batched,
        "com.test.app",
        "123",
        "en-US",
        AppSnapshot(),
        AppSnapshot(title="New"),
        ["Title"],
        app_display_name="English Title (Studio)",
    )

    assert batched[("com.test.app", "123", False)]["app_display_name"] == "English Title (Studio)"
