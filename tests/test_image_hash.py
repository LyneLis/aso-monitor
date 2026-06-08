from io import BytesIO

from PIL import Image

from core.compare import AppSnapshot
from core.image_hash import ensure_icon_hashes, icon_pixel_hash_from_bytes


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
