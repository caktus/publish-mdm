import dagster as dg
import django
import requests

django.setup()

from apps.mdm.mdms import get_active_mdm_instance  # noqa: E402
from apps.mdm.models import Device, Fleet  # noqa: E402


class SyncFleetsConfig(dg.Config):
    fleet_pks: list[int]


@dg.asset(
    description="Sync specific MDM fleet devices and push device configurations",
    group_name="mdm_assets",
)
def sync_and_push_mdm_devices(context: dg.AssetExecutionContext, config: SyncFleetsConfig):
    """Sync the specified fleets from the MDM and push device configurations.

    Accepts a list of fleet PKs so that callers can limit the sync to a specific
    subset of fleets (e.g. only the fleets belonging to a particular organization).
    """
    active_mdm = get_active_mdm_instance()
    if not active_mdm:
        return
    fleets = Fleet.objects.filter(pk__in=config.fleet_pks)
    context.log.info(
        f"Syncing {fleets.count()} fleet(s)",
        extra={"fleet_pks": config.fleet_pks},
    )
    for fleet in fleets:
        active_mdm.sync_fleet(fleet, push_config=True)
        context.log.info(f"Synced fleet {fleet.name} (pk={fleet.pk})")


@dg.asset(description="Get a list of devices from the MDM", group_name="mdm_assets")
def mdm_device_snapshot():
    if active_mdm := get_active_mdm_instance():
        active_mdm.sync_fleets(push_config=False)


class DeviceConfig(dg.Config):
    device_pks: list[int]


@dg.asset(description="Push MDM device configuration")
def push_mdm_device_config(context: dg.AssetExecutionContext, config: DeviceConfig):
    """Push the device configuration to the MDM for the specified device PKs."""
    devices = Device.objects.filter(pk__in=config.device_pks)
    context.log.info(
        f"Pushing configuration for {devices.count()} device(s)",
        extra={"device_pks": config.device_pks},
    )
    if not devices.exists():
        raise ValueError(f"Devices with IDs {config.device_pks} not found.")
    if active_mdm := get_active_mdm_instance():
        failed_pks = []
        for device in devices:
            try:
                active_mdm.push_device_config(device=device)
                context.log.info(f"Configuration pushed for device {device.device_id}")
            except requests.exceptions.RequestException as e:
                try:
                    error_data = e.response.json() if e.response is not None else None
                except requests.exceptions.JSONDecodeError:
                    error_data = None
                context.log.error(
                    f"Failed to push configuration ({device.device_id=} {device.pk=} {e=!s} "
                    f"{error_data=})"
                )
                failed_pks.append(device.pk)
        if failed_pks:
            raise ValueError(f"Failed to push configuration for devices: {failed_pks}")
