from core.parsing import _fetch_ios_app_data, _parse_ios_page_html


class FakeResponse:
    def __init__(self, *, json_data=None, text="", status_code=200):
        self._json_data = json_data or {}
        self.text = text
        self.status_code = status_code
        self.encoding = None

    def json(self):
        return self._json_data


def test_parse_ios_page_html_reads_subtitle_from_web_html():
    subtitle, screens = _parse_ios_page_html(
        '<html><p class="subtitle">Sous-titre français</p></html>',
        ["lookup-screen"],
    )

    assert subtitle == "Sous-titre français"
    assert screens == ["lookup-screen"]


def test_fetch_ios_app_data_uses_web_locale_for_subtitle(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if "itunes.apple.com" in url:
            return FakeResponse(
                json_data={
                    "resultCount": 1,
                    "results": [
                        {
                            "trackName": "Test App",
                            "description": "Description",
                            "subtitle": "English subtitle from lookup",
                            "artworkUrl100": "https://example.com/icon.webp",
                            "screenshotUrls": ["https://example.com/screen.webp"],
                        }
                    ],
                }
            )
        return FakeResponse(text='<html><p class="subtitle">Sous-titre français</p></html>')

    monkeypatch.setattr("core.parsing.requests.get", fake_get)

    result = _fetch_ios_app_data("123456789", "fr-CA", "fr-CA", "CA")

    assert result["summary"] == "Sous-titre français"
    assert result["summary"] != "English subtitle from lookup"
    assert calls[1][0] == "https://apps.apple.com/ca/app/id123456789?l=fr-CA"
    assert calls[1][1]["headers"]["Accept-Language"].startswith("fr-CA")


def test_fetch_ios_app_data_does_not_fallback_to_lookup_subtitle(monkeypatch):
    def fake_get(url, **kwargs):
        if "itunes.apple.com" in url:
            return FakeResponse(
                json_data={
                    "resultCount": 1,
                    "results": [
                        {
                            "trackName": "Test App",
                            "description": "Description",
                            "subtitle": "English subtitle from lookup",
                        }
                    ],
                }
            )
        return FakeResponse(text="<html></html>")

    monkeypatch.setattr("core.parsing.requests.get", fake_get)

    result = _fetch_ios_app_data("123456789", "fr-CA", "fr-CA", "CA")

    assert result["summary"] == ""


def test_fetch_ios_app_data_marks_subtitle_unavailable_on_web_error(monkeypatch):
    def fake_get(url, **kwargs):
        if "itunes.apple.com" in url:
            return FakeResponse(
                json_data={
                    "resultCount": 1,
                    "results": [
                        {
                            "trackName": "Test App",
                            "description": "Description",
                            "subtitle": "English subtitle from lookup",
                        }
                    ],
                }
            )
        raise TimeoutError("web page timeout")

    monkeypatch.setattr("core.parsing.requests.get", fake_get)

    result = _fetch_ios_app_data("123456789", "fr-CA", "fr-CA", "CA")

    assert result["summary"] == ""
    assert result["summary_unavailable"] is True
    assert result["screenshots_unavailable"] is True


def test_fetch_ios_app_data_marks_screenshots_unavailable_on_web_429(monkeypatch):
    def fake_get(url, **kwargs):
        if "itunes.apple.com" in url:
            return FakeResponse(
                json_data={
                    "resultCount": 1,
                    "results": [
                        {
                            "trackName": "Test App",
                            "description": "Description",
                            "screenshotUrls": ["https://example.com/lookup-screen.jpg"],
                        }
                    ],
                }
            )
        return FakeResponse(text="Too Many Requests", status_code=429)

    monkeypatch.setattr("core.parsing.requests.get", fake_get)

    result = _fetch_ios_app_data("123456789", "en-US", "en-US", "US")

    assert result["screenshots"] == ["https://example.com/lookup-screen.jpg"]
    assert result["screenshots_unavailable"] is True
