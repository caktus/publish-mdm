import datetime as dt
import json
import os

import structlog
from django.db.models import Q, Subquery, OuterRef, F
from django.utils import timezone
from requests import Session
from requests.adapters import HTTPAdapter
from requests_ratelimiter import LimiterSession
from urllib3.util.retry import Retry

from apps.mdm.models import Device, DeviceSnapshot, DeviceSnapshotApp, Policy
from apps.odk_publish.models import AppUser

logger = structlog.getLogger(__name__)


def get_tinymdm_session() -> Session:
    """
    Creates a requests session suitable for use with the TinyMDM API. Should be
    shared across all requests during a to avoid hitting the rate limit.
    """
    session = LimiterSession(per_second=5)

    headers = {
        # TODO: Move these to secure credential store
        "X-Tinymdm-Manager-Apikey-Public": os.getenv("TINYMDM_APIKEY_PUBLIC"),
        "X-Tinymdm-Manager-Apikey-Secret": os.getenv("TINYMDM_APIKEY_SECRET"),
        "X-Account-Id": os.getenv("TINYMDM_ACCOUNT_ID"),
    }
    if not all(headers.values()):
        logger.warning("TinyMDM API credentials not configured.")
        return None
    session.headers.update(headers)

    retries = Retry(
        total=5,
        backoff_factor=0.1,
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))

    return session


def update_existing_devices(policy: Policy, mdm_devices: list[dict]):
    """
    Updates existing devices in our datatabase based on the full list
    of mdm_devices returned form the TinyMDM API.
    """
    devices_by_id = {device["id"]: device for device in mdm_devices}
    devices_by_serial = {device["serial_number"]: device for device in mdm_devices}

    our_devices = Device.objects.filter(
        Q(policy=policy)
        & (Q(device_id__in=devices_by_id.keys()) | Q(serial_number__in=devices_by_serial.keys()))
    )

    for our_device in our_devices:
        if our_device.device_id:
            mdm_device = devices_by_id.get(our_device.device_id)
        else:
            mdm_device = devices_by_serial.get(our_device.serial_number)
        if not mdm_device:
            # TODO: Remove the device from our database?
            continue
        our_device.serial_number = mdm_device["serial_number"] or ""
        our_device.device_id = mdm_device["id"]
        our_device.name = mdm_device["nickname"] or mdm_device["name"]
        our_device.raw_mdm_device = mdm_device

    logger.debug("Updating existing devices", our_devices=our_devices)
    Device.objects.bulk_update(
        our_devices, fields=["serial_number", "device_id", "raw_mdm_device", "name"]
    )
    return our_devices


def create_new_devices(policy: Policy, mdm_devices: list[dict]):
    """
    Creates new devices in our database based on the mdm_devices
    received from the API. This list must not contain devices that
    already exist in our database.
    """
    mdm_devices_to_create = [
        Device(
            policy=policy,
            serial_number=mdm_device["serial_number"] or "",
            device_id=mdm_device["id"],
            name=mdm_device["nickname"] or mdm_device["name"],
            raw_mdm_device=mdm_device,
        )
        for mdm_device in mdm_devices
    ]
    logger.debug("Creating new devices", mdm_devices_to_create=mdm_devices_to_create)
    Device.objects.bulk_create(mdm_devices_to_create)
    return mdm_devices_to_create


def create_device_snapshots(session: Session, policy: Policy, mdm_devices: list[dict]):
    """ """
    sync_time = timezone.now()

    # Create snapshots for each device
    logger.debug("Creating device snapshots", policy=policy, total_devices=len(mdm_devices))
    snapshots: list[DeviceSnapshot] = []
    for mdm_device in mdm_devices:
        last_sync = dt.datetime.fromtimestamp(mdm_device["last_sync_timestamp"], tz=dt.UTC)
        latitude, longitude = None, None
        geolocation_positions = mdm_device.get("geolocation_positions", [])
        if len(geolocation_positions) > 0:
            latest_coordinates = geolocation_positions[-1]
            latitude = latest_coordinates.get("latitude")
            longitude = latest_coordinates.get("longitude")
        snapshots.append(
            DeviceSnapshot(
                device_id=mdm_device["id"],
                name=mdm_device["nickname"] or mdm_device["name"],
                serial_number=mdm_device["serial_number"] or "",
                manufacturer=mdm_device["manufacturer"],
                os_version=mdm_device["os_version"],
                battery_level=mdm_device["battery_level"],
                enrollment_type=mdm_device["enrollment_type"],
                last_sync=last_sync,
                latitude=latitude,
                longitude=longitude,
                # Non-API fields
                raw_mdm_device=mdm_device,
                synced_at=sync_time,
            )
        )
    snapshots = DeviceSnapshot.objects.bulk_create(snapshots)

    # Create app snapshots for each device
    logger.debug("Creating app snapshots", policy=policy)
    app_snapshots: list[DeviceSnapshotApp] = []
    for snapshot in snapshots:
        url = f"https://www.tinymdm.net/api/v1/devices/{snapshot.device_id}/apps"
        response = session.request("GET", url)
        response.raise_for_status()
        apps = response.json()["results"]
        logger.debug("Creating app snapshots", app_count=len(apps), device_id=snapshot.device_id)
        app_snapshots.extend(
            [
                DeviceSnapshotApp(
                    device_snapshot=snapshot,
                    package_name=app["package_name"],
                    app_name=app["app_name"],
                    version_code=app["version_code"],
                    version_name=app["version_name"],
                )
                for app in apps
            ]
        )
    DeviceSnapshotApp.objects.bulk_create(app_snapshots)


