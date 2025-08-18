import pytest
from django.conf import settings

from apps.publish_mdm.etl.odk.publish import ProjectAppUserAssignment
from apps.publish_mdm.etl.odk.qrcode import build_collect_settings, create_app_user_qrcode
from apps.publish_mdm.etl.load import generate_and_save_app_user_collect_qrcodes

from tests.publish_mdm.factories import AppUserFactory, ProjectFactory


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
