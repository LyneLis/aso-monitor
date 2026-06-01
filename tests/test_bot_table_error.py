import json

import bot


def test_check_apps_repairs_table_error(monkeypatch):
    class FakeRepo:
        updated_rows = []

        def __init__(self, settings):
            self.settings = settings

        def open(self):
            return None

        def iter_rows(self):
            yield 2, {
                "package_id": "com.test.app",
                "geo": "us",
                "chat_id": "123",
                "title": "#ERROR!",
                "summary": "Old summary",
                "description": "Old description",
                "icon": "",
                "header_image": "",
                "screenshots": "[]",
                "history": "[]",
                "check_log": "[]",
            }

        def update_row(self, row_index, row):
            self.updated_rows.append((row_index, row.copy()))

        @staticmethod
        def parse_row_lists(row):
            return [], [], []

    monkeypatch.setattr(bot, "GspreadAppsRepository", FakeRepo)
    monkeypatch.setattr(bot, "get_minsk_time", lambda: "01.01.2026 12:00:00")
    monkeypatch.setattr(bot.time, "sleep", lambda _: None)
    def fake_fetcher(package_id, geo):
        return {
            "title": "Fixed title",
            "summary": "Fixed summary",
            "description": "Fixed description",
            "icon": "https://example.com/icon.png",
            "headerImage": "https://example.com/header.png",
            "screenshots": ["https://example.com/screen.png"],
        }

    bot.check_apps(fetcher=fake_fetcher)

    assert len(FakeRepo.updated_rows) == 1
    row_index, saved_row = FakeRepo.updated_rows[0]
    assert row_index == 2
    assert saved_row["title"] == "Fixed title"
    assert saved_row["summary"] == "Fixed summary"
    assert saved_row["description"] == "Fixed description"
    assert saved_row["icon"] == "https://example.com/icon.png"
    assert saved_row["header_image"] == "https://example.com/header.png"
    assert json.loads(saved_row["screenshots"]) == ["https://example.com/screen.png"]
    assert json.loads(saved_row["check_log"])[0]["status"] == "🟢 Авто: Исправление ошибки"


def test_check_apps_writes_row_error_to_check_log(monkeypatch):
    class FakeRepo:
        updated_rows = []

        def __init__(self, settings):
            self.settings = settings

        def open(self):
            return None

        def iter_rows(self):
            yield 2, {
                "package_id": "com.test.app",
                "geo": "us",
                "chat_id": "123",
                "title": "Old title",
                "summary": "Old summary",
                "description": "Old description",
                "icon": "",
                "header_image": "",
                "screenshots": "[]",
                "history": "[]",
                "check_log": "[]",
            }

        def update_row(self, row_index, row):
            self.updated_rows.append((row_index, row.copy()))

        @staticmethod
        def parse_row_lists(row):
            return [], [], []

    def failing_fetcher(package_id, geo):
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(bot, "GspreadAppsRepository", FakeRepo)
    monkeypatch.setattr(bot, "get_minsk_time", lambda: "01.01.2026 12:00:00")
    monkeypatch.setattr(bot.time, "sleep", lambda _: None)

    bot.check_apps(fetcher=failing_fetcher)

    assert len(FakeRepo.updated_rows) == 1
    row_index, saved_row = FakeRepo.updated_rows[0]
    assert row_index == 2
    log = json.loads(saved_row["check_log"])
    assert log[0]["status"] == "❌ Авто: Ошибка"
    assert log[0]["error"] == "store unavailable"


def test_auto_alert_uses_english_title_and_publisher(monkeypatch):
    class FakeRepo:
        updated_rows = []

        def __init__(self, settings):
            self.settings = settings

        def open(self):
            return None

        def iter_rows(self):
            yield 2, {
                "package_id": "com.test.app",
                "geo": "ja-JP",
                "chat_id": "123",
                "title": "日本語タイトル",
                "summary": "概要",
                "description": "Description",
                "publisher": "",
                "icon": "",
                "header_image": "",
                "screenshots": '["old-screen"]',
                "history": "[]",
                "check_log": "[]",
            }

        def update_row(self, row_index, row):
            self.updated_rows.append((row_index, row.copy()))

        @staticmethod
        def parse_row_lists(row):
            return json.loads(row.get("screenshots", "[]")), [], []

    class FakeTelegram:
        messages = []

        def send_message(self, text, chat_id, **kwargs):
            self.messages.append(text)
            return True

        def send_document(self, *args, **kwargs):
            return True

        def send_visual_diff(self, *args, **kwargs):
            return True

        def send_screenshots(self, *args, **kwargs):
            return True

        def send_screenshot_collages(self, *args, **kwargs):
            return True

        def send_ai_analysis(self, *args, **kwargs):
            return True

    def fake_fetcher(package_id, geo):
        base = {
            "summary": "Summary" if geo == "en-US" else "概要",
            "description": "Description",
            "developer": "Test Publisher",
            "icon": "",
            "headerImage": "",
        }
        if geo == "en-US":
            return {**base, "title": "English Title", "screenshots": []}
        return {**base, "title": "日本語タイトル", "screenshots": ["new-screen"]}

    fake_telegram = FakeTelegram()
    monkeypatch.setattr(bot, "GspreadAppsRepository", FakeRepo)
    monkeypatch.setattr(bot, "telegram", fake_telegram)
    monkeypatch.setattr(bot, "get_minsk_time", lambda: "01.01.2026 12:00:00")
    monkeypatch.setattr(bot.time, "sleep", lambda _: None)

    bot.check_apps(fetcher=fake_fetcher)

    assert any("📦 English Title (Test Publisher)" in message for message in fake_telegram.messages)


