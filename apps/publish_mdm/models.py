import datetime
import uuid
from functools import cached_property
from typing import ClassVar
from urllib.parse import urlparse

import structlog
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models import F, Value
from django.db.models.functions import NullIf
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from invitations.adapters import get_invitations_adapter
from invitations.app_settings import app_settings as invitations_settings
from invitations.base_invitation import AbstractBaseInvitation
from invitations.signals import invite_url_sent

from apps.infisical.api import kms_api
from apps.infisical.fields import EncryptedCharField, EncryptedEmailField, EncryptedMixin
from apps.infisical.managers import EncryptedManager
from apps.mdm.mdms import get_active_mdm_instance
from apps.mdm.models import Fleet, Policy, PolicyApplication
from apps.patterns.soft_delete import SoftDeleteModel
from apps.users.models import User

from .etl import template
from .etl.google import download_user_google_sheet

logger = structlog.getLogger(__name__)


class AbstractBaseModel(models.Model):
    """Abstract base model for all models in the app."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    modified_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True

    @property
    def is_decrypted(self):
        return getattr(self, "_is_decrypted", False)

    def decrypt(self):
        """Decrypt any encrypted fields. Use this if they were not decrypted when
        getting from the database (i.e. if EncryptedManager was not used).
        """
        if self.is_decrypted:
            return
        key_name = self.__class__.__name__.lower()
        for field in self._meta.fields:
            if isinstance(field, EncryptedMixin):
                value = getattr(self, field.name)
                if value:
                    value = kms_api.decrypt(key_name, value)
                    setattr(self, field.name, value)
        self._is_decrypted = True


class Organization(SoftDeleteModel, AbstractBaseModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="organizations")
    public_signup_enabled = models.BooleanField(
        default=False,
        help_text="Enable a public sign-up page, where anyone can enter an email address to receive an invite.",
    )
    mdm = models.CharField(
        max_length=50,
        choices=[(name, name) for name in settings.MDM_REGISTRY],
        default=next(iter(settings.MDM_REGISTRY)),
        help_text="The Mobile Device Management system used by this organization.",
        verbose_name="MDM",
    )
    # Per-org TinyMDM API credentials
    tinymdm_apikey_public = EncryptedCharField(
        null=True,
        blank=True,
        verbose_name="TinyMDM API key (public)",
        help_text="TinyMDM manager API public key.",
    )
    tinymdm_apikey_secret = EncryptedCharField(
        null=True,
        blank=True,
        verbose_name="TinyMDM API key (secret)",
        help_text="TinyMDM manager API secret key.",
    )
    tinymdm_account_id = EncryptedCharField(
        null=True,
        blank=True,
        verbose_name="TinyMDM account ID",
        help_text="TinyMDM account ID.",
    )
    tinymdm_default_policy_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="TinyMDM default policy ID",
        help_text="TinyMDM default policy ID. A Policy with this ID will be created in the database.",
    )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("publish_mdm:organization-home", args=[self.slug])

    def create_default_fleet(self):
        """Create a default MDM Fleet for the organization if the active MDM's API is
        configured.
        """
        active_mdm = get_active_mdm_instance(organization=self)
        if not active_mdm:
            return None
        # Create an org-specific default policy
        if self.mdm == "TinyMDM":
            policy_id = self.tinymdm_default_policy_id
        else:
            # Create a random policy ID to avoid collisions.
            policy_id = policy_id = f"policy_{get_random_string(20)}"
        with transaction.atomic():
            policy = Policy.objects.create(
                name="Default",
                policy_id=policy_id,
                organization=self,
            )
            if self.mdm != "TinyMDM":
                # Create the pinned ODK Collect app row (order=0) so new policies are consistent
                # with those created via the policy editor UI.
                PolicyApplication.objects.create(
                    policy=policy,
                    package_name=policy.odk_collect_package,
                    install_type="FORCE_INSTALLED",
                    order=0,
                )
            # Ensure the default policy exists in the MDM before linking groups to it.
            active_mdm.create_or_update_policy(policy)
            fleet = Fleet(organization=self, name="Default", policy=policy)
            active_mdm.create_group(fleet)
            active_mdm.add_group_to_policy(fleet)
            active_mdm.get_enrollment_qr_code(fleet)
            fleet.save()
        return fleet


class CentralServer(AbstractBaseModel):
    """A server running ODK Central."""

    base_url = models.URLField(max_length=1024, verbose_name="base URL")
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="central_servers"
    )
    username = EncryptedEmailField(null=True)
    password = EncryptedCharField(null=True)

    # The default manager will *not* decrypt usernames and passwords after fetching
    # them from the database. Usernames and passwords will be encrypted when saving
    # with both managers
    objects = models.Manager()
    decrypted = EncryptedManager()

    def __str__(self):
        parsed_url = urlparse(self.base_url)
        return parsed_url.netloc

    def save(self, *args, **kwargs):
        self.base_url = self.base_url.rstrip("/")
        super().save(*args, **kwargs)

    @property
    def masked_username(self):
        """If a username is set, partially hide it."""
        if self.username:
            mask = "*" * 5
            if "@" in self.username:
                name, rest = self.username.split("@", 1)
                return f"{name[0]}{mask}@{rest}"
            return f"{self.username[0]}{mask}"
        return self.username


class TemplateVariable(AbstractBaseModel):
    """A variable that can be used in a FormTemplate."""

    name = models.CharField(
        max_length=255,
        validators=[
            # https://docs.getodk.org/xlsform/#the-survey-sheet
            RegexValidator(
                regex=r"^[A-Za-z_][A-Za-z0-9_]*$",
                message="Name must start with a letter or underscore and contain no spaces.",
            )
        ],
    )
    transform = models.CharField(choices=template.VariableTransform.choices(), blank=True)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="template_variables"
    )

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["name", "organization"], name="unique_template_variable_name"
            ),
        )

    def __str__(self):
        return self.name


class Project(AbstractBaseModel):
    """A project in ODK Central."""

    # Choices for various ODK Collect settings.
    # https://docs.getodk.org/collect-import-export/#list-of-keys-for-all-settings
    # https://github.com/getodk/collect/blob/master/settings/src/main/resources/client-settings.schema.json
    APP_LANGUAGE_CHOICES: ClassVar = list(
        zip(
            *[
                [
                    "af",
                    "am",
                    "ar",
                    "bg",
                    "bn",
                    "ca",
                    "cs",
                    "da",
                    "de",
                    "en",
                    "es",
                    "et",
                    "fa",
                    "fi",
                    "fr",
                    "hi",
                    "in",
                    "it",
                    "ja",
                    "ka",
                    "km",
                    "ln",
                    "lo_LA",
                    "lt",
                    "mg",
                    "ml",
                    "mr",
                    "ms",
                    "my",
                    "ne_NP",
                    "nl",
                    "no",
                    "pl",
                    "ps",
                    "pt",
                    "ro",
                    "ru",
                    "rw",
                    "si",
                    "sl",
                    "so",
                    "sq",
                    "sr",
                    "sv_SE",
                    "sw",
                    "sw_KE",
                    "te",
                    "th_TH",
                    "ti",
                    "tl",
                    "tr",
                    "uk",
                    "ur",
                    "ur_PK",
                    "vi",
                    "zh",
                    "zu",
                ]
            ]
            * 2,
            strict=False,
        )
    )
    FONT_SIZE_CHOICES: ClassVar = [
        ("13", "13"),
        ("17", "17"),
        ("21", "21"),
        ("25", "25"),
        ("29", "29"),
    ]
    FORM_UPDATE_MODE_CHOICES: ClassVar = [
        ("manual", "Manual"),
        ("previously_downloaded", "Previously downloaded"),
        ("match_exactly", "Match exactly"),
    ]
    PERIODIC_FORM_UPDATES_CHECK_CHOICES: ClassVar = [
        ("every_fifteen_minutes", "Every 15 minutes"),
        ("every_one_hour", "Every hour"),
        ("every_six_hours", "Every 6 hours"),
        ("every_24_hours", "Every 24 hours"),
    ]
    AUTOSEND_CHOICES: ClassVar = [
        ("off", "Off"),
        ("wifi_only", "Wi-Fi only"),
        ("cellular_only", "Cellular only"),
        ("wifi_and_cellular", "Wi-Fi and cellular"),
    ]
    APP_THEME_CHOICES: ClassVar = [
        ("light_theme", "Light"),
        ("dark_theme", "Dark"),
    ]
    NAVIGATION_CHOICES: ClassVar = [
        ("swipe", "Swipe"),
        ("buttons", "Buttons"),
        ("swipe_buttons", "Swipe and buttons"),
    ]
    CONSTRAINT_BEHAVIOR_CHOICES: ClassVar = [
        ("on_swipe", "On swipe"),
        ("on_finalize", "On finalize"),
    ]
    IMAGE_SIZE_CHOICES: ClassVar = [
        ("original", "Original"),
        ("large", "Large"),
        ("medium", "Medium"),
        ("small", "Small"),
        ("very_small", "Very small"),
    ]
    GUIDANCE_HINT_CHOICES: ClassVar = [
        ("no", "Never"),
        ("yes", "Always"),
        ("yes_collapsed", "Collapsed"),
    ]
    PROTOCOL_CHOICES: ClassVar = [
        ("odk_default", "ODK default"),
        ("google_sheets", "Google Sheets"),
    ]
    BASEMAP_SOURCE_CHOICES: ClassVar = [
        ("google", "Google"),
        ("mapbox", "Mapbox"),
        ("osm", "OpenStreetMap"),
        ("usgs", "USGS"),
        ("stamen", "Stamen"),
        ("carto", "Carto"),
    ]
    GOOGLE_MAP_STYLE_CHOICES: ClassVar = [
        ("1", "Normal"),
        ("2", "Satellite"),
        ("3", "Terrain"),
        ("4", "Hybrid"),
    ]
    MAPBOX_MAP_STYLE_CHOICES: ClassVar = [
        ("mapbox://styles/mapbox/light-v10", "Light"),
        ("mapbox://styles/mapbox/dark-v10", "Dark"),
        ("mapbox://styles/mapbox/satellite-v9", "Satellite"),
        ("mapbox://styles/mapbox/satellite-streets-v11", "Satellite streets"),
        ("mapbox://styles/mapbox/outdoors-v11", "Outdoors"),
    ]
    USGS_MAP_STYLE_CHOICES: ClassVar = [
        ("topographic", "Topographic"),
        ("hybrid", "Hybrid"),
        ("satellite", "Satellite"),
    ]
    CARTO_MAP_STYLE_CHOICES: ClassVar = [
        ("positron", "Positron"),
        ("dark_matter", "Dark matter"),
    ]

    name = models.CharField(max_length=255)
    central_id = models.PositiveIntegerField(
        verbose_name="project ID", help_text="The ID of this project in ODK Central."
    )
    central_server = models.ForeignKey(
        CentralServer, on_delete=models.CASCADE, related_name="projects"
    )
    template_variables = models.ManyToManyField(
        TemplateVariable,
        related_name="projects",
        verbose_name="App user template variables",
        help_text="Variables selected here will be set for each app user.",
        blank=True,
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="projects"
    )

    # ---------------------------------------------------------------------------
    # ODK Collect settings — individual fields so each can have its own default,
    # validation, and form widget.  A CollectSettingsSerializer assembles these
    # into the nested dict expected by build_collect_settings().
    #
    # Dynamic fields (server_url, username) depend on the app user assignment
    # and are set in build_collect_settings().
    # All other settings (app_language, admin_pw, project name) come
    # from model fields and are assembled by CollectSettingsSerializer.
    # ---------------------------------------------------------------------------

    # Project display
    collect_project_color = models.CharField(
        max_length=50,
        default="#6ec1e4",
        blank=True,
        verbose_name="Project colour",
        help_text="Hex colour shown for this project in ODK Collect.",
    )
    collect_project_icon = models.CharField(
        max_length=10,
        default="🇱🇾",
        blank=True,
        verbose_name="Project icon",
        help_text="Emoji icon shown for this project in ODK Collect.",
    )

    # General — font / form management / autosend
    collect_general_font_size = models.CharField(
        max_length=5,
        choices=FONT_SIZE_CHOICES,
        default="25",
        verbose_name="Font size",
    )
    collect_general_form_update_mode = models.CharField(
        max_length=30,
        choices=FORM_UPDATE_MODE_CHOICES,
        default="match_exactly",
        verbose_name="Form update mode",
    )
    collect_general_periodic_form_updates_check = models.CharField(
        max_length=30,
        choices=PERIODIC_FORM_UPDATES_CHECK_CHOICES,
        default="every_one_hour",
        verbose_name="Form update check frequency",
    )
    collect_general_autosend = models.CharField(
        max_length=30,
        choices=AUTOSEND_CHOICES,
        default="wifi_and_cellular",
        verbose_name="Auto-send",
    )
    collect_general_delete_send = models.BooleanField(
        default=False,
        verbose_name="Delete after send",
    )
    collect_general_default_completed = models.BooleanField(
        default=True,
        verbose_name="Default to finalized",
    )
    collect_general_analytics = models.BooleanField(
        default=True,
        verbose_name="Analytics",
    )

    # General — user interface
    collect_general_app_language = models.CharField(
        max_length=10,
        choices=APP_LANGUAGE_CHOICES,
        default="en",
        verbose_name="App language",
        help_text="Language used in the ODK Collect UI.",
    )
    collect_general_app_theme = models.CharField(
        max_length=20,
        choices=APP_THEME_CHOICES,
        default="",
        blank=True,
        verbose_name="App theme",
    )
    collect_general_navigation = models.CharField(
        max_length=20,
        choices=NAVIGATION_CHOICES,
        default="",
        blank=True,
        verbose_name="Navigation",
    )

    # General — form entry
    collect_general_constraint_behavior = models.CharField(
        max_length=20,
        choices=CONSTRAINT_BEHAVIOR_CHOICES,
        default="",
        blank=True,
        verbose_name="Constraint behaviour",
    )
    collect_general_high_resolution = models.BooleanField(
        default=False,
        verbose_name="High-resolution video",
    )
    collect_general_image_size = models.CharField(
        max_length=20,
        choices=IMAGE_SIZE_CHOICES,
        default="",
        blank=True,
        verbose_name="Image size",
    )
    collect_general_external_app_recording = models.BooleanField(
        default=True,
        verbose_name="Allow external app to record audio",
    )
    collect_general_guidance_hint = models.CharField(
        max_length=20,
        choices=GUIDANCE_HINT_CHOICES,
        default="",
        blank=True,
        verbose_name="Guidance for questions",
    )
    collect_general_instance_sync = models.BooleanField(
        default=False,
        verbose_name="Finalize forms on import",
    )

    # General — user and device identity
    collect_general_metadata_username = models.CharField(
        max_length=255,
        default="",
        blank=True,
        verbose_name="Username (metadata)",
    )
    collect_general_metadata_phonenumber = models.CharField(
        max_length=50,
        default="",
        blank=True,
        verbose_name="Phone number (metadata)",
    )
    collect_general_metadata_email = models.CharField(
        max_length=255,
        default="",
        blank=True,
        verbose_name="Email address (metadata)",
    )

    # General — server
    collect_general_protocol = models.CharField(
        max_length=20,
        choices=PROTOCOL_CHOICES,
        default="",
        blank=True,
        verbose_name="Protocol",
    )
    collect_general_password = models.CharField(
        max_length=255,
        default="",
        blank=True,
        verbose_name="Password",
    )
    collect_general_formlist_url = models.CharField(
        max_length=2048,
        default="",
        blank=True,
        verbose_name="Form list URL",
    )
    collect_general_submission_url = models.CharField(
        max_length=2048,
        default="",
        blank=True,
        verbose_name="Submission URL",
    )
    collect_general_google_sheets_url = models.CharField(
        max_length=2048,
        default="",
        blank=True,
        verbose_name="Google Sheets URL",
    )

    # General — form management (additional booleans)
    collect_general_automatic_update = models.BooleanField(
        default=False,
        verbose_name="Automatic update",
    )
    collect_general_hide_old_form_versions = models.BooleanField(
        default=False,
        verbose_name="Hide old form versions",
    )

    # General — maps
    collect_general_basemap_source = models.CharField(
        max_length=20,
        choices=BASEMAP_SOURCE_CHOICES,
        default="",
        blank=True,
        verbose_name="Basemap source",
    )
    collect_general_google_map_style = models.CharField(
        max_length=5,
        choices=GOOGLE_MAP_STYLE_CHOICES,
        default="",
        blank=True,
        verbose_name="Google map style",
    )
    collect_general_mapbox_map_style = models.CharField(
        max_length=100,
        choices=MAPBOX_MAP_STYLE_CHOICES,
        default="",
        blank=True,
        verbose_name="Mapbox map style",
    )
    collect_general_usgs_map_style = models.CharField(
        max_length=20,
        choices=USGS_MAP_STYLE_CHOICES,
        default="",
        blank=True,
        verbose_name="USGS map style",
    )
    collect_general_carto_map_style = models.CharField(
        max_length=20,
        choices=CARTO_MAP_STYLE_CHOICES,
        default="",
        blank=True,
        verbose_name="Carto map style",
    )
    collect_general_reference_layer = models.CharField(
        max_length=2048,
        default="",
        blank=True,
        verbose_name="Reference layer",
        help_text="Absolute path to an MBTiles file.",
    )

    # Admin — main menu access controls
    collect_admin_edit_saved = models.BooleanField(
        default=False,
        verbose_name="Edit saved forms",
    )
    collect_admin_send_finalized = models.BooleanField(
        default=False,
        verbose_name="Send finalized forms",
    )
    collect_admin_view_sent = models.BooleanField(
        default=False,
        verbose_name="View sent forms",
    )
    collect_admin_get_blank = models.BooleanField(
        default=False,
        verbose_name="Get blank forms",
    )
    collect_admin_delete_saved = models.BooleanField(
        default=False,
        verbose_name="Delete saved forms",
    )
    collect_admin_qr_code_scanner = models.BooleanField(
        default=False,
        verbose_name="QR code scanner",
    )

    # Admin — project settings access controls
    collect_admin_change_server = models.BooleanField(
        default=False,
        verbose_name="Change server",
    )
    collect_admin_change_project_display = models.BooleanField(
        default=False,
        verbose_name="Change project display",
    )
    collect_admin_change_app_theme = models.BooleanField(
        default=False,
        verbose_name="Change app theme",
    )
    collect_admin_change_navigation = models.BooleanField(
        default=False,
        verbose_name="Change navigation",
    )
    collect_admin_maps = models.BooleanField(
        default=False,
        verbose_name="Maps",
    )

    # Admin — form management access controls
    collect_admin_form_update_mode = models.BooleanField(
        default=False,
        verbose_name="Show form update mode setting",
    )
    collect_admin_periodic_form_updates_check = models.BooleanField(
        default=False,
        verbose_name="Show check frequency setting",
    )
    collect_admin_automatic_update = models.BooleanField(
        default=False,
        verbose_name="Auto-update",
    )
    collect_admin_hide_old_form_versions = models.BooleanField(
        default=False,
        verbose_name="Hide old form versions",
    )
    collect_admin_change_autosend = models.BooleanField(
        default=False,
        verbose_name="Change auto-send",
    )
    collect_admin_delete_after_send = models.BooleanField(
        default=False,
        verbose_name="Delete after send",
    )
    collect_admin_default_to_finalized = models.BooleanField(
        default=False,
        verbose_name="Show default-to-finalized setting",
    )
    collect_admin_change_constraint_behavior = models.BooleanField(
        default=False,
        verbose_name="Change constraint behaviour",
    )
    collect_admin_high_resolution = models.BooleanField(
        default=False,
        verbose_name="High resolution",
    )
    collect_admin_image_size = models.BooleanField(
        default=False,
        verbose_name="Image size",
    )
    collect_admin_guidance_hint = models.BooleanField(
        default=False,
        verbose_name="Guidance hint",
    )
    collect_admin_external_app_recording = models.BooleanField(
        default=False,
        verbose_name="External app recording",
    )
    collect_admin_instance_form_sync = models.BooleanField(
        default=False,
        verbose_name="Finalize forms on import",
    )
    collect_admin_change_form_metadata = models.BooleanField(
        default=False,
        verbose_name="Change form metadata",
    )
    collect_admin_analytics = models.BooleanField(
        default=False,
        verbose_name="Show analytics setting",
    )
    collect_admin_change_app_language = models.BooleanField(
        default=False,
        verbose_name="Change app language",
    )
    collect_admin_change_font_size = models.BooleanField(
        default=False,
        verbose_name="Change font size",
    )

    # Admin — form entry access controls
    collect_admin_moving_backwards = models.BooleanField(
        default=True,
        verbose_name="Allow backward navigation",
    )
    collect_admin_access_settings = models.BooleanField(
        default=False,
        verbose_name="Access settings from within form",
    )
    collect_admin_change_language = models.BooleanField(
        default=True,
        verbose_name="Allow language change",
    )
    collect_admin_jump_to = models.BooleanField(
        default=False,
        verbose_name="Jump to",
    )
    collect_admin_save_mid = models.BooleanField(
        default=False,
        verbose_name="Save form",
    )
    collect_admin_save_as = models.BooleanField(
        default=False,
        verbose_name="Name this form",
    )
    collect_admin_mark_as_finalized = models.BooleanField(
        default=False,
        verbose_name="Mark as finalized",
    )

    def __str__(self):
        return f"{self.name} ({self.central_id})"

    def get_admin_pw(self):
        """Get the value of the project-level admin_pw template variable.
        Will return None if the template variable does not exist.
        """
        return (
            self.project_template_variables.filter(template_variable__name="admin_pw")
            .values_list("value", flat=True)
            .first()
        )


class ProjectTemplateVariable(AbstractBaseModel):
    """A template variable value for a project."""

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="project_template_variables"
    )
    template_variable = models.ForeignKey(
        TemplateVariable, on_delete=models.CASCADE, related_name="projects_through"
    )
    value = models.CharField(
        verbose_name="Project-wide value", max_length=1024, blank=True, help_text="Optional"
    )

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["project", "template_variable"], name="unique_project_template_variable"
            ),
        )

    def __str__(self):
        return f"{self.value} ({self.id})"


class FormTemplate(AbstractBaseModel):
    """A form "template" published to potentially multiple ODK Central forms."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="form_templates")
    title_base = models.CharField(
        max_length=255,
        help_text=(
            "The title to appear in the ODK Collect form list and header of each form "
            "page. The App User will be appended to this title."
        ),
    )
    form_id_base = models.CharField(
        verbose_name="Form ID Base",
        max_length=255,
        help_text=(
            "The prefix of the xml_form_id used to identify the form in ODK Central. "
            "The App User will be appended to this value."
        ),
    )
    template_url = models.URLField(
        verbose_name="Template URL",
        max_length=1024,
        blank=True,
        help_text=(
            "The URL of the Google Sheet template. A new version of this sheet will be "
            "downloaded for each form publish event."
        ),
    )
    template_url_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.CASCADE
    )

    def __str__(self):
        return f"{self.form_id_base} ({self.id})"

    def get_app_users(self, names: list[str] | None = None) -> models.QuerySet["AppUser"]:
        """Get the app users assigned to this form template."""
        q = models.Q(app_user_forms__form_template=self)
        if names:
            q &= models.Q(app_user_forms__app_user__name__in=names)
        return AppUser.objects.filter(q)

    def download_user_google_sheet(self, user: User, name: str) -> SimpleUploadedFile:
        """Download the Google Sheet Excel file for this form template."""
        social_token = user.get_google_social_token()
        if social_token is None:
            raise ValueError("User does not have a Google social token.")
        return download_user_google_sheet(
            token=social_token.token,
            token_secret=social_token.token_secret,
            sheet_url=self.template_url,
            name=name,
        )


