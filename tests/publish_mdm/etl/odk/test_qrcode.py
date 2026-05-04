import pytest
from django.conf import settings

from apps.publish_mdm.etl.load import generate_and_save_app_user_collect_qrcodes
from apps.publish_mdm.etl.odk.constants import DEFAULT_COLLECT_SETTINGS
from apps.publish_mdm.etl.odk.publish import ProjectAppUserAssignment
from apps.publish_mdm.etl.odk.collect_settings import CollectSettingsSerializer
from apps.publish_mdm.etl.odk.qrcode import (
    build_collect_settings,
    create_app_user_qrcode,
    deep_merge,
)
from tests.publish_mdm.factories import AppUserFactory, ProjectFactory


class TestDeepMerge:
    def test_empty_overrides(self):
        base = {"a": 1, "b": {"c": 2}}
        assert deep_merge(base, {}) == base

    def test_empty_base(self):
        overrides = {"a": 1}
        assert deep_merge({}, overrides) == overrides

    def test_flat_override(self):
        result = deep_merge({"a": 1, "b": 2}, {"b": 99})
        assert result == {"a": 1, "b": 99}

    def test_nested_dict_override(self):
        base = {"admin": {"moving_backwards": True, "edit_saved": False}}
        overrides = {"admin": {"moving_backwards": False}}
        result = deep_merge(base, overrides)
        assert result == {"admin": {"moving_backwards": False, "edit_saved": False}}

    def test_non_dict_value_wins(self):
        """A non-dict value in overrides always replaces the base value."""
        result = deep_merge({"a": {"b": 1}}, {"a": "string"})
        assert result == {"a": "string"}

    def test_base_not_mutated(self):
        base = {"a": {"b": 1}}
        deep_merge(base, {"a": {"b": 2}})
        assert base == {"a": {"b": 1}}


