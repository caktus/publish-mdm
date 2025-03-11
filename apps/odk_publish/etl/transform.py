import io
import structlog

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from gspread.utils import ExportFormat

from apps.odk_publish.etl.template import (
    build_entity_list_mapping,
    set_survey_attachments,
    set_survey_template_variables,
    update_entity_references,
    update_setting_variables,
)

from ..models import AppUser, FormTemplateVersion


logger = structlog.getLogger(__name__)


def render_template_for_app_user(
    app_user: AppUser,
    template_version: FormTemplateVersion,
    attachments: dict | None = None,
) -> SimpleUploadedFile:
    """Create the next version of the app user's form."""
    workbook = openpyxl.load_workbook(filename=template_version.file)

    # Fill in the survey template variables
    variables = app_user.get_template_variables()
    set_survey_template_variables(sheet=workbook["survey"], variables=variables)
 
    # Detect static attachments in the survey sheet
    set_survey_attachments(sheet=workbook["survey"], attachments=attachments)
    logger.debug("App user variables", variables=variables)

    # Update ODK entity references on both the survey and entities sheets
    entity_list_mapping = build_entity_list_mapping(workbook=workbook, app_user=app_user.name)
    update_entity_references(workbook=workbook, entity_list_mapping=entity_list_mapping)
    
    # Update the form settings
    form_id_base = template_version.form_template.form_id_base
    update_setting_variables(
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
