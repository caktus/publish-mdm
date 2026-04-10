import json

import structlog
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, GeneratedField, Q, Value
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.models.functions import Coalesce
from django.utils.html import mark_safe
from django.utils.timezone import now

from apps.infisical.fields import EncryptedCharField
from apps.infisical.managers import EncryptedManager

from .serializers import PolicySerializer

logger = structlog.get_logger()


class MDMChoices(models.TextChoices):
    TINYMDM = "TinyMDM", "TinyMDM"
    ANDROID_ENTERPRISE = "Android Enterprise", "Android Enterprise"


class PasswordQuality(models.TextChoices):
    PASSWORD_QUALITY_UNSPECIFIED = "PASSWORD_QUALITY_UNSPECIFIED", "Unspecified"
    BIOMETRIC_WEAK = "BIOMETRIC_WEAK", "Biometric weak"
    SOMETHING = "SOMETHING", "Something"
    NUMERIC = "NUMERIC", "Numeric"
    NUMERIC_COMPLEX = "NUMERIC_COMPLEX", "Numeric complex"
    ALPHABETIC = "ALPHABETIC", "Alphabetic"
    ALPHANUMERIC = "ALPHANUMERIC", "Alphanumeric"
    COMPLEX = "COMPLEX", "Complex"


class RequirePasswordUnlock(models.TextChoices):
    REQUIRE_PASSWORD_UNLOCK_UNSPECIFIED = (
        "REQUIRE_PASSWORD_UNLOCK_UNSPECIFIED",
        "Unspecified",
    )
    USE_DEFAULT_DEVICE_TIMEOUT = "USE_DEFAULT_DEVICE_TIMEOUT", "Use default device timeout"
    REQUIRE_EVERY_DAY = "REQUIRE_EVERY_DAY", "Require every day"


class DeveloperSettings(models.TextChoices):
    DEVELOPER_SETTINGS_DISABLED = "DEVELOPER_SETTINGS_DISABLED", "Disallowed"
    DEVELOPER_SETTINGS_ALLOWED = "DEVELOPER_SETTINGS_ALLOWED", "Allowed"


class KioskPowerButtonActions(models.TextChoices):
    UNSPECIFIED = "POWER_BUTTON_ACTIONS_UNSPECIFIED", "Unspecified"
    AVAILABLE = "POWER_BUTTON_AVAILABLE", "Available"
    BLOCKED = "POWER_BUTTON_BLOCKED", "Blocked"


class KioskSystemErrorWarnings(models.TextChoices):
    UNSPECIFIED = "SYSTEM_ERROR_WARNINGS_UNSPECIFIED", "Unspecified"
    ENABLED = "ERROR_AND_WARNINGS_ENABLED", "Enabled"
    MUTED = "ERROR_AND_WARNINGS_MUTED", "Muted"


class KioskSystemNavigation(models.TextChoices):
    UNSPECIFIED = "SYSTEM_NAVIGATION_UNSPECIFIED", "Unspecified"
    ENABLED = "NAVIGATION_ENABLED", "Enabled"
    DISABLED = "NAVIGATION_DISABLED", "Disabled"
    HOME_ONLY = "HOME_BUTTON_ONLY", "Home button only"


class KioskStatusBar(models.TextChoices):
    UNSPECIFIED = "STATUS_BAR_UNSPECIFIED", "Unspecified"
    ENABLED = "NOTIFICATIONS_AND_SYSTEM_INFO_ENABLED", "Notifications and system info enabled"
    DISABLED = "NOTIFICATIONS_AND_SYSTEM_INFO_DISABLED", "Notifications and system info disabled"
    SYSTEM_INFO_ONLY = "SYSTEM_INFO_ONLY", "System info only"


class KioskDeviceSettings(models.TextChoices):
    UNSPECIFIED = "DEVICE_SETTINGS_UNSPECIFIED", "Unspecified"
    ALLOWED = "SETTINGS_ACCESS_ALLOWED", "Settings access allowed"
    BLOCKED = "SETTINGS_ACCESS_BLOCKED", "Settings access blocked"


