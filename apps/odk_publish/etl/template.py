import structlog
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import BaseModel

from .excel import get_header, get_cell_by_value


logger = structlog.getLogger(__name__)


class TemplateVariable(BaseModel):
    name: str
    value: str | int | float


def set_template_variables(sheet: Worksheet, variables: list[TemplateVariable]):
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
