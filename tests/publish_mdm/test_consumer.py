import json
from urllib.parse import urlencode

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.urls import reverse
from google.auth.exceptions import RefreshError
from gspread.exceptions import APIError, SpreadsheetNotFound
from pytest_django.asserts import assertTemplateUsed
from requests import Response

from apps.publish_mdm.consumers import PublishTemplateConsumer
from apps.publish_mdm.utils import get_login_url
from tests.publish_mdm.factories import FormTemplateFactory
from tests.users.factories import UserFactory


@pytest.mark.django_db(transaction=True)
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

    @pytest.mark.asyncio
    async def test_user_does_not_have_access(self, mocker):
        """Ensure a message asking the user to confirm if they have access is
        displayed if an APIError with "The caller does not have permission" is
        raised when trying to download a spreadsheet. The exception is raised
        by gspread if a user does not have access to the spreadsheet.
        """
        communicator = WebsocketCommunicator(
            PublishTemplateConsumer.as_asgi(), "/ws/publish-template/"
        )
        connected, subprotocol = await communicator.connect()
        assert connected

        user = await database_sync_to_async(UserFactory)()
        communicator.scope["user"] = user
        form_template = await database_sync_to_async(FormTemplateFactory)(
            template_url="https://docs.google.com/spreadsheets/d/test123/edit?usp=drive_web"
        )

        def side_effect(*arg, **kwargs):
            response = Response()
            response._content = json.dumps(
                {
                    "error": {
                        "code": 403,
                        "message": "The caller does not have permission",
                        "status": "PERMISSION_DENIED",
                    }
                }
            ).encode()
            try:
                raise APIError(response)
            except APIError as e:
                raise PermissionError from e

        mocker.patch.object(
            PublishTemplateConsumer, "publish_form_template", side_effect=side_effect
        )

        await communicator.send_json_to({"form_template": form_template.pk, "app_users": ""})
        with assertTemplateUsed("publish_mdm/ws/message.html") as cm:
            await communicator.receive_from()

        assert cm.context.get("error")
        assert cm.context.get("message_text", "").startswith("Traceback (most recent call last)")
        error_summary = cm.context.get("error_summary")
        assert error_summary
        assert (
            "Unfortunately, we could not access the form in Google Sheets. "
            'Click the button below to access the Spreadsheet, click "Share" '
            "(or ask someone with permission to do so), and confirm the "
            f'Google user "{user.email}" appears in the list of people with access.'
        ) in error_summary
        # A link to the Google Sheets url of the form template should also be included
        assert f'<a href="{form_template.template_url}"' in error_summary

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_refresh_token_or_scopes_error(self, mocker):
        """Ensure a message asking the user to log in again is displayed if a
        RefreshError or an APIError with "Request had insufficient authentication scopes"
        is raised when trying to download a spreadsheet.
        """
        communicator = WebsocketCommunicator(
            PublishTemplateConsumer.as_asgi(), "/ws/publish-template/"
        )
        connected, subprotocol = await communicator.connect()
        assert connected

        user = await database_sync_to_async(UserFactory)()
        communicator.scope["user"] = user
        form_template = await database_sync_to_async(FormTemplateFactory)()

        def insufficient_auth_scopes(*arg, **kwargs):
            response = Response()
            response._content = json.dumps(
                {
                    "error": {
                        "code": 403,
                        "message": "Request had insufficient authentication scopes.",
                        "status": "PERMISSION_DENIED",
                    }
                }
            ).encode()
            try:
                raise APIError(response)
            except APIError as e:
                raise PermissionError from e

        for side_effect in [insufficient_auth_scopes, RefreshError()]:
            mocker.patch.object(
                PublishTemplateConsumer, "publish_form_template", side_effect=side_effect
            )

            await communicator.send_json_to({"form_template": form_template.pk, "app_users": ""})
            with assertTemplateUsed("publish_mdm/ws/message.html") as cm:
                await communicator.receive_from()

            assert cm.context.get("error")
            assert cm.context.get("message_text", "").startswith(
                "Traceback (most recent call last)"
            )
            error_summary = cm.context.get("error_summary")
            assert error_summary
            assert (
                "Sorry, you need to log in again to be able to publish. "
                "Please click the button below."
            ) in error_summary
            # Summary should also have a link to log out the user then when they
            # log back in they will be redirected back to the publish page
            logout_url = reverse("account_logout")
            publish_url = reverse(
                "publish_mdm:form-template-publish",
                args=[
                    form_template.project.organization.slug,
                    form_template.project.id,
                    form_template.id,
                ],
            )
            login_url = get_login_url(publish_url)
            expected_button_href = f"{logout_url}?{urlencode({'next': login_url})}"
            assert f'<a href="{expected_button_href}"' in error_summary

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_other_exceptions(self, mocker):
        """Other exceptions should not show the summary, just the traceback."""
        communicator = WebsocketCommunicator(
            PublishTemplateConsumer.as_asgi(), "/ws/publish-template/"
        )
        connected, subprotocol = await communicator.connect()
        assert connected

        def other_api_error(*arg, **kwargs):
            response = Response()
            response._content = json.dumps(
                {
                    "error": {
                        "code": 403,
                        "message": "Some other API error",
                        "status": "ERROR",
                    }
                }
            ).encode()
            try:
                raise APIError(response)
            except APIError as e:
                raise PermissionError from e

        for side_effect in [Exception, other_api_error, PermissionError]:
            mocker.patch.object(
                PublishTemplateConsumer, "publish_form_template", side_effect=side_effect
            )

            await communicator.send_json_to({"form_template": 1, "app_users": ""})
            with assertTemplateUsed("publish_mdm/ws/message.html") as cm:
                await communicator.receive_from()

            assert cm.context.get("error")
            assert cm.context.get("message_text", "").startswith(
                "Traceback (most recent call last)"
            )
            assert cm.context.get("error_summary") is None

        await communicator.disconnect()

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
