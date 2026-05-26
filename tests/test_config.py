from core.config import DEFAULT_SPREADSHEET_URL, Settings


def test_settings_from_env_reads_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")

    settings = Settings.from_env()

    assert settings.database_url == "postgresql://example"


def test_streamlit_secrets_missing_file_falls_back_to_defaults():
    class MissingSecrets:
        def get(self, key):
            raise RuntimeError("No secrets found")

    settings = Settings.from_streamlit_secrets(MissingSecrets())

    assert settings.gemini_api_key is None
    assert settings.telegram_token is None
    assert settings.spreadsheet_url == DEFAULT_SPREADSHEET_URL
    assert settings.database_url is None


def test_streamlit_secrets_reads_database_url():
    class Secrets:
        def get(self, key):
            values = {"DATABASE_URL": "postgresql://streamlit"}
            return values.get(key)

    settings = Settings.from_streamlit_secrets(Secrets())

    assert settings.database_url == "postgresql://streamlit"
