import dagster as dg

from dagster_publish_mdm.assets.tailscale import tailscale_devices
from dagster_publish_mdm.assets import tinymdm_devices
from dagster_publish_mdm.resources.tailscale import TailscaleResource

all_assets = dg.load_assets_from_modules([tailscale_devices, tinymdm_devices])
tailscale_schedule = dg.ScheduleDefinition(
    name="tailscale_schedule",
    target=dg.AssetSelection.groups("tailscale_assets"),
    cron_schedule="*/30 * * * *",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)
tinymdm_schedule = dg.ScheduleDefinition(
    name="tinymdm_schedule",
    target=dg.AssetSelection.groups("tinymdm_assets"),
    cron_schedule="*/30 * * * *",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)
tinymdm_job = dg.define_asset_job(name="tinymdm_job", selection="push_tinymdm_device_config")

tailscale_device_deletion_schedule = dg.ScheduleDefinition(
    name="tailscale_device_deletion_schedule",
    target=dg.AssetSelection.groups("tailscale_device_prunning_assets") | dg.AssetSelection.assets("tailscale_device_snapshot"),
    cron_schedule="*/10 * * * *", # Currently set to every 10 minutes for testing. Will be set to 0 2 * * * in prod
    execution_timezone="Africa/Tripoli",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)

defs = dg.Definitions(
    assets=all_assets,
    resources={
        "tailscale": TailscaleResource(
            client_id=dg.EnvVar("TAILSCALE_OAUTH_CLIENT_ID"),
            client_secret=dg.EnvVar("TAILSCALE_OAUTH_CLIENT_SECRET"),
            tailnet=dg.EnvVar("TAILSCALE_TAILNET"),
        ),
    },
    schedules=[tailscale_schedule, tinymdm_schedule, tailscale_device_deletion_schedule],
    jobs=[tinymdm_job],
)