class PermissionPolicy(models.TextChoices):
    PERMISSION_POLICY_UNSPECIFIED = "PERMISSION_POLICY_UNSPECIFIED", "Unspecified"
    PROMPT = "PROMPT", "Prompt user"
    GRANT = "GRANT", "Grant automatically"
    DENY = "DENY", "Deny automatically"


class InstallType(models.TextChoices):
    FORCE_INSTALLED = "FORCE_INSTALLED", "Force installed"
    PREINSTALLED = "PREINSTALLED", "Pre-installed"
    AVAILABLE = "AVAILABLE", "Available"
    KIOSK = "KIOSK", "Kiosk"
    BLOCKED = "BLOCKED", "Blocked"


class LocationMode(models.TextChoices):
    LOCATION_MODE_UNSPECIFIED = "LOCATION_MODE_UNSPECIFIED", "Unspecified"
    HIGH_ACCURACY = "HIGH_ACCURACY", "High accuracy (deprecated, Android 8 and below)"
    SENSORS_ONLY = "SENSORS_ONLY", "Sensors only / GPS (deprecated, Android 8 and below)"
    BATTERY_SAVING = "BATTERY_SAVING", "Battery saving (deprecated, Android 8 and below)"
    OFF = "OFF", "Off (deprecated, Android 8 and below)"
    LOCATION_ENFORCED = "LOCATION_ENFORCED", "Enforced (Android 9+)"
    LOCATION_DISABLED = "LOCATION_DISABLED", "Disabled (Android 9+)"
    LOCATION_USER_CHOICE = "LOCATION_USER_CHOICE", "User choice (Android 9+)"


class UsbDataAccess(models.TextChoices):
    USB_DATA_ACCESS_UNSPECIFIED = "USB_DATA_ACCESS_UNSPECIFIED", "Unspecified"
    ALLOW_USB_DATA_TRANSFER = "ALLOW_USB_DATA_TRANSFER", "Allow USB data transfer"
    DISALLOW_USB_FILE_TRANSFER = "DISALLOW_USB_FILE_TRANSFER", "Disallow USB file transfer"
    DISALLOW_USB_DATA_TRANSFER = "DISALLOW_USB_DATA_TRANSFER", "Disallow all USB data transfer"


class ConfigureWifi(models.TextChoices):
    CONFIGURE_WIFI_UNSPECIFIED = "CONFIGURE_WIFI_UNSPECIFIED", "Unspecified"
    ALLOW_CONFIGURING_WIFI = "ALLOW_CONFIGURING_WIFI", "Allow configuring Wi-Fi"
    DISALLOW_ADD_WIFI_CONFIG = "DISALLOW_ADD_WIFI_CONFIG", "Disallow adding Wi-Fi networks"
    DISALLOW_CONFIGURING_WIFI = "DISALLOW_CONFIGURING_WIFI", "Disallow configuring Wi-Fi"


class TetheringSettings(models.TextChoices):
    TETHERING_SETTINGS_UNSPECIFIED = "TETHERING_SETTINGS_UNSPECIFIED", "Unspecified"
    ALLOW_ALL_TETHERING = "ALLOW_ALL_TETHERING", "Allow all tethering"
    DISALLOW_WIFI_TETHERING = "DISALLOW_WIFI_TETHERING", "Disallow Wi-Fi tethering"
    DISALLOW_ALL_TETHERING = "DISALLOW_ALL_TETHERING", "Disallow all tethering"


class WifiDirectSettings(models.TextChoices):
    WIFI_DIRECT_SETTINGS_UNSPECIFIED = "WIFI_DIRECT_SETTINGS_UNSPECIFIED", "Unspecified"
    ALLOW_WIFI_DIRECT = "ALLOW_WIFI_DIRECT", "Allow Wi-Fi Direct"
    DISALLOW_WIFI_DIRECT = "DISALLOW_WIFI_DIRECT", "Disallow Wi-Fi Direct"


