import hashlib
from io import BytesIO
from typing import Optional

import requests
from PIL import Image, ImageOps

ICON_HASH_SIZE = (128, 128)
ICON_HASH_PREFIX = "pxsha256"
IMAGE_HASH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def icon_pixel_hash_from_bytes(image_bytes: bytes, size: tuple[int, int] = ICON_HASH_SIZE) -> str:
    with Image.open(BytesIO(image_bytes)) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGBA").resize(size, Image.Resampling.LANCZOS)

    digest = hashlib.sha256()
    digest.update(f"{normalized.mode}:{normalized.size[0]}x{normalized.size[1]}:".encode("ascii"))
    digest.update(normalized.tobytes())
    return f"{ICON_HASH_PREFIX}:{digest.hexdigest()}"


def fetch_icon_pixel_hash(icon_url: str, timeout: float = 10) -> str:
    if not icon_url or str(icon_url).lower() == "nan":
        return ""
    try:
        response = requests.get(
            str(icon_url),
            headers={"User-Agent": IMAGE_HASH_USER_AGENT},
            timeout=timeout,
        )
        if response.status_code != 200:
            print(f"⚠️ Icon hash download HTTP {response.status_code}: {icon_url}")
            return ""
        return icon_pixel_hash_from_bytes(response.content)
    except Exception as e:
        print(f"⚠️ Не удалось посчитать хэш иконки: {e}")
        return ""


def ensure_icon_hashes(old_snapshot, new_snapshot, hash_fetcher=fetch_icon_pixel_hash) -> None:
    old_icon = str(getattr(old_snapshot, "icon", "") or "").strip()
    new_icon = str(getattr(new_snapshot, "icon", "") or "").strip()
    if not old_icon or old_icon.lower() == "nan" or not new_icon or new_icon.lower() == "nan":
        return

    if old_icon == new_icon:
        if old_snapshot.icon_hash and not new_snapshot.icon_hash:
            new_snapshot.icon_hash = old_snapshot.icon_hash
        return

    if old_snapshot.icon_hash and new_snapshot.icon_hash:
        return
    if old_snapshot.icon_hash and not new_snapshot.icon_hash:
        new_snapshot.icon_hash = hash_fetcher(new_icon)
        return
    if new_snapshot.icon_hash and not old_snapshot.icon_hash:
        old_snapshot.icon_hash = hash_fetcher(old_icon)
        return

    old_snapshot.icon_hash = hash_fetcher(old_icon)
    new_snapshot.icon_hash = hash_fetcher(new_icon)
