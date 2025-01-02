import io

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from gspread.utils import ExportFormat

from apps.odk_publish.etl.template import set_setting_variables, set_survey_template_variables

from ..models import AppUser, FormTemplateVersion


def render_template_for_app_user(
    app_user: AppUser, template_version: FormTemplateVersion
) -> SimpleUploadedFile:
    """Create the next version of the app user's form."""
    workbook = openpyxl.load_workbook(filename=template_version.file)
    # Fill in the survey template variables
    set_survey_template_variables(
        sheet=workbook["survey"], variables=app_user.get_template_variables()
    )
    # Set the form settings
    form_id_base = template_version.form_template.form_id_base
    set_setting_variables(
        sheet=workbook["settings"],
        title_base=template_version.form_template.title_base,
        form_id_base=form_id_base,
        app_user=app_user.name,
        version=template_version.version,
    )
    # Save the updated workbook to a new file
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return SimpleUploadedFile(
        name=f"{form_id_base}_{app_user.name}-{template_version.version}.xlsx",
        content=buffer.read(),
        content_type=ExportFormat.EXCEL,
    )
