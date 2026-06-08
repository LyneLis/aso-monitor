from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.image_hash import ensure_icon_hashes
from core.compare import (
    AppSnapshot,
    ChangeResult,
    detect_changes_with_table_error,
    snapshot_from_fetch,
)
from core.subtitle import is_valid_subtitle_candidate


@dataclass
class ItemCheckOutcome:
    package_id: str
    geo: str
    old_snapshot: AppSnapshot
    new_snapshot: AppSnapshot
    result: ChangeResult
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def updates(self) -> int:
        return 1 if self.result.has_changes else 0

    @property
    def changed(self) -> List[str]:
        return self.result.changed

    @property
    def text_payload(self) -> Optional[Dict[str, str]]:
        return self.result.text_payload


def check_item_snapshots(
    package_id: str,
    geo: str,
    old_snapshot: AppSnapshot,
    history: List[dict],
    is_table_error: bool,
    *,
    label_style: str,
    is_ios: bool = False,
    history_limit: Optional[int] = None,
    fetcher: Optional[Callable[[str, str], Dict[str, Any]]] = None,
) -> ItemCheckOutcome:
    if fetcher is None:
        from core.parsing import fetch_app_data

        fetcher = fetch_app_data

    is_ios_package = is_ios or str(package_id).isdigit()
    fetched = fetcher(package_id, geo)
    new_snapshot = snapshot_from_fetch(fetched)
    ensure_icon_hashes(old_snapshot, new_snapshot)
    if is_ios_package and fetched.get("summary_unavailable"):
        if is_valid_subtitle_candidate(old_snapshot.summary):
            new_snapshot.summary = old_snapshot.summary
    if is_ios_package and fetched.get("screenshots_unavailable"):
        new_snapshot.screenshots = old_snapshot.screenshots

    result = detect_changes_with_table_error(
        old_snapshot,
        new_snapshot,
        history,
        is_table_error,
        label_style=label_style,
        is_ios=is_ios_package,
        history_limit=history_limit,
    )
    return ItemCheckOutcome(
        package_id=package_id,
        geo=geo,
        old_snapshot=old_snapshot,
        new_snapshot=new_snapshot,
        result=result,
        metadata=fetched,
    )


def add_changed_locale_to_batch(
    batched_alerts: Dict[Tuple[str, str, bool], Dict[str, Any]],
    package_id: str,
    chat_id: str,
    geo: str,
    old_snapshot: AppSnapshot,
    new_snapshot: AppSnapshot,
    changed: List[str],
    text_payload: Optional[Dict[str, str]] = None,
    *,
    is_rollback: bool = False,
    app_display_name: Optional[str] = None,
) -> None:
    is_ios = str(package_id).isdigit()
    batch_key = (package_id, chat_id, is_ios)
    if batch_key not in batched_alerts:
        batched_alerts[batch_key] = {
            "changes": {},
            "texts": {},
            "visuals": [],
            "is_rollback": False,
            "app_display_name": app_display_name or package_id,
        }

    batch = batched_alerts[batch_key]
    if app_display_name:
        batch["app_display_name"] = app_display_name
    batch["changes"][geo] = changed
    if is_rollback:
        batch["is_rollback"] = True

    if "Иконка" in changed:
        batch["visuals"].append({
            "type": "diff",
            "name": "Иконка",
            "old": old_snapshot.icon,
            "new": new_snapshot.icon,
            "geo": geo,
        })
    if "Feature Graphic" in changed:
        batch["visuals"].append({
            "type": "diff",
            "name": "Feature Graphic",
            "old": old_snapshot.header_image,
            "new": new_snapshot.header_image,
            "geo": geo,
        })
    if "Скриншоты" in changed and (old_snapshot.screenshots or new_snapshot.screenshots):
        batch["visuals"].append({
            "type": "screens",
            "old": old_snapshot.screenshots,
            "new": new_snapshot.screenshots,
            "geo": geo,
        })

    if text_payload:
        batch["texts"][geo] = text_payload
