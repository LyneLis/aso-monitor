from core.config import DEFAULT_SPREADSHEET_URL, Settings


def test_streamlit_secrets_missing_file_falls_back_to_defaults():
    class MissingSecrets:
        def get(self, key):
            raise RuntimeError("No secrets found")

    settings = Settings.from_streamlit_secrets(MissingSecrets())

    assert settings.gemini_api_key is None
    assert settings.telegram_token is None
    assert settings.spreadsheet_url == DEFAULT_SPREADSHEET_URL
