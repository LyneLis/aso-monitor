from typing import Any, Dict, Iterable, Set


def group_ai_audit(data: Dict[str, Dict[str, Any]], keys: Iterable[str]) -> str:
    for key in keys:
        audit = str(data.get(key, {}).get("ai_audit", "") or "").strip()
        if audit:
            return audit
    return ""


def set_group_ai_audit(data: Dict[str, Dict[str, Any]], keys: Iterable[str], audit: str) -> Set[str]:
    updated_keys = set()
    for key in keys:
        if key not in data:
            continue
        data[key]["ai_audit"] = audit
        updated_keys.add(key)
    return updated_keys
