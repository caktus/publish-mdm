import os

import structlog
from django.core.management.base import BaseCommand, CommandError

from apps.mdm.mdms import AndroidEnterprise

logger = structlog.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Configure AMAPI Pub/Sub notifications for the Android Enterprise enterprise. "
        "Creates the Pub/Sub topic and subscription (if they do not exist), grants "
        "Android Device Policy the right to publish to the topic, and patches the "
        "enterprise resource with the topic name. "
        "Reads the pubsub topic from the AMAPI_PUBSUB_TOPIC_NAME environment variable."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--topic",
            default=None,
            help=(
                "Cloud Pub/Sub topic name "
                "(e.g. projects/my-project/topics/my-topic). "
                "Overrides the AMAPI_PUBSUB_TOPIC_NAME environment variable."
            ),
        )
        parser.add_argument(
            "--push-endpoint",
            default=None,
            help=(
                "HTTPS URL that Pub/Sub will POST messages to "
                "(e.g. https://example.com/mdm/api/amapi/notifications/?token=secret). "
                "When omitted a pull subscription is created instead."
            ),
        )
        parser.add_argument(
            "--subscription",
            default=None,
            metavar="SUBSCRIPTION_NAME",
            help=(
                "Fully-qualified Pub/Sub subscription resource name "
                "(e.g. projects/my-project/subscriptions/my-sub). "
                "Defaults to the topic name with '/topics/' replaced by '/subscriptions/'."
            ),
        )
        parser.add_argument(
            "--notification-types",
            nargs="+",
            default=None,
            metavar="TYPE",
            help=(
                "Notification types to enable (space-separated). "
                "Defaults to ENROLLMENT STATUS_REPORT."
            ),
        )

    def handle(self, *args, **options):
        pubsub_topic = options["topic"] or os.getenv("AMAPI_PUBSUB_TOPIC_NAME")
        if not pubsub_topic:
            raise CommandError(
                "Pub/Sub topic not specified. "
                "Set the AMAPI_PUBSUB_TOPIC_NAME environment variable "
                "or pass --topic."
            )

        mdm = AndroidEnterprise()
        if not mdm.is_configured:
            raise CommandError(
                "Android Enterprise is not configured. "
                "Set ANDROID_ENTERPRISE_ID and "
                "ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE."
            )

        notification_types = options["notification_types"]
        push_endpoint = options["push_endpoint"]
        subscription_name = options["subscription"]
        result = mdm.configure_pubsub(
            pubsub_topic,
            notification_types,
            push_endpoint=push_endpoint,
            subscription_name=subscription_name,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Pub/Sub notifications configured for enterprise "
                f"'{mdm.enterprise_name}' with topic '{pubsub_topic}'."
            )
        )
        if result:
            enabled = result.get("enabledNotificationTypes", [])
            self.stdout.write(f"Enabled notification types: {', '.join(enabled)}")
