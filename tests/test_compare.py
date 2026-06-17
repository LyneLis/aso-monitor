from core.compare import (
    AppSnapshot,
    clean_val,
    detect_changes,
    detect_changes_with_table_error,
    fill_missing_assets,
)


def test_clean_val_error():
    assert clean_val("#N/A") == ""
    assert clean_val("#ERROR!") is None


def test_detect_changes_web_title():
    old = AppSnapshot(title="A", summary="s", description="d")
    new = AppSnapshot(title="B", summary="s", description="d")
    r = detect_changes(old, new, [], label_style="web")
    assert r.has_changes
    assert "Title" in r.changed
    assert r.text_payload["old_t"] == "A"


def test_detect_changes_bot_ios_subtitle():
    old = AppSnapshot(title="A", summary="s1", description="d")
    new = AppSnapshot(title="A", summary="s2", description="d")
    r = detect_changes(old, new, [], label_style="bot", is_ios=True)
    assert "Subtitle" in r.changed


def test_rollback_web():
    old = AppSnapshot(title="Live", summary="B", description="C")
    new = AppSnapshot(title="Past", summary="BP", description="CP")
    history = [{"title": "Past", "summary": "BP", "description": "CP"}]
    r = detect_changes(old, new, history, label_style="web")
    assert r.is_rollback


def test_detect_changes_ignores_icon_url_change_when_pixel_hash_matches():
    old = AppSnapshot(icon="https://cdn.example.com/icon-v1.jpg", icon_hash="pxsha256:same")
    new = AppSnapshot(icon="https://cdn.example.com/icon-v2.jpg", icon_hash="pxsha256:same")

    r = detect_changes(old, new, [], label_style="bot")

    assert "Иконка" not in r.changed


def test_detect_changes_reports_icon_change_when_pixel_hash_differs():
    old = AppSnapshot(icon="https://cdn.example.com/icon-v1.jpg", icon_hash="pxsha256:old")
    new = AppSnapshot(icon="https://cdn.example.com/icon-v2.jpg", icon_hash="pxsha256:new")

    r = detect_changes(old, new, [], label_style="bot")

    assert "Иконка" in r.changed


def test_detect_changes_ignores_feature_graphic_url_change_when_pixel_hash_matches():
    old = AppSnapshot(
        header_image="https://cdn.example.com/fg-v1.jpg",
        header_image_hash="pxsha256:same",
    )
    new = AppSnapshot(
        header_image="https://cdn.example.com/fg-v2.jpg",
        header_image_hash="pxsha256:same",
    )

    r = detect_changes(old, new, [], label_style="bot")

    assert "Feature Graphic" not in r.changed


def test_detect_changes_reports_feature_graphic_change_when_pixel_hash_differs():
    old = AppSnapshot(
        header_image="https://cdn.example.com/fg-v1.jpg",
        header_image_hash="pxsha256:old",
    )
    new = AppSnapshot(
        header_image="https://cdn.example.com/fg-v2.jpg",
        header_image_hash="pxsha256:new",
    )

    r = detect_changes(old, new, [], label_style="bot")

    assert "Feature Graphic" in r.changed


def test_detect_changes_ignores_feature_graphic_when_visual_hash_is_close():
    old = AppSnapshot(
        header_image="https://cdn.example.com/fg-v1.jpg",
        header_image_hash="vhash64:0000000000000000",
    )
    new = AppSnapshot(
        header_image="https://cdn.example.com/fg-v2.jpg",
        header_image_hash="vhash64:0000000000000003",
    )

    r = detect_changes(old, new, [], label_style="bot")

    assert "Feature Graphic" not in r.changed


def test_detect_changes_reports_feature_graphic_when_visual_hash_is_far():
    old = AppSnapshot(
        header_image="https://cdn.example.com/fg-v1.jpg",
        header_image_hash="vhash64:0000000000000000",
    )
    new = AppSnapshot(
        header_image="https://cdn.example.com/fg-v2.jpg",
        header_image_hash="vhash64:ffffffffffffffff",
    )

    r = detect_changes(old, new, [], label_style="bot")

    assert "Feature Graphic" in r.changed