class FormTemplateVersion(AbstractBaseModel):
    """A version (like v5) of a form template."""

    form_template = models.ForeignKey(
        FormTemplate, on_delete=models.CASCADE, related_name="versions"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="form_template_versions")
    file = models.FileField(upload_to="form-templates/")
    version = models.CharField(max_length=255)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["form_template", "version"], name="unique_form_template_version"
            ),
        )

    def __str__(self):
        return self.file.name

    def create_app_user_versions(
        self,
        app_users: models.QuerySet["AppUser"] | None = None,
        send_message=None,
        attachments: dict | None = None,
    ) -> list["AppUserFormVersion"]:
        """Create the next version of this form template for each app user."""
        app_user_versions = []
        q = models.Q(form_template=self.form_template)
        # Optionally limit to specific app users (partial publish)
        if app_users is not None:
            q &= models.Q(app_user__in=app_users)
        # Create the next version for each app user
        for app_user_form in AppUserFormTemplate.objects.filter(q):
            logger.info("Creating next AppUserFormVersion", app_user_form=app_user_form)
            app_user_version = app_user_form.create_next_version(
                form_template_version=self, attachments=attachments
            )
            xml_form_id = app_user_version.app_user_form_template.xml_form_id
            version = app_user_version.form_template_version.version
            if send_message:
                send_message(f"Created FormTemplateVersion({xml_form_id=}, {version=})")
            app_user_versions.append(app_user_version)
        return app_user_versions


