from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from apps.odk_publish.etl.excel import get_cell_by_value, get_header
from apps.odk_publish.etl.template import (
    TemplateVariable,
    set_setting_variables,
    set_survey_template_variables,
)


@pytest.fixture
def workbook() -> Workbook:
    file_path = Path(__file__).parent / "ODK XLSForm Template.xlsx"
    return load_workbook(file_path)


@pytest.fixture
def survey_sheet(workbook) -> Worksheet:
    return workbook["survey"]


class TestExcel:
    @pytest.mark.parametrize(
        "column_name, expected_column_index",
        [
            ("type", 1),
            ("name", 2),
            ("calculation", 11),
        ],
    )
    def test_find_name_column(self, survey_sheet, column_name, expected_column_index):
        cell = get_header(sheet=survey_sheet, column_name=column_name)
        assert cell.column == expected_column_index

    def test_find_name_column_not_found(self, survey_sheet):
        cell = get_header(sheet=survey_sheet, column_name="not a column")
        assert cell is None

    def test_find_cell_in_column(self, survey_sheet):
        name_header = get_header(sheet=survey_sheet, column_name="name")
        cell = get_cell_by_value(column_header=name_header, value="fruit")
        assert cell.coordinate == "B2"

    def test_find_cell_in_column_not_found(self, survey_sheet):
        name_header = get_header(sheet=survey_sheet, column_name="name")
        cell = get_cell_by_value(column_header=name_header, value="not a value")
        assert cell is None


class TestTemplate:
    def test_set_template_variable(self, survey_sheet):
        variables = [
            TemplateVariable(name="fruit", value="apple"),
            TemplateVariable(name="color", value="red"),
        ]
        set_survey_template_variables(sheet=survey_sheet, variables=variables)
        assert survey_sheet["K2"].value == "apple"
        assert survey_sheet["K3"].value == "red"

    def test_set_settings(self, workbook):
        settings_sheet = workbook["settings"]
        title_base = "Fruit Survey"
        form_id_base = "fruit_survey"
        app_user = "11030"
        version = "2022-01-01"
        set_setting_variables(
            sheet=settings_sheet,
            title_base=title_base,
            form_id_base=form_id_base,
            app_user=app_user,
            version=version,
        )
        assert settings_sheet["A2"].value == f"{title_base} [11030]"
        assert settings_sheet["B2"].value == f"{form_id_base}_11030"
        assert settings_sheet["C2"].value == version
