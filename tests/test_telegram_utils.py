from core.telegram import clean_ai_for_telegram, format_changes_report


def test_clean_ai_strips_markdown():
    assert clean_ai_for_telegram("*Bold* _x_ #h `c`") == "Bold x h c"


def test_format_changes_report_includes_locales():
    report = format_changes_report(
        "com.test.app",
        {
            "en-US": {
                "old_t": "Old",
                "new_t": "New",
                "old_s": "Sub old",
                "new_s": "Sub new",
                "old_d": "Desc old",
                "new_d": "Desc new",
            }
        },
    )
    assert "com.test.app" in report
    assert "EN-US" in report
    assert "Desc old" in report
    assert "Desc new" in report