class AppUserTemplateVariable(AbstractBaseModel):
    """A template variable value for an app user."""

    app_user = models.ForeignKey(
        "AppUser", on_delete=models.CASCADE, related_name="app_user_template_variables"
    )
    template_variable = models.ForeignKey(
        TemplateVariable, on_delete=models.CASCADE, related_name="app_users_through"
    )
    value = models.CharField(max_length=1024)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["app_user", "template_variable"], name="unique_app_user_template_variable"
            ),
        )

    def __str__(self):
        return f"{self.value} ({self.id})"


class AppUser(AbstractBaseModel):
    """An app user in ODK Central."""

    # While ODK Central does not limit the characters that can be used in an
    # app user's name, we have to limit the characters so that we can use the name
    # in `build_entity_list_mapping()` to generate valid entity list names.
    # An entity list name must be a valid XML identifier and cannot include a period.
    # (See https://docs.getodk.org/central-api-dataset-management/#creating-datasets and
    # https://getodk.github.io/xforms-spec/entities.html#declaring-that-a-form-creates-entities)
    # The RegexValidator below ensures that *when this name is appended* to an entity
    # name prefix it will result in a valid entity list name.
    name = models.CharField(
        max_length=255,
        db_collation="case_insensitive",
        validators=[
            RegexValidator(
                regex=r"^(((:[a-zA-Z_]:?)?[-\w]*)|([-\w]+:[a-zA-Z_][-\w]*))$",
                message="Name can only contain alphanumeric characters, "
                "underscores, hyphens, and not more than one colon.",
            )
        ],
    )
    central_id = models.PositiveIntegerField(
        verbose_name="app user ID",
        help_text="The ID of this app user in ODK Central.",
        blank=True,
        null=True,
    )
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="app_users")
    qr_code = models.ImageField(
        verbose_name="QR Code", upload_to="qr-codes/", blank=True, null=True
    )
    template_variables = models.ManyToManyField(
        through=AppUserTemplateVariable, to=TemplateVariable, related_name="app_users", blank=True
    )
    qr_code_data = models.JSONField(verbose_name="QR Code data", blank=True, null=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(fields=["project", "name"], name="unique_project_name"),
        )

    def __str__(self):
        return self.name

    def get_template_variables(self) -> list[template.TemplateVariable]:
        """Get the project's template variables with this app user's values."""
        # First get project-level variables
        variables = {
            var["name"]: var
            for var in self.project.project_template_variables.annotate(
                name=F("template_variable__name"),
                transform=NullIf(F("template_variable__transform"), Value("")),
            ).values("name", "value", "transform")
        }
        # Then get app-level variables
        for app_user_var in self.app_user_template_variables.annotate(
            name=F("template_variable__name"),
            transform=NullIf(F("template_variable__transform"), Value("")),
        ).values("name", "value", "transform"):
            variables[app_user_var["name"]] = app_user_var
        return [
            template.TemplateVariable.model_validate(variable) for variable in variables.values()
        ]

    @property
    def form_templates(self):
        """Get a set of the form_id_base values from the user's related FormTemplates.
        Used by the "form_templates" column in the files for exporting/importing AppUsers.
        """
        # Prevent `ValueError('AppUser' instance needs to have a primary key
        # value before this relationship can be used)`
        if self.pk:
            return {obj.form_template.form_id_base for obj in self.app_user_forms.all()}
        return set()

    @cached_property
    def app_user_template_variables_dict(self) -> dict[str, str]:
        """Get a dict of the user's template variable values, with the TemplateVariable
        name as the key. Used during import/export of AppUsers to minimize DB queries.
        This assumes the template variables are prefetched.
        """
        # Prevent `ValueError('AppUser' instance needs to have a primary key
        # value before this relationship can be used)`
        if self.pk:
            return {
                i.template_variable.name: i.value for i in self.app_user_template_variables.all()
            }
        return {}

    @cached_property
    def all_template_variables_dict(self) -> dict[str, str]:
        """Get a dict of the user's template variable values, including project-level variables,
        with the TemplateVariable name as the key.
        """
        # Prevent `ValueError('AppUser' instance needs to have a primary key
        # value before this relationship can be used)`
        return {var.name: var.value for var in self.get_template_variables()}

    def get_any_template_variable(self, name: str) -> str | None:
        """
        Get the project- or app-level template variable value with this name for this app user,
        or any empty string.
        """
        return self.all_template_variables_dict.get(name, "")


