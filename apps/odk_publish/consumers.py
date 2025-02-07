import json
from requests import Response
import traceback
import pprint

import structlog
from channels.generic.websocket import WebsocketConsumer
from django.template.loader import render_to_string
from django.db import transaction
from pydantic import BaseModel, field_validator

from .etl.odk.client import ODKPublishClient
from .models import FormTemplate, FormTemplateVersion

logger = structlog.getLogger(__name__)


class PublishTemplateEvent(BaseModel):
    """Model to parse and validate the publish WebSocket message payload."""

    form_template: int
    app_users: list[str]

    @field_validator("app_users", mode="before")
    @classmethod
    def split_comma_separated_app_users(cls, v):
        """Split comma-separated app users into a list."""
        if isinstance(v, str):
            return v.split(",")
        return v


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
        user = self.scope["user"]
        # Parse the event data and raise an error if it's invalid
        publish_event = PublishTemplateEvent(**event_data)
        self.send_message(f"New {repr(publish_event)}")
        # Get the form template
        form_template = FormTemplate.objects.select_related().get(id=publish_event.form_template)
        self.send_message(f"Publishing next version of {repr(form_template)}")
        # Get the next version by querying ODK Central
        client = ODKPublishClient(
            base_url=form_template.project.central_server.base_url,
            project_id=form_template.project.central_id,
        )
        version = client.odk_publish.get_unique_version_by_form_id(
            xml_form_id_base=form_template.form_id_base
        )
        self.send_message(f"Generated version: {version}")
        # Download the template from Google Sheets
        file = form_template.download_google_sheet(
            user=user, name=f"{form_template.form_id_base}-{version}.xlsx"
        )
        self.send_message(f"Downloaded template: {file}")
        with transaction.atomic():
            # Create the next version
            template_version = FormTemplateVersion.objects.create(
                form_template=form_template, user=user, file=file, version=version
            )
            # Create a version for each app user
            app_users = form_template.project.app_users.filter(name__in=publish_event.app_users)
            app_user_versions = template_version.create_app_user_versions(
                app_users=app_users, send_message=self.send_message
            )
            # Publish each app user version to ODK Central
            for app_user_version in app_user_versions:
                form = client.odk_publish.create_or_update_form(
                    xml_form_id=app_user_version.app_user_form_template.xml_form_id,
                    definition=app_user_version.file.read(),
                )
                self.send_message(f"Published form: {form.xmlFormId}")
        self.send_message(f"Successfully published {version}", complete=True)
