import django.db.models.deletion
from django.db import migrations, models

from apps.publish_mdm.etl.odk.utils import get_default_collect_settings_field_values


def create_default_collect_settings(apps, schema_editor):
    """Create a 'Default' CollectSettings for each existing Organization,
    and assign it to all projects in that organization.

    Field values are seeded from ``settings.DEFAULT_COLLECT_SETTINGS`` via
    ``get_default_collect_settings_field_values()``; an empty dict is used
    when that setting is not configured.
    """
    Organization = apps.get_model("publish_mdm", "Organization")
    CollectSettings = apps.get_model("publish_mdm", "CollectSettings")
    Project = apps.get_model("publish_mdm", "Project")

    default_field_values = get_default_collect_settings_field_values()
    if default_field_values:
        # Restrict to actual model fields so unknown JSON keys don't cause errors.
        known = {
            f.name
            for f in CollectSettings._meta.fields
            if any(f.name.startswith(prefix) for prefix in ("admin_", "general_", "project_"))
        }
        default_field_values = {k: v for k, v in default_field_values.items() if k in known}
    for org in Organization.objects.all():
        default_settings = CollectSettings.objects.create(
            organization=org,
            name="Default",
            **default_field_values,
        )
        Project.objects.filter(organization=org, collect_settings__isnull=True).update(
            collect_settings=default_settings
        )