class TestCollectSettings:
    @pytest.fixture
    def app_user(self) -> ProjectAppUserAssignment:
        return ProjectAppUserAssignment(
            projectId=1,
            id=1,
            type=None,
            displayName="10000",
            createdAt="2025-01-07T14:18:37.300Z",
            updatedAt=None,
            deletedAt=None,
            token="token1",
        )

    def test_build_collect_settings(self, app_user):
        collect_settings = build_collect_settings(
            app_user=app_user,
            base_url="https://central",
            project_id=1,
            project_name_prefix="Project",
            language="en",
        )
        assert collect_settings["general"]["server_url"] == "https://central/key/token1/projects/1"
        assert collect_settings["general"]["username"] == app_user.displayName
        assert collect_settings["general"]["app_language"] == "en"
        assert collect_settings["project"]["name"] == "Project: 10000 (en)"

    def test_project_settings_overrides_defaults(self, app_user):
        """project_settings values are merged on top of DEFAULT_COLLECT_SETTINGS."""
        project_settings = {"admin": {"edit_saved": True}, "general": {"font_size": "13"}}
        result = build_collect_settings(
            app_user=app_user,
            base_url="https://central",
            project_id=1,
            project_name_prefix="Project",
            language="en",
            project_settings=project_settings,
        )
        assert result["admin"]["edit_saved"] is True
        assert result["general"]["font_size"] == "13"
        # Other defaults are still present
        assert (
            result["admin"]["moving_backwards"]
            == DEFAULT_COLLECT_SETTINGS["admin"]["moving_backwards"]
        )

    def test_dynamic_fields_override_project_settings(self, app_user):
        """Dynamic fields always win over project_settings."""
        project_settings = {
            "general": {"server_url": "https://attacker.example", "app_language": "zh"},
            "admin": {"admin_pw": "hacked"},
            "project": {"name": "hacked name"},
        }
        result = build_collect_settings(
            app_user=app_user,
            base_url="https://central",
            project_id=1,
            project_name_prefix="Project",
            language="en",
            admin_pw="correct-password",
            project_settings=project_settings,
        )
        assert result["general"]["server_url"] == "https://central/key/token1/projects/1"
        assert result["general"]["app_language"] == "en"
        assert result["admin"]["admin_pw"] == "correct-password"
        assert result["project"]["name"] == "Project: 10000 (en)"

    def test_no_project_settings(self, app_user):
        """When project_settings is None, behaviour is identical to the old code path."""
        result_with_none = build_collect_settings(
            app_user=app_user,
            base_url="https://central",
            project_id=1,
            project_name_prefix="Project",
        )
        result_with_empty = build_collect_settings(
            app_user=app_user,
            base_url="https://central",
            project_id=1,
            project_name_prefix="Project",
            project_settings={},
        )
        assert result_with_none == result_with_empty

    def test_create_app_user_qrcode(self, app_user):
        """Test that the generated QR code includes the correct settings, including admin_pw."""
        kwargs = {
            "app_user": app_user,
            "base_url": "https://central",
            "project_id": 1,
            "project_name_prefix": "Project",
            "language": "en",
            "admin_pw": "secure-password",
        }

        qr_code, collect_settings = create_app_user_qrcode(**kwargs)

        assert qr_code.getvalue()[:4] == b"\x89PNG"
        assert collect_settings == build_collect_settings(**kwargs)
        assert collect_settings["admin"]["admin_pw"] == kwargs["admin_pw"]

    @pytest.mark.django_db
    @pytest.mark.parametrize("app_language", ["", "ar"])
    def test_generate_and_save_app_user_collect_qrcodes(self, app_user, mocker, app_language):
        """When generate_and_save_app_user_collect_qrcodes() is called, it should call
        create_app_user_qrcode with the language arg set to the project's app_language,
        or settings.DEFAULT_APP_LANGUAGE if a app_language is not set on the project.
        """
        project = ProjectFactory(
            app_language=app_language, central_server__base_url="https://central"
        )
        AppUserFactory(name=app_user.displayName, project=project)
        mocker.patch(
            "apps.publish_mdm.etl.odk.publish.PublishService.get_app_users",
            return_value={app_user.displayName: app_user},
        )
        mock_create_app_user_qrcode = mocker.patch(
            "apps.publish_mdm.etl.load.create_app_user_qrcode", wraps=create_app_user_qrcode
        )

        generate_and_save_app_user_collect_qrcodes(project)

        mock_create_app_user_qrcode.assert_called_once()
        mock_call_language = mock_create_app_user_qrcode.mock_calls[0].kwargs["language"]
        if app_language:
            assert mock_call_language == app_language
        else:
            assert mock_call_language == settings.DEFAULT_APP_LANGUAGE

    @pytest.mark.django_db
    def test_generate_and_save_passes_collect_settings(self, app_user, mocker):
        """generate_and_save_app_user_collect_qrcodes() should pass the
        CollectSettingsSerializer output to create_app_user_qrcode as project_settings.
        """
        project = ProjectFactory(
            collect_general_font_size="13",  # non-default value
            central_server__base_url="https://central",
        )
        AppUserFactory(name=app_user.displayName, project=project)
        mocker.patch(
            "apps.publish_mdm.etl.odk.publish.PublishService.get_app_users",
            return_value={app_user.displayName: app_user},
        )
        mock_create_app_user_qrcode = mocker.patch(
            "apps.publish_mdm.etl.load.create_app_user_qrcode", wraps=create_app_user_qrcode
        )

        generate_and_save_app_user_collect_qrcodes(project)

        mock_create_app_user_qrcode.assert_called_once()
        expected_project_settings = CollectSettingsSerializer(project=project).to_dict()
        assert (
            mock_create_app_user_qrcode.mock_calls[0].kwargs["project_settings"]
            == expected_project_settings
        )
        # Verify the non-default font_size is reflected
        assert expected_project_settings["general"]["font_size"] == "13"

    @pytest.mark.django_db
    def test_generate_qrcodes_for_specific_app_users(self, app_user, mocker):
        """When generate_and_save_app_user_collect_qrcodes() is called with the
        app_users arg set, it should only generate QR codes for those app users.
        """
        project = ProjectFactory(central_server__base_url="https://central")
        AppUserFactory.create_batch(3, project=project)
        # Only this AppUser should be updated
        db_app_user = AppUserFactory(name=app_user.displayName, project=project)
        mocker.patch(
            "apps.publish_mdm.etl.odk.publish.PublishService.get_app_users",
            return_value={app_user.displayName: app_user},
        )
        mock_create_app_user_qrcode = mocker.patch(
            "apps.publish_mdm.etl.load.create_app_user_qrcode", wraps=create_app_user_qrcode
        )

        generate_and_save_app_user_collect_qrcodes(project, app_users=[db_app_user])

        mock_create_app_user_qrcode.assert_called_once()
