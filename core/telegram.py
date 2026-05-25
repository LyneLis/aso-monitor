import time
from typing import Any, Dict, List, Optional

import requests

from core.config import Settings

DEFAULT_MESSAGE_LIMIT = 4000
BOT_CHUNK_LIMIT = 3900


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


class TelegramClient:
    def __init__(self, settings: Settings, message_limit: int = DEFAULT_MESSAGE_LIMIT):
        self._token = settings.telegram_token
        self._limit = message_limit

    @property
    def token(self) -> Optional[str]:
        return self._token

    def _api_url(self, method: str) -> Optional[str]:
        if not self._token:
            return None
        return f"https://api.telegram.org/bot{self._token}/{method}"

    def send_message(
        self,
        text: str,
        chat_id: str,
        use_markdown: bool = False,
        chunk_sleep: float = 0,
    ) -> None:
        url = self._api_url("sendMessage")
        if not url or not chat_id:
            return
        for i in range(0, len(text), self._limit):
            chunk = text[i : i + self._limit]
            data: Dict[str, Any] = {"chat_id": chat_id, "text": chunk}
            if use_markdown:
                data["parse_mode"] = "Markdown"
            try:
                res = requests.post(url, data=data)
                if use_markdown and res.status_code != 200:
                    requests.post(url, data={"chat_id": chat_id, "text": chunk})
            except Exception:
                pass
            if chunk_sleep > 0:
                time.sleep(chunk_sleep)

    def send_document(
        self,
        file_content: str,
        filename: str,
        caption: str,
        chat_id: str,
    ) -> None:
        url = self._api_url("sendDocument")
        if not url or not chat_id:
            return
        files = {"document": (filename, file_content.encode("utf-8"))}
        try:
            requests.post(url, data={"chat_id": chat_id, "caption": caption}, files=files)
        except Exception:
            pass

    def send_visual_diff(
        self,
        chat_id: str,
        old_url: str,
        new_url: str,
        name: str,
        pkg_id: str,
        geo: str,
    ) -> None:
        if not old_url or not new_url or old_url.lower() == "nan" or new_url.lower() == "nan":
            return
        url = self._api_url("sendMediaGroup")
        if not url or not chat_id:
            return
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
        try:
            requests.post(url, json={"chat_id": chat_id, "media": media})
        except Exception as e:
            print(f"⚠️ Ошибка отправки медиа-группы: {e}")

    def send_screenshots(
        self,
        chat_id: str,
        screenshots: List[str],
        pkg_id: str,
        geo: str,
        max_count: int = 10,
    ) -> None:
        if not screenshots:
            return
        url = self._api_url("sendMediaGroup")
        if not url or not chat_id:
            return
        geo_upper = geo.upper()
        media = [
            {
                "type": "photo",
                "media": s,
                "parse_mode": "HTML",
                "caption": f"📱 Скриншот {pkg_id} [{geo_upper}]" if idx == 0 else "",
            }
            for idx, s in enumerate(screenshots[:max_count])
        ]
        try:
            requests.post(url, json={"chat_id": chat_id, "media": media})
        except Exception as e:
            print(f"⚠️ Ошибка отправки скриншотов: {e}")

    def send_ai_analysis(
        self,
        chat_id: str,
        ai_text: str,
        prefix: str = "🤖 Анализ:\n\n",
        chunk_limit: Optional[int] = None,
        chunk_sleep: float = 1,
    ) -> None:
        clean_ai = clean_ai_for_telegram(ai_text)
        full_text = f"{prefix}{clean_ai}"
        limit = chunk_limit if chunk_limit is not None else self._limit
        url = self._api_url("sendMessage")
        if not url or not chat_id:
            return
        for chunk_start in range(0, len(full_text), limit):
            chunk = full_text[chunk_start : chunk_start + limit]
            try:
                requests.post(url, data={"chat_id": chat_id, "text": chunk})
            except Exception:
                pass
            if chunk_sleep > 0:
                time.sleep(chunk_sleep)