class PolicyVariableScope(models.TextChoices):
    POLICY = "policy", "Policy"
    FLEET = "fleet", "Fleet"


class Policy(models.Model):
    """A device policy in the MDM."""

    name = models.CharField(max_length=255, help_text="The name of the policy.")
    policy_id = models.CharField(
        verbose_name="Policy ID", max_length=255, help_text="The ID of the policy in the MDM."
    )
    organization = models.ForeignKey(
        "publish_mdm.Organization",
        on_delete=models.CASCADE,
        related_name="policies",
        null=True,
        blank=True,
    )

    # ODK Collect
    odk_collect_package = models.CharField(
        max_length=255,
        default="org.odk.collect.android",
        help_text="Package name for ODK Collect.",
    )
    odk_collect_device_id_template = models.CharField(
        max_length=255,
        blank=True,
        default="${app_user_name}-${device_id}",
        help_text=(
            "Template for the device_id field passed to ODK Collect's managed configuration. "
            "Supports built-in variables: $app_user_name, $device_id, "
            "$serial_number, $imei. Leave blank to omit device_id from the managed configuration."
        ),
    )

    # Device-scope password policy
    device_password_quality = models.CharField(
        max_length=50,
        choices=PasswordQuality,
        default=PasswordQuality.PASSWORD_QUALITY_UNSPECIFIED,
        blank=True,
    )
    device_password_min_length = models.PositiveSmallIntegerField(null=True, blank=True)
    device_password_require_unlock = models.CharField(
        max_length=50,
        choices=RequirePasswordUnlock,
        default=RequirePasswordUnlock.REQUIRE_PASSWORD_UNLOCK_UNSPECIFIED,
        blank=True,
    )

    # Work-profile-scope password policy
    work_password_quality = models.CharField(
        max_length=50,
        choices=PasswordQuality,
        default=PasswordQuality.PASSWORD_QUALITY_UNSPECIFIED,
        blank=True,
    )
    work_password_min_length = models.PositiveSmallIntegerField(null=True, blank=True)
    work_password_require_unlock = models.CharField(
        max_length=50,
        choices=RequirePasswordUnlock,
        default=RequirePasswordUnlock.REQUIRE_PASSWORD_UNLOCK_UNSPECIFIED,
        blank=True,
    )

    # Always-on VPN
    vpn_package_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Package name for always-on VPN. Leave blank to disable.",
    )
    vpn_lockdown = models.BooleanField(
        default=False,
        help_text="If enabled, all networking is blocked when VPN is not connected.",
    )

    # Developer options
    developer_settings = models.CharField(
        max_length=50,
        choices=DeveloperSettings,
        default=DeveloperSettings.DEVELOPER_SETTINGS_DISABLED,
    )

    # Kiosk mode
    kiosk_power_button_actions = models.CharField(
        max_length=60,
        choices=KioskPowerButtonActions,
        default=KioskPowerButtonActions.UNSPECIFIED,
        blank=True,
    )
    kiosk_system_error_warnings = models.CharField(
        max_length=60,
        choices=KioskSystemErrorWarnings,
        default=KioskSystemErrorWarnings.UNSPECIFIED,
        blank=True,
    )
    kiosk_system_navigation = models.CharField(
        max_length=60,
        choices=KioskSystemNavigation,
        default=KioskSystemNavigation.UNSPECIFIED,
        blank=True,
    )
    kiosk_status_bar = models.CharField(
        max_length=60,
        choices=KioskStatusBar,
        default=KioskStatusBar.UNSPECIFIED,
        blank=True,
    )
    kiosk_device_settings = models.CharField(
        max_length=60,
        choices=KioskDeviceSettings,
        default=KioskDeviceSettings.UNSPECIFIED,
        blank=True,
    )
    kiosk_custom_launcher_enabled = models.BooleanField(
        default=False,
        help_text="Enable the custom launcher when the device is in kiosk mode.",
    )

    # Location
    location_mode = models.CharField(
        max_length=50,
        choices=LocationMode,
        default=LocationMode.LOCATION_MODE_UNSPECIFIED,
        blank=True,
    )

    # Device Connectivity Management
    connectivity_usb_data_access = models.CharField(
        max_length=50,
        choices=UsbDataAccess,
        default=UsbDataAccess.USB_DATA_ACCESS_UNSPECIFIED,
        blank=True,
    )
    connectivity_configure_wifi = models.CharField(
        max_length=50,
        choices=ConfigureWifi,
        default=ConfigureWifi.CONFIGURE_WIFI_UNSPECIFIED,
        blank=True,
    )
    connectivity_tethering_settings = models.CharField(
        max_length=50,
        choices=TetheringSettings,
        default=TetheringSettings.TETHERING_SETTINGS_UNSPECIFIED,
        blank=True,
    )
    connectivity_wifi_direct_settings = models.CharField(
        max_length=50,
        choices=WifiDirectSettings,
        default=WifiDirectSettings.WIFI_DIRECT_SETTINGS_UNSPECIFIED,
        blank=True,
    )

    class Meta:
        verbose_name_plural = "policies"
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} ({self.policy_id})"

    def get_policy_data(self, **kwargs):
        """Generates policy data using the PolicySerializer."""
        device = kwargs.get("device")
        applications = list(self.applications.select_related("policy").order_by("order", "pk"))
        variables = list(
            PolicyVariable.decrypted.filter(Q(policy=self) | Q(fleet__in=self.fleets.all()))
        )
        serializer = PolicySerializer(
            policy=self,
            applications=applications,
            variables=variables,
            device=device,
        )
        return serializer.to_dict()


