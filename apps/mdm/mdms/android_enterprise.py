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
PUBSUB_SCOPES = ["https://www.googleapis.com/auth/pubsub"]
# Google-managed service account that Android Device Policy uses to publish notifications.
ANDROID_DEVICE_POLICY_SERVICE_ACCOUNT = "android-mdm-service@system.gserviceaccount.com"


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

    @cached_property
    def pubsub_api(self):
        if not self.is_configured:
            logger.warning("Android Enterprise API credentials not configured.")
            return None
        credentials = Credentials.from_service_account_file(
            self.service_account_file,
            scopes=PUBSUB_SCOPES,
        )
        return build("pubsub", "v1", credentials=credentials)

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
            if response:
                devices += response["devices"]
            else:
                break
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
            if device["state"] == "PROVISIONING":
                # Skip a device that's currently being enrolled and doesn't have a policy applied yet
                # https://developers.google.com/android/management/reference/rest/v1/enterprises.devices#devicestate
                continue
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
        # bulk_create bypasses Device.save(), so set the default app user name here.
        default_app_user_name = fleet.default_app_user.name if fleet.default_app_user_id else ""
        mdm_devices_to_create = [
            Device(
                fleet=fleet,
                serial_number=mdm_device["hardwareInfo"]["serialNumber"],
                device_id=mdm_device.id,
                name=mdm_device["name"],
                raw_mdm_device=mdm_device,
                app_user_name=default_app_user_name,
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
            user_facing_apps = [app for app in apps if app.get("userFacingType") == "USER_FACING"]
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

    def configure_pubsub(
        self,
        pubsub_topic: str,
        notification_types: list[str] | None = None,
        push_endpoint: str | None = None,
        subscription_name: str | None = None,
    ) -> dict | None:
        """Configure Pub/Sub push notifications for the enterprise.

        Performs all required Pub/Sub setup steps, then calls ``enterprises.patch``
        to register the topic with the AMAPI enterprise:

        1. Creates the Pub/Sub topic if it does not already exist.
        2. Grants ``android-mdm-service@system.gserviceaccount.com``
           ``roles/pubsub.publisher`` on the topic so that Android Device Policy
           can publish AMAPI notifications to it.
        3. Creates a subscription (push or pull) if it does not already exist.
        4. Patches the enterprise to set ``pubsubTopic`` and
           ``enabledNotificationTypes``.

        Args:
            pubsub_topic: The Cloud Pub/Sub topic name in the format
                ``projects/{project}/topics/{topic}``.
            notification_types: The notification types to enable.  Defaults to
                ``["ENROLLMENT", "STATUS_REPORT"]``.
            push_endpoint: HTTPS URL that Pub/Sub will POST messages to (i.e.
                the ``/mdm/api/amapi/notifications/`` endpoint of this
                application).  When ``None`` a pull subscription is created
                instead.
            subscription_name: The fully-qualified subscription resource name in
                the format ``projects/{project}/subscriptions/{subscription}``.
                Defaults to the topic name with ``/topics/`` replaced by
                ``/subscriptions/``.

        Returns:
            The updated enterprise resource dict, or ``None`` if the AMAPI is
            not configured.
        """
        if notification_types is None:
            notification_types = ["ENROLLMENT", "STATUS_REPORT"]
        if subscription_name is None:
            subscription_name = pubsub_topic.replace("/topics/", "/subscriptions/", 1)
        logger.info(
            "Configuring AMAPI Pub/Sub notifications",
            enterprise_name=self.enterprise_name,
            pubsub_topic=pubsub_topic,
            notification_types=notification_types,
            push_endpoint=push_endpoint,
            subscription_name=subscription_name,
        )
        self._ensure_pubsub_topic(pubsub_topic)
        self._grant_pubsub_publisher(pubsub_topic)
        self._ensure_pubsub_subscription(pubsub_topic, subscription_name, push_endpoint)
        return self.execute(
            self.api.enterprises().patch(
                name=self.enterprise_name,
                updateMask="pubsubTopic,enabledNotificationTypes",
                body={
                    "pubsubTopic": pubsub_topic,
                    "enabledNotificationTypes": notification_types,
                },
            )
        )

    def _ensure_pubsub_topic(self, topic_name: str) -> None:
        """Create the Pub/Sub topic if it does not already exist."""
        try:
            self.pubsub_api.projects().topics().create(name=topic_name, body={}).execute()
            logger.info("Created Pub/Sub topic", topic=topic_name)
        except HttpError as e:
            if e.status_code == 409:
                logger.info("Pub/Sub topic already exists", topic=topic_name)
            else:
                raise

    def _grant_pubsub_publisher(self, topic_name: str) -> None:
        """Grant Android Device Policy the publisher role on the Pub/Sub topic.

        Fetches the current IAM policy for the topic, appends
        ``android-mdm-service@system.gserviceaccount.com`` to the
        ``roles/pubsub.publisher`` binding (creating the binding if it is
        absent), and writes the updated policy back.
        """
        member = f"serviceAccount:{ANDROID_DEVICE_POLICY_SERVICE_ACCOUNT}"
        try:
            policy = self.pubsub_api.projects().topics().getIamPolicy(resource=topic_name).execute()
        except HttpError as e:
            logger.error(
                "Failed to get IAM policy for Pub/Sub topic",
                topic=topic_name,
                status_code=e.status_code,
            )
            raise
        bindings = policy.get("bindings", [])
        publisher_binding = next(
            (b for b in bindings if b["role"] == "roles/pubsub.publisher"), None
        )
        if publisher_binding is None:
            bindings.append({"role": "roles/pubsub.publisher", "members": [member]})
            policy["bindings"] = bindings
        elif member in publisher_binding.get("members", []):
            logger.info(
                "Android Device Policy already has Pub/Sub publisher rights",
                topic=topic_name,
            )
            return
        else:
            publisher_binding["members"].append(member)
        try:
            self.pubsub_api.projects().topics().setIamPolicy(
                resource=topic_name, body={"policy": policy}
            ).execute()
        except HttpError as e:
            logger.error(
                "Failed to set IAM policy for Pub/Sub topic",
                topic=topic_name,
                status_code=e.status_code,
            )
            raise
        logger.info("Granted Android Device Policy Pub/Sub publisher rights", topic=topic_name)

    def _ensure_pubsub_subscription(
        self, topic_name: str, subscription_name: str, push_endpoint: str | None
    ) -> None:
        """Create the Pub/Sub subscription if it does not already exist.

        A push subscription is created when ``push_endpoint`` is provided;
        otherwise a pull subscription is created.
        """
        body: dict = {"topic": topic_name}
        if push_endpoint:
            body["pushConfig"] = {"pushEndpoint": push_endpoint}
        try:
            self.pubsub_api.projects().subscriptions().create(
                name=subscription_name, body=body
            ).execute()
            logger.info(
                "Created Pub/Sub subscription",
                subscription=subscription_name,
                push_endpoint=push_endpoint,
            )
        except HttpError as e:
            if e.status_code == 409:
                logger.info("Pub/Sub subscription already exists", subscription=subscription_name)
            else:
                raise

    def handle_device_notification(self, device_data: dict, notification_type: str) -> None:
        """Handle a device notification received from AMAPI via Pub/Sub.

        For ``ENROLLMENT`` notifications a new :class:`~apps.mdm.models.Device`
        record is created (or an existing one updated) using the Device resource
        payload.

        For ``STATUS_REPORT`` notifications the existing
        :class:`~apps.mdm.models.Device` record is updated and a new
        :class:`~apps.mdm.models.DeviceSnapshot` is created when sufficient
        data is present.

        Args:
            device_data: The decoded Device resource dict from the Pub/Sub
                message ``data`` field.
            notification_type: The value of the ``notificationType`` Pub/Sub
                message attribute (e.g. ``"ENROLLMENT"`` or
                ``"STATUS_REPORT"``).
        """
        mdm_device = MDMDevice(device_data)
        logger.info(
            "Handling AMAPI device notification",
            notification_type=notification_type,
            device_id=mdm_device.id,
            device_name=mdm_device.get("name"),
        )

        if notification_type == "ENROLLMENT":
            self._handle_enrollment_notification(mdm_device)
        elif notification_type == "STATUS_REPORT":
            self._handle_status_report_notification(mdm_device)
        else:
            logger.info("Ignoring notification type", notification_type=notification_type)

    def _handle_enrollment_notification(self, mdm_device: "MDMDevice") -> None:
        """Create or update a Device record from an ENROLLMENT notification."""
        fleet = self._get_fleet_from_enrollment_token_data(mdm_device)
        if fleet is None:
            logger.warning(
                "Could not determine fleet for ENROLLMENT notification; skipping",
                device_id=mdm_device.id,
            )
            return

        serial_number = mdm_device.get("hardwareInfo", {}).get("serialNumber", "")

        existing_device = Device.objects.filter(device_id=mdm_device.id).first()
        if existing_device:
            logger.info(
                "Updating existing device from ENROLLMENT notification",
                device_id=mdm_device.id,
            )
            existing_device.name = mdm_device["name"]
            existing_device.raw_mdm_device = dict(mdm_device)
            if serial_number:
                existing_device.serial_number = serial_number
            existing_device.save(
                update_fields=["name", "raw_mdm_device", "serial_number"],
                push_to_mdm=False,
            )
        else:
            logger.info(
                "Creating new device from ENROLLMENT notification",
                device_id=mdm_device.id,
                fleet=fleet,
            )
            default_app_user_name = fleet.default_app_user.name if fleet.default_app_user_id else ""
            Device.objects.create(
                fleet=fleet,
                device_id=mdm_device.id,
                name=mdm_device["name"],
                serial_number=serial_number,
                raw_mdm_device=dict(mdm_device),
                app_user_name=default_app_user_name,
            )

    def _handle_status_report_notification(self, mdm_device: "MDMDevice") -> None:
        """Update device metadata and create a snapshot from a STATUS_REPORT notification."""
        existing_device = Device.objects.filter(device_id=mdm_device.id).first()
        if existing_device is None:
            logger.warning(
                "Received STATUS_REPORT for unknown device; skipping",
                device_id=mdm_device.id,
            )
            return

        logger.info(
            "Updating device from STATUS_REPORT notification",
            device_id=mdm_device.id,
        )
        serial_number = mdm_device.get("hardwareInfo", {}).get("serialNumber", "")
        if serial_number:
            existing_device.serial_number = serial_number
        existing_device.raw_mdm_device = dict(mdm_device)
        existing_device.save(
            update_fields=["raw_mdm_device", "serial_number"],
            push_to_mdm=False,
        )

        # Only create a snapshot when the notification carries enough information.
        if "lastPolicySyncTime" in mdm_device and "hardwareInfo" in mdm_device:
            self.create_device_snapshots(existing_device.fleet, [mdm_device])
            # Link the newly created snapshot(s) to the device (create_device_snapshots
            # leaves mdm_device_id as NULL; we resolve it here, scoped to this device).
            # `device_id` in DeviceSnapshot stores the MDM device ID (not the Django pk).
            DeviceSnapshot.all_mdms.filter(
                mdm_device_id=None,
                device_id=mdm_device.id,
            ).update(mdm_device_id=existing_device.pk)
            # Refresh latest_snapshot_id for this device only.
            Device.objects.filter(pk=existing_device.pk).update(
                latest_snapshot_id=Subquery(
                    DeviceSnapshot.all_mdms.filter(mdm_device_id=existing_device.pk)
                    .order_by("-synced_at")
                    .values("id")[:1]
                )
            )

    @staticmethod
    def _get_fleet_from_enrollment_token_data(mdm_device: "MDMDevice") -> "Fleet | None":
        """Return the Fleet referenced by the device's enrollmentTokenData, or ``None``."""
        enrollment_token_data = mdm_device.get("enrollmentTokenData")
        if not enrollment_token_data:
            return None
        try:
            token_data = json.loads(enrollment_token_data)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Could not parse enrollmentTokenData",
                enrollment_token_data=enrollment_token_data,
            )
            return None
        fleet_pk = token_data.get("fleet") if isinstance(token_data, dict) else None
        if fleet_pk is None:
            return None
        return Fleet.objects.filter(pk=fleet_pk).first()
