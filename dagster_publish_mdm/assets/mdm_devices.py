import dagster as dg
import django
import requests
from googleapiclient.errors import Error as GoogleAPIClientError
from pyodk.errors import PyODKError

django.setup()


from apps.mdm.mdms import get_active_mdm_instance  # noqa: E402
from apps.mdm.models import Device  # noqa: E402
from apps.publish_mdm.etl.load import generate_and_save_app_user_collect_qrcodes  # noqa: E402
from apps.publish_mdm.models import CollectSettings, Organization  # noqa: E402


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


class RegenerateCollectQRCodesConfig(dg.Config):
    collect_settings_pk: int


@dg.asset(
    description=(
        "Regenerate QR codes for all projects linked to a CollectSettings and push "
        "device configs to fleet devices whose app_user_name matches a project app user"
    ),
)
def regenerate_collect_qr_codes_and_push_to_devices(
    context: dg.AssetExecutionContext, config: RegenerateCollectQRCodesConfig
):
    """Regenerate QR codes for all projects linked to a CollectSettings.

    For each project whose QR codes are successfully regenerated, push device
    configurations to fleet devices whose app_user_name matches one of the
    project's app users.
    """
    collect_settings = CollectSettings.objects.get(pk=config.collect_settings_pk)
    projects = collect_settings.projects.select_related("central_server").prefetch_related(
        "app_users"
    )
    if projects:
        context.log.info(f"Regenerating QR codes for {len(projects)} projects")
    else:
        context.log.info(f"There are no projects using CollectSettings {collect_settings.pk}")
        return
    active_mdm = get_active_mdm_instance(organization=collect_settings.organization)
    if not active_mdm:
        context.log.warning(f"MDM not configured for organization {collect_settings.organization}")
    for project in projects:
        try:
            generate_and_save_app_user_collect_qrcodes(project)
        except (requests.exceptions.RequestException, PyODKError) as e:
            context.log.error(f"Failed to regenerate QR codes for project {project.name!r} ({e!s})")
            continue
        context.log.info(f"Regenerated QR codes for project {project.name!r}")
        if active_mdm:
            # Push device configs to fleet devices whose app_user_name matches a project app user.
            app_user_names = list(project.app_users.values_list("name", flat=True))
            devices = Device.objects.filter(
                fleet__project=project, app_user_name__in=app_user_names
            )
            if not devices:
                context.log.info(f"There are no devices to push to for project {project.name!r}")
                continue
            for device in devices:
                try:
                    active_mdm.push_device_config(device=device)
                    context.log.info(f"Pushed config to device {device.device_id!r}")
                except (GoogleAPIClientError, requests.exceptions.RequestException) as e:
                    context.log.error(
                        f"Failed to push config ({device.device_id=} {device.pk=} {e!s} "
                    )