class PolicyApplication(models.Model):
    """One row per app in the policy's applications array."""

    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    package_name = models.CharField(max_length=255)
    install_type = models.CharField(
        max_length=20,
        choices=InstallType,
        default=InstallType.FORCE_INSTALLED,
    )
    disabled = models.BooleanField(default=False)
    managed_configuration = models.JSONField(
        null=True,
        blank=True,
        help_text="Managed configuration for this app (from Play Store iframe).",
    )
    order = models.PositiveSmallIntegerField(default=0)
    default_permission_policy = models.CharField(
        max_length=50,
        choices=PermissionPolicy,
        default=PermissionPolicy.PERMISSION_POLICY_UNSPECIFIED,
        blank=True,
    )

    class Meta:
        ordering = ("order", "pk")
        constraints = (
            models.UniqueConstraint(
                fields=["policy", "package_name"],
                name="unique_policy_application",
            ),
        )

    def __str__(self):
        return f"{self.package_name} ({self.get_install_type_display()})"

    def managed_configuration_str(self):
        """Return managed_configuration JSON as a formatted string for display."""
        if self.managed_configuration is None:
            return ""
        return json.dumps(self.managed_configuration, indent=2)


class PolicyVariable(models.Model):
    """User-defined key/value pairs for variable interpolation at push time."""

    key = models.CharField(max_length=255)
    value = models.CharField(max_length=2048, blank=True)
    value_encrypted = EncryptedCharField(null=True, blank=True)
    is_encrypted = models.BooleanField(default=False)
    scope = models.CharField(max_length=10, choices=PolicyVariableScope)
    policy = models.ForeignKey(
        "mdm.Policy",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="policy_variables",
    )
    fleet = models.ForeignKey(
        "mdm.Fleet",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="policy_variables",
    )

    objects = models.Manager()
    decrypted = EncryptedManager()

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["key", "policy"],
                condition=models.Q(scope="policy"),
                name="unique_policy_policy_variable",
            ),
            models.UniqueConstraint(
                fields=["key", "fleet"],
                condition=models.Q(scope="fleet"),
                name="unique_fleet_policy_variable",
            ),
        )

    def __str__(self):
        return f"{self.key} ({self.get_scope_display()})"

    def clean(self):
        if self.scope == PolicyVariableScope.POLICY:
            if not self.policy:
                raise ValidationError("Policy is required for policy-scoped variables.")
            self.fleet = None
        elif self.scope == PolicyVariableScope.FLEET:
            if not self.fleet:
                raise ValidationError("Fleet is required for fleet-scoped variables.")
            self.policy = None


