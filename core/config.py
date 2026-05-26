import os
from dataclasses import dataclass
from typing import Any, Optional

# Override via SPREADSHEET_URL in env (bot) or Streamlit secrets (app).
DEFAULT_SPREADSHEET_URL = (
    "https://docs.google.com/spreadsheets/d/1jHKbRYt0hJg29RWLIXZ2fL3et_hgzvkhCSxVtTjKV9g/edit"
)


@dataclass(frozen=True)
class Settings:
    gemini_api_key: Optional[str] = None
    telegram_token: Optional[str] = None
    spreadsheet_url: Optional[str] = None
    gcp_service_account_json: Optional[str] = None
    database_url: Optional[str] = None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            gemini_api_key=os.environ.get("GEMINI_API_KEY"),
            telegram_token=os.environ.get("TELEGRAM_TOKEN"),
            spreadsheet_url=os.environ.get("SPREADSHEET_URL") or DEFAULT_SPREADSHEET_URL,
            gcp_service_account_json=os.environ.get("GCP_SERVICE_ACCOUNT_JSON"),
            database_url=os.environ.get("DATABASE_URL"),
        )

    @classmethod
    def from_streamlit_secrets(cls, secrets) -> "Settings":
        def secret_get(key: str) -> Optional[Any]:
            try:
                return secrets.get(key)
            except Exception:
                return None

        return cls(
            gemini_api_key=secret_get("GEMINI_API_KEY"),
            telegram_token=secret_get("TELEGRAM_TOKEN"),
            spreadsheet_url=secret_get("SPREADSHEET_URL") or DEFAULT_SPREADSHEET_URL,
            database_url=secret_get("DATABASE_URL"),
        )
