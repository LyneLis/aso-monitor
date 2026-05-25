import codecs


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
