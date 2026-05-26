import time
from typing import Any, Dict, List, Optional

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
    def __init__(self, settings: Settings, verbose: bool = False, client: Optional[Any] = None):
        self._api_key = settings.gemini_api_key
        self._verbose = verbose
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google import genai
            except ImportError as e:
                raise RuntimeError("Пакет google-genai не установлен.") from e
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _available_models(self, client: Any) -> List[str]:
        available_models: List[str] = []
        try:
            for model in client.models.list():
                if not self._supports_generate_content(model):
                    continue
                available_models.append(self._model_name(model))
        except Exception as e:
            if self._verbose:
                print(f"⚠️ Не удалось получить список моделей: {e}")
        return available_models

    @staticmethod
    def _model_name(model: Any) -> str:
        name = getattr(model, "name", str(model))
        return str(name).replace("models/", "", 1)

    @staticmethod
    def _supports_generate_content(model: Any) -> bool:
        supported = getattr(model, "supported_actions", None)
        if supported is None:
            supported = getattr(model, "supported_generation_methods", None)
        if supported is None:
            return True
        normalized = {str(item).replace("_", "").lower() for item in supported}
        return "generatecontent" in normalized

    def run(self, prompt: str) -> str:
        if not self._api_key:
            return NO_API_KEY_MSG

        try:
            client = self._get_client()
        except Exception as e:
            return f"❌ Ошибка ИИ-анализа: {e}"

        available_models = self._available_models(client)
        models_to_try = [m for m in PRIORITY_MODELS if m in available_models]
        if not models_to_try:
            models_to_try = available_models[:2] if available_models else PRIORITY_MODELS

        last_error = ""
        for model_name in models_to_try:
            try:
                if self._verbose:
                    print(f"🤖 Пробую модель: {model_name}...")
                response = client.models.generate_content(model=model_name, contents=prompt)
                text = getattr(response, "text", None)
                if text:
                    return text
            except Exception as e:
                error_str = str(e)
                last_error = error_str
                if "429" in error_str or "Quota" in error_str:
                    time.sleep(QUOTA_RETRY_SLEEP_SEC)
                    try:
                        response = client.models.generate_content(model=model_name, contents=prompt)
                        text = getattr(response, "text", None)
                        if text:
                            return text
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
