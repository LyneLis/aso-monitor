from io import BytesIO

from PIL import Image

from core.compare import AppSnapshot
from core.image_hash import (
    ensure_header_image_hashes,
    ensure_icon_hashes,
    ensure_screenshot_hashes,
    icon_pixel_hash_from_bytes,
    visual_hash_from_bytes,
    visual_hashes_match,
)


def make_png(color, size=(96, 96)):
    output = BytesIO()
    Image.new("RGBA", size, color).save(output, format="PNG")
    return output.getvalue()


def test_icon_pixel_hash_is_stable_for_same_pixels():
    first = icon_pixel_hash_from_bytes(make_png((10, 20, 30, 255)))
    second = icon_pixel_hash_from_bytes(make_png((10, 20, 30, 255)))

    assert first.startswith("pxsha256:")
    assert first == second


def test_icon_pixel_hash_changes_for_different_pixels():
    first = icon_pixel_hash_from_bytes(make_png((10, 20, 30, 255)))
    second = icon_pixel_hash_from_bytes(make_png((10, 20, 31, 255)))

    assert first != second


def test_visual_hash_is_stable_for_same_pixels():
    first = visual_hash_from_bytes(make_png((10, 20, 30, 255)))
    second = visual_hash_from_bytes(make_png((10, 20, 30, 255)))

    assert first.startswith("vhash64:")
    assert first == second


def test_visual_hash_match_allows_small_distance():
    assert visual_hashes_match("vhash64:0000000000000000", "vhash64:0000000000000003", max_distance=2)
    assert not visual_hashes_match("vhash64:0000000000000000", "vhash64:0000000000000007", max_distance=2)


def test_ensure_icon_hashes_fetches_old_and_new_when_urls_differ():
    old = AppSnapshot(icon="https://cdn.example.com/old.jpg")
    new = AppSnapshot(icon="https://cdn.example.com/new.jpg")
    calls = []

    def fake_hash_fetcher(url):
        calls.append(url)
        return "pxsha256:same"

    ensure_icon_hashes(old, new, hash_fetcher=fake_hash_fetcher)

    assert calls == ["https://cdn.example.com/old.jpg", "https://cdn.example.com/new.jpg"]
    assert old.icon_hash == "pxsha256:same"
    assert new.icon_hash == "pxsha256:same"


def test_ensure_header_image_hashes_fetches_old_and_new_when_urls_differ():
    old = AppSnapshot(header_image="https://cdn.example.com/old-fg.jpg")
    new = AppSnapshot(header_image="https://cdn.example.com/new-fg.jpg")
    calls = []

    def fake_hash_fetcher(url):
        calls.append(url)
        return "pxsha256:same"

    ensure_header_image_hashes(old, new, hash_fetcher=fake_hash_fetcher)

    assert calls == ["https://cdn.example.com/old-fg.jpg", "https://cdn.example.com/new-fg.jpg"]
    assert old.header_image_hash == "pxsha256:same"
    assert new.header_image_hash == "pxsha256:same"


def test_ensure_screenshot_hashes_fetches_lists_when_urls_differ():
    old = AppSnapshot(screenshots=["https://cdn.example.com/old-a.jpg", "https://cdn.example.com/old-b.jpg"])
    new = AppSnapshot(screenshots=["https://cdn.example.com/new-a.jpg", "https://cdn.example.com/new-b.jpg"])
    calls = []

    def fake_hash_fetcher(url):
        calls.append(url)
        return f"pxsha256:{url.rsplit('/', 1)[-1]}"

    ensure_screenshot_hashes(old, new, hash_fetcher=fake_hash_fetcher)

    assert calls == [
        "https://cdn.example.com/old-a.jpg",
        "https://cdn.example.com/old-b.jpg",
        "https://cdn.example.com/new-a.jpg",
        "https://cdn.example.com/new-b.jpg",
    ]
    assert old.screenshot_hashes == ["pxsha256:old-a.jpg", "pxsha256:old-b.jpg"]
    assert new.screenshot_hashes == ["pxsha256:new-a.jpg", "pxsha256:new-b.jpg"]
