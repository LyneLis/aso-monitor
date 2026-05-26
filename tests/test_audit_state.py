from core.audit_state import group_ai_audit, set_group_ai_audit


def test_group_ai_audit_reads_saved_audit_from_any_locale():
    data = {
        "app_en_user": {"ai_audit": ""},
        "app_fr_user": {"ai_audit": "Saved audit"},
    }

    assert group_ai_audit(data, ["app_en_user", "app_fr_user"]) == "Saved audit"


def test_set_group_ai_audit_copies_audit_to_all_group_locales():
    data = {
        "app_en_user": {"ai_audit": ""},
        "app_fr_user": {"ai_audit": "Old audit"},
        "other_app_user": {"ai_audit": "Other audit"},
    }

    updated_keys = set_group_ai_audit(data, ["app_en_user", "app_fr_user", "missing"], "New audit")

    assert updated_keys == {"app_en_user", "app_fr_user"}
    assert data["app_en_user"]["ai_audit"] == "New audit"
    assert data["app_fr_user"]["ai_audit"] == "New audit"
    assert data["other_app_user"]["ai_audit"] == "Other audit"
