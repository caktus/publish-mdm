import hashlib
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from apps.publish_mdm.etl.excel import get_column_cell_by_value, get_header
from apps.publish_mdm.etl.template import (
    TemplateVariable,
    build_entity_list_mapping,
    discover_entity_lists,
    update_setting_variables,
    update_entity_references,
    set_survey_template_variables,
    set_survey_attachments,
    VariableTransform,
)
from tests.publish_mdm.factories import ProjectAttachmentFactory, ProjectFactory


@pytest.fixture(scope="module")
def workbook() -> Workbook:
    file_path = Path(__file__).parent / "ODK XLSForm Template.xlsx"
    return load_workbook(file_path)


@pytest.fixture
def survey_sheet(workbook) -> Worksheet:
    return workbook["survey"]


class TestExcelHelpers:
    @pytest.mark.parametrize(
        "column_name, expected_column_index",
        [
            ("type", 1),
            ("name", 2),
            ("calculation", 11),
            ("media::image", 20),
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
        cell = get_column_cell_by_value(column_header=name_header, value="fruit")
        assert cell.coordinate == "B2"

    def test_find_cell_in_column_not_found(self, survey_sheet):
        name_header = get_header(sheet=survey_sheet, column_name="name")
        cell = get_column_cell_by_value(column_header=name_header, value="not a value")
        assert cell is None


class TestTemplate:
    def test_set_template_variable(self, survey_sheet):
        """Test setting a single template variable."""
        variables = [
            TemplateVariable(name="fruit", value="apple"),
            TemplateVariable(name="color", value="red"),
            TemplateVariable(
                name="password", value="pwd", transform=VariableTransform.SHA256_DIGEST
            ),
        ]
        set_survey_template_variables(sheet=survey_sheet, variables=variables)
        assert survey_sheet["K2"].value == '"apple"'
        assert survey_sheet["K3"].value == '"red"'
        assert survey_sheet["K12"].value == f'"{hashlib.sha256(b"pwd").hexdigest()}"'

    def test_set_settings(self, workbook):
        """Test updating the settings sheet."""
        settings_sheet = workbook["settings"]
        title_base = "Fruit Survey"
        form_id_base = "fruit_survey"
        app_user = "11030"
        version = "2022-01-01"
        update_setting_variables(
            sheet=settings_sheet,
            title_base=title_base,
            form_id_base=form_id_base,
            app_user=app_user,
            version=version,
        )
        assert settings_sheet["A2"].value == f"{title_base} [11030]"
        assert settings_sheet["B2"].value == f"{form_id_base}_11030"
        assert settings_sheet["C2"].value == version

    @pytest.mark.django_db
    def test_set_attachments(self, survey_sheet):
        """Test setting a static attachment."""
        # Create one attachment with the name in the in the survey sheet
        project = ProjectFactory()
        should_detect = [
            ProjectAttachmentFactory(name="logo.png", project=project),
            ProjectAttachmentFactory(name="vegetables.csv", project=project),
        ]
        # Create 2 more attachments that are not used in the survey sheet
        ProjectAttachmentFactory.create_batch(2, project=project)
        attachments = {i.name: i.file for i in project.attachments.all()}
        assert len(attachments) == 4
        set_survey_attachments(sheet=survey_sheet, attachments=attachments)
        # The `attachments` dictionary has been updated and only contains the
        # attachment that was detected in the form
        assert attachments == {i.name: i.file for i in should_detect}

    def test_set_template_variable_not_in_sheet(self, survey_sheet):
        """Attempting to set a template variable that is not in the survey sheet
        should raise an error with an informative error message.
        """
        # One variable exists in the sheet and the other doesn't
        variables = [
            TemplateVariable(name="fruit", value="apple"),
            TemplateVariable(name="NOT_IN_SHEET", value="12345"),
        ]
        with pytest.raises(
            LookupError,
            match=(
                "'NOT_IN_SHEET' is not a valid variable in the XLSForm template. "
                "Please check the variable name and try again."
            ),
        ):
            set_survey_template_variables(sheet=survey_sheet, variables=variables)


class TestEntityReferences:
    def test_discovers_entity_references(self, workbook):
        """Test discovering entity references in the survey sheet."""
        assert {
            "fruits",
            "vegetables",
            "nuts",
            "staff",
            "cats_APP_USER",
            "dogs_APP_USER",
            "pets_APP_USER",
        } == discover_entity_lists(workbook=workbook)

    def test_build_entity_list_mapping(self, workbook):
        """Test building a mapping of entity lists to new entity list names."""
        mapping = build_entity_list_mapping(workbook=workbook, app_user="11030")
        # Entity lists not ending in "_APP_USER" will remain the same, so will
        # not be included in the mapping
        assert {
            "cats_APP_USER": "cats_11030",
            "dogs_APP_USER": "dogs_11030",
            "pets_APP_USER": "pets_11030",
        } == mapping

    def test_update_entity_references(self, workbook):
        """Test updating entity list references in the survey and entity sheets."""
        orig = "cats_APP_USER"
        new = "cats_11030"
        update_entity_references(workbook=workbook, entity_list_mapping={orig: new})
        survey_sheet = workbook["survey"]
        assert survey_sheet["A8"].value == f"select_one_from_file {new}.csv"
        assert (
            survey_sheet["K10"].value == f"instance('{new}')/root/item[name=${{cats_entity}}]/color"
        )
        entity_sheet = workbook["entities"]
        # Ensure project-wide entity list names are unchanged
        assert survey_sheet["A4"].value == "select_one_from_file fruits.csv"
        assert entity_sheet["A2"].value == "fruits"
        assert (
            survey_sheet["K5"].value == "instance('fruits')/root/item[name=${fruits_entity}]/color"
        )
