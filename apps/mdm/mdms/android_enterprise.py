import datetime as dt
import json
import os
from functools import cached_property

import structlog
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import F, OuterRef, Q, Subquery
from django.urls import reverse
from django.utils import timezone
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from apps.mdm.models import Device, DeviceSnapshot, DeviceSnapshotApp, Fleet, Policy
from apps.publish_mdm.utils import create_qr_code

from .base import MDM, MDMAPIError

logger = structlog.getLogger(__name__)
# Single set of scopes used for the combined credentials object.
ALL_SCOPES = [
    "https://www.googleapis.com/auth/androidmanagement",
    "https://www.googleapis.com/auth/pubsub",
]
# Google-managed service account that Android Device Policy uses to publish notifications.
ANDROID_DEVICE_POLICY_SERVICE_ACCOUNT = "android-cloud-policy@system.gserviceaccount.com"
# Fixed resource name suffix used for this application's Pub/Sub topic and subscription.
PUBSUB_RESOURCE_NAME = "publish-mdm"


class MDMDevice(dict):
    """A dict for storing device data gotten from the MDM."""

    # An `id` attr will be used to store the device ID extracted from the device name.
    # It avoids adding an "id" key in the raw data dict gotten via the API
    @cached_property
    def id(self):
        return self["name"].split("/")[-1]


