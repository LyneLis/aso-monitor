import time
from io import BytesIO
from typing import Any, Dict, List, Optional

import requests
from PIL import Image, ImageDraw, ImageOps

from core.config import Settings

DEFAULT_MESSAGE_LIMIT = 4000
BOT_CHUNK_LIMIT = 3900
TELEGRAM_REQUEST_TIMEOUT_SEC = 15
TELEGRAM_RETRY_COUNT = 2
TELEGRAM_RETRY_SLEEP_SEC = 0.0
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
SCREENSHOT_COLLAGE_THUMB_SIZE = (320, 720)
SCREENSHOT_COLLAGE_GAP = 16
IMAGE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def clean_ai_for_telegram(text: str) -> str:
    return text.replace("*", "").replace("_", "").replace("#", "").replace("`", "")


def format_changes_report(pkg_id: str, texts_by_geo: Dict[str, Dict[str, str]]) -> str:
    report = f"ОТЧЕТ ОБ ИЗМЕНЕНИЯХ\nПриложение: {pkg_id}\n\n"
    for geo, txt in texts_by_geo.items():
        report += f"Локаль: {geo.upper()}\n{'=' * 40}\n"
        report += (
            f"--- БЫЛО ---\nНазвание: {txt['old_t']}\nSD/Subtitle: {txt['old_s']}\nFD:\n{txt['old_d']}\n\n"
            f"--- СТАЛО ---\nНазвание: {txt['new_t']}\nSD/Subtitle: {txt['new_s']}\nFD:\n{txt['new_d']}\n\n"
        )
    return report


def _download_image(url: str, timeout: float = TELEGRAM_REQUEST_TIMEOUT_SEC) -> Optional[Image.Image]:
    if not url or str(url).lower() == "nan":
        return None
    try:
        response = requests.get(str(url), headers={"User-Agent": IMAGE_USER_AGENT}, timeout=timeout)
        if response.status_code != 200:
            print(f"⚠️ Screenshot download HTTP {response.status_code}: {url}")
            return None
        image = Image.open(BytesIO(response.content))
        return ImageOps.exif_transpose(image).convert("RGB")
    except Exception as e:
        print(f"⚠️ Не удалось скачать скриншот для коллажа: {e}")
        return None


def _placeholder_collage_bytes() -> bytes:
    image = Image.new("RGB", (900, 480), (245, 247, 250))
    draw = ImageDraw.Draw(image)
    draw.text((360, 225), "NO SCREENSHOTS", fill=(92, 101, 112))
    output = BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True)
    return output.getvalue()


def _collage_columns(count: int) -> int:
    if count <= 1:
        return 1
    if count <= 4:
        return 2
    if count <= 9:
        return 3
    return 4


def build_screenshot_collage_bytes(screenshot_urls: List[str]) -> bytes:
    images = [
        image
        for image in (_download_image(url) for url in screenshot_urls)
        if image is not None
    ]
    if not images:
        return _placeholder_collage_bytes()

    thumbs = [ImageOps.contain(image, SCREENSHOT_COLLAGE_THUMB_SIZE) for image in images]
    columns = _collage_columns(len(thumbs))
    rows = (len(thumbs) + columns - 1) // columns
    cell_w = max(image.width for image in thumbs)
    cell_h = max(image.height for image in thumbs)
    gap = SCREENSHOT_COLLAGE_GAP
    canvas_w = columns * cell_w + (columns + 1) * gap
    canvas_h = rows * cell_h + (rows + 1) * gap
    collage = Image.new("RGB", (canvas_w, canvas_h), (245, 247, 250))

    for idx, image in enumerate(thumbs):
        col = idx % columns
        row = idx // columns
        x = gap + col * (cell_w + gap) + (cell_w - image.width) // 2
        y = gap + row * (cell_h + gap) + (cell_h - image.height) // 2
        collage.paste(image, (x, y))

    output = BytesIO()
    collage.save(output, format="JPEG", quality=88, optimize=True)
    return output.getvalue()


