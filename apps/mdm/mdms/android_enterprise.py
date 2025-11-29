import datetime as dt
import json
import os
from functools import cached_property

import structlog
from django.db.models import F, OuterRef, Q, Subquery
from django.utils import timezone
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from apps.mdm.models import Device, DeviceSnapshot, DeviceSnapshotApp, Fleet, Policy
from apps.publish_mdm.utils import create_qr_code

from .base import MDM, MDMAPIError

logger = structlog.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/androidmanagement"]


class MDMDevice(dict):
    """A dict for storing device data gotten from the MDM."""

    # An `id` attr will be used to store the device ID extracted from the device name.
    # It avoids adding an "id" key in the raw data dict gotten via the API
    @cached_property
    def id(self):
        return self["name"].split("/")[-1]


class AndroidEnterprise(MDM):
    name = "Android Enterprise"

    def __init__(self):
        self.api_errors = []
        self.enterprise_id = os.getenv("ANDROID_ENTERPRISE_ID")
        self.service_account_file = os.getenv("ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE")

    @property
    def enterprise_name(self):
        return f"enterprises/{self.enterprise_id}"

    @cached_property
    def api(self):
        if not self.is_configured:
            logger.warning("Android Enterprise API credentials not configured.")
            return None
        credentials = Credentials.from_service_account_file(
            self.service_account_file,
            scopes=SCOPES,
        )
        return build("androidmanagement", "v1", credentials=credentials)

    @property
    def is_configured(self):
        return bool(
            self.enterprise_id
            and self.service_account_file
            and os.path.isfile(self.service_account_file)
        )

    def execute(self, resource_method, raise_exception=True):
        """Executes an API request. In case of an error response, add a api_error
        attribute (a MDMAPIError object) to the exception raised by the execute()
        call. If raise_exception is passed and it's falsy, this function will not
        raise an exception for an error response, but will instead add an MDMAPIError
        object to the api_errors list.
        """
        try:
            return resource_method.execute()
        except HttpError as e:
            try:
                error_data = json.loads(e.content.decode())
            except json.JSONDecodeError:
                error_data = None
            api_error = MDMAPIError(url=e.uri, status_code=e.status_code, error_data=error_data)
            logger.debug("Android Enterprise API error", api_error=api_error)
            if raise_exception:
                e.api_error = api_error
                raise
            self.api_errors.append(api_error)

    def get_devices(self):
        """Gets all the devices enrolled in the enterprise. It's not possible to
        request devices for a specific policy or fleet.
        """
        # We cache the devices, mostly so that we don't make repeated API requests
        # when calling sync_fleets
        if hasattr(self, "_devices"):
            logger.info("Returning cached devices")
            return self._devices
        logger.info("Pulling devices from Android Enterprise")
        devices = []
        response = {}
        while not response or "nextPageToken" in response:
            response = self.execute(
                self.api.enterprises()
                .devices()
                .list(
                    parent=self.enterprise_name,
                    pageSize=1000,
                    pageToken=response.get("nextPageToken"),
                )
            )
            devices += response["devices"]
        self._devices = devices
        return devices

    def get_devices_for_fleet(self, fleet: Fleet):
        """Gets the devices linked to a Fleet."""
        current_fleet_device_ids = set()
        other_fleets_device_ids = set()
        for device_id, fleet_id in Device.objects.values_list("device_id", "fleet"):
            if fleet_id == fleet.id:
                current_fleet_device_ids.add(device_id)
            else:
                other_fleets_device_ids.add(device_id)
        fleet_devices = []
        for device in self.get_devices():
            device = MDMDevice(device)
            if device.id in current_fleet_device_ids:
                # The device is currently linked to this Fleet in the DB
                fleet_devices.append(device)
            elif device.id not in other_fleets_device_ids and (
                enrollment_token_data := device.get("enrollmentTokenData")
            ):
                # The device has not been assigned to another Fleet in the DB.
                # Check if it enrolled using an enrollment token created for
                # this Fleet
                try:
                    enrollment_token_data = json.loads(enrollment_token_data)
                except json.JSONDecodeError:
                    continue
                if (
                    isinstance(enrollment_token_data, dict)
                    and enrollment_token_data.get("fleet") == fleet.pk
                ):
                    fleet_devices.append(device)
        return fleet_devices

    def create_enrollment_token(self, fleet: Fleet):
        """Creates an enrollment token. A device that enrolls using this token
        will be added to the specified Fleet when we save it for the first time.
        """
        if not fleet.pk:
            # We need a Fleet ID to set in the enrollment token's additional data.
            # It will be used to determine which Fleet a Device should be added
            # to when we first save it in our database.
            fleet.save()
        return self.execute(
            self.api.enterprises()
            .enrollmentTokens()
            .create(
                parent=self.enterprise_name,
                body={
                    "policyName": f"{self.enterprise_name}/policies/{fleet.policy.policy_id}",
                    "additionalData": json.dumps({"fleet": fleet.pk}),
                    # Valid for one day
                    "duration": f"{24 * 60 * 60}s",
                },
            )
        )

    def update_existing_devices(self, fleet: Fleet, mdm_devices: list[dict]):
        """
        Updates existing devices in our database based on the full list
        of mdm_devices returned from the Android Enterprise API.
        """
        devices_by_id = {device.id: device for device in mdm_devices}
        devices_by_serial = {
            device["hardwareInfo"]["serialNumber"]: device for device in mdm_devices
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
                logger.debug(
                    "Skipping device in our DB but not in the API response", device=our_device
                )
                continue
            logger.debug(
                "Updating device",
                db_serial_number=our_device.serial_number,
                db_device_id=our_device.device_id,
            )
            our_device.serial_number = mdm_device["hardwareInfo"]["serialNumber"]
            our_device.device_id = mdm_device.id
            our_device.name = mdm_device["name"]
            our_device.raw_mdm_device = mdm_device

        logger.debug("Updating existing devices", our_devices=our_devices, count=len(our_devices))
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
                serial_number=mdm_device["hardwareInfo"]["serialNumber"],
                device_id=mdm_device.id,
                name=mdm_device["name"],
                raw_mdm_device=mdm_device,
            )
            for mdm_device in mdm_devices
        ]
        logger.debug(
            "Creating new devices",
            mdm_devices_to_create=mdm_devices_to_create,
            count=len(mdm_devices_to_create),
        )
        Device.objects.bulk_create(mdm_devices_to_create)
        return mdm_devices_to_create

    def create_device_snapshots(self, fleet: Fleet, mdm_devices: list[dict]):
        sync_time = timezone.now()

        # Create snapshots for each device
        logger.debug("Creating device snapshots", fleet=fleet, total_devices=len(mdm_devices))
        snapshots: list[DeviceSnapshot] = []
        for mdm_device in mdm_devices:
            last_sync = dt.datetime.fromisoformat(mdm_device["lastPolicySyncTime"])
            hardware_info = mdm_device["hardwareInfo"]
            # softwareInfo is only available if enabled on the policy
            sofware_info = mdm_device.get("softwareInfo", {})
            # powerManagementEvents is only available if enabled on the policy
            # (enabled by default); battery level is not available for BYOD devices
            battery_level = None
            for event in mdm_device.get("powerManagementEvents", []):
                if event["eventType"] == "BATTERY_LEVEL_COLLECTED":
                    battery_level = event["batteryLevel"]
                    break
            snapshots.append(
                DeviceSnapshot(
                    device_id=mdm_device.id,
                    name=mdm_device["name"],
                    serial_number=hardware_info["serialNumber"],
                    manufacturer=hardware_info["manufacturer"],
                    os_version=sofware_info.get("androidVersion"),
                    battery_level=battery_level,
                    enrollment_type=mdm_device["managementMode"],
                    last_sync=last_sync,
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
            # applicationReports is only available if enabled on the policy
            apps = snapshot.raw_mdm_device.get("applicationReports")
            if not apps:
                logger.debug("Application reports not available", device_id=snapshot.device_id)
                continue
            user_facing_apps = [app for app in apps if app["userFacingType"] == "USER_FACING"]
            logger.debug(
                "Creating app snapshots",
                app_count=len(apps),
                device_id=snapshot.device_id,
                user_facing_app_count=len(user_facing_apps),
            )
            app_snapshots.extend(
                [
                    DeviceSnapshotApp(
                        device_snapshot=snapshot,
                        package_name=app["packageName"],
                        app_name=app["displayName"],
                        version_code=app["versionCode"],
                        version_name=app["versionName"],
                    )
                    for app in user_facing_apps
                ]
            )
        DeviceSnapshotApp.objects.bulk_create(app_snapshots)

    def pull_devices(self, fleet: Fleet):
        """
        Retrieves devices from Android Enterprise and updates or creates the records in our
        database for those devices.
        """
        mdm_devices = self.get_devices_for_fleet(fleet)
        self.create_device_snapshots(fleet=fleet, mdm_devices=mdm_devices)
        our_devices = self.update_existing_devices(fleet, mdm_devices)
        our_device_ids = {device.device_id for device in our_devices}
        mdm_devices_to_create = [
            mdm_device for mdm_device in mdm_devices if mdm_device.id not in our_device_ids
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
        """Create or update a device-specific policy in the MDM based on the
        json_template of the device's Policy.
        """
        if not device.raw_mdm_device:
            logger.debug("New device. Cannot sync", device=device)
            return
        policy_data = device.fleet.policy.get_policy_data(
            device=device, tailscale_auth_key=os.getenv("TAILSCALE_AUTH_KEY")
        )
        if not policy_data:
            logger.debug(
                "Could not generate policy data. Cannot sync",
                device=device,
                fleet=device.fleet,
                policy=device.fleet.policy,
            )
            return
        logger.debug("Syncing device", device=device)
        # Create or update a device-specific policy
        policy_name = f"{self.enterprise_name}/policies/fleet{device.fleet_id}_{device.device_id}"
        logger.debug(
            "Create/update policy for device",
            device=device,
            policy_name=policy_name,
            fleet=device.fleet,
            policy=device.fleet.policy,
        )
        self.execute(self.api.enterprises().policies().patch(name=policy_name, body=policy_data))
        current_policy_name = device.raw_mdm_device["policyName"]
        if current_policy_name != policy_name:
            # Update the policyName for the device
            logger.debug(
                "Updating the policyName for device",
                device=device,
                new_policy_name=policy_name,
                current_policy_name=current_policy_name,
            )
            mdm_device = self.execute(
                self.api.enterprises()
                .devices()
                .patch(
                    name=device.name,
                    updateMask="policyName",
                    body={"policyName": policy_name},
                )
            )
            # Update the Device with the latest info, to make sure the policyName
            # in the raw_mdm_device field stays in sync
            mdm_device = MDMDevice(mdm_device)
            self.create_device_snapshots(device.fleet, [mdm_device])
            self.update_existing_devices(device.fleet, [mdm_device])
            # Delete the current policy if it's also device-specific
            if current_policy_name.endswith(device.device_id):
                logger.debug(
                    "Deleting the previous device-specific policy",
                    device=device,
                    previous_policy_name=current_policy_name,
                )
                self.execute(self.api.enterprises().policies().delete(name=current_policy_name))

    def sync_fleet(self, fleet: Fleet, push_config: bool = True):
        """
        Synchronizes the remote Android Enterprise device list with our database,
        and updates the device configuration in Android Enterprise based on the
        configured ODK Central app users.
        """
        logger.info("Syncing fleet to Android Enterprise devices", fleet=fleet)
        self.pull_devices(fleet)
        if push_config:
            for device in fleet.devices.exclude(app_user_name="").select_related("fleet").all():
                self.push_device_config(device=device)

    def sync_fleets(self, push_config: bool = True):
        """
        Synchronizes all configured fleets with Android Enterprise and updates the
        applicable device configurations.
        """
        logger.info("Syncing fleets with Android Enterprise")
        for fleet in Fleet.objects.all():
            self.sync_fleet(fleet=fleet, push_config=push_config)

    def create_group(self, fleet: Fleet):
        """No-op. Android Enterprise has no groups."""

    def add_group_to_policy(self, fleet: Fleet):
        """No-op. Android Enterprise has no groups."""

    def get_enrollment_qr_code(self, fleet: Fleet):
        """Download the enrollment QR code image for a Fleet and save it in the
        enroll_qr_code field.
        """
        logger.info(
            "Creating an Android Enterprise enrollment token", fleet=fleet, policy=fleet.policy
        )
        enrollment_token = self.create_enrollment_token(fleet)
        logger.info(
            "Creating the enrollment QR code", fleet=fleet, enrollment_token=enrollment_token
        )
        qr_code = create_qr_code(enrollment_token["qrCode"])
        # Update the enroll_qr_code field. Do not call Fleet.save()
        fleet.enroll_qr_code.save(f"{fleet}.png", qr_code, save=False)
        # Update other fields
        fleet.enroll_token_expires_at = dt.datetime.fromisoformat(
            enrollment_token["expirationTimestamp"]
        )
        fleet.enroll_token_value = enrollment_token["value"]

    def delete_group(self, fleet: Fleet) -> bool:
        """Returns False if the Fleet has devices in the database, meaning it
        should not be deleted.
        """
        if fleet.devices.exists():
            logger.debug(
                "Cannot delete Fleet because it has devices linked to it in the database",
                fleet=fleet,
            )
            return False
        return True

    def create_or_update_policy(self, policy: Policy):
        """Creates or updates a policy in the MDM based on the template in the
        Policy.json_template field.
        """
        logger.debug("Create/update policy", policy=policy)
        policy_data = policy.get_policy_data(tailscale_auth_key=os.getenv("TAILSCALE_AUTH_KEY"))
        if not policy_data:
            logger.debug(
                "Could not generate policy data. Cannot create/update the policy",
                policy=policy,
            )
            return
        policy_name = f"{self.enterprise_name}/policies/{policy.policy_id}"
        self.execute(self.api.enterprises().policies().patch(name=policy_name, body=policy_data))
