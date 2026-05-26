from typing import Any, Dict, Iterable, Mapping

ENGLISH_LOCALES = frozenset({"en", "en-us", "en_us", "us"})
PUBLISHER_KEYS = ("publisher", "developer", "developerName", "artistName", "sellerName")


def clean_display_value(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in ("", "nan", "none", "#n/a"):
        return ""
    return text


def publisher_from_fetch(data: Mapping[str, Any]) -> str:
    for key in PUBLISHER_KEYS:
        publisher = clean_display_value(data.get(key))
        if publisher:
            return publisher
    return ""


def apply_current_metadata(current: Dict[str, Any], data: Mapping[str, Any]) -> None:
    publisher = publisher_from_fetch(data)
    if publisher:
        current["publisher"] = publisher


def format_app_label(title: Any, publisher: Any = "", fallback_id: Any = "") -> str:
    clean_title = clean_display_value(title) or clean_display_value(fallback_id)
    clean_publisher = clean_display_value(publisher)
    if clean_title and clean_publisher:
        return f"{clean_title} ({clean_publisher})"
    return clean_title or clean_publisher or clean_display_value(fallback_id)


def is_english_locale(geo: Any) -> bool:
    return clean_display_value(geo).lower() in ENGLISH_LOCALES


def _record_current(record: Mapping[str, Any]) -> Mapping[str, Any]:
    current = record.get("current")
    if isinstance(current, Mapping):
        return current
    return record


def app_label_from_records(records: Iterable[Mapping[str, Any]], fallback_id: Any = "") -> str:
    english_title = ""
    fallback_title = ""
    publisher = ""

    for record in records:
        current = _record_current(record)
        title = clean_display_value(current.get("title") or record.get("title"))
        record_publisher = clean_display_value(current.get("publisher") or record.get("publisher"))

        if not fallback_title and title:
            fallback_title = title
        if not english_title and is_english_locale(record.get("geo")) and title:
            english_title = title
        if not publisher and record_publisher:
            publisher = record_publisher

    return format_app_label(english_title or fallback_title, publisher, fallback_id)


def app_label_from_group(
    data: Mapping[str, Mapping[str, Any]],
    keys: Iterable[str],
    fallback_id: Any = "",
) -> str:
    return app_label_from_records((data[key] for key in keys if key in data), fallback_id)
