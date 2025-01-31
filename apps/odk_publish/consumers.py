import json
import traceback

import structlog
from channels.generic.websocket import WebsocketConsumer
from django.template.loader import render_to_string
from django.db import transaction
from pydantic import BaseModel, field_validator

from .etl.odk.client import ODKPublishClient
from .models import FormTemplate, FormTemplateVersion

logger = structlog.getLogger(__name__)


class PublishTemplateEvent(BaseModel):
    form_template: int
    app_users: list[str]

    @field_validator("app_users", mode="before")
    @classmethod
    def split_comma_separated_app_users(cls, v):
        if isinstance(v, str):
            return v.split(",")
        return v


class PublishTemplateConsumer(WebsocketConsumer):
    def connect(self):
        logger.debug(f"New connection: {self.channel_layer}")
        super().connect()

    def send_message(self, message: str, error: bool = False):
        if not error:
            logger.debug(f"Sending message: {message}")
        message = render_to_string(
            "odk_publish/ws/message.html", {"message_text": message, "error": error}
        )
        self.send(text_data=message)

    def receive(self, text_data):
        logger.debug("Received message", text_data=f"{text_data[:50]}...")
        event_data = json.loads(text_data)
        try:
            self.publish_form_template(event_data=event_data)
        except Exception as e:
            logger.exception(f"Error publishing form: {e}")
            self.send_message(traceback.format_exc(), error=True)

    def publish_form_template(self, event_data: dict):
        publish_event = PublishTemplateEvent(**event_data)
        self.send_message(f"Received event: {publish_event}")
        form_template = FormTemplate.objects.select_related().get(id=publish_event.form_template)
        app_users = form_template.project.app_users.filter(name__in=publish_event.app_users)
        self.send_message(f'Publishing form template "{form_template.title_base}"')
        user = self.scope["user"]
        client = ODKPublishClient(
            base_url=form_template.project.central_server.base_url,
            project_id=form_template.project.central_id,
        )
        version = client.odk_publish.get_unique_version_by_form_id(
            xml_form_id_base=form_template.form_id_base
        )
        self.send_message(f"Generated version: {version}")
        name = f"{form_template.form_id_base}-{version}.xlsx"
        file = form_template.download_google_sheet(user=user, name=name)
        self.send_message(f"Downloaded template: {file}")
        with transaction.atomic():
            version = FormTemplateVersion.objects.create(
                form_template=form_template, user=user, file=file, version=version
            )
            app_user_versions = version.create_app_user_versions(
                app_users=app_users, send_message=self.send_message
            )
            for app_user_version in app_user_versions:
                form = client.odk_publish.create_or_update_form(
                    xml_form_id=app_user_version.app_user_form_template.xml_form_id,
                    definition=app_user_version.file.read(),
                )
                self.send_message(f"Published form: {form.xmlFormId}")
        self.send_message("Publish complete!")