class Migration(migrations.Migration):
    dependencies = [
        ("publish_mdm", "0018_alter_organization_mdm"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="project",
            name="app_language",
        ),
        migrations.CreateModel(
            name="CollectSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("modified_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("name", models.CharField(max_length=255)),
                (
                    "project_color",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Hex colour shown for this project in ODK Collect.",
                        max_length=50,
                        verbose_name="Project colour",
                    ),
                ),
                (
                    "project_icon",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Icon shown for this project in ODK Collect.",
                        max_length=20,
                        verbose_name="Project icon",
                    ),
                ),
                (
                    "general_font_size",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("13", "13"),
                            ("17", "17"),
                            ("21", "21"),
                            ("25", "25"),
                            ("29", "29"),
                        ],
                        default="",
                        max_length=5,
                        verbose_name="Font size",
                    ),
                ),
                (
                    "general_form_update_mode",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("manual", "Manual"),
                            ("previously_downloaded", "Previously downloaded"),
                            ("match_exactly", "Match exactly"),
                        ],
                        default="",
                        max_length=30,
                        verbose_name="Form update mode",
                    ),
                ),
                (
                    "general_periodic_form_updates_check",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("every_fifteen_minutes", "Every 15 minutes"),
                            ("every_one_hour", "Every hour"),
                            ("every_six_hours", "Every 6 hours"),
                            ("every_24_hours", "Every 24 hours"),
                        ],
                        default="",
                        max_length=30,
                        verbose_name="Form update check frequency",
                    ),
                ),
                (
                    "general_autosend",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("off", "Off"),
                            ("wifi_only", "Wi-Fi only"),
                            ("cellular_only", "Cellular only"),
                            ("wifi_and_cellular", "Wi-Fi and cellular"),
                        ],
                        default="",
                        max_length=30,
                        verbose_name="Auto-send",
                    ),
                ),
                (
                    "general_app_language",
                    models.CharField(
                        choices=[
                            ("af", "af"),
                            ("am", "am"),
                            ("ar", "ar"),
                            ("bg", "bg"),
                            ("bn", "bn"),
                            ("ca", "ca"),
                            ("cs", "cs"),
                            ("da", "da"),
                            ("de", "de"),
                            ("en", "en"),
                            ("es", "es"),
                            ("et", "et"),
                            ("fa", "fa"),
                            ("fi", "fi"),
                            ("fr", "fr"),
                            ("hi", "hi"),
                            ("in", "in"),
                            ("it", "it"),
                            ("ja", "ja"),
                            ("ka", "ka"),
                            ("km", "km"),
                            ("ln", "ln"),
                            ("lo_LA", "lo_LA"),
                            ("lt", "lt"),
                            ("mg", "mg"),
                            ("ml", "ml"),
                            ("mr", "mr"),
                            ("ms", "ms"),
                            ("my", "my"),
                            ("ne_NP", "ne_NP"),
                            ("nl", "nl"),
                            ("no", "no"),
                            ("pl", "pl"),
                            ("ps", "ps"),
                            ("pt", "pt"),
                            ("ro", "ro"),
                            ("ru", "ru"),
                            ("rw", "rw"),
                            ("si", "si"),
                            ("sl", "sl"),
                            ("so", "so"),
                            ("sq", "sq"),
                            ("sr", "sr"),
                            ("sv_SE", "sv_SE"),
                            ("sw", "sw"),
                            ("sw_KE", "sw_KE"),
                            ("te", "te"),
                            ("th_TH", "th_TH"),
                            ("ti", "ti"),
                            ("tl", "tl"),
                            ("tr", "tr"),
                            ("uk", "uk"),
                            ("ur", "ur"),
                            ("ur_PK", "ur_PK"),
                            ("vi", "vi"),
                            ("zh", "zh"),
                            ("zu", "zu"),
                        ],
                        default="en",
                        help_text="Language used in the ODK Collect UI.",
                        max_length=10,
                        verbose_name="App language",
                    ),
                ),
                (
                    "general_app_theme",
                    models.CharField(
                        blank=True,
                        choices=[("light_theme", "Light"), ("dark_theme", "Dark")],
                        default="",
                        max_length=20,
                        verbose_name="App theme",
                    ),
                ),
                (
                    "general_navigation",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("swipe", "Swipe"),
                            ("buttons", "Buttons"),
                            ("swipe_buttons", "Swipe and buttons"),
                        ],
                        default="",
                        max_length=20,
                        verbose_name="Navigation",
                    ),
                ),
                (
                    "general_constraint_behavior",
                    models.CharField(
                        blank=True,
                        choices=[("on_swipe", "On swipe"), ("on_finalize", "On finalize")],
                        default="",
                        max_length=20,
                        verbose_name="Constraint behaviour",
                    ),
                ),
                (
                    "general_image_size",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("original", "Original"),
                            ("large", "Large"),
                            ("medium", "Medium"),
                            ("small", "Small"),
                            ("very_small", "Very small"),
                        ],
                        default="",
                        max_length=20,
                        verbose_name="Image size",
                    ),
                ),
                (
                    "general_guidance_hint",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("no", "Never"),
                            ("yes", "Always"),
                            ("yes_collapsed", "Collapsed"),
                        ],
                        default="",
                        max_length=20,
                        verbose_name="Guidance for questions",
                    ),
                ),
                (
                    "general_metadata_username",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="Username (metadata)",
                    ),
                ),
                (
                    "general_metadata_phonenumber",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=50,
                        verbose_name="Phone number (metadata)",
                    ),
                ),
                (
                    "general_metadata_email",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="Email address (metadata)",
                    ),
                ),
                (
                    "general_protocol",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("odk_default", "ODK default"),
                            ("google_sheets", "Google Sheets"),
                        ],
                        default="",
                        max_length=20,
                        verbose_name="Protocol",
                    ),
                ),
                (
                    "general_password",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="Password",
                    ),
                ),
                (
                    "general_formlist_url",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=2048,
                        verbose_name="Form list URL",
                    ),
                ),
                (
                    "general_submission_url",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=2048,
                        verbose_name="Submission URL",
                    ),
                ),
                (
                    "general_google_sheets_url",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=2048,
                        verbose_name="Google Sheets URL",
                    ),
                ),
                (
                    "general_basemap_source",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("google", "Google"),
                            ("mapbox", "Mapbox"),
                            ("osm", "OpenStreetMap"),
                            ("usgs", "USGS"),
                            ("stamen", "Stamen"),
                            ("carto", "Carto"),
                        ],
                        default="",
                        max_length=20,
                        verbose_name="Basemap source",
                    ),
                ),
                (
                    "general_google_map_style",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("1", "Normal"),
                            ("2", "Satellite"),
                            ("3", "Terrain"),
                            ("4", "Hybrid"),
                        ],
                        default="",
                        max_length=5,
                        verbose_name="Google map style",
                    ),
                ),
                (
                    "general_mapbox_map_style",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("mapbox://styles/mapbox/light-v10", "Light"),
                            ("mapbox://styles/mapbox/dark-v10", "Dark"),
                            ("mapbox://styles/mapbox/satellite-v9", "Satellite"),
                            ("mapbox://styles/mapbox/satellite-streets-v11", "Satellite streets"),
                            ("mapbox://styles/mapbox/outdoors-v11", "Outdoors"),
                        ],
                        default="",
                        max_length=100,
                        verbose_name="Mapbox map style",
                    ),
                ),
                (
                    "general_usgs_map_style",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("topographic", "Topographic"),
                            ("hybrid", "Hybrid"),
                            ("satellite", "Satellite"),
                        ],
                        default="",
                        max_length=20,
                        verbose_name="USGS map style",
                    ),
                ),
                (
                    "general_carto_map_style",
                    models.CharField(
                        blank=True,
                        choices=[("positron", "Positron"), ("dark_matter", "Dark matter")],
                        default="",
                        max_length=20,
                        verbose_name="Carto map style",
                    ),
                ),
                (
                    "general_reference_layer",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Absolute path to an MBTiles file.",
                        max_length=2048,
                        verbose_name="Reference layer",
                    ),
                ),
                (
                    "general_delete_send",
                    models.BooleanField(default=False, verbose_name="Delete after send"),
                ),
                (
                    "general_default_completed",
                    models.BooleanField(default=True, verbose_name="Default to finalized"),
                ),
                (
                    "general_analytics",
                    models.BooleanField(default=True, verbose_name="Analytics"),
                ),
                (
                    "general_high_resolution",
                    models.BooleanField(default=False, verbose_name="High-resolution video"),
                ),
                (
                    "general_external_app_recording",
                    models.BooleanField(
                        default=True, verbose_name="Allow external app to record audio"
                    ),
                ),
                (
                    "general_instance_sync",
                    models.BooleanField(default=False, verbose_name="Finalize forms on import"),
                ),
                (
                    "general_automatic_update",
                    models.BooleanField(default=False, verbose_name="Automatic update"),
                ),
                (
                    "general_hide_old_form_versions",
                    models.BooleanField(default=False, verbose_name="Hide old form versions"),
                ),
                (
                    "admin_edit_saved",
                    models.BooleanField(default=True, verbose_name="Edit saved forms"),
                ),
                (
                    "admin_send_finalized",
                    models.BooleanField(default=True, verbose_name="Send finalized forms"),
                ),
                (
                    "admin_view_sent",
                    models.BooleanField(default=True, verbose_name="View sent forms"),
                ),
                (
                    "admin_get_blank",
                    models.BooleanField(default=True, verbose_name="Get blank forms"),
                ),
                (
                    "admin_delete_saved",
                    models.BooleanField(default=True, verbose_name="Delete saved forms"),
                ),
                (
                    "admin_qr_code_scanner",
                    models.BooleanField(default=True, verbose_name="QR code scanner"),
                ),
                (
                    "admin_change_server",
                    models.BooleanField(default=True, verbose_name="Change server"),
                ),
                (
                    "admin_change_project_display",
                    models.BooleanField(default=True, verbose_name="Change project display"),
                ),
                (
                    "admin_change_app_theme",
                    models.BooleanField(default=True, verbose_name="Change app theme"),
                ),
                (
                    "admin_change_navigation",
                    models.BooleanField(default=True, verbose_name="Change navigation"),
                ),
                (
                    "admin_maps",
                    models.BooleanField(default=True, verbose_name="Maps"),
                ),
                (
                    "admin_form_update_mode",
                    models.BooleanField(default=True, verbose_name="Show form update mode setting"),
                ),
                (
                    "admin_periodic_form_updates_check",
                    models.BooleanField(default=True, verbose_name="Show check frequency setting"),
                ),
                (
                    "admin_automatic_update",
                    models.BooleanField(default=False, verbose_name="Auto-update"),
                ),
                (
                    "admin_hide_old_form_versions",
                    models.BooleanField(default=True, verbose_name="Hide old form versions"),
                ),
                (
                    "admin_change_autosend",
                    models.BooleanField(default=True, verbose_name="Change auto-send"),
                ),
                (
                    "admin_delete_after_send",
                    models.BooleanField(default=False, verbose_name="Delete after send"),
                ),
                (
                    "admin_default_to_finalized",
                    models.BooleanField(
                        default=True, verbose_name="Show default-to-finalized setting"
                    ),
                ),
                (
                    "admin_change_constraint_behavior",
                    models.BooleanField(default=True, verbose_name="Change constraint behaviour"),
                ),
                (
                    "admin_high_resolution",
                    models.BooleanField(default=True, verbose_name="High resolution"),
                ),
                (
                    "admin_image_size",
                    models.BooleanField(default=True, verbose_name="Image size"),
                ),
                (
                    "admin_guidance_hint",
                    models.BooleanField(default=True, verbose_name="Guidance hint"),
                ),
                (
                    "admin_external_app_recording",
                    models.BooleanField(default=False, verbose_name="External app recording"),
                ),
                (
                    "admin_instance_form_sync",
                    models.BooleanField(default=True, verbose_name="Finalize forms on import"),
                ),
                (
                    "admin_change_form_metadata",
                    models.BooleanField(default=True, verbose_name="Change form metadata"),
                ),
                (
                    "admin_analytics",
                    models.BooleanField(default=True, verbose_name="Show analytics setting"),
                ),
                (
                    "admin_change_app_language",
                    models.BooleanField(default=True, verbose_name="Change app language"),
                ),
                (
                    "admin_change_font_size",
                    models.BooleanField(default=True, verbose_name="Change font size"),
                ),
                (
                    "admin_moving_backwards",
                    models.BooleanField(default=True, verbose_name="Allow backward navigation"),
                ),
                (
                    "admin_access_settings",
                    models.BooleanField(
                        default=True, verbose_name="Access settings from within form"
                    ),
                ),
                (
                    "admin_change_language",
                    models.BooleanField(default=True, verbose_name="Allow language change"),
                ),
                (
                    "admin_jump_to",
                    models.BooleanField(default=True, verbose_name="Jump to"),
                ),
                (
                    "admin_save_mid",
                    models.BooleanField(default=True, verbose_name="Save form"),
                ),
                (
                    "admin_save_as",
                    models.BooleanField(default=True, verbose_name="Name this form"),
                ),
                (
                    "admin_mark_as_finalized",
                    models.BooleanField(default=True, verbose_name="Mark as finalized"),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="collect_settings",
                        to="publish_mdm.organization",
                    ),
                ),
            ],
            options={
                "abstract": False,
                "verbose_name_plural": "collect settings",
            },
        ),
        migrations.AddField(
            model_name="project",
            name="collect_settings",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="projects",
                to="publish_mdm.collectsettings",
                verbose_name="ODK Collect settings",
                help_text="Settings to be used to generate Collect QR codes for this project's app users.",
            ),
        ),
        migrations.RunPython(
            create_default_collect_settings,
            migrations.RunPython.noop,
        ),
    ]
