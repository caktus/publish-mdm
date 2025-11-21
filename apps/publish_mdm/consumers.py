import json
import pprint
import traceback
from urllib.parse import urlencode

import structlog
from channels.generic.websocket import WebsocketConsumer
from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.template.loader import render_to_string
from django.urls import reverse
from google.auth.exceptions import RefreshError
from gspread.exceptions import APIError, SpreadsheetNotFound
from gspread.utils import extract_id_from_url
from requests import Response

from apps.publish_mdm.models import FormTemplate

from .etl.load import PublishTemplateEvent, publish_form_template
from .utils import get_login_url

logger = structlog.getLogger(__name__)


class PublishTemplateConsumer(WebsocketConsumer):
    """Websocket consumer for publishing form templates to ODK Central."""

    def connect(self):
        logger.debug(f"New connection: {self.channel_layer}")
        super().connect()

    def send_message(
        self,
        message: str,
        error: bool = False,
        complete: bool = False,
        error_summary: str | None = None,
    ):
        """Send a message to the browser."""
        if not error:
            logger.debug(f"Sending message: {message}")
        message = render_to_string(
            "publish_mdm/ws/message.html",
            {
                "message_text": message,
                "error": error,
                "complete": complete,
                "error_summary": error_summary,
            },
        )
        self.send(text_data=message)

    def receive(self, text_data):
        """Receive a message from the browser."""
        logger.debug("Received message", text_data=f"{text_data[:50]}...")
        try:
            event_data = json.loads(text_data)
            self.publish_form_template(event_data=event_data)
        except Exception as e:
            if isinstance(e, LookupError):
                logger.debug("Error publishing form", exc_info=True)
            else:
                logger.exception("Error publishing form")
            tbe = traceback.TracebackException.from_exception(exc=e, compact=True)
            message = "".join(tbe.format())
            summary = self.get_error_summary(e, event_data)
            # If the error is from ODK Central, format the error message for easier reading
            if len(e.args) >= 2 and isinstance(e.args[1], Response):
                data = e.args[1].json()
                message = f"ODK Central error:\n\n{pprint.pformat(data)}\n\n{message}"
            self.send_message(message, error=True, error_summary=summary)

    def get_error_summary(self, exc: Exception, event_data: dict):
        """For some exceptions, add a helpful message or instructions that will be
        displayed above the traceback.
        """
        if isinstance(exc, SpreadsheetNotFound):
            # User has not authorized us to access the file using their credentials.
            # Display a message to that effect and a button for them to give us access
            # using the Google Picker
            return self.get_google_picker(form_template_id=event_data.get("form_template"))

        error_message = None
        button = None

        if (is_refresh_error := isinstance(exc, RefreshError)) or (
            # gspread raises an APIError, catches it, then does `raise PermissionError from ...`
            isinstance(exc, PermissionError) and isinstance(exc.__context__, APIError)
        ):
            if (
                is_refresh_error
                or "Request had insufficient authentication scopes"
                in exc.__context__.error["message"]
            ):
                # Either an expired/invalid refresh token, or the user did not
                # check the checkbox to give us access to their Google Drive files
                # when they first logged in. Ask them to log in again
                error_message = (
                    "Sorry, you need to log in again to be able to publish. "
                    "Please click the button below."
                )
                form_template = FormTemplate.objects.get(id=event_data.get("form_template"))
                publish_url = reverse(
                    "publish_mdm:form-template-publish",
                    args=[
                        form_template.project.organization.slug,
                        form_template.project.id,
                        form_template.id,
                    ],
                )
                # Add a link that will log them out then redirect to the login page.
                # User will be taken through the OAuth flow again then redirected
                # back to the publish page
                logout_url = reverse("account_logout")
                login_url = get_login_url(publish_url)
                querystring = urlencode({REDIRECT_FIELD_NAME: login_url})
                button = {
                    "href": f"{logout_url}?{querystring}",
                    "text": "Log in again",
                }
            elif "The caller does not have permission" in exc.__context__.error["message"]:
                # User does not have access to the file in Google Sheets.
                # Display instructions on how to confirm if they have access
                error_message = (
                    "Unfortunately, we could not access the form in Google Sheets. "
                    'Click the button below to access the Spreadsheet, click "Share" '
                    "(or ask someone with permission to do so), and confirm the "
                    f'Google user "{self.scope["user"].email}" appears in the list of '
                    "people with access."
                )
                form_template = FormTemplate.objects.get(id=event_data.get("form_template"))
                button = {"href": form_template.template_url, "text": "Open spreadsheet"}

        if error_message or button:
            context = {
                "error_message": error_message,
                "button": button,
            }
            return render_to_string("publish_mdm/ws/form_template_error_summary.html", context)

    def publish_form_template(self, event_data: dict):
        """Publish a form template to ODK Central and stream progress to the browser."""
        # Parse the event data and raise an error if it's invalid
        publish_event = PublishTemplateEvent(**event_data)
        # Hand off to the ETL process to publish the form template
        publish_form_template(
            event=publish_event, user=self.scope["user"], send_message=self.send_message
        )

    def get_google_picker(self, form_template_id):
        """Gets the HTML for displaying a button for the user to give us permission
        to access a FormTemplate's Google Sheet using their Google credentials.
        """
        form_template = FormTemplate.objects.get(id=form_template_id)
        context = {
            "user": self.scope["user"],
            "google_client_id": settings.GOOGLE_CLIENT_ID,
            "google_scopes": " ".join(settings.SOCIALACCOUNT_PROVIDERS["google"]["SCOPE"]),
            "google_api_key": settings.GOOGLE_API_KEY,
            "google_app_id": settings.GOOGLE_APP_ID,
            "google_sheet_id": extract_id_from_url(form_template.template_url),
        }
        return render_to_string("publish_mdm/ws/form_template_access_form.html", context)
