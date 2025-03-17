from functools import cached_property
from urllib.parse import urlparse

import structlog
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Value
from django.db.models.functions import NullIf

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


class CentralServer(AbstractBaseModel):
    """A server running ODK Central."""

    base_url = models.URLField(max_length=1024)

    def __str__(self):
        parsed_url = urlparse(self.base_url)
        return parsed_url.netloc

    def save(self, *args, **kwargs):
        self.base_url = self.base_url.rstrip("/")
        super().save(*args, **kwargs)


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

    def __str__(self):
        return self.name

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["name"], name="unique_template_variable_name"),
        ]


class Project(AbstractBaseModel):
    """A project in ODK Central."""

    name = models.CharField(max_length=255)
    central_id = models.PositiveIntegerField(
        verbose_name="project ID", help_text="The ID of this project in ODK Central."
    )
    central_server = models.ForeignKey(
        CentralServer, on_delete=models.CASCADE, related_name="projects"
    )
    template_variables = models.ManyToManyField(
        TemplateVariable, related_name="projects", blank=True
    )

    def __str__(self):
        return f"{self.name} ({self.central_id})"


class FormTemplate(AbstractBaseModel):
    """A form "template" published to potentially multiple ODK Central forms."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="form_templates")
    title_base = models.CharField(max_length=255)
    form_id_base = models.CharField(max_length=255)
    template_url = models.URLField(max_length=1024, blank=True)
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

    def download_user_google_sheet(self, name: str) -> SimpleUploadedFile:
        """Download the Google Sheet Excel file for this form template."""
        if not self.template_url_user:
            raise ValueError("The user who gave access to the Google Sheet is not known.")
        social_token = self.template_url_user.get_google_social_token()
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
        constraints = [
            models.UniqueConstraint(
                fields=["form_template", "version"], name="unique_form_template_version"
            ),
        ]

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
        constraints = [
            models.UniqueConstraint(
                fields=["app_user", "template_variable"], name="unique_app_user_template_variable"
            ),
        ]

    def __str__(self):
        return f"{self.value} ({self.id})"


class AppUser(AbstractBaseModel):
    """An app user in ODK Central."""

    name = models.CharField(max_length=255, db_collation="case_insensitive")
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
        constraints = [
            models.UniqueConstraint(fields=["project", "name"], name="unique_project_name"),
        ]

    def __str__(self):
        return self.name

    def get_template_variables(self) -> list[template.TemplateVariable]:
        """Get the project's template variables with this app user's values."""
        variables = self.app_user_template_variables.annotate(
            name=F("template_variable__name"),
            transform=NullIf(F("template_variable__transform"), Value("")),
        ).values("name", "value", "transform")
        return [
            template.TemplateVariable.model_validate(template_variable)
            for template_variable in variables
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
    def template_variables_dict(self):
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


class AppUserFormTemplate(AbstractBaseModel):
    """An app user's form template assignment."""

    app_user = models.ForeignKey(AppUser, on_delete=models.CASCADE, related_name="app_user_forms")
    form_template = models.ForeignKey(
        FormTemplate, on_delete=models.CASCADE, related_name="app_user_forms"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["app_user", "form_template"], name="unique_app_user_form_template"
            ),
        ]

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
        from .etl.transform import render_template_for_app_user

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
        constraints = [
            models.UniqueConstraint(
                fields=["app_user_form_template", "form_template_version"],
                name="unique_app_user_form_template_version",
            ),
        ]

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
        constraints = [
            models.UniqueConstraint(fields=["project", "name"], name="unique_project_attachments"),
        ]

    def __str__(self):
        return f"{self.name}: {self.file.name}"
