import dagster as dg
import django
import requests

django.setup()

from apps.mdm.models import Device  # noqa: E402
from apps.mdm.tasks import get_tinymdm_session, push_device_config, sync_fleets  # noqa: E402


@dg.asset(description="Get a list of devices from TinyMDM", group_name="tinymdm_assets")
def tinymdm_device_snapshot():
    sync_fleets(push_config=False)


class DeviceConfig(dg.Config):
    device_pks: list[int]


@dg.asset(description="Push TinyMDM device configuration")
def push_tinymdm_device_config(context: dg.AssetExecutionContext, config: DeviceConfig):
    """Push the device configuration to TinyMDM for the specified device PKs."""
    devices = Device.objects.filter(pk__in=config.device_pks)
    context.log.info(
        f"Pushing configuration for {devices.count()} device(s)",
        extra={"device_pks": config.device_pks},
    )
    if not devices.exists():
        raise ValueError(f"Devices with IDs {config.device_pks} not found.")
    if session := get_tinymdm_session():
        failed_pks = []
        for device in devices:
            try:
                push_device_config(session=session, device=device)
                context.log.info(f"Configuration pushed for device {device.device_id}")
            except requests.exceptions.RequestException as e:
                try:
                    error_data = e.response.json() if e.response is not None else None
                except requests.exceptions.JSONDecodeError:
                    error_data = None
                context.log.error(
                    f"Failed to push configuration ({device.device_id=} {device.pk=} {str(e)=} "
                    f"{error_data=})"
                )
                failed_pks.append(device.pk)
        if failed_pks:
            raise ValueError(f"Failed to push configuration for devices: {failed_pks}")
