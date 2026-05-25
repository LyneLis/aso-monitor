import time
from typing import Any, Dict, List, Optional

import google.generativeai as genai

from core.config import Settings
from core.prompts import ASO_PROMPT, CURRENT_ASO_PROMPT

PRIORITY_MODELS = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-2.5-pro",
    "gemini-1.5-pro",
    "gemini-pro",
]
QUOTA_RETRY_SLEEP_SEC = 35
NO_API_KEY_MSG = "❌ Ключ Gemini API не найден."


class GeminiClient:
    def __init__(self, settings: Settings, verbose: bool = False):
        self._api_key = settings.gemini_api_key
        self._verbose = verbose
        if self._api_key:
            genai.configure(api_key=self._api_key, transport="rest")

    def run(self, prompt: str) -> str:
        if not self._api_key:
            return NO_API_KEY_MSG

        available_models: List[str] = []
        try:
            for m in genai.list_models():
                if "generateContent" in m.supported_generation_methods:
                    available_models.append(m.name.replace("models/", ""))
        except Exception as e:
            if self._verbose:
                print(f"⚠️ Не удалось получить список моделей: {e}")

        models_to_try = [m for m in PRIORITY_MODELS if m in available_models]
        if not models_to_try:
            models_to_try = available_models[:2] if available_models else PRIORITY_MODELS

        last_error = ""
        for model_name in models_to_try:
            try:
                if self._verbose:
                    print(f"🤖 Пробую модель: {model_name}...")
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                if response and response.text:
                    return response.text
            except Exception as e:
                error_str = str(e)
                last_error = error_str
                if "429" in error_str or "Quota" in error_str:
                    time.sleep(QUOTA_RETRY_SLEEP_SEC)
                    try:
                        response = model.generate_content(prompt)
                        if response and response.text:
                            return response.text
                    except Exception as retry_e:
                        last_error = str(retry_e)
                continue

        return f"❌ Ошибка ИИ-анализа: {last_error}"

    def analyze_changes(
        self,
        old_t: str,
        new_t: str,
        old_s: str,
        new_s: str,
        old_d: str,
        new_d: str,
    ) -> str:
        if not self._api_key:
            return NO_API_KEY_MSG
        prompt = (
            f"{ASO_PROMPT}\n\n"
            f"--- БЫЛО ---\nTitle: {old_t}\nShort Description: {old_s}\nFull Description: {old_d}\n\n"
            f"--- СТАЛО ---\nTitle: {new_t}\nShort Description: {new_s}\nFull Description: {new_d}"
        )
        return self.run(prompt)

    def analyze_batched_changes(self, batched_data: Dict[str, Dict[str, str]]) -> str:
        if not self._api_key:
            return NO_API_KEY_MSG
        prompt = (
            ASO_PROMPT
            + "\n\nВНИМАНИЕ: Конкурент обновил сразу несколько локалей. "
            "Проанализируй общую ASO-стратегию этих изменений (какие рынки в фокусе, какие ключевики тестируют):\n"
        )
        for loc, data in batched_data.items():
            prompt += f"\n🌍 --- ЛОКАЛЬ: {loc.upper()} ---\n"
            prompt += f"БЫЛО:\nTitle: {data['old_t']}\nShort/Subtitle: {data['old_s']}\nFull Desc: {data['old_d']}\n"
            prompt += f"СТАЛО:\nTitle: {data['new_t']}\nShort/Subtitle: {data['new_s']}\nFull Desc: {data['new_d']}\n"
        return self.run(prompt)

    def analyze_current_aso(self, batched_data: Dict[str, Dict[str, str]]) -> str:
        if not self._api_key:
            return NO_API_KEY_MSG
        prompt = (
            CURRENT_ASO_PROMPT
            + "\n\nПроанализируй текущую ASO-стратегию конкурента на основе следующих данных:\n"
        )
        for loc, data in batched_data.items():
            prompt += f"\n🌍 --- ЛОКАЛЬ: {loc.upper()} ---\n"
            prompt += (
                f"Title: {data['title']}\n"
                f"Subtitle/Short Desc: {data['summary']}\n"
                f"Full Desc: {data['description']}\n"
            )
        return self.run(prompt)

    def is_error_response(self, text: Optional[str]) -> bool:
        return not text or "❌" in text
