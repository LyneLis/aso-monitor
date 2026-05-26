from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

TEXT_LABELS_WEB = frozenset({"Title", "SD", "FD"})
TEXT_LABELS_BOT = frozenset({"Название", "SD", "Subtitle", "FD", "Описание"})


@dataclass
class AppSnapshot:
    title: str = ""
    summary: str = ""
    description: str = ""
    icon: str = ""
    header_image: str = ""
    screenshots: List[str] = field(default_factory=list)


@dataclass
class ChangeResult:
    changed: List[str] = field(default_factory=list)
    is_table_error: bool = False
    is_rollback: bool = False
    text_payload: Optional[Dict[str, str]] = None

    @property
    def has_changes(self) -> bool:
        return bool(self.changed)


def clean_val(val: Any) -> Optional[str]:
    s_val = str(val).strip()
    if s_val.lower() in ("nan", "none", "#n/a", ""):
        return ""
    if "#error" in s_val.lower():
        return None
    return s_val


def snapshot_from_fetch(res: Dict[str, Any]) -> AppSnapshot:
    return AppSnapshot(
        title=str(res.get("title", "")).strip(),
        summary=str(res.get("summary", "")).strip(),
        description=str(res.get("description", "")).strip(),
        icon=str(res.get("icon", "")).strip(),
        header_image=str(res.get("headerImage", res.get("header_image", ""))).strip(),
        screenshots=list(res.get("screenshots") or []),
    )


def snapshot_from_current(current: Dict[str, Any]) -> Tuple[AppSnapshot, bool]:
    old_t = clean_val(current.get("title"))
    old_s = clean_val(current.get("summary"))
    old_d = clean_val(current.get("description"))
    is_table_error = old_t is None or old_s is None or old_d is None
    return (
        AppSnapshot(
            title=old_t or "",
            summary=old_s or "",
            description=old_d or "",
            icon=str(current.get("icon") or "").strip(),
            header_image=str(current.get("header_image") or "").strip(),
            screenshots=list(current.get("screenshots") or []),
        ),
        is_table_error,
    )


def snapshot_from_row(
    title: Any,
    summary: Any,
    description: Any,
    icon: Any,
    header_image: Any,
    screenshots: List[str],
) -> Tuple[AppSnapshot, bool]:
    old_t = clean_val(title)
    old_s = clean_val(summary)
    old_d = clean_val(description)
    is_table_error = old_t is None or old_s is None or old_d is None
    return (
        AppSnapshot(
            title=old_t or "",
            summary=old_s or "",
            description=old_d or "",
            icon=clean_val(icon) or "",
            header_image=clean_val(header_image) or "",
            screenshots=screenshots,
        ),
        is_table_error,
    )


def _is_rollback(
    new: AppSnapshot,
    history: List[dict],
    fields: Tuple[str, ...],
    history_limit: Optional[int] = None,
) -> bool:
    entries = history[-history_limit:] if history_limit else history
    for past in entries:
        if all(getattr(new, f) == past.get(f) for f in fields):
            return True
    return False


def detect_changes(
    old: AppSnapshot,
    new: AppSnapshot,
    history: List[dict],
    *,
    label_style: str = "web",
    is_ios: bool = False,
    history_limit: Optional[int] = None,
) -> ChangeResult:
    result = ChangeResult(is_table_error=False)

    if label_style == "bot":
        rollback_fields = ("title", "summary")
        text_labels = TEXT_LABELS_BOT
    else:
        rollback_fields = ("title", "summary", "description")
        text_labels = TEXT_LABELS_WEB

    changed: List[str] = []

    if label_style == "bot":
        if new.title != old.title:
            changed.append("Название")
        if new.summary != old.summary:
            changed.append("Subtitle" if is_ios else "SD")
        if new.description != old.description:
            changed.append("Описание" if is_ios else "FD")
    else:
        if new.title != old.title:
            changed.append("Title")
        if new.summary != old.summary:
            changed.append("SD")
        if new.description != old.description:
            changed.append("FD")

    if old.icon and old.icon != "nan" and new.icon != old.icon:
        changed.append("Иконка")
    if old.header_image and old.header_image != "nan" and new.header_image != old.header_image:
        changed.append("Feature Graphic")
    if new.screenshots != old.screenshots:
        changed.append("Скриншоты")

    result.changed = changed
    if not changed:
        return result

    result.is_rollback = _is_rollback(new, history, rollback_fields, history_limit)

    if any(label in text_labels for label in changed):
        result.text_payload = {
            "old_t": old.title,
            "new_t": new.title,
            "old_s": old.summary,
            "new_s": new.summary,
            "old_d": old.description,
            "new_d": new.description,
        }

    return result


def detect_changes_with_table_error(
    old: AppSnapshot,
    new: AppSnapshot,
    history: List[dict],
    is_table_error: bool,
    **kwargs: Any,
) -> ChangeResult:
    if is_table_error:
        return ChangeResult(is_table_error=True)
    return detect_changes(old, new, history, **kwargs)


def current_dict_from_snapshot(snap: AppSnapshot) -> Dict[str, Any]:
    return {
        "title": snap.title,
        "summary": snap.summary,
        "description": snap.description,
        "icon": snap.icon,
        "header_image": snap.header_image,
        "screenshots": snap.screenshots,
    }


def fill_missing_assets(current: Dict[str, Any], new: AppSnapshot) -> None:
    if (not current.get("icon") or current.get("icon") == "nan") and new.icon:
        current["icon"] = new.icon
    if (not current.get("header_image") or current.get("header_image") == "nan") and new.header_image:
        current["header_image"] = new.header_image
    if (not current.get("screenshots") or len(current.get("screenshots", [])) == 0) and new.screenshots:
        current["screenshots"] = new.screenshots


def format_single_locale_report(
    package_id: str,
    geo: str,
    old: AppSnapshot,
    new: AppSnapshot,
    timestamp: str,
) -> str:
    return (
        f"ОТЧЕТ ОБ ИЗМЕНЕНИЯХ\nПриложение: {package_id}\nЛокаль: {geo.upper()}\nДата: {timestamp}\n"
        f"{'=' * 40}\n\n--- БЫЛО ---\nНазвание: {old.title}\nSD / Subtitle: {old.summary}\nFD / Описание:\n{old.description}\n\n"
        f"{'-' * 40}\n\n--- СТАЛО ---\nНазвание: {new.title}\nSD / Subtitle: {new.summary}\nFD / Описание:\n{new.description}\n"
    )


def history_entry_from_snapshot(old: AppSnapshot, timestamp: str) -> Dict[str, str]:
    return {
        "title": old.title,
        "summary": old.summary,
        "description": old.description,
        "time": timestamp,
    }