class AppUserFormTemplate(AbstractBaseModel):
    """An app user's form template assignment."""

    app_user = models.ForeignKey(AppUser, on_delete=models.CASCADE, related_name="app_user_forms")
    form_template = models.ForeignKey(
        FormTemplate, on_delete=models.CASCADE, related_name="app_user_forms"
    )

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["app_user", "form_template"], name="unique_app_user_form_template"
            ),
        )

    def __str__(self):
        return self.xml_form_id

    @property
    def xml_form_id(self) -> str:
        """The ODK Central xmlFormId for this AppUserFormTemplate."""
        return f"{self.form_template.form_id_base}_{self.app_user.name}"

    def create_next_version(
        self, form_template_version: FormTemplateVersion, attachments: dict | None = None
    ):
        """Create the next version of this app user form template."""
        from .etl.transform import render_template_for_app_user  # noqa: PLC0415

        version_file = render_template_for_app_user(
            app_user=self.app_user, template_version=form_template_version, attachments=attachments
        )
        return AppUserFormVersion.objects.create(
            app_user_form_template=self,
            form_template_version=form_template_version,
            file=version_file,
        )


class AppUserFormVersion(AbstractBaseModel):
    """A version of an app user's form template that is published to ODK Central."""

    app_user_form_template = models.ForeignKey(
        AppUserFormTemplate,
        on_delete=models.CASCADE,
        related_name="app_user_form_template_versions",
    )
    form_template_version = models.ForeignKey(
        FormTemplateVersion, on_delete=models.CASCADE, related_name="app_user_form_templates"
    )
    file = models.FileField(upload_to="form-templates/")

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["app_user_form_template", "form_template_version"],
                name="unique_app_user_form_template_version",
            ),
        )

    def __str__(self):
        return f"{self.app_user_form_template} - {self.form_template_version}"

    @property
    def xml_form_id(self) -> str:
        """The ODK Central xmlFormId for this version's AppUserFormTemplate."""
        return self.app_user_form_template.xml_form_id

    @property
    def app_user(self) -> AppUser:
        """The app user for this version."""
        return self.app_user_form_template.app_user


