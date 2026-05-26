import pytest

from core.config import Settings
from database.postgres_repo import PostgresAppsRepository


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.queries.append((query, params))
        return FakeCursor(self.rows)


class ImportConnection(FakeConnection):
    def execute(self, query, params=None):
        self.queries.append((query, params))
        query_lower = " ".join(query.lower().split())
        if "returning chat_id" in query_lower:
            return FakeCursor([{"chat_id": params[1]}])
        if "returning id" in query_lower and "tracked_apps" in query_lower:
            return FakeCursor([{"id": "app-id"}])
        if "returning id" in query_lower and "tracked_locales" in query_lower:
            return FakeCursor([{"id": "locale-id"}])
        if "count(*)" in query_lower:
            return FakeCursor([{"count": 1}])
        return FakeCursor([])


def test_postgres_repo_requires_database_url():
    repo = PostgresAppsRepository(Settings())

    with pytest.raises(ValueError, match="DATABASE_URL"):
        repo.ping()


def test_postgres_repo_ping_uses_connection_factory():
    calls = []

    def factory(database_url):
        calls.append(database_url)
        return FakeConnection([{"ok": 1}])

    repo = PostgresAppsRepository(
        Settings(database_url="postgresql://example"),
        connection_factory=factory,
    )

    assert repo.ping() is True
    assert calls == ["postgresql://example"]


def test_postgres_repo_load_users():
    def factory(database_url):
        return FakeConnection([
            {"name": "Igor", "chat_id": "123"},
            {"name": "Team", "chat_id": "456"},
        ])

    repo = PostgresAppsRepository(
        Settings(database_url="postgresql://example"),
        connection_factory=factory,
    )

    assert repo.load_users() == {"Igor": "123", "Team": "456"}


def test_postgres_repo_load_apps_matches_existing_info_shape():
    def factory(database_url):
        return FakeConnection([
            {
                "package_id": "com.test.app",
                "geo": "en-US",
                "chat_id": "123",
                "title": "Title",
                "summary": "Summary",
                "description": "Description",
                "icon": "https://example.com/icon.png",
                "header_image": "",
                "screenshots": ["https://example.com/screen.png"],
                "check_log": [{"time": "26.05.2026 12:00:00", "status": "Ok"}],
                "ai_audit": "Audit",
            }
        ])

    repo = PostgresAppsRepository(
        Settings(database_url="postgresql://example"),
        connection_factory=factory,
    )

    apps = repo.load_apps()

    info = apps["com.test.app_en-US_123"]
    assert info["package_id"] == "com.test.app"
    assert info["geo"] == "en-US"
    assert info["chat_id"] == "123"
    assert info["current"]["title"] == "Title"
    assert info["current"]["summary"] == "Summary"
    assert info["current"]["screenshots"] == ["https://example.com/screen.png"]
    assert info["check_log"] == [{"time": "26.05.2026 12:00:00", "status": "Ok"}]
    assert info["ai_audit"] == "Audit"


def test_postgres_repo_import_tracked_apps_upserts_existing_shape():
    connections = []

    def factory(database_url):
        conn = ImportConnection([])
        connections.append(conn)
        return conn

    repo = PostgresAppsRepository(
        Settings(database_url="postgresql://example"),
        connection_factory=factory,
    )
    info = {
        "package_id": "com.test.app",
        "geo": "en-US",
        "chat_id": "123",
        "current": {
            "title": "Title",
            "summary": "Summary",
            "description": "Description",
            "icon": "icon",
            "header_image": "",
            "screenshots": ["screen"],
        },
        "history": [],
        "check_log": [{"time": "26.05.2026 12:00:00", "status": "Ok"}],
        "ai_audit": "Audit",
    }

    summary = repo.import_tracked_apps({"com.test.app_en-US_123": info}, users={"Igor": "123"})

    assert summary == {"users": 1, "locales": 1, "skipped": 0}
    executed = "\n".join(query for conn in connections for query, _ in conn.queries)
    assert "insert into public.monitor_users" in executed
    assert "insert into public.tracked_apps" in executed
    assert "insert into public.tracked_locales" in executed
    assert "insert into public.snapshots" in executed
    assert "insert into public.check_logs" in executed
    assert "insert into public.aso_audits" in executed