def test_auto_alert_is_skipped_when_row_save_fails(monkeypatch):
    class FakeRepo:
        def __init__(self, settings):
            self.settings = settings

        def open(self):
            return None

        def iter_rows(self):
            yield 2, {
                "package_id": "com.test.app",
                "geo": "hi-IN",
                "chat_id": "123",
                "title": "पुराना नाम",
                "summary": "Old summary",
                "description": "Old description",
                "publisher": "",
                "icon": "",
                "header_image": "",
                "screenshots": "[]",
                "history": "[]",
                "check_log": "[]",
            }

        def update_row(self, row_index, row):
            raise RuntimeError("sheet write failed")

        @staticmethod
        def parse_row_lists(row):
            return [], [], []

    class FakeTelegram:
        def __init__(self):
            self.messages = []
            self.documents = []
            self.ai_messages = []

        def send_message(self, text, chat_id, **kwargs):
            self.messages.append(text)
            return True

        def send_document(self, *args, **kwargs):
            self.documents.append(args)
            return True

        def send_visual_diff(self, *args, **kwargs):
            return True

        def send_screenshots(self, *args, **kwargs):
            return True

        def send_screenshot_collages(self, *args, **kwargs):
            return True

        def send_ai_analysis(self, *args, **kwargs):
            self.ai_messages.append(args)
            return True

    def fake_fetcher(package_id, geo):
        return {
            "title": "English Title",
            "summary": "Old summary",
            "description": "Old description",
            "developer": "Test Publisher",
            "icon": "",
            "headerImage": "",
            "screenshots": [],
        }

    fake_telegram = FakeTelegram()
    monkeypatch.setattr(bot, "GspreadAppsRepository", FakeRepo)
    monkeypatch.setattr(bot, "telegram", fake_telegram)
    monkeypatch.setattr(bot, "get_minsk_time", lambda: "01.01.2026 12:00:00")
    monkeypatch.setattr(bot.time, "sleep", lambda _: None)

    bot.check_apps(fetcher=fake_fetcher)

    assert fake_telegram.messages == []
    assert fake_telegram.documents == []
    assert fake_telegram.ai_messages == []


def test_auto_alert_records_telegram_delivery_failure(monkeypatch):
    class FakeRepo:
        updated_rows = []

        def __init__(self, settings):
            self.settings = settings

        def open(self):
            return None

        def iter_rows(self):
            yield 2, {
                "package_id": "com.test.app",
                "geo": "en-US",
                "chat_id": "123",
                "title": "Old title",
                "summary": "Old summary",
                "description": "Old description",
                "publisher": "",
                "icon": "",
                "header_image": "",
                "screenshots": "[]",
                "history": "[]",
                "check_log": "[]",
            }

        def update_row(self, row_index, row):
            self.updated_rows.append((row_index, row.copy()))

        @staticmethod
        def parse_row_lists(row):
            return [], [], []

    class FakeTelegram:
        def send_message(self, *args, **kwargs):
            return True

        def send_document(self, *args, **kwargs):
            return False

        def send_visual_diff(self, *args, **kwargs):
            return True

        def send_screenshot_collages(self, *args, **kwargs):
            return True

        def send_ai_analysis(self, *args, **kwargs):
            return True

    class FakeGemini:
        def analyze_batched_changes(self, *args, **kwargs):
            return "AI ok"

        def is_error_response(self, text):
            return False

    def fake_fetcher(package_id, geo):
        return {
            "title": "New title",
            "summary": "New summary",
            "description": "New description",
            "developer": "Test Publisher",
            "icon": "",
            "headerImage": "",
            "screenshots": [],
        }

    monkeypatch.setattr(bot, "GspreadAppsRepository", FakeRepo)
    monkeypatch.setattr(bot, "telegram", FakeTelegram())
    monkeypatch.setattr(bot, "gemini", FakeGemini())
    monkeypatch.setattr(bot, "get_minsk_time", lambda: "01.01.2026 12:00:00")
    monkeypatch.setattr(bot.time, "sleep", lambda _: None)

    bot.check_apps(fetcher=fake_fetcher)

    assert len(FakeRepo.updated_rows) == 2
    _, saved_row = FakeRepo.updated_rows[-1]
    log = json.loads(saved_row["check_log"])
    assert log[-1]["status"] == "❌ Авто: Telegram"
    assert "файл отчета" in log[-1]["error"]
