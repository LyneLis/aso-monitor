from io import BytesIO

import requests
from PIL import Image

from core.config import Settings
from core.telegram import SCREENSHOT_COLLAGE_MAX_COUNT, build_screenshot_collage_bytes
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


def test_send_message_retries_retryable_status(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status_code, text=""):
            self.status_code = status_code
            self.text = text
            self.headers = {}

    def fake_post(url, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return Response(500, "temporary error")
        return Response(200)

    monkeypatch.setattr(requests, "post", fake_post)

    client = TelegramClient(Settings(telegram_token="token"), retry_count=1, retry_sleep=0)

    assert client.send_message("hello", "123") is True
    assert len(calls) == 2


def test_send_screenshots_uses_single_photo_for_one_image(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        text = ""

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(requests, "post", fake_post)

    client = TelegramClient(Settings(telegram_token="token"))

    assert client.send_screenshots("123", ["https://example.com/screen.jpg"], "app", "en-US") is True
    assert len(calls) == 1
    assert calls[0][0].endswith("/sendPhoto")
    assert calls[0][1]["data"]["photo"] == "https://example.com/screen.jpg"


def test_send_screenshots_falls_back_to_individual_photos(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status_code, text=""):
            self.status_code = status_code
            self.text = text

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/sendMediaGroup"):
            return Response(400, "bad photo")
        return Response(200)

    monkeypatch.setattr(requests, "post", fake_post)

    client = TelegramClient(Settings(telegram_token="token"))

    assert client.send_screenshots(
        "123",
        ["https://example.com/one.jpg", "https://example.com/two.jpg"],
        "app",
        "en-US",
    ) is True
    assert calls[0][0].endswith("/sendMediaGroup")
    assert [call[0].split("/")[-1] for call in calls[1:]] == ["sendPhoto", "sendPhoto"]


def make_test_image_bytes(color):
    output = BytesIO()
    Image.new("RGB", (80, 160), color).save(output, format="JPEG")
    return output.getvalue()


def test_build_screenshot_collage_downloads_all_images(monkeypatch):
    downloaded = []

    class Response:
        status_code = 200
        content = make_test_image_bytes((120, 20, 20))

    def fake_get(url, **kwargs):
        downloaded.append(url)
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)

    collage = build_screenshot_collage_bytes(["https://example.com/one.jpg", "https://example.com/two.jpg"])

    assert downloaded == ["https://example.com/one.jpg", "https://example.com/two.jpg"]
    assert collage.startswith(b"\xff\xd8")


def test_build_screenshot_collage_limits_downloaded_images(monkeypatch):
    downloaded = []

    class Response:
        status_code = 200
        content = make_test_image_bytes((120, 20, 20))

    def fake_get(url, **kwargs):
        downloaded.append(url)
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)

    urls = [f"https://example.com/{idx}.jpg" for idx in range(SCREENSHOT_COLLAGE_MAX_COUNT + 5)]

    collage = build_screenshot_collage_bytes(urls)

    assert downloaded == urls[:SCREENSHOT_COLLAGE_MAX_COUNT]
    assert collage.startswith(b"\xff\xd8")


def test_send_screenshot_collages_sends_before_and_after_photos(monkeypatch):
    calls = []

    class GetResponse:
        status_code = 200
        content = make_test_image_bytes((20, 120, 20))

    class PostResponse:
        status_code = 200
        text = ""

    def fake_get(url, **kwargs):
        return GetResponse()

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return PostResponse()

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)

    client = TelegramClient(Settings(telegram_token="token"))

    assert client.send_screenshot_collages(
        "123",
        ["https://example.com/old-1.jpg", "https://example.com/old-2.jpg"],
        ["https://example.com/new-1.jpg", "https://example.com/new-2.jpg"],
        "Test App",
        "en-US",
    ) is True
    assert [call[0].split("/")[-1] for call in calls] == ["sendPhoto", "sendPhoto"]
    assert "БЫЛО" in calls[0][1]["data"]["caption"]
    assert "СТАЛО" in calls[1][1]["data"]["caption"]
    assert calls[0][1]["files"]["photo"][0] == "screenshots_before.jpg"
    assert calls[1][1]["files"]["photo"][0] == "screenshots_after.jpg"


def test_send_screenshot_collages_falls_back_to_urls_when_uploads_fail(monkeypatch):
    calls = []

    class GetResponse:
        status_code = 200
        content = make_test_image_bytes((20, 120, 20))

    class PostResponse:
        def __init__(self, status_code):
            self.status_code = status_code
            self.text = ""

    def fake_get(url, **kwargs):
        return GetResponse()

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return PostResponse(500 if "files" in kwargs else 200)

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)

    client = TelegramClient(Settings(telegram_token="token"), retry_count=0)

    assert client.send_screenshot_collages(
        "123",
        ["https://example.com/old.jpg"],
        ["https://example.com/new.jpg"],
        "Test App",
        "en-US",
    ) is True
    assert [call[0].split("/")[-1] for call in calls] == [
        "sendPhoto",
        "sendPhoto",
        "sendPhoto",
        "sendPhoto",
    ]
    assert "БЫЛО" in calls[0][1]["data"]["caption"]
    assert "СТАЛО" in calls[1][1]["data"]["caption"]
    assert calls[2][1]["data"]["photo"] == "https://example.com/old.jpg"
    assert calls[3][1]["data"]["photo"] == "https://example.com/new.jpg"