class AndroidEnterprise(MDM):
    name = "Android Enterprise"

    def __init__(self, organization=None):
        # Do not pass an organization if you only need to perform operations that are
        # not organization or enterprise-specific (e.g. setting up Pub/Sub, enrolling an enterprise, etc.)
        self.api_errors = []
        self.organization = organization
        self.service_account_file = os.getenv("ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE")
        if (
            organization
            and (self.enterprise_id or self.service_account_file)
            and not self.is_configured
        ):
            raise ValueError(
                "Android Enterprise MDM credentials are not properly configured or service account file is missing. "
                f"{self.enterprise_id=}, {self.service_account_file=}"
            )

    @property
    def enterprise_id(self):
        try:
            account = self.organization.android_enterprise
            if account.enterprise_id:
                return account.enterprise_id
        except (AttributeError, ObjectDoesNotExist):
            pass
        return None

    @property
    def enterprise_name(self):
        return f"enterprises/{self.enterprise_id}"

    @cached_property
    def credentials(self):
        """Single :class:`~google.oauth2.service_account.Credentials` object with
        both the Android Management and Pub/Sub OAuth scopes.  All API clients
        share this object so that only one service-account key file read is needed.
        """
        if not self.has_valid_service_account_file:
            raise ValueError("ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE is not configured")
        return Credentials.from_service_account_file(
            self.service_account_file,
            scopes=ALL_SCOPES,
        )

    @cached_property
    def api(self):
        return build("androidmanagement", "v1", credentials=self.credentials)

    @cached_property
    def pubsub_api(self):
        return build("pubsub", "v1", credentials=self.credentials)

    @property
    def project_id(self) -> str | None:
        """Google Cloud project ID derived from the service account credentials."""
        return self.credentials.project_id

    @property
    def pubsub_topic(self) -> str:
        """Fully-qualified Pub/Sub topic resource name for this application."""
        return f"projects/{self.project_id}/topics/{PUBSUB_RESOURCE_NAME}-{settings.ENVIRONMENT}"

    @property
    def pubsub_subscription(self) -> str:
        """Fully-qualified Pub/Sub subscription resource name for this application."""
        return f"projects/{self.project_id}/subscriptions/{PUBSUB_RESOURCE_NAME}-{settings.ENVIRONMENT}"

    @property
    def is_configured(self):
        return bool(self.enterprise_id) and self.has_valid_service_account_file

    @property
    def has_valid_service_account_file(self):
        return bool(self.service_account_file) and os.path.isfile(self.service_account_file)

    def get_signup_url(self, callback_url: str) -> dict:
        """Returns {'name': 'signupUrls/...', 'url': 'https://enterprise.google.com/...'}"""
        return (
            self.api.signupUrls()
            .create(
                projectId=self.credentials.project_id,
                callbackUrl=callback_url,
            )
            .execute()
        )

    def create_enterprise(self, signup_name: str, enterprise_token: str, display_name: str) -> dict:
        """Returns {'name': 'enterprises/LC00lvvue0'}"""
        body: dict = {"enterpriseDisplayName": display_name}
        if self.pubsub_enabled():
            body["pubsubTopic"] = self.pubsub_topic
            body["enabledNotificationTypes"] = ["ENROLLMENT", "STATUS_REPORT"]
        return (
            self.api.enterprises()
            .create(
                projectId=self.credentials.project_id,
                signupUrlName=signup_name,
                enterpriseToken=enterprise_token,
                body=body,
            )
            .execute()
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
            elif (
                device.id not in other_fleets_device_ids
                and self._get_fleet_pk_from_enrollment_token_data(device) == fleet.pk
            ):
                # The device has not been assigned to another Fleet in the DB.
                # and it enrolled using an enrollment token created for this Fleet.
                fleet_devices.append(device)
        return fleet_devices

    def create_enrollment_token(
        self,
        fleet: Fleet,
        duration_seconds: int = 24 * 60 * 60,
        allow_personal_usage: str = "ALLOW_PERSONAL_USAGE_UNSPECIFIED",
    ):
        """Creates an enrollment token. A device that enrolls using this token
        will be added to the specified Fleet when we save it for the first time.
        """
        if not fleet.pk:
            fleet.save()
        return self.execute(
            self.api.enterprises()
            .enrollmentTokens()
            .create(
                parent=self.enterprise_name,
                body={
                    "policyName": f"{self.enterprise_name}/policies/{fleet.policy.policy_id}",
                    "additionalData": json.dumps({"fleet": fleet.pk}),
                    "duration": f"{duration_seconds}s",
                    "allowPersonalUsage": allow_personal_usage,
                },
            )
        )

    def revoke_enrollment_token(self, resource_name: str) -> None:
        """Revoke (delete) an enrollment token by its AMAPI resource name.

        Handles 404 gracefully — the token may already be expired or deleted.
        https://developers.google.com/android/management/reference/rest/v1/enterprises.enrollmentTokens/delete
        """
        logger.info("Revoking enrollment token", resource_name=resource_name)
        try:
            self.execute(self.api.enterprises().enrollmentTokens().delete(name=resource_name))
        except HttpError as e:
            if e.status_code == 404:
                logger.warning(
                    "Enrollment token not found in AMAPI; it may already be revoked or expired",
                    resource_name=resource_name,
                )
                return
            raise

    def update_existing_devices(self, fleet: Fleet, mdm_devices: list[dict]):
        """
        Updates existing devices in our database based on the full list
        of mdm_devices returned from the Android Enterprise API. Devices in
        the fleet that are not in the mdm_devices list will be soft-deleted.
        """
        devices_by_id = {device.id: device for device in mdm_devices}
        devices_by_serial = {
            device["hardwareInfo"]["serialNumber"]: device for device in mdm_devices
        }

        # Soft-delete any devices whose names appear in previousDeviceNames —
        # they are old incarnations of devices that have since re-enrolled.
        previous_names = {
            name for device in mdm_devices for name in device.get("previousDeviceNames", [])
        }
        if previous_names and (
            count := Device.objects.filter(name__in=previous_names).soft_delete()
        ):
            logger.info(
                "Soft-deleted re-enrolled devices",
                count=count,
                previous_names=previous_names,
            )

        our_devices = Device.all_objects.filter(
            Q(device_id__in=devices_by_id.keys())
            | Q(serial_number__in=devices_by_serial.keys())
            | Q(fleet=fleet)
        )
        to_update = []

        for our_device in our_devices:
            if our_device.is_deleted or our_device.fleet != fleet:
                logger.debug(
                    "Skipping device",
                    device=our_device,
                    is_deleted=our_device.is_deleted,
                    device_fleet=our_device.fleet,
                )
                continue
            to_update.append(our_device)
            if our_device.device_id:
                mdm_device = devices_by_id.get(our_device.device_id)
            else:
                mdm_device = devices_by_serial.get(our_device.serial_number)
            if not mdm_device:
                logger.info("Soft-deleting device not found in API response", device=our_device)
                our_device.soft_delete(commit=False)
                continue
            logger.debug(
                "Updating device",
                db_serial_number=our_device.serial_number,
                db_device_id=our_device.device_id,
            )
            self._update_device(our_device, mdm_device)

        logger.debug("Updating existing devices", to_update=to_update, count=len(to_update))
        Device.objects.bulk_update(
            to_update,
            fields=["serial_number", "device_id", "raw_mdm_device", "name", "deleted_at"],
        )
        return our_devices

    def create_new_devices(self, fleet: Fleet, mdm_devices: list[dict]):
        """
        Creates new devices in our database based on the mdm_devices
        received from the API. This list must not contain devices that
        already exist in our database.
        """
        mdm_devices_to_create = [
            self._create_device(fleet, mdm_device) for mdm_device in mdm_devices
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
        qs = DeviceSnapshot.objects.filter(mdm_device_id=None).select_for_update()
        # Get the ID for each snapshot's device_id
        qs = qs.annotate(
            existing_device_id=Subquery(
                Device.all_objects.filter(device_id=OuterRef("device_id")).values("id")[:1]
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
        normalized fields of the device's Policy.
        """
        if not device.raw_mdm_device:
            logger.debug("New device. Cannot sync", device=device)
            return
        policy_data = device.fleet.policy.get_policy_data(device=device)
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
            self._update_device(device, mdm_device)
            device.save()
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
            for device in fleet.devices.select_related("fleet").all():
                self.push_device_config(device=device)

    def sync_fleets(self, push_config: bool = True):
        """
        Synchronizes all configured fleets with Android Enterprise and updates the
        applicable device configurations.
        """
        logger.info("Syncing fleets with Android Enterprise")
        for fleet in self.organization.fleets.all():
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

    def delete_device(self, device: Device) -> None:
        """Deletes a device from Android Enterprise. For fully managed (DEVICE_OWNER)
        devices this triggers a factory reset; for work-profile devices it removes the
        work profile.

        https://developers.google.com/android/management/reference/rest/v1/enterprises.devices/delete
        """
        logger.info("Deleting device from Android Enterprise", device_name=device.name)
        try:
            self.execute(self.api.enterprises().devices().delete(name=device.name))
        except HttpError as e:
            if e.status_code == 404:
                logger.warning(
                    "Device not found in Android Enterprise; it may already be wiped",
                    device_name=device.name,
                )
                return
            raise

    def create_or_update_policy(self, policy: Policy):
        """Creates or updates a policy in the MDM based on the normalized
        Policy fields.
        """
        logger.debug("Create/update policy", policy=policy)
        policy_data = policy.get_policy_data()
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
        push_endpoint_domain: str | None = None,
    ) -> None:
        """Configure Pub/Sub infrastructure.

        Performs all required Pub/Sub setup steps:

        1. Creates the Pub/Sub topic
           ``projects/{project_id}/topics/publish-mdm-{environment}``
           if it does not already exist.
        2. Creates (or updates) a push subscription
           ``projects/{project_id}/subscriptions/publish-mdm-{environment}``.
           The push endpoint is built from ``push_endpoint_domain`` when
           provided, otherwise from ``ANDROID_ENTERPRISE_CALLBACK_DOMAIN``
           (if set), otherwise from the current ``Site`` domain.
        3. Grants ``android-cloud-policy@system.gserviceaccount.com``
           ``roles/pubsub.publisher`` on the topic so that Android Device Policy
           can publish AMAPI notifications to it.

        To register the topic with each enrolled AMAPI enterprise, call
        :meth:`patch_enterprise_pubsub` separately (e.g. via the
        ``configure_amapi_pubsub`` management command).

        Args:
            push_endpoint_domain: Domain (without scheme, e.g. ``example.com``)
                used to construct the full push endpoint.  When ``None``,
                ``ANDROID_ENTERPRISE_CALLBACK_DOMAIN`` is used if set,
                otherwise the domain is taken from the current
                ``django.contrib.sites`` ``Site`` object.  HTTPS is always used.
        """
        push_endpoint = self._build_push_endpoint(domain=push_endpoint_domain)
        logger.info(
            "Configuring AMAPI Pub/Sub notifications",
            topic_name=self.pubsub_topic,
            subscription_name=self.pubsub_subscription,
            push_endpoint=push_endpoint,
        )
        self._ensure_pubsub_topic()
        self._ensure_pubsub_subscription(push_endpoint)
        self._grant_pubsub_publisher()

    def patch_enterprise_pubsub(self) -> dict:
        """Patch the enterprise Pub/Sub registration.

        Calls ``enterprises.patch`` to update ``pubsubTopic`` and
        ``enabledNotificationTypes`` on the AMAPI enterprise resource.

        - If :meth:`pubsub_enabled` returns ``True`` (token configured and
          topic exists), points the enterprise at
          ``projects/{project_id}/topics/publish-mdm-{environment}`` and
          enables ``ENROLLMENT`` and ``STATUS_REPORT`` notification types.
        - Otherwise (token not set or topic does not yet exist), clears both
          fields.

        Returns:
            The updated enterprise resource dict returned by the AMAPI.
        """
        if self.pubsub_enabled():
            body = {
                "pubsubTopic": self.pubsub_topic,
                "enabledNotificationTypes": ["ENROLLMENT", "STATUS_REPORT"],
            }
        else:
            body = {"pubsubTopic": "", "enabledNotificationTypes": []}
        return self.execute(
            self.api.enterprises().patch(
                name=self.enterprise_name,
                updateMask="pubsubTopic,enabledNotificationTypes",
                body=body,
            )
        )

    def _build_push_endpoint(self, domain: str | None = None) -> str:
        """Build the push endpoint URL.

        Reverses the ``mdm:amapi_notifications`` URL and appends the
        ``ANDROID_ENTERPRISE_PUBSUB_TOKEN`` as a query parameter.  HTTPS
        is always used.  The domain is resolved with the following priority:

        1. The ``domain`` argument (when explicitly supplied).
        2. ``settings.ANDROID_ENTERPRISE_CALLBACK_DOMAIN`` (when set).
        3. The current ``django.contrib.sites`` ``Site`` object domain (fallback).

        Args:
            domain: Optional domain override (without scheme, e.g.
                ``example.com``).  When ``None``, the domain is read from
                ``ANDROID_ENTERPRISE_CALLBACK_DOMAIN`` or the ``Site`` model.

        Returns:
            Full HTTPS URL for the Pub/Sub push endpoint.
        """
        token = settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN
        if not token:
            raise ValueError(
                "ANDROID_ENTERPRISE_PUBSUB_TOKEN must be set before configuring Pub/Sub. "
                "The notification endpoint rejects all requests when this setting is absent."
            )
        path = reverse("mdm:amapi_notifications")
        if domain is None:
            domain = (
                settings.ANDROID_ENTERPRISE_CALLBACK_DOMAIN or Site.objects.get_current().domain
            )
        return f"https://{domain.rstrip('/')}{path}?token={token}"

    def pubsub_enabled(self) -> bool:
        """Return True if Pub/Sub is fully enabled.

        Requires both that ``ANDROID_ENTERPRISE_PUBSUB_TOKEN`` is configured
        (so the push endpoint can authenticate incoming notifications) and that
        the Pub/Sub topic already exists.  When either condition is not met,
        returns ``False``.
        """
        if not settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN:
            return False
        try:
            self.pubsub_api.projects().topics().get(topic=self.pubsub_topic).execute()
            return True
        except HttpError as e:
            if e.status_code == 404:
                return False
            raise

    def _ensure_pubsub_topic(self) -> None:
        """Create the Pub/Sub topic if it does not already exist."""
        topic_name = self.pubsub_topic
        try:
            self.pubsub_api.projects().topics().create(name=topic_name, body={}).execute()
            logger.info("Created Pub/Sub topic", topic=topic_name)
        except HttpError as e:
            if e.status_code == 409:
                logger.info("Pub/Sub topic already exists", topic=topic_name)
            else:
                raise

    def _grant_pubsub_publisher(self) -> None:
        """Grant Android Device Policy the publisher role on the Pub/Sub topic.

        Fetches the current IAM policy for the topic, appends
        ``android-mdm-service@system.gserviceaccount.com`` to the
        ``roles/pubsub.publisher`` binding (creating the binding if it is
        absent), and writes the updated policy back.
        """
        topic_name = self.pubsub_topic
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
        for binding in bindings:
            if binding["role"] == "roles/pubsub.publisher":
                if member in binding.get("members", []):
                    logger.info(
                        "Android Device Policy already has Pub/Sub publisher rights",
                        topic=topic_name,
                    )
                    return
                binding["members"].append(member)
                break
        else:
            bindings.append({"role": "roles/pubsub.publisher", "members": [member]})
            policy["bindings"] = bindings
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

    def _ensure_pubsub_subscription(self, push_endpoint: str) -> None:
        """Create the Pub/Sub push subscription, or update its endpoint if it already exists."""
        topic_name = self.pubsub_topic
        subscription_name = self.pubsub_subscription
        body: dict = {"topic": topic_name, "pushConfig": {"pushEndpoint": push_endpoint}}
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
                logger.info(
                    "Pub/Sub subscription already exists, updating push endpoint",
                    subscription=subscription_name,
                    push_endpoint=push_endpoint,
                )
                self.pubsub_api.projects().subscriptions().modifyPushConfig(
                    subscription=subscription_name,
                    body={"pushConfig": {"pushEndpoint": push_endpoint}},
                ).execute()
                logger.info(
                    "Updated Pub/Sub subscription push endpoint",
                    subscription=subscription_name,
                    push_endpoint=push_endpoint,
                )
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

        Ignore all other notifications.

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

    def _create_device(self, fleet: Fleet, mdm_device: MDMDevice) -> Device:
        """Build a new :class:`~apps.mdm.models.Device` instance from MDM data.

        The returned instance is **not** saved to the database; callers are
        responsible for calling ``save()`` or passing it to ``bulk_create()``.

        Args:
            fleet: The fleet the device belongs to.
            mdm_device: The MDM device data.

        Returns:
            An unsaved ``Device`` instance.
        """
        default_app_user_name = fleet.default_app_user.name if fleet.default_app_user_id else ""
        serial_number = mdm_device.get("hardwareInfo", {}).get("serialNumber", "")
        return Device(
            fleet=fleet,
            device_id=mdm_device.id,
            name=mdm_device["name"],
            serial_number=serial_number,
            raw_mdm_device=dict(mdm_device),
            app_user_name=default_app_user_name,
        )

    def _update_device(self, device: Device, mdm_device: MDMDevice) -> None:
        """Apply MDM device data to an existing :class:`~apps.mdm.models.Device` instance.

        Updates ``device_id``, ``name``, ``raw_mdm_device``, and (when non-empty)
        ``serial_number`` in-place.  The caller is responsible for persisting the
        changes via ``save()`` or ``bulk_update()``.

        Args:
            device: The existing ``Device`` instance to update.
            mdm_device: The MDM device data.
        """
        device.device_id = mdm_device.id
        device.name = mdm_device["name"]
        serial_number = mdm_device.get("hardwareInfo", {}).get("serialNumber", "")
        if serial_number:
            device.serial_number = serial_number
        device.raw_mdm_device = dict(mdm_device)

    def _handle_enrollment_notification(self, mdm_device: MDMDevice) -> None:
        """Create or update a Device record from an ENROLLMENT notification."""
        fleet = self._get_fleet_from_enrollment_token_data(mdm_device)
        if fleet is None:
            logger.warning(
                "Could not determine fleet for ENROLLMENT notification; skipping",
                device_id=mdm_device.id,
            )
            return

        existing_device = Device.objects.filter(device_id=mdm_device.id).first()
        if existing_device:
            logger.info(
                "Updating existing device from ENROLLMENT notification",
                device_id=mdm_device.id,
            )
            self._update_device(existing_device, mdm_device)
            existing_device.save(
                update_fields=["name", "device_id", "raw_mdm_device", "serial_number"],
                push_to_mdm=False,
            )
        else:
            logger.info(
                "Creating new device from ENROLLMENT notification",
                device_id=mdm_device.id,
                fleet=fleet,
            )
            device = self._create_device(fleet, mdm_device)
            device.save(push_to_mdm=False)

        if previous_names := mdm_device.get("previousDeviceNames"):
            count = Device.objects.filter(name__in=previous_names).soft_delete()
            logger.info(
                "Soft-deleted re-enrolled devices from ENROLLMENT notification",
                count=count,
                previous_names=previous_names,
            )

    def _handle_status_report_notification(self, mdm_device: MDMDevice) -> None:
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
        previous_state = (existing_device.raw_mdm_device or {}).get("state")
        self._update_device(existing_device, mdm_device)
        existing_device.save(
            update_fields=["name", "device_id", "raw_mdm_device", "serial_number"],
            push_to_mdm=False,
        )

        # If the device just finished enrolling, has an assigned app user, and hasn't
        # yet received a device-specific policy, push its config now.
        if (
            previous_state == "PROVISIONING"
            and mdm_device.get("state") == "ACTIVE"
            and existing_device.app_user_name
            and not mdm_device.get("policyName", "").endswith(mdm_device.id)
        ):
            logger.info(
                "Device transitioned from PROVISIONING to ACTIVE; pushing device config",
                device_id=mdm_device.id,
                app_user_name=existing_device.app_user_name,
            )
            self.push_device_config(existing_device)
        # Only create a snapshot when the notification carries enough information.
        elif "lastPolicySyncTime" in mdm_device and "hardwareInfo" in mdm_device:
            self.create_device_snapshots(existing_device.fleet, [mdm_device])
            # Link the newly created snapshot(s) to the device (create_device_snapshots
            # leaves mdm_device_id as NULL; we resolve it here, scoped to this device).
            # `device_id` in DeviceSnapshot stores the MDM device ID (not the Django pk).
            DeviceSnapshot.objects.filter(
                mdm_device_id=None,
                device_id=mdm_device.id,
            ).update(mdm_device_id=existing_device.pk)
            # Refresh latest_snapshot_id for this device only.
            Device.objects.filter(pk=existing_device.pk).update(
                latest_snapshot_id=Subquery(
                    DeviceSnapshot.objects.filter(mdm_device_id=existing_device.pk)
                    .order_by("-synced_at")
                    .values("id")[:1]
                )
            )

    @staticmethod
    def _get_fleet_pk_from_enrollment_token_data(mdm_device: MDMDevice) -> int | None:
        """Extract the fleet primary key from the device's ``enrollmentTokenData``.

        Returns the ``fleet`` value from the parsed JSON, or ``None`` when the
        field is absent, not valid JSON, or does not contain a ``fleet`` key.
        """
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
        return token_data.get("fleet") if isinstance(token_data, dict) else None

    @staticmethod
    def _get_fleet_from_enrollment_token_data(mdm_device: MDMDevice) -> Fleet | None:
        """Return the Fleet referenced by the device's enrollmentTokenData, or ``None``."""
        fleet_pk = AndroidEnterprise._get_fleet_pk_from_enrollment_token_data(mdm_device)
        if fleet_pk is None:
            return None
        return Fleet.objects.filter(pk=fleet_pk).first()
