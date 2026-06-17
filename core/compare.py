from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.image_hash import visual_hashes_match

TEXT_LABELS_WEB = frozenset({"Title", "SD", "FD"})
TEXT_LABELS_BOT = frozenset({"Название", "SD", "Subtitle", "FD", "Описание"})


@dataclass
class AppSnapshot:
    title: str = ""
    summary: str = ""
    description: str = ""
    icon: str = ""
    icon_hash: str = ""
    header_image: str = ""
    header_image_hash: str = ""
    screenshots: List[str] = field(default_factory=list)
    screenshot_hashes: List[str] = field(default_factory=list)


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
        icon_hash=str(res.get("iconHash", res.get("icon_hash", ""))).strip(),
        header_image=str(res.get("headerImage", res.get("header_image", ""))).strip(),
        header_image_hash=str(res.get("headerImageHash", res.get("header_image_hash", ""))).strip(),
        screenshots=list(res.get("screenshots") or []),
        screenshot_hashes=list(res.get("screenshotHashes", res.get("screenshot_hashes", [])) or []),
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
            icon_hash=str(current.get("icon_hash") or "").strip(),
            header_image=str(current.get("header_image") or "").strip(),
            header_image_hash=str(current.get("header_image_hash") or "").strip(),
            screenshots=list(current.get("screenshots") or []),
            screenshot_hashes=list(current.get("screenshot_hashes") or []),
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
    icon_hash: Any = "",
    header_image_hash: Any = "",
    screenshot_hashes: Optional[List[str]] = None,
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
            icon_hash=clean_val(icon_hash) or "",
            header_image=clean_val(header_image) or "",
            header_image_hash=clean_val(header_image_hash) or "",
            screenshots=screenshots,
            screenshot_hashes=screenshot_hashes or [],
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


def _has_icon_changed(old: AppSnapshot, new: AppSnapshot) -> bool:
    if not old.icon or old.icon == "nan" or new.icon == old.icon:
        return False
    if old.icon_hash and new.icon_hash:
        return old.icon_hash != new.icon_hash
    return True


def _has_header_image_changed(old: AppSnapshot, new: AppSnapshot) -> bool:
    if not old.header_image or old.header_image == "nan" or new.header_image == old.header_image:
        return False
    if old.header_image_hash and new.header_image_hash:
        return not visual_hashes_match(old.header_image_hash, new.header_image_hash)
    return True


def _has_screenshots_changed(old: AppSnapshot, new: AppSnapshot) -> bool:
    if new.screenshots == old.screenshots:
        return False
    if (
        old.screenshot_hashes
        and new.screenshot_hashes
        and len(old.screenshot_hashes) == len(old.screenshots)
        and len(new.screenshot_hashes) == len(new.screenshots)
        and all(old.screenshot_hashes)
        and all(new.screenshot_hashes)
    ):
        return any(
            not visual_hashes_match(old_hash, new_hash)
            for old_hash, new_hash in zip(old.screenshot_hashes, new.screenshot_hashes)
        )
    return True


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

    if _has_icon_changed(old, new):
        changed.append("Иконка")
    if _has_header_image_changed(old, new):
        changed.append("Feature Graphic")
    if _has_screenshots_changed(old, new):
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
        "icon_hash": snap.icon_hash,
        "header_image": snap.header_image,
        "header_image_hash": snap.header_image_hash,
        "screenshots": snap.screenshots,
        "screenshot_hashes": snap.screenshot_hashes,
    }


def fill_missing_assets(current: Dict[str, Any], new: AppSnapshot) -> None:
    if (not current.get("icon") or current.get("icon") == "nan") and new.icon:
        current["icon"] = new.icon
    if new.icon_hash and (not current.get("icon_hash") or current.get("icon_hash") == new.icon_hash):
        current["icon_hash"] = new.icon_hash
        if new.icon:
            current["icon"] = new.icon
    if (not current.get("header_image") or current.get("header_image") == "nan") and new.header_image:
        current["header_image"] = new.header_image
    if new.header_image_hash and (not current.get("header_image_hash") or current.get("header_image_hash") == new.header_image_hash):
        current["header_image_hash"] = new.header_image_hash
        if new.header_image:
            current["header_image"] = new.header_image
    if (not current.get("screenshots") or len(current.get("screenshots", [])) == 0) and new.screenshots:
        current["screenshots"] = new.screenshots
    if new.screenshot_hashes and (
        not current.get("screenshot_hashes") or current.get("screenshot_hashes") == new.screenshot_hashes
    ):
        current["screenshot_hashes"] = new.screenshot_hashes
        if new.screenshots:
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
