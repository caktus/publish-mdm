import os

import structlog
from django.core.management.base import BaseCommand

from apps.publish_mdm.models import CentralServer

logger = structlog.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Update CentralServer username and password fields using values "
        "from the ODK_CENTRAL_CREDENTIALS environment variable."
    )

    def handle(self, *args, **options):
        for server in os.getenv("ODK_CENTRAL_CREDENTIALS", "").split(","):
            server = server.split(";")
            server = {
                key: value for key, value in [item.split("=") for item in server if "=" in item]
            }
            if all(i in server for i in ("base_url", "username", "password")):
                base_url = server.pop("base_url").rstrip("/")
                updated = CentralServer.objects.filter(base_url=base_url).update(**server)
                logger.info(f"Updated {updated} CentralServers", base_url=base_url)
