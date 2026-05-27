import codecs
import re

GENERIC_SUBTITLE_VALUES = frozenset({
    "card",
    "cards",
    "app",
    "apps",
    "game",
    "games",
    "preview",
    "previews",
    "screenshot",
    "screenshots",
})


def decode_apple_subtitle(raw: str) -> str:
    """unicode_escape, latin-1 mojibake fix, strip quotes."""
    if not raw:
        return ""
    subtitle = raw
    try:
        subtitle = codecs.decode(raw, "unicode_escape")
    except Exception:
        subtitle = raw
    try:
        subtitle = subtitle.encode("latin-1").decode("utf-8")
    except UnicodeEncodeError:
        pass
    return subtitle.strip('"')


def clean_subtitle_candidate(subtitle: str) -> str:
    return re.sub(r"\s+", " ", str(subtitle or "").strip().strip('"'))


def is_valid_subtitle_candidate(subtitle: str) -> bool:
    clean = clean_subtitle_candidate(subtitle)
    if not clean:
        return False
    normalized = clean.lower()
    if normalized in GENERIC_SUBTITLE_VALUES:
        return False
    if normalized.startswith(("http://", "https://")):
        return False
    if any(ch in normalized for ch in "{}[]<>"):
        return False
    return True
