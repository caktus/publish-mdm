import dagster as dg
import django
import requests

django.setup()

from apps.mdm.mdms import get_active_mdm_instance  # noqa: E402
from apps.mdm.models import Device  # noqa: E402
from apps.publish_mdm.models import Organization  # noqa: E402


@dg.asset(description="Get a list of devices from the MDM", group_name="mdm_assets")
def mdm_device_snapshot():
    for org in Organization.objects.all():
        if active_mdm := get_active_mdm_instance(org):
            active_mdm.sync_fleets(push_config=False, organization=org)


class DeviceConfig(dg.Config):
    device_pks: list[int]


@dg.asset(description="Push MDM device configuration")
def push_mdm_device_config(context: dg.AssetExecutionContext, config: DeviceConfig):
    """Push the device configuration to the MDM for the specified device PKs."""
    devices = Device.objects.filter(pk__in=config.device_pks).select_related(
        "fleet__organization"
    )
    context.log.info(
        f"Pushing configuration for {devices.count()} device(s)",
        extra={"device_pks": config.device_pks},
    )
    if not devices.exists():
        raise ValueError(f"Devices with IDs {config.device_pks} not found.")
    failed_pks = []
    for device in devices:
        org = device.fleet.organization
        if active_mdm := get_active_mdm_instance(org):
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
        else:
            context.log.warning(
                f"MDM not configured for organization {org}. Skipping device {device.device_id}."
            )
    if failed_pks:
        raise ValueError(f"Failed to push configuration for devices: {failed_pks}")
