import structlog
from django.core.management.base import BaseCommand
from requests.exceptions import RequestException

from apps.mdm.mdms import get_active_mdm_instance
from apps.mdm.models import Fleet

logger = structlog.getLogger(__name__)


class Command(BaseCommand):
    help = "Create groups in TinyMDM for any Fleets whose mdm_group_id is not set."

    def handle(self, *args, **options):
        fleets = Fleet.objects.filter(
            mdm_group_id__isnull=True, organization__mdm="TinyMDM"
        ).select_related("organization")
        logger.info(f"Creating TinyMDM groups for {len(fleets)} Fleets")

        for fleet in fleets:
            active_mdm = get_active_mdm_instance(fleet.organization)
            if not active_mdm:
                continue
            try:
                active_mdm.create_group(fleet)
            except RequestException:
                logger.debug(
                    "Unable to create TinyMDM group",
                    fleet=fleet,
                    organization=fleet.organization,
                    policy=fleet.policy,
                    group_name=fleet.group_name,
                    exc_info=True,
                )

            try:
                active_mdm.get_enrollment_qr_code(fleet)
            except RequestException:
                logger.debug(
                    "TinyMDM group created but unable to get the enrollment QR code",
                    fleet=fleet,
                    organization=fleet.organization,
                    policy=fleet.policy,
                    group_name=fleet.group_name,
                    mdm_group_id=fleet.mdm_group_id,
                    exc_info=True,
                )

            fleet.save()

            try:
                active_mdm.add_group_to_policy(fleet)
            except RequestException:
                logger.debug(
                    "TinyMDM group created but unable to add it to policy",
                    fleet=fleet,
                    organization=fleet.organization,
                    policy=fleet.policy,
                    group_name=fleet.group_name,
                    mdm_group_id=fleet.mdm_group_id,
                    exc_info=True,
                )
