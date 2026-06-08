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
    assert "with repo.cached_save(db):" in mass_check_block
    assert "updated_keys={key}" in mass_check_block
    assert "updated_keys=db.keys()" not in mass_check_block
    assert group_check_block.index("save_apps_or_show_error") < group_check_block.index("telegram.send_message")
    assert "with repo.cached_save(db):" in group_check_block
    assert "updated_keys={k}" in group_check_block
    assert "updated_keys=keys" not in group_check_block
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


def test_problem_filter_includes_changes():
    root = Path(__file__).resolve().parents[1]
    app_source = (root / "app.py").read_text()
    problem_block = app_source[
        app_source.index("def is_problem_info"):
        app_source.index("def status_priority_for_info")
    ]

    assert "is_change_status(status)" in problem_block


def test_site_manual_checks_send_visual_alerts():
    root = Path(__file__).resolve().parents[1]
    app_source = (root / "app.py").read_text()
    group_check_block = app_source[
        app_source.index("if st.button(\n                        f\"Проверить локали"):
        app_source.index("with col2:")
    ]
    single_locale_alert_block = app_source[
        app_source.index("def send_single_locale_alert"):
        app_source.index("# --- ИНТЕРФЕЙС ---")
    ]

    assert "def send_visual_change_alerts" in app_source
    assert "send_visual_change_alerts(c_id, changed" in single_locale_alert_block
    assert "visual_alerts.append" in group_check_block
    assert "send_visual_change_alerts(" in group_check_block


def test_site_telegram_delivery_failures_are_recorded():
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

    assert "def record_telegram_failure" in app_source
    assert "telegram_failures" in mass_check_block
    assert "record_telegram_failure(data.get(\"keys\"" in mass_check_block
    assert "telegram_failures" in group_check_block
    assert "record_telegram_failure(changed_keys" in group_check_block
    assert "record_telegram_failure({k}" in single_locale_block