def project_directory_path(instance: "ProjectAttachment", filename: str):
    return f"project/{instance.project.id}/attachment/{filename}"


class ProjectAttachment(AbstractBaseModel):
    name = models.CharField(max_length=255)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=project_directory_path)

    class Meta:
        constraints = (
            models.UniqueConstraint(fields=["project", "name"], name="unique_project_attachments"),
        )

    def __str__(self):
        return f"{self.name}: {self.file.name}"


class OrganizationInvitation(AbstractBaseInvitation):
    """Similar to django-invitation's builtin Invitation model, but adds a FK
    to Organization and removes the unique constraint on the email field.
    """

    email = models.EmailField(
        verbose_name=_("e-mail address"),
        max_length=invitations_settings.EMAIL_MAX_LENGTH,
    )
    created = models.DateTimeField(verbose_name=_("created"), default=timezone.now)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    @classmethod
    def create(cls, email, inviter=None, **kwargs):
        """Identical to django-invitation's Invitation model."""
        key = get_random_string(64).lower()
        instance = cls._default_manager.create(email=email, key=key, inviter=inviter, **kwargs)
        return instance

    def key_expired(self):
        """Identical to django-invitation's Invitation model."""
        expiration_date = self.sent + datetime.timedelta(
            days=invitations_settings.INVITATION_EXPIRY,
        )
        return expiration_date <= timezone.now()

    def send_invitation(self, request, **kwargs):
        """Identical to django-invitation's Invitation model except for the
        new context variables indicated below.
        """
        current_site = get_current_site(request)
        invite_url = reverse(invitations_settings.CONFIRMATION_URL_NAME, args=[self.key])
        invite_url = request.build_absolute_uri(invite_url)
        ctx = kwargs
        ctx.update(
            {
                "invite_url": invite_url,
                "site_name": current_site.name,
                "email": self.email,
                "key": self.key,
                "inviter": self.inviter,
                # New context variables below
                "organization_name": self.organization.name,
                "expiry_days": invitations_settings.INVITATION_EXPIRY,
            },
        )

        email_template = "invitations/email/email_invite"

        get_invitations_adapter().send_mail(email_template, self.email, ctx)
        self.sent = timezone.now()
        self.save()

        invite_url_sent.send(
            sender=self.__class__,
            instance=self,
            invite_url_sent=invite_url,
            inviter=self.inviter,
        )

    def __str__(self):
        return f"Invite: {self.email}"


class AndroidEnterpriseAccount(AbstractBaseModel):
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="android_enterprise",
    )
    signup_url_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="signupUrls resource name from AMAPI, e.g. 'signupUrls/C455570ef9b12bfc'.",
    )
    signup_url = models.URLField(
        max_length=2048,
        blank=True,
        default="",
        help_text="Google Enterprise signup URL. Navigate here to complete enterprise creation.",
    )
    callback_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Embedded in the callback URL to authenticate Google's redirect.",
    )
    enterprise_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Full AMAPI enterprise resource name, e.g. 'enterprises/LC00lvvue0'.",
    )

    def __str__(self):
        return self.enterprise_name or f"(pending) {self.organization}"

    @property
    def enterprise_id(self):
        """Short ID, e.g. 'LC00lvvue0'. Empty string until enrollment completes."""
        if self.enterprise_name:
            return self.enterprise_name.split("/")[-1]
        return ""

    @property
    def is_enrolled(self):
        return bool(self.enterprise_name)
