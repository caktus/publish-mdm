import io

from django.core.files.uploadedfile import SimpleUploadedFile
from gspread.utils import ExportFormat
from openpyxl import load_workbook

from apps.odk_publish.etl.template import set_template_variables

from ..models import AppUserFormTemplate, FormTemplateVersion


def fill_in_survey_template_variables(template: AppUserFormTemplate, version: FormTemplateVersion):
    """Fill in the survey template variables and return the updated file."""
    workbook = load_workbook(version.file)
    template_variables = template.app_user.get_template_variables()
    set_template_variables(sheet=workbook["survey"], variables=template_variables)
    # Save the updated workbook to a buffer and return a SimpleUploadedFile to
    # use in a Django model FileField.
    name = f"{version.form_template.form_id_base}_{template.app_user.name}-{version.version}.xlsx"
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return SimpleUploadedFile(
        name=name,
        content=buffer.read(),
        content_type=ExportFormat.EXCEL,
    )
