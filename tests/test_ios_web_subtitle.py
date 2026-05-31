from core.parsing import _fetch_ios_app_data, _parse_ios_page_html
from core.parsing import fetch_app_data


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


def test_parse_ios_page_html_ignores_generic_card_subtitle_from_json():
    subtitle, screens = _parse_ios_page_html(
        '<html><script>{"subtitle":"कार्ड"}</script></html>',
        ["lookup-screen"],
    )

    assert subtitle == ""
    assert screens == ["lookup-screen"]


def test_fetch_ios_app_data_uses_web_locale_for_subtitle(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if "itunes.apple.com" in url:
            if "lang=en_us" in url:
                return FakeResponse(
                    json_data={
                        "resultCount": 1,
                        "results": [
                            {
                                "trackName": "Test App",
                                "description": "English Description",
                                "artworkUrl100": "https://example.com/icon.webp",
                                "screenshotUrls": ["https://example.com/screen.webp"],
                            }
                        ],
                    }
                )
            return FakeResponse(
                json_data={
                    "resultCount": 1,
                    "results": [
                        {
                            "trackName": "Test App",
                            "artistName": "Test Publisher",
                            "description": "Description française",
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
    assert result["publisher"] == "Test Publisher"
    assert result["summary"] != "English subtitle from lookup"
    assert calls[1][0] == "https://itunes.apple.com/lookup?id=123456789&country=CA&lang=en_us"
    assert calls[2][0] == "https://apps.apple.com/ca/app/id123456789?l=fr-CA"
    assert calls[2][1]["headers"]["Accept-Language"].startswith("fr-CA")


def test_fetch_ios_app_data_uses_english_web_subtitle_when_locale_has_noise(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if "itunes.apple.com" in url:
            if "lang=en_us" in url:
                return FakeResponse(
                    json_data={
                        "resultCount": 1,
                        "results": [
                            {
                                "trackName": "Cardscapes",
                                "description": "English description",
                                "artworkUrl100": "https://example.com/icon.webp",
                                "screenshotUrls": ["https://example.com/screen.webp"],
                            }
                        ],
                    }
                )
            return FakeResponse(
                json_data={
                    "resultCount": 1,
                    "results": [
                        {
                            "trackName": "Cardscapes Localized",
                            "description": "Localized description",
                            "artworkUrl100": "https://example.com/icon.webp",
                            "screenshotUrls": ["https://example.com/screen.webp"],
                        }
                    ],
                }
            )
        if "l=hi-IN" in url:
            return FakeResponse(text='<html><script>{"subtitle":"कार्ड"}</script></html>')
        return FakeResponse(text='<html><p class="subtitle">Relaxing jigsaw puzzles</p></html>')

    monkeypatch.setattr("core.parsing.requests.get", fake_get)

    result = _fetch_ios_app_data("123456789", "hi-IN", "hi-IN", "IN")

    assert result["title"] == "Cardscapes Localized"
    assert result["description"] == "Localized description"
    assert result["summary"] == "Relaxing jigsaw puzzles"
    assert result["summary_unavailable"] is False
    assert calls[1][0] == "https://itunes.apple.com/lookup?id=123456789&country=IN&lang=en_us"
    assert calls[2][0] == "https://apps.apple.com/in/app/id123456789?l=hi-IN"
    assert calls[3][0] == "https://apps.apple.com/in/app/id123456789?l=en-US"


def test_fetch_ios_app_data_uses_english_web_subtitle_when_lookup_is_unlocalized(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if "itunes.apple.com" in url:
            return FakeResponse(
                json_data={
                    "resultCount": 1,
                    "results": [
                        {
                            "trackName": "Cardscapes",
                            "description": "English description",
                            "artworkUrl100": "https://example.com/icon.webp",
                            "screenshotUrls": ["https://example.com/screen.webp"],
                        }
                    ],
                }
            )
        if "l=hi-IN" in url:
            return FakeResponse(text='<html><p class="subtitle">रंगीन जिग्सॉ पज़ल पूरा करें!</p></html>')
        return FakeResponse(text='<html><p class="subtitle">Complete colorful jigsaw puzzles!</p></html>')

    monkeypatch.setattr("core.parsing.requests.get", fake_get)

    result = _fetch_ios_app_data("123456789", "hi-IN", "hi-IN", "IN")

    assert result["title"] == "Cardscapes"
    assert result["description"] == "English description"
    assert result["summary"] == "Complete colorful jigsaw puzzles!"
    assert result["summary"] != "रंगीन जिग्सॉ पज़ल पूरा करें!"
    assert calls[0][0] == "https://itunes.apple.com/lookup?id=123456789&country=IN&lang=hi_in"
    assert calls[1][0] == "https://itunes.apple.com/lookup?id=123456789&country=IN&lang=en_us"
    assert calls[2][0] == "https://apps.apple.com/in/app/id123456789?l=en-US"


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
    assert result["summary_unavailable"] is True


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


def test_fetch_app_data_normalizes_google_play_package_id(monkeypatch):
    calls = []

    def fake_gp_app(package_id, **kwargs):
        calls.append((package_id, kwargs))
        return {"title": "Gardenscapes"}

    monkeypatch.setattr("core.parsing.gp_app", fake_gp_app)

    result = fetch_app_data("com.playrix.gardenscapes&pcampaignid=promo&hl=ru", "en-US")

    assert result == {"title": "Gardenscapes"}
    assert calls == [("com.playrix.gardenscapes", {"lang": "en-US", "country": "US"})]
