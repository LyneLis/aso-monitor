import hashlib
from io import BytesIO

import requests
from PIL import Image, ImageOps

ICON_HASH_SIZE = (128, 128)
VISUAL_HASH_SIZE = (9, 8)
IMAGE_HASH_PREFIX = "pxsha256"
ICON_HASH_PREFIX = IMAGE_HASH_PREFIX
VISUAL_HASH_PREFIX = "vhash64"
IMAGE_HASH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def image_pixel_hash_from_bytes(image_bytes: bytes, size: tuple[int, int]) -> str:
    with Image.open(BytesIO(image_bytes)) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGBA").resize(size, Image.Resampling.LANCZOS)

    digest = hashlib.sha256()
    digest.update(f"{normalized.mode}:{normalized.size[0]}x{normalized.size[1]}:".encode("ascii"))
    digest.update(normalized.tobytes())
    return f"{IMAGE_HASH_PREFIX}:{digest.hexdigest()}"


def icon_pixel_hash_from_bytes(image_bytes: bytes, size: tuple[int, int] = ICON_HASH_SIZE) -> str:
    return image_pixel_hash_from_bytes(image_bytes, size)


def visual_hash_from_bytes(image_bytes: bytes, size: tuple[int, int] = VISUAL_HASH_SIZE) -> str:
    with Image.open(BytesIO(image_bytes)) as image:
        normalized = ImageOps.exif_transpose(image).convert("L").resize(size, Image.Resampling.LANCZOS)

    pixels = list(normalized.tobytes())
    bits = []
    width, height = size
    for row in range(height):
        offset = row * width
        for col in range(width - 1):
            bits.append(1 if pixels[offset + col] > pixels[offset + col + 1] else 0)

    value = 0
    for bit in bits:
        value = (value << 1) | bit
    return f"{VISUAL_HASH_PREFIX}:{value:016x}"


def hash_distance(first_hash: str, second_hash: str) -> int | None:
    first_prefix, _, first_value = str(first_hash or "").partition(":")
    second_prefix, _, second_value = str(second_hash or "").partition(":")
    if first_prefix != VISUAL_HASH_PREFIX or second_prefix != VISUAL_HASH_PREFIX:
        return None
    try:
        return (int(first_value, 16) ^ int(second_value, 16)).bit_count()
    except ValueError:
        return None


def visual_hashes_match(first_hash: str, second_hash: str, *, max_distance: int = 6) -> bool:
    distance = hash_distance(first_hash, second_hash)
    if distance is None:
        return bool(first_hash and second_hash and first_hash == second_hash)
    return distance <= max_distance


def fetch_image_hash(
    image_url: str,
    *,
    label: str = "Image",
    timeout: float = 10,
    hash_from_bytes=visual_hash_from_bytes,
) -> str:
    if not image_url or str(image_url).lower() == "nan":
        return ""
    try:
        response = requests.get(
            str(image_url),
            headers={"User-Agent": IMAGE_HASH_USER_AGENT},
            timeout=timeout,
        )
        if response.status_code != 200:
            print(f"⚠️ {label} hash download HTTP {response.status_code}: {image_url}")
            return ""
        return hash_from_bytes(response.content)
    except Exception as e:
        print(f"⚠️ Не удалось посчитать хэш {label}: {e}")
        return ""


def fetch_icon_pixel_hash(icon_url: str, timeout: float = 10) -> str:
    return fetch_image_hash(icon_url, label="Icon", timeout=timeout, hash_from_bytes=icon_pixel_hash_from_bytes)


def fetch_header_image_visual_hash(image_url: str, timeout: float = 10) -> str:
    return fetch_image_hash(image_url, label="Feature Graphic", timeout=timeout)


def fetch_screenshot_visual_hash(image_url: str, timeout: float = 10) -> str:
    return fetch_image_hash(image_url, label="Screenshot", timeout=timeout)


def _ensure_single_asset_hash(old_snapshot, new_snapshot, url_attr, hash_attr, hash_fetcher) -> None:
    old_url = str(getattr(old_snapshot, url_attr, "") or "").strip()
    new_url = str(getattr(new_snapshot, url_attr, "") or "").strip()
    if not old_url or old_url.lower() == "nan" or not new_url or new_url.lower() == "nan":
        return

    old_hash = str(getattr(old_snapshot, hash_attr, "") or "").strip()
    new_hash = str(getattr(new_snapshot, hash_attr, "") or "").strip()

    if old_url == new_url:
        if old_hash and not new_hash:
            setattr(new_snapshot, hash_attr, old_hash)
        return

    if old_hash and new_hash:
        return
    if old_hash and not new_hash:
        setattr(new_snapshot, hash_attr, hash_fetcher(new_url))
        return
    if new_hash and not old_hash:
        setattr(old_snapshot, hash_attr, hash_fetcher(old_url))
        return

    setattr(old_snapshot, hash_attr, hash_fetcher(old_url))
    setattr(new_snapshot, hash_attr, hash_fetcher(new_url))


def ensure_icon_hashes(old_snapshot, new_snapshot, hash_fetcher=fetch_icon_pixel_hash) -> None:
    _ensure_single_asset_hash(old_snapshot, new_snapshot, "icon", "icon_hash", hash_fetcher)


def ensure_header_image_hashes(old_snapshot, new_snapshot, hash_fetcher=fetch_header_image_visual_hash) -> None:
    _ensure_single_asset_hash(old_snapshot, new_snapshot, "header_image", "header_image_hash", hash_fetcher)


def ensure_screenshot_hashes(old_snapshot, new_snapshot, hash_fetcher=fetch_screenshot_visual_hash) -> None:
    old_screens = [str(url).strip() for url in getattr(old_snapshot, "screenshots", []) or []]
    new_screens = [str(url).strip() for url in getattr(new_snapshot, "screenshots", []) or []]
    if not old_screens or not new_screens:
        return

    old_hashes = list(getattr(old_snapshot, "screenshot_hashes", []) or [])
    new_hashes = list(getattr(new_snapshot, "screenshot_hashes", []) or [])

    if old_screens == new_screens:
        if old_hashes and not new_hashes:
            new_snapshot.screenshot_hashes = list(old_hashes)
        return

    if (
        len(old_hashes) == len(old_screens)
        and len(new_hashes) == len(new_screens)
        and all(old_hashes)
        and all(new_hashes)
    ):
        return
    if len(old_hashes) == len(old_screens) and all(old_hashes) and len(new_hashes) != len(new_screens):
        fetched_hashes = [hash_fetcher(url) for url in new_screens]
        if all(fetched_hashes):
            new_snapshot.screenshot_hashes = fetched_hashes
        return
    if len(new_hashes) == len(new_screens) and all(new_hashes) and len(old_hashes) != len(old_screens):
        fetched_hashes = [hash_fetcher(url) for url in old_screens]
        if all(fetched_hashes):
            old_snapshot.screenshot_hashes = fetched_hashes
        return

    fetched_old_hashes = [hash_fetcher(url) for url in old_screens]
    fetched_new_hashes = [hash_fetcher(url) for url in new_screens]
    if all(fetched_old_hashes):
        old_snapshot.screenshot_hashes = fetched_old_hashes
    if all(fetched_new_hashes):
        new_snapshot.screenshot_hashes = fetched_new_hashes


def ensure_visual_asset_hashes(old_snapshot, new_snapshot) -> None:
    ensure_icon_hashes(old_snapshot, new_snapshot)
    ensure_header_image_hashes(old_snapshot, new_snapshot)
    ensure_screenshot_hashes(old_snapshot, new_snapshot)
