import re
from urllib.parse import parse_qs, unquote, urlparse


def normalize_app_id(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    parsed = urlparse(text)
    if parsed.scheme and parsed.netloc:
        query = parse_qs(parsed.query)
        if query.get("id"):
            return unquote(query["id"][0]).strip()
        match = re.search(r"/id(\d+)(?:[/?#]|$)", parsed.path)
        if match:
            return match.group(1)

    match = re.search(r"(?:^|/)id(\d+)(?:[/?&#]|$)", text)
    if match:
        return match.group(1)

    if "id=" in text:
        query_text = text.split("?", 1)[1] if "?" in text else text
        query = parse_qs(query_text)
        if query.get("id"):
            return unquote(query["id"][0]).strip()

    return unquote(re.split(r"[?&#]", text, maxsplit=1)[0]).strip()
