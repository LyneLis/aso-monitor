from types import SimpleNamespace

from core.config import Settings
from core.gemini import GeminiClient, NO_API_KEY_MSG, QUOTA_RETRY_SLEEP_SEC


class FakeModels:
    def __init__(self, responses=None, fail_once=None):
        self.calls = []
        self._responses = list(responses or ["ok"])
        self._fail_once = fail_once

    def list(self):
        return [
            SimpleNamespace(name="models/gemini-2.5-flash", supported_actions=["generateContent"]),
            SimpleNamespace(name="models/image-only", supported_actions=["generateImage"]),
        ]

    def generate_content(self, model, contents):
        self.calls.append((model, contents))
        if self._fail_once:
            error = self._fail_once
            self._fail_once = None
            raise RuntimeError(error)
        return SimpleNamespace(text=self._responses.pop(0))


class FakeClient:
    def __init__(self, models):
        self.models = models


def test_run_without_api_key_returns_message():
    client = GeminiClient(Settings())

    assert client.run("hello") == NO_API_KEY_MSG


def test_run_uses_new_genai_client_shape():
    models = FakeModels(responses=["analysis"])
    client = GeminiClient(Settings(gemini_api_key="key"), client=FakeClient(models))

    assert client.run("prompt") == "analysis"
    assert models.calls == [("gemini-2.5-flash", "prompt")]


def test_run_retries_quota_error(monkeypatch):
    sleeps = []
    models = FakeModels(responses=["after retry"], fail_once="429 Quota exceeded")
    client = GeminiClient(Settings(gemini_api_key="key"), client=FakeClient(models))

    monkeypatch.setattr("core.gemini.time.sleep", lambda seconds: sleeps.append(seconds))

    assert client.run("prompt") == "after retry"
    assert len(models.calls) == 2
    assert sleeps == [QUOTA_RETRY_SLEEP_SEC]


def test_analyze_changes_keeps_existing_prompt_contract():
    models = FakeModels(responses=["analysis"])
    client = GeminiClient(Settings(gemini_api_key="key"), client=FakeClient(models))

    assert client.analyze_changes("old t", "new t", "old s", "new s", "old d", "new d") == "analysis"

    _, prompt = models.calls[0]
    assert "--- БЫЛО ---" in prompt
    assert "Title: old t" in prompt
    assert "Short Description: old s" in prompt
    assert "Full Description: old d" in prompt
    assert "--- СТАЛО ---" in prompt
    assert "Title: new t" in prompt
    assert "Short Description: new s" in prompt
    assert "Full Description: new d" in prompt
