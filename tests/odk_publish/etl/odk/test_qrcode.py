import pytest

from apps.odk_publish.etl.odk.publish import ProjectAppUserAssignment
from apps.odk_publish.etl.odk.qrcode import build_collect_settings, create_app_user_qrcode


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

        assert qr_code.getvalue()[:4] == b"\x89PNG"  # ✅ Ensure it's a PNG
        assert collect_settings == build_collect_settings(**kwargs)  # ✅ Compare settings

        assert collect_settings["admin_pw"] == "secure-password"