def test_detect_changes_ignores_screenshot_url_change_when_pixel_hashes_match():
    old = AppSnapshot(
        screenshots=["https://cdn.example.com/screen-a-v1.jpg", "https://cdn.example.com/screen-b-v1.jpg"],
        screenshot_hashes=["pxsha256:a", "pxsha256:b"],
    )
    new = AppSnapshot(
        screenshots=["https://cdn.example.com/screen-a-v2.jpg", "https://cdn.example.com/screen-b-v2.jpg"],
        screenshot_hashes=["pxsha256:a", "pxsha256:b"],
    )

    r = detect_changes(old, new, [], label_style="bot")

    assert "Скриншоты" not in r.changed


def test_detect_changes_ignores_screenshot_when_visual_hashes_are_close():
    old = AppSnapshot(
        screenshots=["https://cdn.example.com/screen-v1.jpg"],
        screenshot_hashes=["vhash64:0000000000000000"],
    )
    new = AppSnapshot(
        screenshots=["https://cdn.example.com/screen-v2.jpg"],
        screenshot_hashes=["vhash64:0000000000000007"],
    )

    r = detect_changes(old, new, [], label_style="bot")

    assert "Скриншоты" not in r.changed


def test_detect_changes_reports_screenshot_change_when_pixel_hashes_differ():
    old = AppSnapshot(
        screenshots=["https://cdn.example.com/screen-a-v1.jpg"],
        screenshot_hashes=["pxsha256:a"],
    )
    new = AppSnapshot(
        screenshots=["https://cdn.example.com/screen-a-v2.jpg"],
        screenshot_hashes=["pxsha256:b"],
    )

    r = detect_changes(old, new, [], label_style="bot")

    assert "Скриншоты" in r.changed


def test_table_error_skips_diff():
    old = AppSnapshot()
    new = AppSnapshot(title="T", summary="S", description="D")
    r = detect_changes_with_table_error(old, new, [], is_table_error=True, label_style="web")
    assert r.is_table_error
    assert not r.has_changes


def test_fill_missing_assets():
    current = {"icon": "nan", "screenshots": []}
    fill_missing_assets(current, AppSnapshot(icon="http://i", screenshots=["s1"]))
    assert current["icon"] == "http://i"
    assert current["screenshots"] == ["s1"]


def test_fill_missing_assets_refreshes_equivalent_icon_url_and_hash():
    current = {"icon": "https://cdn.example.com/icon-v1.jpg", "icon_hash": "pxsha256:same"}

    fill_missing_assets(
        current,
        AppSnapshot(icon="https://cdn.example.com/icon-v2.jpg", icon_hash="pxsha256:same"),
    )

    assert current["icon"] == "https://cdn.example.com/icon-v2.jpg"
    assert current["icon_hash"] == "pxsha256:same"


def test_fill_missing_assets_refreshes_equivalent_feature_graphic_and_screenshots():
    current = {
        "header_image": "https://cdn.example.com/fg-v1.jpg",
        "header_image_hash": "pxsha256:fg",
        "screenshots": ["https://cdn.example.com/screen-v1.jpg"],
        "screenshot_hashes": ["pxsha256:screen"],
    }

    fill_missing_assets(
        current,
        AppSnapshot(
            header_image="https://cdn.example.com/fg-v2.jpg",
            header_image_hash="pxsha256:fg",
            screenshots=["https://cdn.example.com/screen-v2.jpg"],
            screenshot_hashes=["pxsha256:screen"],
        ),
    )

    assert current["header_image"] == "https://cdn.example.com/fg-v2.jpg"
    assert current["header_image_hash"] == "pxsha256:fg"
    assert current["screenshots"] == ["https://cdn.example.com/screen-v2.jpg"]
    assert current["screenshot_hashes"] == ["pxsha256:screen"]
