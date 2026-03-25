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
        "The topic and subscription are automatically derived from the service account "
        "credentials (projects/{project_id}/topics/publish-mdm and "
        "projects/{project_id}/subscriptions/publish-mdm). "
        "The push endpoint is built as https://{domain}/mdm/api/amapi/notifications/?token=<token>. "
        "When --push-endpoint-domain is omitted, the domain is taken from the current Site object."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--push-endpoint-domain",
            default=None,
            help=(
                "Domain (without scheme, e.g. example.com) used to build the full "
                "Pub/Sub push endpoint. HTTPS is always used. "
                "Defaults to the domain from the current Site object."
            ),
        )

    def handle(self, *args, **options):
        mdm = AndroidEnterprise()
        if not mdm.is_configured:
            raise CommandError(
                "Android Enterprise is not configured. "
                "Set ANDROID_ENTERPRISE_ID and "
                "ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE."
            )

        push_endpoint_domain = options["push_endpoint_domain"]
        result = mdm.configure_pubsub(push_endpoint_domain=push_endpoint_domain)
        enabled = result.get("enabledNotificationTypes", [])
        self.stdout.write(
            self.style.SUCCESS(
                f"Pub/Sub notifications configured for enterprise "
                f"'{mdm.enterprise_name}' with topic '{mdm.pubsub_topic}'."
                f"\nEnabled notification types: {', '.join(enabled)}"
            )
        )
