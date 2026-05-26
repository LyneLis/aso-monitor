import requests

from core.config import Settings
from core.telegram import clean_ai_for_telegram, format_changes_report
from core.telegram import TelegramClient


def test_clean_ai_strips_markdown():
    assert clean_ai_for_telegram("*Bold* _x_ #h `c`") == "Bold x h c"


def test_format_changes_report_includes_locales():
    report = format_changes_report(
        "com.test.app",
        {
            "en-US": {
                "old_t": "Old",
                "new_t": "New",
                "old_s": "Sub old",
                "new_s": "Sub new",
                "old_d": "Desc old",
                "new_d": "Desc new",
            }
        },
    )
    assert "com.test.app" in report
    assert "EN-US" in report
    assert "Desc old" in report
    assert "Desc new" in report


def test_send_message_uses_timeout(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        text = ""

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(requests, "post", fake_post)

    client = TelegramClient(Settings(telegram_token="token"), request_timeout=7)
    client.send_message("hello", "123")

    assert len(calls) == 1
    assert calls[0][0].endswith("/sendMessage")
    assert calls[0][1]["timeout"] == 7
    assert calls[0][1]["data"] == {"chat_id": "123", "text": "hello"}


def test_send_message_markdown_falls_back_to_plain_text(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status_code, text=""):
            self.status_code = status_code
            self.text = text

    def fake_post(url, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return Response(400, "bad markdown")
        return Response(200)

    monkeypatch.setattr(requests, "post", fake_post)

    client = TelegramClient(Settings(telegram_token="token"))
    client.send_message("*hello*", "123", use_markdown=True)

    assert len(calls) == 2
    assert calls[0]["data"]["parse_mode"] == "Markdown"
    assert "parse_mode" not in calls[1]["data"]


def test_send_message_logs_request_error(monkeypatch, capsys):
    def fake_post(url, **kwargs):
        raise requests.Timeout("network timeout")

    monkeypatch.setattr(requests, "post", fake_post)

    client = TelegramClient(Settings(telegram_token="token"))
    client.send_message("hello", "123")

    captured = capsys.readouterr()
    assert "Telegram sendMessage: ошибка запроса" in captured.out
