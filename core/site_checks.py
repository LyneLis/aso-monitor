from typing import Any, Callable, Dict, List, Optional, Tuple

from core.compare import current_dict_from_snapshot, fill_missing_assets, snapshot_from_current
from core.display import apply_current_metadata
from core.monitoring import ItemCheckOutcome, check_item_snapshots
from core.time_utils import get_minsk_time


def run_site_check_for_item(
    info: Dict[str, Any],
    *,
    item_key: str = "",
    fetcher: Optional[Callable[[str, str], Dict[str, Any]]] = None,
) -> Tuple[int, List[str], Optional[Dict[str, str]], Optional[ItemCheckOutcome]]:
    updates = 0
    changed: List[str] = []
    text_changes_payload = None
    outcome = None

    try:
        log_entry = {"time": get_minsk_time(), "status": "🟢 Ок"}
        old_snap, is_table_error = snapshot_from_current(info["current"])

        outcome = check_item_snapshots(
            info["package_id"],
            info["geo"],
            old_snap,
            info.get("history", []),
            is_table_error,
            label_style="web",
            fetcher=fetcher,
        )
        new_snap = outcome.new_snapshot
        result = outcome.result

        if result.has_changes:
            updates = 1
            changed = result.changed
            text_changes_payload = result.text_payload

            info.setdefault("history", []).append(info["current"])
            info["current"] = current_dict_from_snapshot(new_snap)
            apply_current_metadata(info["current"], outcome.metadata)
            log_entry["status"] = f"🔴 Изменение ({', '.join(changed)})"

        elif result.is_table_error:
            info["current"] = current_dict_from_snapshot(new_snap)
            apply_current_metadata(info["current"], outcome.metadata)
            log_entry["status"] = "🟢 Исправление ошибки"
        else:
            fill_missing_assets(info["current"], new_snap)
            apply_current_metadata(info["current"], outcome.metadata)

        info.setdefault("check_log", []).append(log_entry)
        info["check_log"] = info["check_log"][-5:]
    except Exception as e:
        label = item_key or f"{info.get('package_id', 'unknown')}_{info.get('geo', 'unknown')}"
        print(f"Ошибка проверки {label}: {e}")
        log_entry = {"time": get_minsk_time(), "status": "❌ Ошибка"}
        info.setdefault("check_log", []).append(log_entry)
        info["check_log"] = info["check_log"][-5:]

    return updates, changed, text_changes_payload, outcome
