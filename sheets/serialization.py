import json
from typing import Any, Dict, List, Optional

from core.app_ids import normalize_app_id


def parse_json_list(value: Any, default: Optional[List] = None) -> List:
    default = default if default is not None else []
    if value is None:
        return list(default)
    try:
        return json.loads(str(value))
    except Exception:
        return list(default)


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_na(value: Any) -> bool:
    try:
        import pandas as pd

        if pd.isna(value):
            return True
    except Exception:
        pass
    return str(value).strip().lower() in ("nan", "none", "")


def tracked_info_from_row(
    package_id: Any,
    geo: Any,
    chat_id: Any = "",
    *,
    title: Any = "",
    summary: Any = "",
    description: Any = "",
    icon: Any = "",
    icon_hash: Any = "",
    header_image: Any = "",
    publisher: Any = "",
    screenshots: Any = "[]",
    history: Any = "[]",
    check_log: Any = "[]",
    ai_audit: Any = "",
    use_pandas_na: bool = False,
) -> Optional[Dict[str, Any]]:
    if use_pandas_na:
        if _is_na(package_id) or _is_na(geo):
            return None
        p_id, geo_str = normalize_app_id(package_id), _cell_str(geo)
        if not p_id or p_id.lower() == "nan":
            return None
        c_id = "" if _is_na(chat_id) else _cell_str(chat_id)
        current = {
            "title": "" if _is_na(title) else _cell_str(title),
            "summary": "" if _is_na(summary) else _cell_str(summary),
            "description": "" if _is_na(description) else _cell_str(description),
            "publisher": "" if _is_na(publisher) else _cell_str(publisher),
            "icon": "" if _is_na(icon) else _cell_str(icon),
            "icon_hash": "" if _is_na(icon_hash) else _cell_str(icon_hash),
            "header_image": "" if _is_na(header_image) else _cell_str(header_image),
            "screenshots": parse_json_list(screenshots) if not _is_na(screenshots) else [],
        }
        c_log = parse_json_list(check_log) if not _is_na(check_log) else []
        hist = parse_json_list(history) if not _is_na(history) else []
        audit = "" if _is_na(ai_audit) else _cell_str(ai_audit)
    else:
        p_id, geo_str = normalize_app_id(package_id), _cell_str(geo)
        if not p_id or p_id.lower() == "nan" or not geo_str or geo_str.lower() == "nan":
            return None
        c_id = _cell_str(chat_id)
        if c_id.lower() == "nan":
            c_id = ""
        current = {
            "title": _cell_str(title),
            "summary": _cell_str(summary),
            "description": _cell_str(description),
            "publisher": _cell_str(publisher),
            "icon": _cell_str(icon),
            "icon_hash": _cell_str(icon_hash),
            "header_image": _cell_str(header_image),
            "screenshots": parse_json_list(screenshots),
        }
        c_log = parse_json_list(check_log)
        hist = parse_json_list(history)
        audit = _cell_str(ai_audit)

    storage_key = f"{p_id}_{geo_str}_{c_id}"
    return {
        "package_id": p_id,
        "geo": geo_str,
        "chat_id": c_id,
        "current": current,
        "history": hist,
        "check_log": c_log,
        "ai_audit": audit,
        "_storage_key": storage_key,
    }


def tracked_info_to_apps_row(info: Dict[str, Any]) -> Dict[str, str]:
    current = info["current"]
    return {
        "package_id": info["package_id"],
        "geo": info["geo"],
        "chat_id": info.get("chat_id", ""),
        "title": current["title"],
        "summary": current["summary"],
        "description": current["description"],
        "publisher": current.get("publisher", ""),
        "icon": current.get("icon", ""),
        "icon_hash": current.get("icon_hash", ""),
        "header_image": current.get("header_image", ""),
        "screenshots": json.dumps(current.get("screenshots", []), ensure_ascii=False),
        "history": json.dumps(info.get("history", []), ensure_ascii=False),
        "check_log": json.dumps(info.get("check_log", []), ensure_ascii=False),
        "ai_audit": info.get("ai_audit", ""),
    }


def storage_key(info: Dict[str, Any]) -> str:
    return f"{info['package_id']}_{info['geo']}_{info.get('chat_id', '')}"
