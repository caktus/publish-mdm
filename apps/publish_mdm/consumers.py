import json
import pprint
import traceback

import structlog
from channels.generic.websocket import WebsocketConsumer
from django.conf import settings
from django.template.loader import render_to_string
from gspread.exceptions import SpreadsheetNotFound
from gspread.utils import extract_id_from_url
from requests import Response

from apps.publish_mdm.models import FormTemplate

from .etl.load import PublishTemplateEvent, publish_form_template

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
            summary = None
            if isinstance(e, SpreadsheetNotFound):
                summary = self.get_google_picker(form_template_id=event_data.get("form_template"))
            # If the error is from ODK Central, format the error message for easier reading
            if len(e.args) >= 2 and isinstance(e.args[1], Response):
                data = e.args[1].json()
                message = f"ODK Central error:\n\n{pprint.pformat(data)}\n\n{message}"
            self.send_message(message, error=True, error_summary=summary)

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
