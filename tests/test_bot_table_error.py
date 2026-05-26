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