def enroll_qr_code_path(fleet, filename):
    return f"mdm-enroll-qr-codes/{fleet.organization.slug}/{filename}"


class Fleet(models.Model):
    """A fleet of devices that corresponds to a single group in the MDM."""

    organization = models.ForeignKey(
        "publish_mdm.Organization",
        on_delete=models.CASCADE,
        help_text="The organization that this fleet belongs to.",
        related_name="fleets",
    )
    name = models.CharField(max_length=255)
    mdm_group_id = models.CharField(
        verbose_name="MDM Group ID",
        max_length=32,
        help_text="The ID of the group in the MDM.",
        unique=True,
        null=True,
        blank=True,
    )
    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        help_text="The MDM policy to assign for this fleet of devices.",
        related_name="fleets",
    )
    project = models.ForeignKey(
        "publish_mdm.Project",
        on_delete=models.CASCADE,
        help_text="The project to deploy to this fleet of devices.",
        related_name="fleets",
        null=True,
        blank=True,
    )
    default_app_user = models.ForeignKey(
        "publish_mdm.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_fleet_set",
        help_text="If set, newly enrolled devices are automatically assigned this app user.",
    )
    enroll_qr_code = models.ImageField(
        upload_to=enroll_qr_code_path, null=True, blank=True, verbose_name="enrollment QR code"
    )
    enroll_token_expires_at = models.DateTimeField(blank=True, null=True)
    enroll_token_value = models.CharField(max_length=30, blank=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(fields=["organization", "name"], name="unique_org_and_name"),
        )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        from .mdms import get_active_mdm_instance  # noqa: PLC0415

        sync_with_mdm = kwargs.pop("sync_with_mdm", False)
        super().save(*args, **kwargs)
        if sync_with_mdm and (
            active_mdm := get_active_mdm_instance(organization=self.organization)
        ):
            active_mdm.pull_devices(self)

    def clean(self):
        if self.default_app_user_id:
            if not self.project_id:
                raise ValidationError(
                    {"default_app_user": "A default app user cannot be set without a project."}
                )
            if self.default_app_user.project_id != self.project_id:
                raise ValidationError(
                    {"default_app_user": "The default app user must belong to the fleet's project."}
                )

    @property
    def group_name(self):
        return f"{self.organization.name}: {self.name}"

    @property
    def enroll_token_expired(self):
        if self.enroll_token_expires_at:
            return now() >= self.enroll_token_expires_at
        return False

    @property
    def enrollment_url(self):
        if self.enroll_token_value and self.organization.mdm == "Android Enterprise":
            return f"https://enterprise.google.com/android/enroll?et={self.enroll_token_value}"


class PushMethodChoices(models.TextChoices):
    """Choices for how to push device configurations to the MDM."""

    NEW_AND_UPDATED = "new-and-updated", "Push New and Updated Devices Only"
    ALL = "all", "Push All Devices"


