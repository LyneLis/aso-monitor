from core.subtitle import decode_apple_subtitle, is_valid_subtitle_candidate


def test_unicode_escape_japanese():
    assert decode_apple_subtitle("\\u30b2\\u30fc\\u30e0") == "ゲーム"


def test_plain_latin():
    assert decode_apple_subtitle("Relax puzzle game") == "Relax puzzle game"


def test_strips_surrounding_quotes():
    assert decode_apple_subtitle('"Daily challenges"') == "Daily challenges"


def test_empty():
    assert decode_apple_subtitle("") == ""


def test_hindi_card_is_not_valid_subtitle_candidate():
    assert is_valid_subtitle_candidate("कार्ड") is False
    assert is_valid_subtitle_candidate(" कार्ड्स ") is False
