from pathlib import Path


def test_current_aso_audit_stays_site_only():
    root = Path(__file__).resolve().parents[1]

    assert "analyze_current_aso" in (root / "app.py").read_text()
    assert "analyze_current_aso" not in (root / "bot.py").read_text()


def test_google_sheets_load_errors_use_compatibility_helper():
    root = Path(__file__).resolve().parents[1]
    app_source = (root / "app.py").read_text()

    assert "def repo_load_errors" in app_source
    assert "load_errors = repo_load_errors(repo)" in app_source
    assert "if repo.load_errors:" not in app_source


def test_site_checks_save_before_telegram_notifications():
    root = Path(__file__).resolve().parents[1]
    app_source = (root / "app.py").read_text()
    mass_check_block = app_source[
        app_source.index("if st.button(\n    \"🔍 Проверить все локали\""):
        app_source.index("# --- ФИЛЬТРАЦИЯ И ГРУППИРОВКА ---")
    ]
    group_check_block = app_source[
        app_source.index("if st.button(\n                        f\"Проверить локали"):
        app_source.index("with col2:")
    ]
    single_locale_block = app_source[
        app_source.index("if st.button(\"Проверить локаль\""):
        app_source.index("with c3:")
    ]

    assert mass_check_block.index("save_apps_or_show_error") < mass_check_block.index("telegram.send_message")
    assert group_check_block.index("save_apps_or_show_error") < group_check_block.index("telegram.send_message")
    assert group_check_block.index("telegram.send_document") < group_check_block.index("gemini.analyze_batched_changes")
    assert single_locale_block.index("save_apps_or_show_error") < single_locale_block.index("send_single_locale_alert")


def test_legacy_json_state_is_not_used():
    root = Path(__file__).resolve().parents[1]
    code_paths = [
        root / "app.py",
        root / "bot.py",
        *sorted((root / "core").glob("*.py")),
        *sorted((root / "sheets").glob("*.py")),
    ]

    assert not (root / "apps_history.json").exists()
    assert all("apps_history" not in path.read_text() for path in code_paths)


def test_site_ui_hides_neutral_ok_badges():
    root = Path(__file__).resolve().parents[1]
    app_source = (root / "app.py").read_text()

    assert 'return "🟢 Ок"' not in app_source
    assert "def is_neutral_status" in app_source
    assert "if is_neutral_status(status):" in app_source
    assert "append_status_label(" in app_source