class Device(models.Model):
    """A device that is enrolled in the MDM."""

    fleet = models.ForeignKey(
        "Fleet",
        on_delete=models.CASCADE,
        help_text="The fleet that the device is assigned to.",
        related_name="devices",
    )
    device_id = models.CharField(
        verbose_name="Device ID",
        max_length=32,
        help_text="The ID of the device in the MDM.",
        unique=True,
        blank=True,
        null=True,
    )
    serial_number = models.CharField(
        max_length=255, help_text="The serial number of the device.", blank=True
    )
    name = models.CharField(
        max_length=255, help_text="The name or nickname of the device in the MDM.", blank=True
    )
    raw_mdm_device = models.JSONField(
        verbose_name="Raw MDM Device",
        help_text="The raw JSON response from the MDM for this device.",
        null=True,
        blank=True,
    )
    manufacturer = GeneratedField(
        expression=Coalesce(
            # JSON path for AMAPI:
            KeyTextTransform("manufacturer", KeyTransform("hardwareInfo", "raw_mdm_device")),
            # JSON path for TinyMDM:
            KeyTextTransform("manufacturer", "raw_mdm_device"),
            Value(""),
            output_field=models.TextField(),
        ),
        output_field=models.CharField(max_length=255),
        db_persist=True,
        help_text="The device manufacturer extracted from raw MDM device data.",
    )
    model = GeneratedField(
        expression=Coalesce(
            # JSON path for AMAPI:
            KeyTextTransform("model", KeyTransform("hardwareInfo", "raw_mdm_device")),
            # JSON path for TinyMDM, which doesn't include a "model" but may
            # include the model in the "name" field, if configured as such:
            F("name"),
            Value(""),
            output_field=models.TextField(),
        ),
        output_field=models.CharField(max_length=255),
        db_persist=True,
        help_text="The device model extracted from raw MDM device data or device name.",
    )
    app_user_name = models.CharField(
        max_length=255,
        db_collation="case_insensitive",
        validators=[
            RegexValidator(
                regex=r"^(((:[a-zA-Z_]:?)?[-\w]*)|([-\w]+:[a-zA-Z_][-\w]*))$",
                message="Name can only contain alphanumeric characters, "
                "underscores, hyphens, and not more than one colon.",
            )
        ],
        help_text="Name of the app user (in the Publish MDM app) to assign to this device, if any.",
        blank=True,
    )
    latest_snapshot = models.OneToOneField(
        "DeviceSnapshot",
        on_delete=models.SET_NULL,
        help_text="The latest snapshot of the device.",
        related_name="latest_device",
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.name} ({self.device_id})"

    def save(self, *args, **kwargs):
        from .mdms import get_active_mdm_instance  # noqa: PLC0415

        push_to_mdm = kwargs.pop("push_to_mdm", False)

        if not self.app_user_name and self.fleet_id and self.fleet.default_app_user_id:
            self.app_user_name = self.fleet.default_app_user.name
            if "update_fields" in kwargs:
                kwargs["update_fields"] = [*kwargs["update_fields"], "app_user_name"]

        super().save(*args, **kwargs)
        logger.info(
            "Device saved",
            device_id=self.device_id,
            push_to_mdm=push_to_mdm,
            app_user_name=self.app_user_name,
        )

        if push_to_mdm and (
            active_mdm := get_active_mdm_instance(organization=self.fleet.organization)
        ):
            active_mdm.push_device_config(self)

    def get_odk_collect_qr_code_string(self):
        """Gets a QR code string that can be used to update the managed configuration
        for ODK Collect in the MDM.
        """
        if (
            self.app_user_name
            and self.fleet.project
            and (app_user := self.fleet.project.app_users.filter(name=self.app_user_name).first())
        ):
            return json.dumps(app_user.qr_code_data, separators=(",", ":"))
        return ""

    @property
    def odk_collect_qr_code(self):
        """Gets a ODK Collect QR code string that is safe to insert in the JSON
        template for creating or updating a policy in the MDM.
        """
        # Need to pass the string through dumps() again so the string is properly escaped
        return mark_safe(json.dumps(self.get_odk_collect_qr_code_string()))

    @property
    def username(self):
        return f"{self.app_user_name} - {self.device_id}"