class TelegramClient:
    def __init__(
        self,
        settings: Settings,
        message_limit: int = DEFAULT_MESSAGE_LIMIT,
        request_timeout: float = TELEGRAM_REQUEST_TIMEOUT_SEC,
        retry_count: int = TELEGRAM_RETRY_COUNT,
        retry_sleep: float = TELEGRAM_RETRY_SLEEP_SEC,
    ):
        self._token = settings.telegram_token
        self._limit = message_limit
        self._request_timeout = request_timeout
        self._retry_count = retry_count
        self._retry_sleep = retry_sleep

    @property
    def token(self) -> Optional[str]:
        return self._token

    def _api_url(self, method: str) -> Optional[str]:
        if not self._token:
            return None
        return f"https://api.telegram.org/bot{self._token}/{method}"

    def _post(self, method: str, **kwargs: Any) -> Optional[requests.Response]:
        url = self._api_url(method)
        if not url:
            return None

        for attempt in range(self._retry_count + 1):
            try:
                response = requests.post(url, timeout=self._request_timeout, **kwargs)
            except requests.RequestException as e:
                print(f"⚠️ Telegram {method}: ошибка запроса: {e}")
                if attempt < self._retry_count:
                    self._wait_before_retry()
                    continue
                return None
            except Exception as e:
                print(f"⚠️ Telegram {method}: неожиданная ошибка: {e}")
                return None

            if response.status_code != 200:
                body = response.text[:300] if response.text else ""
                print(f"⚠️ Telegram {method}: HTTP {response.status_code} {body}")
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < self._retry_count:
                    self._wait_before_retry(response)
                    continue
            return response

        return None

    def _wait_before_retry(self, response: Optional[requests.Response] = None) -> None:
        retry_after = None
        if response is not None:
            retry_after = getattr(response, "headers", {}).get("Retry-After")
        try:
            delay = float(retry_after) if retry_after else self._retry_sleep
        except (TypeError, ValueError):
            delay = self._retry_sleep
        if delay > 0:
            time.sleep(delay)

    def send_message(
        self,
        text: str,
        chat_id: str,
        use_markdown: bool = False,
        chunk_sleep: float = 0,
    ) -> bool:
        if not chat_id:
            return False
        ok = True
        for i in range(0, len(text), self._limit):
            chunk = text[i : i + self._limit]
            data: Dict[str, Any] = {"chat_id": chat_id, "text": chunk}
            if use_markdown:
                data["parse_mode"] = "Markdown"
            res = self._post("sendMessage", data=data)
            if use_markdown and (not res or res.status_code != 200):
                res = self._post("sendMessage", data={"chat_id": chat_id, "text": chunk})
            if not res or res.status_code != 200:
                ok = False
            if chunk_sleep > 0:
                time.sleep(chunk_sleep)
        return ok

    def send_document(
        self,
        file_content: str,
        filename: str,
        caption: str,
        chat_id: str,
    ) -> bool:
        if not chat_id:
            return False
        files = {"document": (filename, file_content.encode("utf-8"))}
        res = self._post("sendDocument", data={"chat_id": chat_id, "caption": caption}, files=files)
        return bool(res and res.status_code == 200)

    def send_visual_diff(
        self,
        chat_id: str,
        old_url: str,
        new_url: str,
        name: str,
        pkg_id: str,
        geo: str,
    ) -> bool:
        if not old_url or not new_url or old_url.lower() == "nan" or new_url.lower() == "nan":
            return False
        if not chat_id:
            return False
        media = [
            {
                "type": "photo",
                "media": old_url,
                "parse_mode": "HTML",
                "caption": f"🔴 <b>БЫЛО</b> | {name}\n📦 {pkg_id} [{geo}]",
            },
            {
                "type": "photo",
                "media": new_url,
                "parse_mode": "HTML",
                "caption": f"🟢 <b>СТАЛО</b> | {name}\n📦 {pkg_id} [{geo}]",
            },
        ]
        res = self._post("sendMediaGroup", json={"chat_id": chat_id, "media": media})
        return bool(res and res.status_code == 200)

    def send_screenshots(
        self,
        chat_id: str,
        screenshots: List[str],
        pkg_id: str,
        geo: str,
        max_count: int = 10,
    ) -> bool:
        if not screenshots:
            return False
        if not chat_id:
            return False
        geo_upper = geo.upper()
        limited_screenshots = screenshots[:max_count]

        if len(limited_screenshots) == 1:
            return self._send_single_screenshot(chat_id, limited_screenshots[0], pkg_id, geo_upper, 1, 1)

        media = [
            {
                "type": "photo",
                "media": s,
                "parse_mode": "HTML",
                "caption": f"📱 Скриншот {pkg_id} [{geo_upper}]" if idx == 0 else "",
            }
            for idx, s in enumerate(limited_screenshots)
        ]
        res = self._post("sendMediaGroup", json={"chat_id": chat_id, "media": media})
        if res and res.status_code == 200:
            return True

        sent_any = False
        for idx, screenshot in enumerate(limited_screenshots, start=1):
            sent_any = self._send_single_screenshot(
                chat_id,
                screenshot,
                pkg_id,
                geo_upper,
                idx,
                len(limited_screenshots),
            ) or sent_any
        return sent_any

    def _send_single_screenshot(
        self,
        chat_id: str,
        screenshot: str,
        pkg_id: str,
        geo_upper: str,
        index: int,
        total: int,
    ) -> bool:
        if not screenshot:
            return False
        caption = f"📱 Скриншот {index}/{total} {pkg_id} [{geo_upper}]"
        res = self._post("sendPhoto", data={"chat_id": chat_id, "photo": screenshot, "caption": caption})
        return bool(res and res.status_code == 200)

    def send_screenshot_collages(
        self,
        chat_id: str,
        old_screenshots: List[str],
        new_screenshots: List[str],
        pkg_id: str,
        geo: str,
    ) -> bool:
        if not chat_id:
            return False
        old_collage = build_screenshot_collage_bytes(old_screenshots)
        new_collage = build_screenshot_collage_bytes(new_screenshots)
        geo_upper = geo.upper()
        old_sent = self._send_collage_photo(
            chat_id,
            old_collage,
            "screenshots_before.jpg",
            f"🔴 БЫЛО | Скриншоты\n📦 {pkg_id} [{geo_upper}]",
        )
        new_sent = self._send_collage_photo(
            chat_id,
            new_collage,
            "screenshots_after.jpg",
            f"🟢 СТАЛО | Скриншоты\n📦 {pkg_id} [{geo_upper}]",
        )
        return old_sent and new_sent

    def _send_collage_photo(self, chat_id: str, image_bytes: bytes, filename: str, caption: str) -> bool:
        files = {"photo": (filename, image_bytes, "image/jpeg")}
        res = self._post("sendPhoto", data={"chat_id": chat_id, "caption": caption}, files=files)
        return bool(res and res.status_code == 200)

    def send_ai_analysis(
        self,
        chat_id: str,
        ai_text: str,
        prefix: str = "🤖 Анализ:\n\n",
        chunk_limit: Optional[int] = None,
        chunk_sleep: float = 1,
    ) -> bool:
        clean_ai = clean_ai_for_telegram(ai_text)
        full_text = f"{prefix}{clean_ai}"
        limit = chunk_limit if chunk_limit is not None else self._limit
        if not chat_id:
            return False
        ok = True
        for chunk_start in range(0, len(full_text), limit):
            chunk = full_text[chunk_start : chunk_start + limit]
            res = self._post("sendMessage", data={"chat_id": chat_id, "text": chunk})
            if not res or res.status_code != 200:
                ok = False
            if chunk_sleep > 0:
                time.sleep(chunk_sleep)
        return ok
