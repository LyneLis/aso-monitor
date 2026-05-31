from core.app_ids import normalize_app_id


def test_normalize_google_play_package_with_query_params():
    assert (
        normalize_app_id("com.playrix.gardenscapes&pcampaignid=merch_published_cluster&hl=ru")
        == "com.playrix.gardenscapes"
    )


def test_normalize_google_play_url():
    assert (
        normalize_app_id("https://play.google.com/store/apps/details?id=com.playrix.gardenscapes&hl=ru")
        == "com.playrix.gardenscapes"
    )


def test_normalize_app_store_url():
    assert normalize_app_id("https://apps.apple.com/us/app/test/id123456789?l=ru") == "123456789"
