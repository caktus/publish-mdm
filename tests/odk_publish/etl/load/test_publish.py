import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from gspread.utils import ExportFormat

from apps.odk_publish.etl.load import PublishTemplateEvent, publish_form_template
from apps.odk_publish.etl.odk.publish import ProjectAppUserAssignment
from tests.odk_publish.factories import (
    AppUserFormTemplateFactory,
    FormTemplateFactory,
    ProjectFactory,
)
from tests.users.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestPublishFormTemplate:
    """Test full publish_form_template function."""

    def send_message(self, message: str, complete: bool = False):
        pass

    def test_publish(self, mocker, requests_mock):
        project = ProjectFactory(central_server__base_url="https://central", central_id=2)
        form_template = FormTemplateFactory(project=project, form_id_base="staff_registration")
        # Create 2 app users
        user_form1 = AppUserFormTemplateFactory(form_template=form_template, app_user__name="user1")
        user_form2 = AppUserFormTemplateFactory(form_template=form_template, app_user__name="user2")
        event = PublishTemplateEvent(form_template=form_template.id, app_users=["user1"])
        # Mock Gspread download
        mock_gspread_client = mocker.patch("apps.odk_publish.etl.google.gspread_client")
        mock_gspread_client.return_value.open_by_url.return_value.export.return_value = (
            b"file content"
        )
        # Mock rendering the template
        mock_file = SimpleUploadedFile(
            "myform.xlsx", b"file content", content_type=ExportFormat.EXCEL
        )
        mocker.patch(
            "apps.odk_publish.etl.transform.render_template_for_app_user", return_value=mock_file
        )
        # Mock the ODK Central client
        mock_get_version = mocker.patch(
            "apps.odk_publish.etl.odk.publish.PublishService.get_unique_version_by_form_id",
            return_value="2025-02-01-v1",
        )

        assignments = {
            "user1": ProjectAppUserAssignment(
                projectId=project.central_id,
                id=user_form1.app_user.central_id,
                type="field_key",
                displayName="user1",
                createdAt=dt.datetime.now(),
                updatedAt=None,
                deletedAt=None,
                token="token1",
                xml_form_ids=["staff_registration_user1"],
            ),
            "user2": ProjectAppUserAssignment(
                projectId=project.central_id,
                id=user_form2.app_user.central_id,
                type="field_key",
                displayName="user2",
                createdAt=dt.datetime.now(),
                updatedAt=None,
                deletedAt=None,
                token="token1",
                xml_form_ids=["staff_registration_user2"],
            ),
        }
        mock_get_users = mocker.patch(
            "apps.odk_publish.etl.odk.publish.PublishService.get_or_create_app_users",
            return_value=assignments,
        )
        mock_create_or_update_form = mocker.patch(
            "apps.odk_publish.etl.odk.publish.PublishService.create_or_update_form",
            return_value=mocker.Mock(),
        )
        mock_assign_app_users_forms = mocker.patch(
            "apps.odk_publish.etl.odk.publish.PublishService.assign_app_users_forms"
        )
        publish_form_template(event=event, user=UserFactory(), send_message=self.send_message)
        mock_get_users.assert_called_once()
        mock_get_version.assert_called_once_with(xml_form_id_base=form_template.form_id_base)
        mock_create_or_update_form.assert_has_calls(
            [
                mocker.call(
                    definition=b"file content",
                    xml_form_id=user_form1.xml_form_id,
                ),
            ]
        )
        mock_assign_app_users_forms.assert_has_calls(
            [
                mocker.call(app_users=[assignments["user1"]]),
                mocker.call(app_users=[assignments["user2"]]),
            ]
        )