def pull_devices(session: Session, policy: Policy):
    """
    Retrieves devices from TinyMDM and updates or creates the records in our
    database for those devices.
    """
    url = "https://www.tinymdm.net/api/v1/devices"
    querystring = {"policy_id": policy.policy_id, "per_page": 1000}
    logger.info("Pulling devices from TinyMDM", url=url, querystring=querystring)
    response = session.request("GET", url, params=querystring)
    response.raise_for_status()
    mdm_devices = response.json()["results"]
    create_device_snapshots(session=session, policy=policy, mdm_devices=mdm_devices)
    our_devices = update_existing_devices(policy, mdm_devices)
    our_device_ids = {device.device_id for device in our_devices}
    mdm_devices_to_create = [
        mdm_device for mdm_device in mdm_devices if mdm_device["id"] not in our_device_ids
    ]
    create_new_devices(policy, mdm_devices_to_create)
    # Link snapshots to devices
    # Get all snapshots that don't have a device
    qs = DeviceSnapshot.objects.filter(mdm_device_id=None).select_for_update()
    # Get the ID for each snapshot's device_id
    qs = qs.annotate(
        existing_device_id=Subquery(
            Device.objects.filter(device_id=OuterRef("device_id")).values("id")[:1]
        )
    )
    # Update the device_id field with the existing device ID
    num_updated = qs.filter(existing_device_id__isnull=False).update(
        mdm_device_id=F("existing_device_id")
    )
    logger.debug("Set device_id on snapshots", num_updated=num_updated)
    # Update the latest_snapshot_id field for all devices
    Device.objects.annotate(
        new_snapshot_id=Subquery(
            DeviceSnapshot.objects.filter(mdm_device_id=OuterRef("id"))
            .order_by("-synced_at")
            .values("id")[:1]
        )
    ).update(latest_snapshot_id=F("new_snapshot_id"))
    logger.debug("Set latest_snapshot_id on devices")


def push_device_config(session: Session, device: Device):
    """
    Updates "custom_field_1" on the device's user record in TinyMDM
    with the ODK Collect configuration necessary to attach to the devices project.

    https://www.tinymdm.net/mobile-device-management/api/#put-/users/-id-
    """
    logger.debug("Syncing device", device=device)
    if (device.app_user_name) and (
        app_user := AppUser.objects.filter(
            name=device.app_user_name, project=device.policy.project
        ).first()
    ):
        qr_code_data = json.dumps(app_user.qr_code_data, separators=(",", ":"))
    else:
        qr_code_data = ""
    user_id = device.raw_mdm_device["user_id"]
    url = f"https://www.tinymdm.net/api/v1/users/{user_id}"
    device_name = device.raw_mdm_device["nickname"] or device.raw_mdm_device["name"]
    data = {
        "name": f"{device.app_user_name}-{device_name}",
        "custom_field_1": qr_code_data,
    }
    logger.debug("Updating user", url=url, user_id=user_id, data=data)
    response = session.request("PUT", url, json=data)
    response.raise_for_status()
    # Send a message to the user to inform them of the update and trigger a policy reload
    url = "https://www.tinymdm.net/api/v1/actions/message"
    logger.debug("Sending message to device", url=url, user_id=user_id)
    data = {
        "message": (
            f"This device has been configured for Center Number {device.app_user_name}.\n\n"
            "Please close and re-open the HNEC Collect app to see the new project.\n\n"
            "In case of any issues, please open the TinyMDM app and reload the policy "
            "or restart the device."
        ),
        "title": "HNEC Collect Project Update",
        "devices": [device.device_id],
    }
    response = session.request("POST", url, json=data)
    response.raise_for_status()


def sync_policy(session: Session, policy: Policy, push_config: bool = True):
    """
    Synchronizes the remote TinyMDM device list with our database,
    and updates the device (user) configuration in TinyMDM based on the
    configured ODK Central app users.
    """
    logger.info("Syncing policy to TinyMDM devices", policy=policy)
    pull_devices(session, policy)
    if push_config:
        for device in policy.devices.exclude(app_user_name="").select_related("policy").all():
            push_device_config(session=session, device=device)


def sync_policies(push_config: bool = True):
    """
    Synchronizes all configured policies with TinyMDM and updates the applicable
    device configurations.
    """
    logger.info("Syncing policies with TinyMDM")
    session = get_tinymdm_session()
    for policy in Policy.objects.all():
        sync_policy(session=session, policy=policy, push_config=push_config)
