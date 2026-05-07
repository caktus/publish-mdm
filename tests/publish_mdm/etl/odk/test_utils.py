"""Tests for apps.publish_mdm.etl.odk.utils."""

from django.test import override_settings

from apps.publish_mdm.etl.odk.utils import get_default_collect_settings_field_values


class TestGetDefaultCollectSettingsFieldValues:
    """Unit tests for get_default_collect_settings_field_values()."""

    @override_settings(DEFAULT_COLLECT_SETTINGS=None)
    def test_returns_empty_dict_when_setting_is_none(self):
        assert get_default_collect_settings_field_values() == {}

    @override_settings(DEFAULT_COLLECT_SETTINGS="not a dict")
    def test_returns_empty_dict_when_setting_is_not_a_dict(self):
        assert get_default_collect_settings_field_values() == {}

    @override_settings(DEFAULT_COLLECT_SETTINGS={})
    def test_returns_empty_dict_for_empty_setting(self):
        assert get_default_collect_settings_field_values() == {}

    @override_settings(
        DEFAULT_COLLECT_SETTINGS={
            "general": {"app_language": "en", "font_size": "25", "appTheme": "dark_theme"},
            "admin": {"edit_saved": False},
        }
    )
    def test_flattens_nested_dict(self):
        """Nested dicts are flattened to {section}_{key} field names."""
        result = get_default_collect_settings_field_values()
        assert result == {
            "general_app_language": "en",
            "general_font_size": "25",
            "admin_edit_saved": False,
            "general_app_theme": "dark_theme",
        }

    @override_settings(
        DEFAULT_COLLECT_SETTINGS={
            "general": {
                "server_url": "https://central.example.com",
                "username": "user",
                "app_language": "en",
            },
            "project": {"name": "My Project", "color": "#abc123"},
            "admin": {"admin_pw": "secret", "edit_saved": False},
        }
    )
    def test_excludes_dynamic_keys(self):
        """server_url, username, project.name, and admin_pw are excluded from the result."""
        result = get_default_collect_settings_field_values()
        assert "general_server_url" not in result
        assert "general_username" not in result
        assert "project_name" not in result
        assert "admin_admin_pw" not in result
        # Non-dynamic keys in the same sections are still included
        assert result["general_app_language"] == "en"
        assert result["project_color"] == "#abc123"
        assert result["admin_edit_saved"] is False

    @override_settings(
        DEFAULT_COLLECT_SETTINGS={
            "general": {"app_language": "en"},
            "bad_section": "not a dict",
        }
    )
    def test_skips_sections_with_non_dict_values(self):
        """Sections whose value is not a dict are silently skipped."""
        result = get_default_collect_settings_field_values()
        assert "general_app_language" in result
        # bad_section should produce no keys
        assert not any(k.startswith("bad_section") for k in result)

    @override_settings(
        DEFAULT_COLLECT_SETTINGS={
            "admin": {"edit_saved": False, "send_finalized": False},
        }
    )
    def test_includes_boolean_false_values(self):
        """Boolean False values are preserved in the output (not treated as empty/missing)."""
        result = get_default_collect_settings_field_values()
        assert result["admin_edit_saved"] is False
        assert result["admin_send_finalized"] is False
