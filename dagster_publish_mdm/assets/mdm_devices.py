import dagster as dg
import django
import requests
from googleapiclient.errors import Error as GoogleAPIClientError

django.setup()


from apps.mdm.mdms import get_active_mdm_instance  # noqa: E402
from apps.mdm.models import Device  # noqa: E402
from apps.publish_mdm.models import Organization  # noqa: E402


class SyncFleetsConfig(dg.Config):
    organization_pk: int


@dg.asset(
    description="Sync specific MDM fleet devices and push device configurations",
)
def sync_and_push_mdm_devices(context: dg.AssetExecutionContext, config: SyncFleetsConfig):
    """Sync an organization's fleets from the MDM and push device configurations."""
    organization = Organization.objects.get(pk=config.organization_pk)
    active_mdm = get_active_mdm_instance(organization=organization)
    if not active_mdm:
        context.log.warning(f"MDM not configured for organization {organization}")
        return
    active_mdm.sync_fleets(push_config=True)
    context.log.info(f"Synced all fleets in {organization}")


@dg.asset(description="Get a list of devices from the MDM", group_name="mdm_assets")
def mdm_device_snapshot(context: dg.AssetExecutionContext):
    for org in Organization.objects.all():
        if active_mdm := get_active_mdm_instance(org):
            try:
                active_mdm.sync_fleets(push_config=False)
            except (GoogleAPIClientError, requests.exceptions.RequestException) as e:
                context.log.error(f"Failed to sync devices for {org} ({org.slug=} {e=!s})")
            else:
                context.log.info(f"Synced all fleets in {org}")
        else:
            context.log.warning(f"MDM not configured for organization {org}")


class DeviceConfig(dg.Config):
    device_pks: list[int]


@dg.asset(description="Push MDM device configuration")
def push_mdm_device_config(context: dg.AssetExecutionContext, config: DeviceConfig):
    """Push the device configuration to the MDM for the specified device PKs."""
    devices = Device.objects.filter(pk__in=config.device_pks).select_related("fleet__organization")
    context.log.info(
        f"Pushing configuration for {devices.count()} device(s)",
        extra={"device_pks": config.device_pks},
    )
    if not devices.exists():
        raise ValueError(f"Devices with IDs {config.device_pks} not found.")
    failed_pks = []
    # Group devices by organization so we use the correct MDM instance per org.
    devices_by_org: dict[Organization, list[Device]] = {}
    for device in devices:
        org = device.fleet.organization
        devices_by_org.setdefault(org, []).append(device)
    for org, org_devices in devices_by_org.items():
        active_mdm = get_active_mdm_instance(organization=org)
        if not active_mdm:
            context.log.warning(f"MDM not configured for organization {org}")
            failed_pks.extend(d.pk for d in org_devices)
            continue
        for device in org_devices:
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
