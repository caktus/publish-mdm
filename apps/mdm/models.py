import json

import structlog
from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator
from django.template import Context, Template
from django.utils.html import mark_safe
from django.utils.timezone import now

logger = structlog.get_logger()


class MDMChoices(models.TextChoices):
    TINYMDM = "TinyMDM", "TinyMDM"
    ANDROID_ENTERPRISE = "Android Enterprise", "Android Enterprise"


class PolicyManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(mdm=settings.ACTIVE_MDM["name"])


class Policy(models.Model):
    """A device policy in the MDM."""

    name = models.CharField(max_length=255, help_text="The name of the policy.")
    policy_id = models.CharField(
        verbose_name="Policy ID", max_length=255, help_text="The ID of the policy in the MDM."
    )
    default_policy = models.BooleanField(default=False)
    mdm = models.CharField(max_length=50, choices=MDMChoices, verbose_name="MDM")
    json_template = models.TextField(
        blank=True,
        verbose_name="JSON template",
        help_text="A JSON template (using Django template syntax) that can be used "
        "to create this policy and its child policies.",
    )

    objects = PolicyManager()
    all_mdms = models.Manager()

    class Meta:
        verbose_name_plural = "policies"
        constraints = [
            models.UniqueConstraint(
                fields=["default_policy", "mdm"],
                condition=models.Q(default_policy=True),
                name="unique_default_policy",
                violation_error_message="A default policy already exists.",
            ),
        ]
        # Default policy first
        ordering = ("-default_policy", "id")

    def __str__(self):
        return f"{self.name} ({self.policy_id})"

    @classmethod
    def get_default(cls):
        """Gets the default policy. First tries to get the Policy marked as default.
        If none exists and the MDM_DEFAULT_POLICY setting is set, get or create
        a Policy with that policy_id.
        """
        policy = cls.objects.filter(default_policy=True).first()
        if not policy and settings.MDM_DEFAULT_POLICY:
            policy = cls.objects.get_or_create(
                policy_id=settings.MDM_DEFAULT_POLICY,
                mdm=settings.ACTIVE_MDM["name"],
                defaults={"name": "Default", "default_policy": True},
            )[0]
        return policy

    def get_policy_data(self, **kwargs):
        """Generates policy data that can be used to create/update this policy
        and its child policies in the MDM.
        """
        if self.json_template:
            template = Template(self.json_template)
            context = Context(kwargs)
            policy = template.render(context)
            try:
                return json.loads(policy)
            except json.JSONDecodeError:
                pass
        return None


def enroll_qr_code_path(fleet, filename):
    return f"mdm-enroll-qr-codes/{fleet.organization.slug}/{filename}"


class FleetManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(policy__mdm=settings.ACTIVE_MDM["name"])


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
    enroll_qr_code = models.ImageField(
        upload_to=enroll_qr_code_path, null=True, blank=True, verbose_name="enrollment QR code"
    )
    enroll_token_expires_at = models.DateTimeField(blank=True, null=True)
    enroll_token_value = models.CharField(max_length=30, blank=True)

    objects = FleetManager()
    all_mdms = models.Manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="unique_org_and_name"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        from .mdms import get_active_mdm_instance

        sync_with_mdm = kwargs.pop("sync_with_mdm", False)
        super().save(*args, **kwargs)
        if sync_with_mdm and (active_mdm := get_active_mdm_instance()):
            active_mdm.pull_devices(self)

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
        if self.enroll_token_value and self.policy.mdm == "Android Enterprise":
            return f"https://enterprise.google.com/android/enroll?et={self.enroll_token_value}"


class PushMethodChoices(models.TextChoices):
    """Choices for how to push device configurations to the MDM."""

    NEW_AND_UPDATED = "new-and-updated", "Push New and Updated Devices Only"
    ALL = "all", "Push All Devices"


class DeviceManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(fleet__policy__mdm=settings.ACTIVE_MDM["name"])


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

    objects = DeviceManager()
    all_mdms = models.Manager()

    def save(self, *args, **kwargs):
        from .mdms import get_active_mdm_instance

        push_to_mdm = kwargs.pop("push_to_mdm", False)
        super().save(*args, **kwargs)
        logger.info(
            "Device saved",
            device_id=self.device_id,
            push_to_mdm=push_to_mdm,
            app_user_name=self.app_user_name,
        )

        if push_to_mdm and (active_mdm := get_active_mdm_instance()):
            active_mdm.push_device_config(self)

    def __str__(self):
        return f"{self.name} ({self.device_id})"

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


class DeviceSnapshotManager(models.Manager):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(mdm_device__fleet__policy__mdm=settings.ACTIVE_MDM["name"])
        )


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
    os_version = models.CharField(
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

    objects = DeviceSnapshotManager()
    all_mdms = models.Manager()

    class Meta:
        indexes = [
            models.Index(fields=["last_sync"]),
            models.Index(fields=["synced_at"]),
        ]

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
        constraints = [
            models.UniqueConstraint(
                fields=["device_snapshot", "package_name"],
                name="unique_device_snapshot_and_package",
            ),
        ]

    def __str__(self):
        return f"{self.app_name} ({self.package_name}) snapshot"


class FirmwareSnapshotManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(device__fleet__policy__mdm=settings.ACTIVE_MDM["name"])


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

    objects = FirmwareSnapshotManager()
    all_mdms = models.Manager()

    def __str__(self):
        return f"{self.device_id} ({self.version}) firmware snapshot"

    class Meta:
        indexes = [
            models.Index(fields=["synced_at"]),
        ]
