import structlog
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.mdm.mdms import AndroidEnterprise
from apps.publish_mdm.models import Organization

logger = structlog.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Configure AMAPI Pub/Sub infrastructure and register all enrolled Android Enterprise "
        "organizations. "
        "When ANDROID_ENTERPRISE_PUBSUB_TOKEN is set, first creates the Pub/Sub topic and "
        "subscription (if they do not exist) and grants Android Device Policy the right to "
        "publish to the topic. "
        "The topic and subscription names are derived from the service account credentials "
        "and the current ENVIRONMENT setting: "
        "projects/{project_id}/topics/publish-mdm-{environment} and "
        "projects/{project_id}/subscriptions/publish-mdm-{environment}. "
        "The push endpoint is built as https://{domain}/mdm/api/amapi/notifications/?token=<token>. "
        "When --push-endpoint-domain is omitted, the domain is taken from "
        "ANDROID_ENTERPRISE_CALLBACK_DOMAIN (if set), otherwise from the current Site object. "
        "Regardless of whether ANDROID_ENTERPRISE_PUBSUB_TOKEN is set, all enrolled Android "
        "Enterprise organizations are patched: if the token is set they receive the Pub/Sub "
        "topic; if not, their pubsubTopic and enabledNotificationTypes are cleared."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--push-endpoint-domain",
            default=None,
            help=(
                "Domain (without scheme, e.g. example.com) used to build the full "
                "Pub/Sub push endpoint. HTTPS is always used. "
                "Defaults to ANDROID_ENTERPRISE_CALLBACK_DOMAIN if set, "
                "otherwise the domain from the current Site object. "
                "Only used when ANDROID_ENTERPRISE_PUBSUB_TOKEN is set."
            ),
        )

    def handle(self, *args, **options):
        mdm = AndroidEnterprise()
        if not mdm.has_valid_service_account_file:
            raise CommandError(
                "Android Enterprise is not configured. Set ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE."
            )

        if settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN:
            push_endpoint_domain = options["push_endpoint_domain"]
            mdm.configure_pubsub(push_endpoint_domain=push_endpoint_domain)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Pub/Sub topic '{mdm.pubsub_topic}' and subscription "
                    f"'{mdm.pubsub_subscription}' configured."
                    f"\nAndroid Device Policy has been granted the publisher role."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "ANDROID_ENTERPRISE_PUBSUB_TOKEN is not set. "
                    "Skipping Pub/Sub infrastructure setup. "
                    "Enrolled organizations will have their Pub/Sub registration cleared."
                )
            )

        organizations = Organization.objects.filter(
            mdm="Android Enterprise",
            android_enterprise__enterprise_name__gt="",
        ).select_related("android_enterprise")
        org_count = organizations.count()
        if not org_count:
            self.stdout.write("No enrolled Android Enterprise organizations found.")
            return

        self.stdout.write(f"Patching {org_count} enrolled organization(s)...")
        for org in organizations:
            org_mdm = AndroidEnterprise(organization=org)
            org_mdm.patch_enterprise_pubsub()
            self.stdout.write(self.style.SUCCESS(f"  Patched enterprise for organization '{org}'."))

        self.stdout.write(self.style.SUCCESS(f"Done. {org_count} organization(s) patched."))
