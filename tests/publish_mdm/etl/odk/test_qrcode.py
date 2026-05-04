import pytest

from apps.publish_mdm.etl.load import generate_and_save_app_user_collect_qrcodes
from apps.publish_mdm.etl.odk.collect_settings import CollectSettingsSerializer
from apps.publish_mdm.etl.odk.publish import ProjectAppUserAssignment
from apps.publish_mdm.etl.odk.qrcode import build_collect_settings, create_app_user_qrcode
from tests.publish_mdm.factories import AppUserFactory, ProjectFactory


class TestCollectSettingsSerializer:
    """Unit tests for CollectSettingsSerializer.to_dict()."""

    @pytest.mark.django_db
    def test_includes_app_language(self):
        project = ProjectFactory(collect_general_app_language="ar")
        result = CollectSettingsSerializer(project=project).to_dict()
        assert result["general"]["app_language"] == "ar"

    @pytest.mark.django_db
    def test_includes_admin_pw(self, mocker):
        project = ProjectFactory()
        mocker.patch.object(project, "get_admin_pw", return_value="secret")
        result = CollectSettingsSerializer(project=project).to_dict()
        assert result["admin"]["admin_pw"] == "secret"

    @pytest.mark.django_db
    def test_admin_pw_empty_when_not_set(self):
        project = ProjectFactory()
        result = CollectSettingsSerializer(project=project).to_dict()
        assert result["admin"]["admin_pw"] == ""

    @pytest.mark.django_db
    def test_optional_string_fields_omitted_when_blank(self):
        """Fields with blank=True and default='' are omitted from the output."""
        project = ProjectFactory(collect_general_app_theme="")
        result = CollectSettingsSerializer(project=project).to_dict()
        assert "app_theme" not in result["general"]

    @pytest.mark.django_db
    def test_optional_string_fields_included_when_set(self):
        project = ProjectFactory(collect_general_app_theme="dark_theme")
        result = CollectSettingsSerializer(project=project).to_dict()
        assert result["general"]["app_theme"] == "dark_theme"

    @pytest.mark.django_db
    def test_non_default_font_size_reflected(self):
        project = ProjectFactory(collect_general_font_size="13")
        result = CollectSettingsSerializer(project=project).to_dict()
        assert result["general"]["font_size"] == "13"


class TestBuildCollectSettings:
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

    @pytest.mark.django_db
    def test_build_collect_settings(self, app_user):
        project = ProjectFactory(
            central_id=1,
            collect_general_app_language="en",
            central_server__base_url="https://central",
        )
        collect_settings = build_collect_settings(
            project=project,
            app_user=app_user,
            base_url="https://central",
        )
        assert collect_settings["general"]["server_url"] == "https://central/key/token1/projects/1"
        assert collect_settings["general"]["username"] == app_user.displayName
        assert collect_settings["general"]["app_language"] == "en"
        assert collect_settings["project"]["name"] == f"{project.name}: 10000 (en)"

    @pytest.mark.django_db
    def test_model_fields_reflected_in_output(self, app_user):
        """Non-default model field values appear in the generated settings."""
        project = ProjectFactory(
            central_id=1,
            collect_general_font_size="13",
            collect_admin_edit_saved=True,
            central_server__base_url="https://central",
        )
        result = build_collect_settings(
            project=project,
            app_user=app_user,
            base_url="https://central",
        )
        assert result["general"]["font_size"] == "13"
        assert result["admin"]["edit_saved"] is True

    @pytest.mark.django_db
    def test_server_url_and_username_are_dynamic(self, app_user):
        """server_url and username are always set from app_user, not model fields."""
        project = ProjectFactory(
            central_id=1,
            central_server__base_url="https://central",
        )
        result = build_collect_settings(
            project=project,
            app_user=app_user,
            base_url="https://central",
        )
        assert result["general"]["server_url"] == "https://central/key/token1/projects/1"
        assert result["general"]["username"] == "10000"

    @pytest.mark.django_db
    def test_create_app_user_qrcode(self, app_user):
        """QR code PNG is generated and contains the correct settings."""
        project = ProjectFactory(
            central_id=1,
            collect_general_app_language="en",
            central_server__base_url="https://central",
        )
        qr_code, collect_settings = create_app_user_qrcode(
            project=project,
            app_user=app_user,
            base_url="https://central",
        )
        assert qr_code.getvalue()[:4] == b"\x89PNG"
        assert collect_settings["general"]["server_url"] == "https://central/key/token1/projects/1"

    @pytest.mark.django_db
    def test_generate_and_save_app_user_collect_qrcodes(self, app_user, mocker):
        """generate_and_save_app_user_collect_qrcodes() passes project to create_app_user_qrcode."""
        project = ProjectFactory(
            collect_general_app_language="ar",
            central_server__base_url="https://central",
        )
        AppUserFactory(name=app_user.displayName, project=project)
        mocker.patch(
            "apps.publish_mdm.etl.odk.publish.PublishService.get_app_users",
            return_value={app_user.displayName: app_user},
        )
        mock_create = mocker.patch(
            "apps.publish_mdm.etl.load.create_app_user_qrcode", wraps=create_app_user_qrcode
        )

        generate_and_save_app_user_collect_qrcodes(project)

        mock_create.assert_called_once()
        assert mock_create.mock_calls[0].kwargs["project"] == project

    @pytest.mark.django_db
    def test_generate_and_save_passes_project_language_to_qrcode(self, app_user, mocker):
        """The app language from model field is embedded in the generated QR code."""
        project = ProjectFactory(
            collect_general_app_language="ar",
            central_server__base_url="https://central",
        )
        AppUserFactory(name=app_user.displayName, project=project)
        mocker.patch(
            "apps.publish_mdm.etl.odk.publish.PublishService.get_app_users",
            return_value={app_user.displayName: app_user},
        )
        mocker.patch(
            "apps.publish_mdm.etl.load.create_app_user_qrcode", wraps=create_app_user_qrcode
        )

        generate_and_save_app_user_collect_qrcodes(project)

        # Reload to get saved qr_code_data
        app_user_db = project.app_users.get(name=app_user.displayName)
        assert app_user_db.qr_code_data["general"]["app_language"] == "ar"

    @pytest.mark.django_db
    def test_generate_qrcodes_for_specific_app_users(self, app_user, mocker):
        """When app_users is provided, only those users' QR codes are regenerated."""
        project = ProjectFactory(central_server__base_url="https://central")
        AppUserFactory.create_batch(3, project=project)
        db_app_user = AppUserFactory(name=app_user.displayName, project=project)
        mocker.patch(
            "apps.publish_mdm.etl.odk.publish.PublishService.get_app_users",
            return_value={app_user.displayName: app_user},
        )
        mock_create = mocker.patch(
            "apps.publish_mdm.etl.load.create_app_user_qrcode", wraps=create_app_user_qrcode
        )

        generate_and_save_app_user_collect_qrcodes(project, app_users=[db_app_user])

        mock_create.assert_called_once()
