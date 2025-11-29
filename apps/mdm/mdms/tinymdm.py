import datetime as dt
from functools import cached_property

import requests
import structlog
from django.core.files.base import ContentFile
from django.db.models import F, OuterRef, Q, Subquery
from django.utils import timezone
from requests.adapters import HTTPAdapter
from requests_ratelimiter import LimiterSession
from urllib3.util.retry import Retry

from apps.mdm.models import Device, DeviceSnapshot, DeviceSnapshotApp, Fleet
from apps.publish_mdm.utils import get_secret

from .base import MDM, MDMAPIError

logger = structlog.getLogger(__name__)


class TinyMDMRetry(Retry):
    def is_retry(self, method: str, status_code: int, has_retry_after: bool = False) -> bool:
        """Retry POSTs only on 429 responses."""
        if method.upper() == "POST" and status_code == 429:
            return True
        return super().is_retry(method, status_code, has_retry_after)


class TinyMDM(MDM):
    name = "TinyMDM"

    def __init__(self):
        self.api_errors = []

    @cached_property
    def session(self) -> LimiterSession:
        """
        Creates a requests session suitable for use with the TinyMDM API. Should be
        shared across all requests during a to avoid hitting the rate limit.
        """
        session = LimiterSession(per_second=5)

        headers = {
            # TODO: Move these to secure credential store
            "X-Tinymdm-Manager-Apikey-Public": get_secret("TINYMDM_APIKEY_PUBLIC"),
            "X-Tinymdm-Manager-Apikey-Secret": get_secret("TINYMDM_APIKEY_SECRET"),
            "X-Account-Id": get_secret("TINYMDM_ACCOUNT_ID"),
        }
        if not all(headers.values()):
            logger.warning("TinyMDM API credentials not configured.")
            return None
        session.headers.update(headers)

        retries = TinyMDMRetry(
            total=5,
            backoff_factor=0.1,
            status_forcelist=[429, 500, 502, 503, 504],
            # Don't raise a MaxRetryError if retries are exhausted due to status code;
            # we'll raise a HTTPError using response.raise_for_status() if necessary
            raise_on_status=False,
        )
        session.mount("https://", HTTPAdapter(max_retries=retries))

        return session

    @property
    def is_configured(self):
        return bool(self.session)

    def request(self, method: str, url: str, *args, **kwargs):
        """Makes a TinyMDM API request. In case of an error response, add a api_error
        attribute (a MDMAPIError object) to the exception raised by Response.raise_for_status().
        If a raise_for_status kwarg is passed and it's falsy, this function will not
        raise an exception for an error response, but will instead add an MDMAPIError
        object to the api_errors list.
        """
        raise_for_status = kwargs.pop("raise_for_status", True)
        response = self.session.request(method, url, *args, **kwargs)
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            try:
                error_data = e.response.json() if e.response is not None else None
            except requests.exceptions.JSONDecodeError:
                error_data = None
            status_code = getattr(e.response, "status_code", None)
            api_error = MDMAPIError(
                method=method, url=url, status_code=status_code, error_data=error_data
            )
            logger.debug("TinyMDM API error", api_error=api_error)
            if raise_for_status:
                e.api_error = api_error
                raise
            self.api_errors.append(api_error)
        return response

    def update_existing_devices(self, fleet: Fleet, mdm_devices: list[dict]):
        """
        Updates existing devices in our database based on the full list
        of mdm_devices returned from the TinyMDM API.
        """
        devices_by_id = {device["id"]: device for device in mdm_devices}
        devices_by_serial = {
            device["serial_number"]: device for device in mdm_devices if device["serial_number"]
        }

        our_devices = Device.objects.filter(
            Q(device_id__in=devices_by_id.keys()) | Q(serial_number__in=devices_by_serial.keys())
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
            if our_device.fleet_id != fleet.id:
                logger.debug(
                    "Device seems to be assigned to the wrong Fleet in our database",
                    device=our_device,
                    fleet_id=our_device.fleet_id,
                    correct_fleet_id=fleet.id,
                )

        logger.debug("Updating existing devices", our_devices=our_devices)
        Device.objects.bulk_update(
            our_devices, fields=["serial_number", "device_id", "raw_mdm_device", "name"]
        )
        return our_devices

    def create_new_devices(self, fleet: Fleet, mdm_devices: list[dict]):
        """
        Creates new devices in our database based on the mdm_devices
        received from the API. This list must not contain devices that
        already exist in our database.
        """
        mdm_devices_to_create = [
            Device(
                fleet=fleet,
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

    def create_device_snapshots(self, fleet: Fleet, mdm_devices: list[dict]):
        """ """
        sync_time = timezone.now()

        # Create snapshots for each device
        logger.debug("Creating device snapshots", fleet=fleet, total_devices=len(mdm_devices))
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
        logger.debug("Creating app snapshots", fleet=fleet)
        app_snapshots: list[DeviceSnapshotApp] = []
        for snapshot in snapshots:
            url = f"https://www.tinymdm.net/api/v1/devices/{snapshot.device_id}/apps"
            response = self.request("GET", url)
            apps = response.json()["results"]
            logger.debug(
                "Creating app snapshots", app_count=len(apps), device_id=snapshot.device_id
            )
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

    def pull_devices(self, fleet: Fleet):
        """
        Retrieves devices from TinyMDM and updates or creates the records in our
        database for those devices.
        """
        url = "https://www.tinymdm.net/api/v1/devices"
        querystring = {"group_id": fleet.mdm_group_id, "per_page": 1000}
        logger.info("Pulling devices from TinyMDM", url=url, querystring=querystring)
        response = self.request("GET", url, params=querystring)
        mdm_devices = response.json()["results"]
        self.create_device_snapshots(fleet=fleet, mdm_devices=mdm_devices)
        our_devices = self.update_existing_devices(fleet, mdm_devices)
        our_device_ids = {device.device_id for device in our_devices}
        mdm_devices_to_create = [
            mdm_device for mdm_device in mdm_devices if mdm_device["id"] not in our_device_ids
        ]
        self.create_new_devices(fleet, mdm_devices_to_create)
        # Link snapshots to devices
        # Get all snapshots that don't have a device
        qs = DeviceSnapshot.all_mdms.filter(mdm_device_id=None).select_for_update()
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

    def push_device_config(self, device: Device):
        """
        Updates "custom_field_1" on the device's user record in TinyMDM
        with the ODK Collect configuration necessary to attach to the devices project.

        https://www.tinymdm.net/mobile-device-management/api/#put-/users/-id-
        """
        if not device.raw_mdm_device:
            logger.debug("New device. Cannot sync", device=device)
            return
        logger.debug("Syncing device", device=device)
        user_id = device.raw_mdm_device["user_id"]
        url = f"https://www.tinymdm.net/api/v1/users/{user_id}"
        qr_code_data = device.get_odk_collect_qr_code_string()
        data = {
            "name": device.username,
            "custom_field_1": qr_code_data,
        }
        logger.debug("Updating user", url=url, user_id=user_id, data=data)
        self.request("PUT", url, json=data)
        # Add the user to the MDM group
        url = f"https://www.tinymdm.net/api/v1/groups/{device.fleet.mdm_group_id}/users/{user_id}"
        logger.debug(
            "Adding user to group", url=url, user_id=user_id, group_id=device.fleet.mdm_group_id
        )
        self.request("POST", url, headers={"content-type": "application/json"})
        if qr_code_data:
            # Send a message to the user to inform them of the update and trigger a policy reload
            url = "https://www.tinymdm.net/api/v1/actions/message"
            logger.debug("Sending message to device", url=url, user_id=user_id)
            data = {
                "message": (
                    f"This device has been configured for App User {device.app_user_name}.\n\n"
                    "Please close and re-open the Collect app to see the new project.\n\n"
                    "In case of any issues, please open the TinyMDM app and reload the policy "
                    "or restart the device."
                ),
                "title": "Project Update",
                "devices": [device.device_id],
            }
            self.request("POST", url, json=data)

    def sync_fleet(self, fleet: Fleet, push_config: bool = True):
        """
        Synchronizes the remote TinyMDM device list with our database,
        and updates the device (user) configuration in TinyMDM based on the
        configured ODK Central app users.
        """
        logger.info("Syncing fleet to TinyMDM devices", fleet=fleet)
        self.pull_devices(fleet)
        if push_config:
            for device in fleet.devices.exclude(app_user_name="").select_related("fleet").all():
                self.push_device_config(device=device)

    def sync_fleets(self, push_config: bool = True):
        """
        Synchronizes all configured fleets with TinyMDM and updates the applicable
        device configurations.
        """
        logger.info("Syncing fleets with TinyMDM")
        for fleet in Fleet.objects.filter(mdm_group_id__isnull=False):
            self.sync_fleet(fleet=fleet, push_config=push_config)

    def create_group(self, fleet: Fleet):
        """Creates a group in TinyMDM."""
        logger.info(
            "Creating a group in TinyMDM",
            fleet=fleet,
            organization=fleet.organization,
            policy=fleet.policy,
            group_name=fleet.group_name,
        )
        response = self.request(
            "POST", "https://www.tinymdm.net/api/v1/groups", json={"name": fleet.group_name}
        )
        # Update the Fleet.mdm_group_id field
        fleet.mdm_group_id = response.json()["id"]

    def add_group_to_policy(self, fleet: Fleet):
        """Adds a group to a policy in TinyMDM. If the group was previously in another
        policy it will be moved to the new policy.
        """
        logger.info("Adding the TinyMDM group to its policy", fleet=fleet, policy=fleet.policy)
        self.request(
            "POST",
            f"https://www.tinymdm.net/api/v1/policies/{fleet.policy.policy_id}/members/{fleet.mdm_group_id}",
            headers={"content-type": "application/json"},
        )

    def get_enrollment_qr_code(self, fleet: Fleet):
        """Download the enrollment QR code image for a Fleet and save it in the
        enroll_qr_code field.
        """
        logger.info(
            "Getting the URL for the TinyMDM enrollment QR code", fleet=fleet, policy=fleet.policy
        )
        response = self.request(
            "GET",
            f"https://www.tinymdm.net/api/v1/groups/{fleet.mdm_group_id}/enrollment_qr_code",
            params={"prefix_type": "SERIAL_NUMBER"},
            headers={"content-type": "application/json"},
        )
        qr_code_url = response.json()["enrollment_qr_code_url"]
        logger.info("Downloading TinyMDM enrollment QR code", fleet=fleet, url=qr_code_url)
        response = requests.get(qr_code_url, timeout=10)
        response.raise_for_status()
        # Update the enroll_qr_code field. Do not call Fleet.save()
        fleet.enroll_qr_code.save(f"{fleet}.png", ContentFile(response.content), save=False)

    def delete_group(self, fleet: Fleet) -> bool:
        """Delete a TinyMDM group. If the group has devices either in the database or
        in TinyMDM, it will not be deleted.
        """
        logger.debug("Deleting TinyMDM group", fleet=fleet, group_id=fleet.mdm_group_id)
        if fleet.devices.exists():
            # Fleet has devices in DB. Don't delete
            logger.debug(
                "Cannot delete TinyMDM group because it has devices linked to it in the database",
                fleet=fleet,
                group_id=fleet.mdm_group_id,
            )
            return False
        response = self.request(
            "GET",
            f"https://www.tinymdm.net/api/v1/groups/{fleet.mdm_group_id}/devices",
            raise_for_status=False,
        )
        if response.status_code in (400, 404):
            # Invalid group ID or the group was not found
            logger.debug(
                "Invalid or non-existent TinyMDM group ID",
                fleet=fleet,
                group_id=fleet.mdm_group_id,
                response=response.content,
                status_code=response.status_code,
            )
            return True
        response.raise_for_status()
        if response.json()["results"]:
            # Fleet has devices in TinyMDM. Don't delete
            logger.debug(
                "Cannot delete TinyMDM group because it has devices linked to it in TinyMDM",
                fleet=fleet,
                group_id=fleet.mdm_group_id,
            )
            return False
        # Delete the group in TinyMDM
        self.request("DELETE", f"https://www.tinymdm.net/api/v1/groups/{fleet.mdm_group_id}")
        return True

    def create_user(self, name: str, email: str, fleet: Fleet):
        """Creates a TinyMDM user and adds them to the provided fleet's TinyMDM group."""
        logger.info("Creating a TinyMDM user", name=name, email=email)
        data = {
            "name": name,
            "is_anonymous": False,
            "email": email,
            "send_email": True,
        }
        response = self.request("POST", "https://www.tinymdm.net/api/v1/users", json=data)
        logger.info("Successfully created a TinyMDM user", user=response.content)
        user_id = response.json()["id"]
        logger.info(
            "Adding new TinyMDM user to a group",
            user_id=user_id,
            fleet=fleet,
            group_id=fleet.mdm_group_id,
        )
        self.request(
            "POST",
            f"https://www.tinymdm.net/api/v1/groups/{fleet.mdm_group_id}/users/{user_id}",
            headers={"content-type": "application/json"},
        )

    def check_license_limit(self):
        """Gets the devices limit as per the TinyMDM account's license and the number
        of devices currently enrolled.
        """
        logger.info("Checking TinyMDM license limit")
        response = self.request(
            "GET",
            "https://www.tinymdm.net/api/v1/enterprise/info",
            headers={"content-type": "application/json"},
        )
        limit = response.json()["paid_licence"]
        response = self.request(
            "GET",
            "https://www.tinymdm.net/api/v1/devices",
            headers={"content-type": "application/json"},
        )
        enrolled = response.json()["count"]
        logger.info(
            "TinyMDM license limit check done",
            limit=limit,
            enrolled=enrolled,
            limit_reached=(enrolled >= limit),
        )
        return limit, enrolled
