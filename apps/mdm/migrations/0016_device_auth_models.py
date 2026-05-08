from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("mdm", "0015_merge_0014_device_screen_sharing_0014_enrollmenttoken"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="auth_key_bound_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the current device auth key was bound.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="device",
            name="auth_key_state",
            field=models.CharField(
                choices=[("unbound", "Unbound"), ("active", "Active"), ("revoked", "Revoked")],
                default="unbound",
                help_text="Current state of the bound device auth key.",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="device",
            name="auth_key_version",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Monotonic version for the bound device auth key.",
            ),
        ),
        migrations.AddField(
            model_name="device",
            name="auth_public_key_fingerprint",
            field=models.CharField(
                blank=True,
                default="",
                help_text="SHA-256 fingerprint (hex) of auth_public_key_pem.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="device",
            name="auth_public_key_pem",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Device public key (PEM) used for challenge-response authentication.",
            ),
        ),
        migrations.CreateModel(
            name="DeviceAuthChallenge",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("challenge_id", models.UUIDField(unique=True)),
                ("request_id", models.CharField(max_length=64)),
                ("nonce", models.CharField(max_length=128)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="auth_challenges",
                        to="mdm.device",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="DeviceBindCode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("code_hash", models.CharField(db_index=True, max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="bind_codes",
                        to="mdm.device",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ScreenShareAuditLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("event_type", models.CharField(max_length=64)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("metadata_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="screen_share_audit_logs",
                        to="users.user",
                    ),
                ),
                (
                    "device",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="screen_share_audit_logs",
                        to="mdm.device",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ScreenShareSession",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("session_id", models.UUIDField(unique=True)),
                ("token_hash", models.CharField(db_index=True, max_length=64)),
                ("request_id", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="screen_share_sessions",
                        to="mdm.device",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="deviceauthchallenge",
            index=models.Index(fields=["challenge_id"], name="mdm_devicea_challen_df287e_idx"),
        ),
        migrations.AddIndex(
            model_name="deviceauthchallenge",
            index=models.Index(
                fields=["device", "request_id"], name="mdm_devicea_device__050b57_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="deviceauthchallenge",
            index=models.Index(fields=["expires_at"], name="mdm_devicea_expires_2eb624_idx"),
        ),
        migrations.AddIndex(
            model_name="deviceauthchallenge",
            index=models.Index(fields=["used_at"], name="mdm_devicea_used_at_acd1a4_idx"),
        ),
        migrations.AddIndex(
            model_name="devicebindcode",
            index=models.Index(
                fields=["device", "expires_at"], name="mdm_deviceb_device__ba7750_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="devicebindcode",
            index=models.Index(fields=["used_at"], name="mdm_deviceb_used_at_6e5ccc_idx"),
        ),
        migrations.AddIndex(
            model_name="screenshareauditlog",
            index=models.Index(
                fields=["event_type", "created_at"], name="mdm_screens_event_t_50dd78_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="screenshareauditlog",
            index=models.Index(
                fields=["device", "created_at"], name="mdm_screens_device__167a6d_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="screenshareauditlog",
            index=models.Index(
                fields=["actor", "created_at"], name="mdm_screens_actor_i_e21baa_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="screensharesession",
            index=models.Index(fields=["session_id"], name="mdm_screens_session_35b699_idx"),
        ),
        migrations.AddIndex(
            model_name="screensharesession",
            index=models.Index(
                fields=["device", "request_id"], name="mdm_screens_device__233dc6_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="screensharesession",
            index=models.Index(fields=["expires_at"], name="mdm_screens_expires_e10b2a_idx"),
        ),
        migrations.AddIndex(
            model_name="screensharesession",
            index=models.Index(fields=["used_at"], name="mdm_screens_used_at_1b5111_idx"),
        ),
    ]
