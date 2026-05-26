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
