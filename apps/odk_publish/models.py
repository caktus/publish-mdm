from urllib.parse import urlparse

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import models

from apps.users.models import User

from .etl.google import download_user_google_sheet
from .etl.odk.config import odk_central_client
from .etl.odk.forms import get_unique_version_by_form_id


class AbstractBaseModel(models.Model):
    """Abstract base model for all models in the app"""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    modified_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


class CentralServer(AbstractBaseModel):
    base_url = models.URLField(max_length=1024)

    def __str__(self):
        parsed_url = urlparse(self.base_url)
        return parsed_url.netloc


class Project(AbstractBaseModel):
    name = models.CharField(max_length=255)
    project_id = models.PositiveIntegerField(verbose_name="project ID")
    central_server = models.ForeignKey(
        CentralServer, on_delete=models.CASCADE, related_name="projects"
    )

    def __str__(self):
        return f"{self.name} ({self.project_id})"


class FormTemplate(AbstractBaseModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="form_templates")
    title_base = models.CharField(max_length=255)
    form_id_base = models.CharField(max_length=255)
    template_url = models.URLField(max_length=1024)

    def __str__(self):
        return f"{self.form_id_base} ({self.id})"

    def download_google_sheet(self, user: User, name: str) -> SimpleUploadedFile:
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

    def create_next_version(self, user: User) -> "FormTemplateVersion":
        """Create the next version of this form template.

        Steps to create the next version:

        1. Query the ODK Central server for this `form_id_base` and increment
           the version number with today's date.
        2. Download the Google Sheet Excel file for this form template.
        3. Create a new FormTemplateVersion instance with the downloaded file.
        """
        with odk_central_client(base_url=self.project.central_server.base_url) as client:
            version = get_unique_version_by_form_id(
                client=client, project_id=self.project.project_id, form_id_base=self.form_id_base
            )
            name = f"{self.form_id_base}-{version}.xlsx"
            file = self.download_google_sheet(user=user, name=name)
            return FormTemplateVersion.objects.create(
                form_template=self, user=user, file=file, version=version
            )


class FormTemplateVersion(AbstractBaseModel):
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
