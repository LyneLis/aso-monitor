from importlib import import_module

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
from core.locales import GP_LOCALES_RAW
from core.monitoring import ItemCheckOutcome, add_changed_locale_to_batch, check_item_snapshots
from core.prompts import ASO_PROMPT, CURRENT_ASO_PROMPT
from core.subtitle import decode_apple_subtitle
from core.time_utils import get_minsk_time

_LAZY_IMPORTS = {
    "GeminiClient": ("core.gemini", "GeminiClient"),
    "TelegramClient": ("core.telegram", "TelegramClient"),
    "clean_ai_for_telegram": ("core.telegram", "clean_ai_for_telegram"),
    "fetch_app_data": ("core.parsing", "fetch_app_data"),
    "format_changes_report": ("core.telegram", "format_changes_report"),
}

__all__ = [
    "AppSnapshot",
    "ChangeResult",
    "ASO_PROMPT",
    "CURRENT_ASO_PROMPT",
    "DEFAULT_SPREADSHEET_URL",
    "GP_LOCALES_RAW",
    "GeminiClient",
    "ItemCheckOutcome",
    "Settings",
    "TelegramClient",
    "add_changed_locale_to_batch",
    "check_item_snapshots",
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
    if name in _LAZY_IMPORTS:
        module_name, attr_name = _LAZY_IMPORTS[name]
        value = getattr(import_module(module_name), attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
