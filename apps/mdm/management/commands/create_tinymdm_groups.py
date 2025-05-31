import structlog
from django.core.management.base import BaseCommand
from requests.exceptions import RequestException

from apps.mdm.models import Fleet
from apps.mdm.tasks import add_group_to_policy, create_group, get_tinymdm_session

logger = structlog.getLogger(__name__)


class Command(BaseCommand):
    help = "Create groups in TinyMDM for any Fleets whose mdm_group_id is not set."

    def handle(self, *args, **options):
        if not (session := get_tinymdm_session()):
            return

        fleets = Fleet.objects.filter(mdm_group_id__isnull=True).select_related()
        logger.info(f"Creating TinyMDM groups for {len(fleets)} Fleets")

        for fleet in fleets:
            try:
                create_group(session, fleet)
            except RequestException:
                logger.debug(
                    "Unable to create TinyMDM group",
                    fleet=fleet,
                    organization=fleet.organization,
                    policy=fleet.policy,
                    group_name=fleet.group_name,
                    exc_info=True,
                )

            fleet.save()

            try:
                add_group_to_policy(session, fleet)
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
