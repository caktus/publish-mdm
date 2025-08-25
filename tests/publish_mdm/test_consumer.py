import pytest
from channels.testing import WebsocketCommunicator
from gspread.exceptions import SpreadsheetNotFound
from pytest_django.asserts import assertTemplateUsed

from apps.publish_mdm.consumers import PublishTemplateConsumer
from tests.publish_mdm.factories import FormTemplateFactory
from tests.users.factories import UserFactory


class TestPublishTemplateConsumer:
    """Tests for PublishTemplateConsumer."""

    @pytest.mark.asyncio
    async def test_google_access_error(self, mocker):
        """Ensures get_google_picker() is called if we get a SpreadsheetNotFound
        exception when publishing. The exception is raised by gspread if a user
        has not given us permission to access a file using their Google credentials.
        """
        communicator = WebsocketCommunicator(
            PublishTemplateConsumer.as_asgi(), "/ws/publish-template/"
        )
        connected, subprotocol = await communicator.connect()
        assert connected
        mocker.patch.object(
            PublishTemplateConsumer, "publish_form_template", side_effect=SpreadsheetNotFound()
        )
        google_picker = "google picker html"
        mock_get_google_picker = mocker.patch.object(
            PublishTemplateConsumer, "get_google_picker", return_value=google_picker
        )
        form_template_id = 1

        await communicator.send_json_to({"form_template": form_template_id, "app_users": ""})
        with assertTemplateUsed("publish_mdm/ws/message.html") as cm:
            await communicator.receive_from()

        assert cm.context.get("error")
        assert cm.context.get("message_text", "").startswith("Traceback (most recent call last)")
        mock_get_google_picker.assert_called_with(form_template_id=form_template_id)
        assert cm.context.get("error_summary") == google_picker
        await communicator.disconnect()

    @pytest.mark.django_db
    def test_get_google_picker(self):
        """Tests the get_google_picker method."""
        google_sheet_id = "test123"
        form_template = FormTemplateFactory(
            template_url=f"https://docs.google.com/spreadsheets/d/{google_sheet_id}/edit?usp=drive_web"
        )
        consumer = PublishTemplateConsumer()
        consumer.scope = {"user": UserFactory()}
        with assertTemplateUsed(
            template_name="publish_mdm/ws/form_template_access_form.html"
        ) as cm:
            result = consumer.get_google_picker(form_template.id)
        assert cm.context.get("google_sheet_id") == google_sheet_id
        assert (
            "Unfortunately, we could not access the form in Google Sheets. "
            "Click the button below to grant us access."
        ) in result
