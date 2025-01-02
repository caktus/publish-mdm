import structlog
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import BaseModel

from .excel import get_header, get_cell_by_value


logger = structlog.getLogger(__name__)


class TemplateVariable(BaseModel):
    name: str
    value: str


def set_survey_template_variables(sheet: Worksheet, variables: list[TemplateVariable]):
    """Fill in the template variables on the survey sheet.

    Variables are just `calculate` rows in the survey sheet, so we need to find
    the variable in the `name` column and then offset to the `calculation`
    column to fill in the value.
    """
    name_header = get_header(sheet=sheet, column_name="name")
    calculation_column = get_header(sheet=sheet, column_name="calculation").column
    # Calculate the number of columns over to the calculation column
    offset = calculation_column - name_header.column
    for variable in variables:
        variable_cell = get_cell_by_value(column_header=name_header, value=variable.name)
        calculation_cell = variable_cell.offset(column=offset)
        logger.debug(
            "Setting variable value",
            variable=variable.name,
            value=variable.value,
            cell=calculation_cell.coordinate,
        )
        calculation_cell.value = variable.value


def set_setting_variables(
    sheet: Worksheet, title_base: str, form_id_base: str, app_user: str, version: str
):
    """Adapt the settings sheet to be specific to the app user.

    Available settings: https://docs.getodk.org/xlsform/#the-settings-sheet
    """
    # Append [<app_user>] to the form_title
    form_title_cell = get_header(sheet=sheet, column_name="form_title").offset(row=1)
    form_title_cell.value = f"{title_base} [{app_user}]"
    logger.debug("Set form_title", cell=form_title_cell.coordinate, value=form_title_cell.value)
    # Append _<app_user> to the form_id
    form_id_cell = get_header(sheet=sheet, column_name="form_id").offset(row=1)
    form_id_cell.value = f"{form_id_base}_{app_user}"
    logger.debug("Set form_id", cell=form_id_cell.coordinate, value=form_id_cell.value)
    # Update the version, with the current date in YYYY-MM-DD format
    version_cell = get_header(sheet=sheet, column_name="version").offset(row=1)
    version_cell.value = version
    logger.debug("Set version", cell=version_cell.coordinate, value=version_cell.value)
