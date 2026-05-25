from core.compare import (
    AppSnapshot,
    ChangeResult,
    clean_val,
    current_dict_from_snapshot,
    detect_changes,
    detect_changes_with_table_error,
    fill_missing_assets,
    format_single_locale_report,
    history_entry_from_snapshot,
    snapshot_from_current,
    snapshot_from_fetch,
    snapshot_from_row,
)
from core.config import DEFAULT_SPREADSHEET_URL, Settings
from core.gemini import GeminiClient
from core.locales import GP_LOCALES_RAW
from core.prompts import ASO_PROMPT, CURRENT_ASO_PROMPT
from core.subtitle import decode_apple_subtitle
from core.telegram import TelegramClient, clean_ai_for_telegram, format_changes_report
from core.time_utils import get_minsk_time

__all__ = [
    "AppSnapshot",
    "ChangeResult",
    "ASO_PROMPT",
    "CURRENT_ASO_PROMPT",
    "DEFAULT_SPREADSHEET_URL",
    "GP_LOCALES_RAW",
    "GeminiClient",
    "Settings",
    "TelegramClient",
    "clean_ai_for_telegram",
    "clean_val",
    "current_dict_from_snapshot",
    "detect_changes",
    "detect_changes_with_table_error",
    "fill_missing_assets",
    "format_single_locale_report",
    "history_entry_from_snapshot",
    "snapshot_from_current",
    "snapshot_from_fetch",
    "snapshot_from_row",
    "decode_apple_subtitle",
    "fetch_app_data",
    "format_changes_report",
    "get_minsk_time",
]


def __getattr__(name: str):
    if name == "fetch_app_data":
        from core.parsing import fetch_app_data

        return fetch_app_data
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