class DeviceSnapshot(models.Model):
    """
    A device that is enrolled in the MDM. Only a subset of the API fields are
    stored in table columns, the rest are stored as JSON in the `raw_mdm_device`
    field.
    """

    device_id = models.CharField(
        verbose_name="Device ID", max_length=255, help_text="The ID of the device in the MDM."
    )
    name = models.CharField(
        max_length=255, help_text="The name or nickname of the device in the MDM."
    )
    serial_number = models.CharField(max_length=255, help_text="The serial number of the device.")
    manufacturer = models.CharField(max_length=64, help_text="The manufacturer of the device.")
    os_version = models.CharField(  # noqa: DJ001
        verbose_name="OS Version",
        max_length=32,
        help_text="The version of the operating system.",
        blank=True,
        null=True,
    )
    battery_level = models.SmallIntegerField(
        help_text="The current battery level of the device, as a percentage.",
        blank=True,
        null=True,
    )
    enrollment_type = models.CharField(
        max_length=32,
        help_text="The type of enrollment for the device.",
    )
    last_sync = models.DateTimeField(
        help_text="Last device synchronization with the MDM servers.",
    )
    latitude = models.FloatField(
        help_text="The last known latitude of the device.", null=True, blank=True
    )
    longitude = models.FloatField(
        help_text="The last known longitude of the device.", null=True, blank=True
    )

    # Non-API fields
    mdm_device = models.ForeignKey(
        "Device",
        on_delete=models.CASCADE,
        help_text="The device that this snapshot is for.",
        related_name="snapshots",
        verbose_name="MDM Device",
        null=True,
        blank=True,
    )
    raw_mdm_device = models.JSONField(
        verbose_name="Raw MDM Device",
        help_text="The full JSON response from the MDM API for this device.",
    )
    synced_at = models.DateTimeField(help_text="When the device snapshot was synced.")

    class Meta:
        indexes = (
            models.Index(fields=["last_sync"]),
            models.Index(fields=["synced_at"]),
        )

    def __str__(self):
        return f"{self.name} ({self.device_id})"


class DeviceSnapshotApp(models.Model):
    """
    An app installed on a device enrolled in the MDM.

    For TinyMDM: https://www.tinymdm.net/mobile-device-management/api/#get-/devices/-id-/apps
    For Android Enterprise: https://developers.google.com/android/management/reference/rest/v1/enterprises.devices#Device.FIELDS.application_reports
    """

    device_snapshot = models.ForeignKey(
        DeviceSnapshot, on_delete=models.CASCADE, related_name="apps"
    )
    package_name = models.CharField(max_length=255, help_text="Complete name of the package.")
    app_name = models.CharField(max_length=255, help_text="Application name")
    version_code = models.IntegerField(help_text="Current version code of the app on the device")
    version_name = models.CharField(
        max_length=128, help_text="Current version name of the app on the device"
    )

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["device_snapshot", "package_name"],
                name="unique_device_snapshot_and_package",
            ),
        )

    def __str__(self):
        return f"{self.app_name} ({self.package_name}) snapshot"


class FirmwareSnapshot(models.Model):
    """
    A firmware installed on a device enrolled in the MDM.
    """

    device_identifier = models.CharField(
        verbose_name="Device Identifier",
        max_length=255,
        help_text="The ID of the device set via the MDM.",
        blank=True,
    )
    serial_number = models.CharField(
        max_length=255, help_text="The serial number of the device.", blank=True
    )
    version = models.CharField(max_length=255, help_text="Firmware version", blank=True)
    synced_at = models.DateTimeField(
        help_text="When the device snapshot was synced.", auto_now_add=True
    )
    raw_data = models.JSONField(
        verbose_name="Raw Device Data",
        help_text="The full data sent by the device to Publish MDM.",
        null=True,
        blank=True,
    )
    device = models.ForeignKey(
        Device,
        on_delete=models.SET_NULL,
        related_name="firmware_snapshots",
        null=True,
        blank=True,
    )

    class Meta:
        indexes = (models.Index(fields=["synced_at"]),)

    def __str__(self):
        return f"{self.device_identifier} ({self.version}) firmware snapshot"
