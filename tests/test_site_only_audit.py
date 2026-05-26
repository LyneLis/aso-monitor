from pathlib import Path


def test_current_aso_audit_stays_site_only():
    root = Path(__file__).resolve().parents[1]

    assert "analyze_current_aso" in (root / "app.py").read_text()
    assert "analyze_current_aso" not in (root / "bot.py").read_text()
