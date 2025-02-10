import json
import pprint
import traceback

import structlog
from channels.generic.websocket import WebsocketConsumer
from django.template.loader import render_to_string
from requests import Response

from .etl.load import PublishTemplateEvent, publish_form_template

logger = structlog.getLogger(__name__)


class PublishTemplateConsumer(WebsocketConsumer):
    """Websocket consumer for publishing form templates to ODK Central."""

    def connect(self):
        logger.debug(f"New connection: {self.channel_layer}")
        super().connect()

    def send_message(self, message: str, error: bool = False, complete: bool = False):
        """Send a message to the browser."""
        if not error:
            logger.debug(f"Sending message: {message}")
        message = render_to_string(
            "odk_publish/ws/message.html",
            {"message_text": message, "error": error, "complete": complete},
        )
        self.send(text_data=message)

    def receive(self, text_data):
        """Receive a message from the browser."""
        logger.debug("Received message", text_data=f"{text_data[:50]}...")
        try:
            event_data = json.loads(text_data)
            self.publish_form_template(event_data=event_data)
        except Exception as e:
            logger.exception("Error publishing form")
            tbe = traceback.TracebackException.from_exception(
                exc=e,
                capture_locals=True,
                compact=True,
                limit=1,
            )
            message = "".join(tbe.format())
            if len(e.args) >= 2 and isinstance(e.args[1], Response):
                data = e.args[1].json()
                message = f"ODK Central error:\n\n{pprint.pformat(data)}\n\n{message}"
            self.send_message(message, error=True)

    def publish_form_template(self, event_data: dict):
        """Publish a form template to ODK Central and stream progress to the browser."""
        # Parse the event data and raise an error if it's invalid
        publish_event = PublishTemplateEvent(**event_data)
        # Hand off to the ETL process to publish the form template
        publish_form_template(
            event=publish_event, user=self.scope["user"], send_message=self.send_message
        )
