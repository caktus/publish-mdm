from unittest.mock import call

import pytest
from tablib import Dataset

from apps.mdm.mdms import get_active_mdm_class
from apps.publish_mdm import import_export, models
from apps.publish_mdm.etl.load import update_app_users_central_id
from apps.publish_mdm.etl.odk.publish import ProjectAppUserAssignment
from tests.mdm import TestAllMDMsNoAutouse
from tests.mdm.factories import DeviceFactory
from tests.publish_mdm.factories import (
    AppUserFactory,
    CentralServerFactory,
    OrganizationFactory,
    ProjectFactory,
    TemplateVariableFactory,
)


@pytest.mark.django_db
class TestAppUserResource:
    @pytest.fixture
    def organization(self):
        return OrganizationFactory()

    @pytest.fixture
    def template_variables(self, organization):
        return [
            TemplateVariableFactory(name=i, organization=organization)
            for i in ("center_id", "center_label", "public_key", "manager_password")
        ]

    @pytest.fixture
    def project(self, template_variables, organization):
        central_server = CentralServerFactory(
            organization=organization,
        )
        project = ProjectFactory(
            name="Caktus Test",
            central_id=1,
            central_server=central_server,
            organization=organization,
        )
        project.template_variables.set(template_variables)
        project.form_templates.create(form_id_base="template1")
        project.form_templates.create(form_id_base="template2")
        return project

    @pytest.fixture
    def other_project(self, template_variables, organization):
        myodkcloud = CentralServerFactory(organization=organization)
        project = ProjectFactory(
            name="Other Project",
            central_id=5,
            central_server=myodkcloud,
            organization=organization,
        )
        project.template_variables.set(template_variables)
        project.form_templates.create(form_id_base="template3")
        project.form_templates.create(form_id_base="template4")
        return project

    @pytest.fixture
    def app_user(self, project):
        app_user = AppUserFactory(
            name="12345",
            project=project,
            central_id=1,
        )
        for var in project.template_variables.all():
            app_user.app_user_template_variables.create(template_variable=var, value="test")
        for template in project.form_templates.order_by("form_id_base"):
            app_user.app_user_forms.create(form_template=template)
        return app_user

    def test_export(self, project, other_project, template_variables):
        expected_export_values = set()

        # Create 5 users for each project
        for center_id in range(11030, 11040):
            app_user = models.AppUser.objects.create(
                name=str(center_id),
                project=project if center_id % 2 else other_project,
                central_id=center_id - 11000,
            )
            template_ids = []
            for template in app_user.project.form_templates.order_by("form_id_base"):
                app_user.app_user_forms.create(form_template=template)
                template_ids.append(template.form_id_base)
            export_values = [
                app_user.id,
                app_user.name,
                app_user.central_id,
                ",".join(template_ids),
            ]
            for var, value in zip(
                template_variables,
                (center_id, f"Center {center_id}", f"key{center_id}", f"pass{center_id}"),
                strict=False,
            ):
                models.AppUserTemplateVariable.objects.create(
                    app_user=app_user, template_variable=var, value=value
                )
                export_values.append(value)
            if app_user.project == project:
                expected_export_values.add(tuple(str(i) for i in export_values))

        resource = import_export.AppUserResource(project)
        dataset = resource.export()

        # Only data for the selected project should be exported
        assert len(dataset) == 5
        assert dataset.headers == [
            "id",
            "name",
            "central_id",
            "form_templates",
            "center_id",
            "center_label",
            "public_key",
            "manager_password",
        ]
        for i in range(len(dataset)):
            assert dataset.get(i) in expected_export_values

    def test_successful_import(self, app_user):
        project = app_user.project
        app_user2 = models.AppUser.objects.create(
            name="67890",
            project=project,
            central_id=2,
        )
        app_user3 = models.AppUser.objects.create(
            name="user3",
            project=project,
            central_id=3,
        )
        assert models.AppUser.objects.count() == 3
        assert models.AppUserTemplateVariable.objects.count() == project.template_variables.count()
        assert models.AppUserFormTemplate.objects.count() == 2

        csv_data = (
            "id,name,central_id,form_templates,center_id,center_label,public_key,manager_password\n"
            f"{app_user.id},11031,31,template1,11031,Center 11031,key11031,pass11031\n"
            f"{app_user2.id},11033,33,template2,11033,Center 11033,key11033,pass11033\n"
            f"{app_user3.id},user3,3,,,,,\n"
            ',11035,35,"template1,template2",11035,Center 11035,key11035,pass11035\n'
            ",11037,37,template2,11037,Center 11037,key11037,pass11037\n"
            ",11039,39, ,11039,Center 11039,key11039,pass11039\n"
        )
        dataset = Dataset().load(csv_data)
        resource = import_export.AppUserResource(project)
        result = resource.import_data(
            dataset, use_transactions=True, rollback_on_validation_errors=True
        )

        assert not result.has_validation_errors()
        assert not result.has_errors()
        assert models.AppUser.objects.count() == 6
        assert (
            models.AppUserTemplateVariable.objects.count() == project.template_variables.count() * 5
        )
        assert models.AppUserFormTemplate.objects.count() == 5

        expected_import_types = [
            "update",
            "update",
            "skip",
            "new",
            "new",
            "new",
        ]
        valid_rows = result.valid_rows()

        # Make sure user data has been added / updated
        for index, row in enumerate(dataset.dict):
            pk = row.pop("id")
            name = row.pop("name")
            form_templates = row.pop("form_templates")
            if pk:
                # User was already in the DB
                app_user = models.AppUser.objects.get(pk=pk)
                assert app_user.name == name
            else:
                # New user. Get by name
                app_user = project.app_users.get(name=name)
            assert app_user.central_id == int(row.pop("central_id"))
            assert dict(
                app_user.app_user_template_variables.values_list("template_variable__name", "value")
            ) == {k: v for k, v in row.items() if v}
            assert set(app_user.form_templates) == {
                t for i in form_templates.split(",") if (t := i.strip())
            }
            # Check the data that would be shown in a preview page
            preview_row = valid_rows[index]
            # In our HTML, the import_type is used to determine the color of the row
            assert preview_row.import_type == expected_import_types[index]
            # There should be some text in the diff for each column that had a value in the import data
            assert [bool(i) for i in preview_row.diff[1:]] == [
                bool(i.strip()) for i in dataset._data[index][1:]
            ]

    def test_cannot_import_other_projects_users(self, app_user, other_project):
        app_user2 = models.AppUser.objects.create(
            name=67890,
            project=other_project,
            central_id=2,
        )
        csv_data = (
            "id,name,central_id,form_templates,center_id,center_label,public_key,manager_password\n"
            f"{app_user.id},11031,31,template1,11031,Center 11031,key11031,pass11031\n"
            f"{app_user2.id},11033,33,template3,11033,Center 11033,key11033,pass11033"
        )
        dataset = Dataset().load(csv_data)
        resource = import_export.AppUserResource(app_user.project)
        result = resource.import_data(
            dataset, use_transactions=True, rollback_on_validation_errors=True
        )

        # Import should fail because app_user2 is linked to other_project
        assert result.has_validation_errors()
        assert len(result.invalid_rows) == 1
        assert result.invalid_rows[0].number == 2  # Row number of the row with the error
        assert result.invalid_rows[0].error_dict == {
            "id": [f"An app user with ID {app_user2.id} does not exist in the current project."]
        }

        # Nothing should be updated, including the user belonging to the correct project
        app_user.refresh_from_db()
        assert app_user.name == "12345"
        assert app_user.central_id == 1
        assert (
            list(app_user.app_user_template_variables.values_list("value", flat=True))
            == ["test"] * 4
        )
        assert list(
            app_user.app_user_forms.values_list("form_template__form_id_base", flat=True)
        ) == ["template1", "template2"]

        app_user2.refresh_from_db()
        assert app_user2.name == "67890"
        assert app_user2.central_id == 2
        assert app_user2.app_user_template_variables.count() == 0
        assert app_user2.app_user_forms.count() == 0

    def test_blank_template_variables_deleted(self, app_user):
        assert app_user.app_user_template_variables.count() == 4

        csv_data = (
            "id,name,central_id,form_templates,center_id,center_label,public_key,manager_password\n"
            f"{app_user.id},11031,31,template1,11031,Center 11031,,"
        )

        dataset = Dataset().load(csv_data)
        resource = import_export.AppUserResource(app_user.project)
        result = resource.import_data(
            dataset, use_transactions=True, rollback_on_validation_errors=True
        )

        assert not result.has_validation_errors()
        assert not result.has_errors()

        # Ensure "public_key" and "manager_password" variables have been deleted
        # for the user, while "center_id" and "center_label" have been updated
        variables = dict(
            app_user.app_user_template_variables.values_list("template_variable__name", "value")
        )
        assert len(variables) == 2
        assert variables["center_id"] == "11031"
        assert variables["center_label"] == "Center 11031"

    def test_validation_errors(self, app_user):
        app_user2 = models.AppUser.objects.create(
            name="user2",
            project=app_user.project,
            central_id=2,
        )
        app_user3 = models.AppUser.objects.create(
            name="user3",
            project=app_user.project,
            central_id=3,
        )
        # CSV with some invalid rows
        csv_data = (
            "id,name,central_id,form_templates,center_id,center_label,public_key,manager_password\n"
            f"{app_user.id},,,,,,,\n"  # Existing user has no name
            ",,1,,,,,\n"  # New user has central_id but no name
            ",new1,xx,,,,,\n"  # New user has a non-integer central_id
            f",new2,2,,{'1' * 1025},,,\n"  # New user has a center_id with more than 1024 characters
            f",{app_user.name},2,,,,,\n"  # New user has the same name as the existing user
            ",new5,5,nonexistent,,,,\n"  # New user with invalid template ID
            f",{app_user2.name.upper()},,,,,,\n"  # New user with same name as existing user, but uppercase
            f"{app_user2.id},{app_user3.name.upper()},,,,,,\n"  # Renaming with same name as another user, but uppercase
            # Valid rows
            ",new3,3,,,,,\n"  # New user has both name and central_id, so is valid
            ",new4,,,,,,\n"  # New user with name only is valid
            # End valid rows
            ",NEW4,,,,,,\n"  # Same name as valid new user, but uppercase
            ",with space,,,,,,\n"  # A name with a space is invalid
        )

        dataset = Dataset().load(csv_data)
        resource = import_export.AppUserResource(app_user.project)
        result = resource.import_data(
            dataset, use_transactions=True, rollback_on_validation_errors=True
        )
        same_name_error = {"__all__": ["App user with this Project and Name already exists."]}
        expected_errors = [
            (
                1,
                {
                    "name": ["This field cannot be blank."],
                },
            ),
            (2, {"name": ["This field cannot be blank."]}),
            (3, {"central_id": ["Value must be an integer."]}),
            (4, {"center_id": ["Ensure this value has at most 1024 characters (it has 1025)."]}),
            (5, same_name_error),
            (
                6,
                {
                    "form_templates": [
                        "The following form templates do not exist on the project: nonexistent"
                    ]
                },
            ),
            (7, same_name_error),
            (8, same_name_error),
            (11, same_name_error),
            (
                12,
                {
                    "name": [
                        "Name can only contain alphanumeric characters, underscores, hyphens, "
                        "and not more than one colon."
                    ]
                },
            ),
        ]

        assert result.has_validation_errors()
        assert len(result.invalid_rows) == len(expected_errors)

        for index, (row_number, row_errors) in enumerate(expected_errors):
            assert result.invalid_rows[index].number == row_number
            assert result.invalid_rows[index].error_dict == row_errors

    def test_appuser_central_id_updated(self, app_user):
        app_user.central_id = None
        app_user.save()
        odk_central_user = ProjectAppUserAssignment(
            **{
                "projectId": 1,
                "id": 3,
                "type": "field_key",
                "displayName": app_user.name,
                "createdAt": "2024-07-08T21:43:16.249Z",
                "updatedAt": None,
                "deletedAt": None,
                "token": "token3",
            }
        )
        update_app_users_central_id(app_user.project, {app_user.name: odk_central_user})
        app_user.refresh_from_db()
        assert app_user.central_id == odk_central_user.id


