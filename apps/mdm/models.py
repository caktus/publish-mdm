import structlog
from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator

logger = structlog.get_logger()


class Policy(models.Model):
    """A device policy in the MDM."""

    name = models.CharField(max_length=255, help_text="The name of the policy.")
    policy_id = models.CharField(
        verbose_name="Policy ID", max_length=255, help_text="The ID of the policy in the MDM."
    )
    default_policy = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "policies"
        constraints = [
            models.UniqueConstraint(
                fields=["default_policy"],
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
        If none exists and the TINYMDM_DEFAULT_POLICY setting is set, get or create
        a Policy with that policy_id.
        """
        policy = cls.objects.filter(default_policy=True).first()
        if not policy and settings.TINYMDM_DEFAULT_POLICY:
            policy = cls.objects.get_or_create(
                policy_id=settings.TINYMDM_DEFAULT_POLICY,
                defaults={"name": "Default", "default_policy": True},
            )[0]
        return policy


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

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="unique_org_and_name"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        from apps.mdm.tasks import get_tinymdm_session, pull_devices

        sync_with_mdm = kwargs.pop("sync_with_mdm", False)
        super().save(*args, **kwargs)
        if sync_with_mdm and (session := get_tinymdm_session()):
            pull_devices(session, self)

    @property
    def group_name(self):
        return f"{self.organization.name}: {self.name}"


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

    def save(self, *args, **kwargs):
        from apps.mdm.tasks import get_tinymdm_session, push_device_config

        push_to_mdm = kwargs.pop("push_to_mdm", False)
        super().save(*args, **kwargs)
        logger.info(
            "Device saved",
            device_id=self.device_id,
            push_to_mdm=push_to_mdm,
            app_user_name=self.app_user_name,
        )

        if push_to_mdm:
            if session := get_tinymdm_session():
                push_device_config(session, self)

    def __str__(self):
        return f"{self.name} ({self.device_id})"


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
        verbose_name="OS Version", max_length=32, help_text="The version of the operating system."
    )
    battery_level = models.SmallIntegerField(
        help_text="The current battery level of the device, as a percentage."
    )
    enrollment_type = models.CharField(
        max_length=32,
        help_text="The type of enrollment for the device.",
    )
    last_sync = models.DateTimeField(
        help_text="Last device synchronization with TinyMDM servers.",
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
        indexes = [
            models.Index(fields=["last_sync"]),
            models.Index(fields=["synced_at"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.device_id})"


class DeviceSnapshotApp(models.Model):
    """
    An app installed on a device enrolled in the MDM.

    https://www.tinymdm.net/mobile-device-management/api/#get-/devices/-id-/apps
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

    def __str__(self):
        return f"{self.device_id} ({self.version}) firmware snapshot"

    class Meta:
        indexes = [
            models.Index(fields=["synced_at"]),
        ]
