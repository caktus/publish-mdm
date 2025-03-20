from django.db import models
from django.core.validators import RegexValidator

from apps.odk_publish.models import Project


class Policy(models.Model):
    """A device policy in the MDM."""

    name = models.CharField(max_length=255, help_text="The name of the policy.")
    policy_id = models.CharField(
        verbose_name="Policy ID", max_length=255, help_text="The ID of the policy in the MDM."
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        help_text="The project that this policy belongs to.",
        related_name="policies",
    )

    def save(self, *args, **kwargs):
        from apps.mdm.tasks import get_tinymdm_session, pull_devices

        super().save(*args, **kwargs)
        if session := get_tinymdm_session():
            pull_devices(session, self)

    class Meta:
        verbose_name_plural = "policies"

    def __str__(self):
        return f"{self.name} ({self.policy_id})"


class Device(models.Model):
    """A device that is enrolled in the MDM."""

    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        help_text="The policy that the device is assigned to.",
        related_name="devices",
    )
    device_id = models.CharField(
        verbose_name="Device ID",
        max_length=255,
        help_text="The ID of the device in the MDM.",
        unique=True,
        blank=True,
    )
    serial_number = models.CharField(max_length=255, help_text="The serial number of the device.")
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
        help_text="Name of the app user (in the ODK Publish app) to assign to this device, if any.",
        blank=True,
    )

    def save(self, *args, **kwargs):
        from apps.mdm.tasks import get_tinymdm_session, push_device_config

        super().save(*args, **kwargs)
        if session := get_tinymdm_session():
            push_device_config(session, self)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["policy", "device_id"], name="unique_policy_and_device_id"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.device_id})"
