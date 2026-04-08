import structlog
from django.core.management.base import BaseCommand, CommandError

from apps.mdm.mdms import AndroidEnterprise

logger = structlog.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Configure AMAPI Pub/Sub infrastructure for the Android Enterprise enterprise. "
        "Creates the Pub/Sub topic and subscription (if they do not exist) and grants "
        "Android Device Policy the right to publish to the topic. "
        "The topic and subscription names are derived from the service account credentials "
        "and the current ENVIRONMENT setting: "
        "projects/{project_id}/topics/publish-mdm-{environment} and "
        "projects/{project_id}/subscriptions/publish-mdm-{environment}. "
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
        if not mdm.has_valid_service_account_file:
            raise CommandError(
                "Android Enterprise is not configured. Set ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE."
            )

        push_endpoint_domain = options["push_endpoint_domain"]
        mdm.configure_pubsub(push_endpoint_domain=push_endpoint_domain)
        self.stdout.write(
            self.style.SUCCESS(
                f"Pub/Sub topic '{mdm.pubsub_topic}' and subscription "
                f"'{mdm.pubsub_subscription}' configured."
                f"\nAndroid Device Policy has been granted the publisher role."
            )
        )
