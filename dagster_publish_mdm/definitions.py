import dagster as dg

from .assets.tailscale import tailscale_devices
from .assets import tinymdm_devices
from .resources.tailscale import TailscaleResource

all_assets = dg.load_assets_from_modules([tailscale_devices, tinymdm_devices])
tailscale_schedule = dg.ScheduleDefinition(
    name="tailscale_schedule",
    target=dg.AssetSelection.groups("tailscale_assets"),
    cron_schedule="*/30 * * * *",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)
tailscale_schedule = dg.ScheduleDefinition(
    name="tailscale_schedule",
    target=dg.AssetSelection.groups("tinymdm_devices"),
    cron_schedule="*/30 * * * *",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)

defs = dg.Definitions(
    assets=all_assets,
    resources={
        "tailscale": TailscaleResource(
            api_key=dg.EnvVar("TAILSCALE_API_KEY"),
            tailnet=dg.EnvVar("TAILSCALE_TAILNET"),
        ),
    },
    schedules=[tailscale_schedule],
)
