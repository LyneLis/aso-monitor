from core.display import app_label_from_group, app_label_from_records, format_app_label, publisher_from_fetch


def test_publisher_from_fetch_supports_google_play_and_app_store_keys():
    assert publisher_from_fetch({"developer": "GP Studio"}) == "GP Studio"
    assert publisher_from_fetch({"artistName": "iOS Studio"}) == "iOS Studio"
    assert publisher_from_fetch({"sellerName": "Seller LLC"}) == "Seller LLC"


def test_format_app_label_adds_publisher_in_parentheses():
    assert format_app_label("English Title", "Studio", "com.app") == "English Title (Studio)"
    assert format_app_label("", "Studio", "com.app") == "com.app (Studio)"


def test_app_label_from_records_prefers_english_title_and_any_publisher():
    records = [
        {"geo": "fr-FR", "title": "Titre Francais", "publisher": "Studio"},
        {"geo": "en-US", "title": "English Title", "publisher": ""},
    ]

    assert app_label_from_records(records, "com.app") == "English Title (Studio)"


def test_app_label_from_group_reads_current_state():
    data = {
        "app_fr": {"geo": "fr-FR", "current": {"title": "Titre", "publisher": "Studio"}},
        "app_en": {"geo": "en-US", "current": {"title": "English Title", "publisher": ""}},
    }

    assert app_label_from_group(data, ["app_fr", "app_en"], "com.app") == "English Title (Studio)"
