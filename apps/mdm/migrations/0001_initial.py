# Generated by Django 5.1.5 on 2025-03-19 20:34

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("publish_mdm", "0007_alter_appuser_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="Policy",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(help_text="The name of the policy.", max_length=255)),
                (
                    "policy_id",
                    models.CharField(
                        help_text="The ID of the policy in the MDM.",
                        max_length=255,
                        verbose_name="Policy ID",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        help_text="The project that this policy belongs to.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="policies",
                        to="publish_mdm.project",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "policies",
            },
        ),
        migrations.CreateModel(
            name="Device",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "device_id",
                    models.CharField(
                        blank=True,
                        help_text="The ID of the device in the MDM.",
                        max_length=255,
                        unique=True,
                        verbose_name="Device ID",
                    ),
                ),
                (
                    "serial_number",
                    models.CharField(help_text="The serial number of the device.", max_length=255),
                ),
                (
                    "name",
                    models.CharField(
                        blank=True,
                        help_text="The name or nickname of the device in the MDM.",
                        max_length=255,
                    ),
                ),
                (
                    "raw_mdm_device",
                    models.JSONField(
                        blank=True,
                        help_text="The raw JSON response from the MDM for this device.",
                        null=True,
                        verbose_name="Raw MDM Device",
                    ),
                ),
                (
                    "app_user_name",
                    models.CharField(
                        blank=True,
                        db_collation="case_insensitive",
                        help_text="Name of the app user (in the Publish MDM app) to assign to this device, if any.",
                        max_length=255,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="Name can only contain alphanumeric characters, underscores, hyphens, and not more than one colon.",
                                regex="^(((:[a-zA-Z_]:?)?[-\\w]*)|([-\\w]+:[a-zA-Z_][-\\w]*))$",
                            )
                        ],
                    ),
                ),
                (
                    "policy",
                    models.ForeignKey(
                        help_text="The policy that the device is assigned to.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="devices",
                        to="mdm.policy",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("policy", "device_id"), name="unique_policy_and_device_id"
                    )
                ],
            },
        ),
    ]
