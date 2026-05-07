"""Tests for apps.publish_mdm.etl.odk.serializers.CollectSettingsSerializer."""

import pytest
from django.test import override_settings

from apps.publish_mdm.etl.odk.serializers import CollectSettingsSerializer
from tests.publish_mdm.factories import ProjectFactory


@pytest.mark.django_db
class TestCollectSettingsSerializerNullCollectSettings:
    """Tests for CollectSettingsSerializer.to_dict() when project.collect_settings is None.

    This class covers the fallback path when no CollectSettings model instance is linked.
    The model-backed path is covered by TestCollectSettingsSerializerWithModel below.
    """

    @pytest.fixture
    def project(self):
        return ProjectFactory(collect_settings=None)

    @override_settings(DEFAULT_COLLECT_SETTINGS=None)
    def test_returns_minimal_defaults(self, project):
        """With no CollectSettings and no DEFAULT_COLLECT_SETTINGS, returns minimal defaults."""
        result = CollectSettingsSerializer(project=project).to_dict()
        assert result == {
            "project": {},
            "general": {"app_language": "en"},
            "admin": {"admin_pw": ""},
        }

    @override_settings(
        DEFAULT_COLLECT_SETTINGS={
            "general": {"app_language": "ar", "font_size": "17"},
            "admin": {"edit_saved": False},
        }
    )
    def test_merges_default_collect_settings(self, project):
        """Values from DEFAULT_COLLECT_SETTINGS are merged into the result."""
        result = CollectSettingsSerializer(project=project).to_dict()
        assert result["general"]["app_language"] == "ar"
        assert result["general"]["font_size"] == "17"
        assert result["admin"]["edit_saved"] is False

    @override_settings(DEFAULT_COLLECT_SETTINGS=None)
    def test_admin_pw_injected_from_project(self, project, mocker):
        """admin_pw comes from project.get_admin_pw() even when collect_settings is None."""
        mocker.patch.object(project, "get_admin_pw", return_value="mypw")
        result = CollectSettingsSerializer(project=project).to_dict()
        assert result["admin"]["admin_pw"] == "mypw"

    @override_settings(DEFAULT_COLLECT_SETTINGS=None)
    def test_admin_pw_empty_string_when_not_set(self, project):
        """admin_pw is an empty string when get_admin_pw() returns None."""
        result = CollectSettingsSerializer(project=project).to_dict()
        assert result["admin"]["admin_pw"] == ""

    @override_settings(
        DEFAULT_COLLECT_SETTINGS={
            "general": {"app_language": "fr"},
            "project": {"color": "#abc"},
        }
    )
    def test_only_known_sections_are_merged(self, project):
        """Only 'general', 'project', and 'admin' sections are merged from the setting."""
        result = CollectSettingsSerializer(project=project).to_dict()
        assert result["general"]["app_language"] == "fr"
        assert result["project"]["color"] == "#abc"


@pytest.mark.django_db
class TestCollectSettingsSerializerWithModel:
    """Tests for CollectSettingsSerializer.to_dict() when project.collect_settings is set."""

    def test_project_color_and_icon_included(self):
        """project.color and project.icon from the model are always included."""
        project = ProjectFactory(
            collect_settings__project_color="#ff0000",
            collect_settings__project_icon="T",
        )
        result = CollectSettingsSerializer(project=project).to_dict()
        assert result["project"]["color"] == "#ff0000"
        assert result["project"]["icon"] == "T"

    def test_boolean_general_fields_always_present(self):
        """The 8 boolean general_* fields are always included regardless of value."""
        project = ProjectFactory(
            collect_settings__general_delete_send=True,
            collect_settings__general_default_completed=False,
            collect_settings__general_analytics=True,
            collect_settings__general_high_resolution=False,
        )
        result = CollectSettingsSerializer(project=project).to_dict()
        assert result["general"]["delete_send"] is True
        assert result["general"]["default_completed"] is False
        assert result["general"]["analytics"] is True
        assert result["general"]["high_resolution"] is False
        # Other boolean general fields are also always present
        for key in (
            "external_app_recording",
            "instance_sync",
            "automatic_update",
            "hide_old_form_versions",
        ):
            assert key in result["general"]

    def test_all_admin_keys_present(self):
        """All 33 admin keys defined in the serializer are present in the output."""
        project = ProjectFactory()
        result = CollectSettingsSerializer(project=project).to_dict()
        expected_admin_keys = {
            "admin_pw",
            "edit_saved",
            "send_finalized",
            "view_sent",
            "get_blank",
            "delete_saved",
            "qr_code_scanner",
            "change_server",
            "change_project_display",
            "change_app_theme",
            "change_navigation",
            "maps",
            "form_update_mode",
            "periodic_form_updates_check",
            "automatic_update",
            "hide_old_form_versions",
            "change_autosend",
            "delete_after_send",
            "default_to_finalized",
            "change_constraint_behavior",
            "high_resolution",
            "image_size",
            "guidance_hint",
            "external_app_recording",
            "instance_form_sync",
            "change_form_metadata",
            "analytics",
            "change_app_language",
            "change_font_size",
            "moving_backwards",
            "access_settings",
            "change_language",
            "jump_to",
            "save_mid",
            "save_as",
            "mark_as_finalized",
        }
        assert set(result["admin"].keys()) == expected_admin_keys

    def test_includes_admin_pw(self, mocker):
        """admin_pw from get_admin_pw() is injected into the admin section."""
        project = ProjectFactory()
        mocker.patch.object(project, "get_admin_pw", return_value="secret")
        result = CollectSettingsSerializer(project=project).to_dict()
        assert result["admin"]["admin_pw"] == "secret"

    def test_admin_pw_empty_when_not_set(self):
        """admin_pw is an empty string when get_admin_pw() returns None."""
        project = ProjectFactory()
        result = CollectSettingsSerializer(project=project).to_dict()
        assert result["admin"]["admin_pw"] == ""

    def test_nonblank_string_fields_included(self):
        """Non-blank choice/string fields appear in the output."""
        project = ProjectFactory(
            collect_settings__general_app_language="ar",
            collect_settings__general_app_theme="dark_theme",
            collect_settings__general_font_size="13",
            collect_settings__general_metadata_username="user123",
        )
        result = CollectSettingsSerializer(project=project).to_dict()
        assert result["general"]["app_language"] == "ar"
        assert result["general"]["appTheme"] == "dark_theme"
        assert result["general"]["font_size"] == "13"
        assert result["general"]["metadata_username"] == "user123"

    def test_optional_string_fields_absent_when_blank(self):
        """Optional choice/string fields set to '' are not included in the output."""
        project = ProjectFactory(
            collect_settings__general_font_size="",
            collect_settings__general_autosend="",
            collect_settings__general_app_theme="",
        )
        result = CollectSettingsSerializer(project=project).to_dict()
        assert "font_size" not in result["general"]
        assert "autosend" not in result["general"]
        assert "appTheme" not in result["general"]
        assert "color" not in result["project"]
        assert "icon" not in result["project"]
