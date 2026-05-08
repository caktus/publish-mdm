import dagster as dg

from dagster_publish_mdm.assets import mdm_devices
from dagster_publish_mdm.assets.tailscale import tailscale_devices
from dagster_publish_mdm.resources.tailscale import TailscaleResource

all_assets = dg.load_assets_from_modules([tailscale_devices, mdm_devices])
tailscale_schedule = dg.ScheduleDefinition(
    name="tailscale_schedule",
    target=dg.AssetSelection.groups("tailscale_assets"),
    cron_schedule="*/30 * * * *",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)
mdm_schedule = dg.ScheduleDefinition(
    name="mdm_schedule",
    target=dg.AssetSelection.groups("mdm_assets"),
    cron_schedule="*/30 * * * *",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)
mdm_job = dg.define_asset_job(name="mdm_job", selection="push_mdm_device_config")
sync_fleets_job = dg.define_asset_job(name="sync_fleets_job", selection="sync_and_push_mdm_devices")
regenerate_collect_qr_codes_job = dg.define_asset_job(
    name="regenerate_collect_qr_codes_job",
    selection="regenerate_collect_qr_codes_and_push_to_devices",
)

tailscale_device_deletion_schedule = dg.ScheduleDefinition(
    name="tailscale_device_deletion_schedule",
    target=dg.AssetSelection.groups("tailscale_device_prunning_assets")
    | dg.AssetSelection.assets("tailscale_device_snapshot"),
    cron_schedule="0 16 * * *",  # Once a day at 4PM UTC
    default_status=dg.DefaultScheduleStatus.STOPPED,
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
    schedules=[tailscale_schedule, mdm_schedule, tailscale_device_deletion_schedule],
    jobs=[mdm_job, sync_fleets_job, regenerate_collect_qr_codes_job],
)
