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
