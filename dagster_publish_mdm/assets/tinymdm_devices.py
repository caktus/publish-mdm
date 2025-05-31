import dagster as dg
import django

django.setup()

from apps.mdm.tasks import sync_fleets  # noqa: E402


@dg.asset(
    description="Get a list of devices from TinyMDM",
    group_name="tinymdm_assets",
)
def tinymdm_device_snapshot():
    sync_fleets(push_config=False)