@pytest.mark.django_db
class TestDeviceResource(TestAllMDMsNoAutouse):
    def import_data(self, csv_data, organization, dry_run=False):
        dataset = Dataset().load(csv_data)
        resource = import_export.DeviceResource(organization)
        result = resource.import_data(
            dataset, use_transactions=True, rollback_on_validation_errors=True, dry_run=dry_run
        )
        return result

    def test_export(self, organization):
        """Only devices from the selected organization should be exported."""
        devices = DeviceFactory.create_batch(2, fleet__organization=organization)
        # A device in a different organization
        DeviceFactory()

        resource = import_export.DeviceResource(organization)
        dataset = resource.export()

        assert len(dataset) == 2
        assert dataset.headers == [
            "device_id",
            "serial_number",
            "manufacturer",
            "model",
            "app_user_name",
        ]
        assert {row[0] for row in dataset} == {i.device_id for i in devices}

    def test_successful_import(self, organization):
        """Importing should update app_user_name on existing devices."""
        devices = DeviceFactory.create_batch(2, fleet__organization=organization)
        csv_data = "device_id,serial_number,app_user_name\n"
        for i in devices:
            csv_data += f"{i.device_id},{i.serial_number},{i.app_user_name}_edited\n"

        result = self.import_data(csv_data, organization)

        assert not result.has_validation_errors()
        assert not result.has_errors()
        for device in devices:
            device.refresh_from_db()
            assert device.app_user_name.endswith("_edited")

    def test_cannot_import_other_orgs_devices(self, organization):
        """A device_id from another organization should produce a validation error."""
        device = DeviceFactory(fleet__organization=organization, app_user_name="app_user")
        # A device in a different organization
        other_device = DeviceFactory()
        csv_data = "device_id,serial_number,app_user_name\n"
        for i in (device, other_device):
            csv_data += f"{i.device_id},{i.serial_number},{i.app_user_name}_edited\n"

        result = self.import_data(csv_data, organization)

        assert result.has_validation_errors()
        assert len(result.invalid_rows) == 1
        assert result.invalid_rows[0].number == 2
        assert result.invalid_rows[0].error_dict == {
            "device_id": [
                f"A device with ID '{other_device.device_id}' does not exist in the current organization."
            ]
        }
        # The valid device should not be updated due to rollback
        device.refresh_from_db()
        assert device.app_user_name == "app_user"

    def test_unknown_device_id(self, organization):
        """A device_id that doesn't match any device should produce a validation error."""
        csv_data = "device_id,serial_number,app_user_name\nnonexistent_device,serial,new_user\n"
        result = self.import_data(csv_data, organization)

        assert result.has_validation_errors()
        assert len(result.invalid_rows) == 1
        assert result.invalid_rows[0].error_dict == {
            "device_id": [
                "A device with ID 'nonexistent_device' does not exist in the current organization."
            ]
        }

    def test_blank_device_id(self, organization):
        """A blank device_id should produce a validation error instead of attempting
        to create a new Device.
        """
        csv_data = "device_id,serial_number,app_user_name\n,serial,new_user\n"
        result = self.import_data(csv_data, organization)

        assert result.has_validation_errors()
        assert len(result.invalid_rows) == 1
        assert result.invalid_rows[0].error_dict == {
            "device_id": ["A device_id is required to update an existing device."]
        }

    def test_unchanged_rows_skipped(self, organization):
        """Rows where app_user_name hasn't changed should be marked as skip."""
        devices = DeviceFactory.create_batch(2, fleet__organization=organization)
        csv_data = "device_id,serial_number,app_user_name\n"
        for i in devices:
            csv_data += f"{i.device_id},{i.serial_number},{i.app_user_name}\n"

        result = self.import_data(csv_data, organization)

        assert not result.has_validation_errors()
        assert not result.has_errors()
        valid_rows = result.valid_rows()
        assert len(valid_rows) == 2
        for row in valid_rows:
            assert row.import_type == "skip"

    @pytest.mark.parametrize("dry_run", [True, False])
    def test_valid_import_dry_run(self, organization, mocker, dry_run, all_mdms, set_mdm_env_vars):
        """Ensure we only push to the MDM when an import is confirmed and not
        during the dry run (preview).
        """
        devices = DeviceFactory.create_batch(3, fleet__organization=organization)
        csv_data = "device_id,serial_number,app_user_name\n"
        # Update 2 of the 3 devices
        for n, i in enumerate(devices):
            app_user_name = i.app_user_name
            if n:
                app_user_name += "_edited"
            csv_data += f"{i.device_id},{i.serial_number},{app_user_name}\n"

        MDM = get_active_mdm_class()
        mock_push_device_config = mocker.patch.object(MDM, "push_device_config")
        result = self.import_data(csv_data, organization, dry_run=dry_run)

        # Ensure there are no validation errors
        assert len(result.valid_rows()) == 3
        # Ensure push_device_config() is only called for the edited devices if
        # the import is not a dry run
        if dry_run:
            mock_push_device_config.assert_not_called()
        else:
            assert mock_push_device_config.call_count == 2
            mock_push_device_config.assert_has_calls(
                [call(device) for device in devices[1:]], any_order=True
            )
