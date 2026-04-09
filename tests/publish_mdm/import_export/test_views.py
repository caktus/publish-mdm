import os
import random
import re
import shutil
from io import BytesIO, StringIO
from pathlib import Path
from typing import ClassVar

import pytest
from django.conf import settings
from django.contrib.messages import ERROR, Message
from django.urls import reverse
from import_export.tmp_storages import MediaStorage
from pytest_django.asserts import assertContains, assertFormError, assertMessages
from tablib import Dataset

from apps.mdm.mdms import get_active_mdm_class
from apps.publish_mdm.forms import (
    ConfirmImportForm,
    ExportForm,
    ImportForm,
)
from apps.publish_mdm.models import AppUser
from tests.mdm.factories import DeviceFactory, FleetFactory
from tests.publish_mdm.factories import (
    AppUserFactory,
    AppUserTemplateVariableFactory,
    FormTemplateFactory,
    OrganizationFactory,
    ProjectFactory,
    UserFactory,
)


@pytest.mark.django_db
class ImportExportTestBase:
    """Base class for testing the import and export processes."""

    @pytest.fixture
    def user(self, client):
        user = UserFactory()
        user.save()
        client.force_login(user=user)
        return user

    @pytest.fixture
    def organization(self, user):
        org = OrganizationFactory()
        org.users.add(user)
        return org

    def test_login_required(self, client, url):
        client.logout()
        response = client.get(url)
        assert response.status_code == 302


class ImportTestBase(ImportExportTestBase):
    """Base class for testing the import process."""

    # Map each format name to a tuple with:
    # - an instance of the class from `settings.IMPORT_EXPORT_FORMATS`
    # - an `io` class to use to create a file-like object for POST data
    # - the value for selecting the format in import forms
    FORMATS: ClassVar = {}
    for index, format_class in enumerate(settings.IMPORT_EXPORT_FORMATS):
        f = format_class()
        if f.is_binary():
            f.encoding = "utf-8-sig"
        FORMATS[f.get_title()] = (f, BytesIO if f.is_binary() else StringIO, index)

    def teardown_class(cls):
        shutil.rmtree(os.path.join(settings.MEDIA_ROOT, "django-import-export"), ignore_errors=True)

    def test_get(self, client, url, user):
        response = client.get(url)
        assert response.status_code == 200


class TestAppUserImport(ImportTestBase):
    """Test the AppUser import process."""

    @pytest.fixture
    def project(self, organization):
        project = ProjectFactory(organization=organization)
        project.template_variables.create(name="var1", organization=organization)
        project.template_variables.create(name="var2", organization=organization)
        return project

    @pytest.fixture
    def url(self, project):
        return reverse(
            "publish_mdm:app-users-import",
            kwargs={"organization_slug": project.organization.slug, "odk_project_pk": project.pk},
        )

    @pytest.fixture
    def dataset(self, project):
        """Valid CSV import data with two new users."""
        return Dataset(
            ("", "newuser", "", "", "value1", ""),
            ("", "newuser2", "", "", "", ""),
            headers=["id", "name", "central_id", "form_templates", "var1", "var2"],
        )

    def check_valid_upload(self, client, url, format_name, dataset, import_file=None):
        import_format, io_class, form_format = self.FORMATS[format_name]
        if not import_file:
            import_file_data = dataset.export(format_name)
            import_file = io_class(import_file_data)
        data = {"format": form_format, "import_file": import_file}
        response = client.post(url, data=data)
        assert response.status_code == 200
        assert isinstance(response.context["form"], ConfirmImportForm)
        response_content = response.content.decode()
        assert (
            "Below is a preview of data to be imported. If you are satisfied "
            "with the results, click 'Confirm import'."
        ) in response_content
        assert len(response.context["result"].valid_rows()) == 2
        # The user should not be created yet
        assert AppUser.objects.count() == 0
        # The import file data should be saved in a temp file
        tmp_storage = MediaStorage(
            name=response.context["form"].initial["import_file_name"],
            encoding=import_format.encoding,
        )
        # Read the temp file and make sure it has the same data
        tmp_storage.read_mode = import_format.get_read_mode()
        tmp_dataset = import_format.create_dataset(tmp_storage.read())
        # A Dataset created from an Excel file will have None values instead of empty strings
        assert dataset.dict == [{k: v or "" for k, v in row.items()} for row in tmp_dataset.dict]
        # Ensure there is a warning message for numeric values
        assert (
            "If some numeric values are not displayed correctly here, consider "
            "setting the correct number format for those values in your original "
            "document, then try importing it again."
        ) in response_content

    @pytest.mark.parametrize("format_name", ["csv", "xlsx"])
    def test_valid_upload(self, client, url, user, dataset, format_name):
        """Ensure the review page is shown after a valid import file is uploaded."""
        self.check_valid_upload(client, url, format_name, dataset)

    @pytest.mark.parametrize("format_name", ["csv", "xlsx"])
    def test_import_confirmed(self, client, url, user, project, dataset, format_name):
        """Ensure confirming the import in the review page updates users."""
        import_format, _, form_format = self.FORMATS[format_name]
        import_file_data = dataset.export(format_name)
        # Save the import data in a temp file, as would happen when a valid file is uploaded
        tmp_storage = MediaStorage(
            encoding=import_format.encoding,
            read_mode=import_format.get_read_mode(),
        )
        tmp_storage.save(import_file_data)
        # Submit a form for confirming the import
        data = {
            "import_file_name": tmp_storage.name,
            "original_file_name": f"test.{format_name}",
            "format": form_format,
            "resource": "",
        }
        response = client.post(url, data=data, follow=True)
        # A new user is created and there's a redirect to the user list page
        # with a success message
        assert response.status_code == 200
        assert AppUser.objects.count() == 2
        assert response.redirect_chain == [
            (
                reverse("publish_mdm:app-user-list", args=[project.organization.slug, project.id]),
                302,
            )
        ]
        assert (
            "Import finished successfully, with 2 new and 0 updated app users."
            in response.content.decode()
        )

    @pytest.mark.parametrize("format_name", ["csv", "xlsx"])
    def test_invalid_upload(self, client, url, user, project, dataset, format_name):
        """Ensure form validation errors are displayed in case of invalid data in the upload."""
        # Add a row with an invalid central_id
        dataset.append(("", "newuser2", "xx", "", "", ""))
        _, io_class, form_format = self.FORMATS[format_name]
        import_file_data = dataset.export(format_name)
        data = {"format": form_format, "import_file": io_class(import_file_data)}
        response = client.post(url, data=data)
        response_content = response.content.decode()
        expected_error = "Value must be an integer."
        result = response.context["result"]

        assert response.status_code == 200
        assert isinstance(response.context["form"], ImportForm)
        assert (
            "Please correct these errors in your data where possible, then reupload "
            "it using the form above."
        ) in response_content
        assert len(result.invalid_rows) == 1
        assert result.invalid_rows[0].field_specific_errors["central_id"] == [expected_error]
        assert expected_error in response_content
        # A user should not be created
        assert AppUser.objects.count() == 0
        # Ensure there is a warning message for numeric values
        assert (
            "If some numeric values are not displayed correctly here, consider "
            "setting the correct number format for those values in your original "
            "document, then try importing it again."
        ) in response_content

    def test_valid_google_sheets_xlsx_upload(self, client, url, user, dataset):
        """Ensures a valid xlsx file edited and downloaded from Google Sheets can be
        uploaded without errors. The file has the same data as the `dataset` fixture.
        """
        file_path = Path(__file__).parent / "app_users_import_from_google_sheets.xlsx"
        with open(file_path, "rb") as import_file:
            self.check_valid_upload(client, url, "xlsx", dataset, import_file)

    @pytest.mark.parametrize("format_name", ["csv", "xlsx"])
    def test_error_creating_import_dataset(
        self, client, url, user, dataset, format_name, mocker, caplog
    ):
        """Ensure a message is logged with DEBUG level and the import form is
        displayed with an error message if the user submits a valid import form but
        an exception occurs when we're attempting to create the import dataset.
        """
        import_format, io_class, form_format = self.FORMATS[format_name]
        import_file_data = dataset.export(format_name)
        import_file = io_class(import_file_data)
        data = {"format": form_format, "import_file": import_file}
        mocker.patch.object(
            import_format.__class__, "create_dataset", side_effect=Exception("some error")
        )
        response = client.post(url, data=data)
        for record in caplog.records:
            if record.name == "apps.publish_mdm.forms":
                assert record.levelname == "DEBUG"
                expected_msg = {
                    "event": "An error occurred when reading import file",
                    "selected_format": format_name,
                }
                assert expected_msg.items() <= record.msg.items()
                break
        else:
            pytest.fail("No log messages from apps.publish_mdm.forms")
        form = response.context.get("form")
        assert isinstance(form, ImportForm)
        assertFormError(
            form,
            "format",
            "An error was encountered while trying to read the file. "
            "Ensure you have chosen the correct format for the file.",
        )
        assertMessages(response, [])

    @pytest.mark.parametrize("format_name", ["csv", "xlsx"])
    def test_error_creating_import_dataset_when_confirming(
        self, client, url, user, dataset, format_name, mocker, caplog
    ):
        """Ensure a message is logged with ERROR level and a message is shown to
        the user if they submit a valid import confirmation form but an exception
        occurs when we're attempting to create the import dataset.
        """
        import_format, _, form_format = self.FORMATS[format_name]
        import_file_data = dataset.export(format_name)
        # Save the import data in a temp file, as would happen when a valid file is uploaded
        tmp_storage = MediaStorage(
            encoding=import_format.encoding,
            read_mode=import_format.get_read_mode(),
        )
        tmp_storage.save(import_file_data)
        # Submit a form for confirming the import
        data = {
            "import_file_name": tmp_storage.name,
            "original_file_name": f"test.{format_name}",
            "format": form_format,
            "resource": "",
        }
        mocker.patch.object(
            import_format.__class__, "create_dataset", side_effect=Exception("some error")
        )
        response = client.post(url, data=data)
        for record in caplog.records:
            if record.name == "apps.publish_mdm.forms":
                assert record.levelname == "ERROR"
                expected_msg = {
                    "event": "An error occurred when reading import temp file in confirm stage",
                    "selected_format": format_name,
                    "filename": tmp_storage.name,
                }
                assert expected_msg.items() <= record.msg.items()
                break
        else:
            pytest.fail("No log messages from apps.publish_mdm.forms")
        assertMessages(
            response,
            [Message(ERROR, "We could not complete your import. Please try importing again.")],
        )
        form = response.context.get("form")
        assert isinstance(form, ImportForm)
        assert not form.is_bound


class TestDeviceImport(ImportTestBase):
    """Test the Device import process."""

    @pytest.fixture
    def fleet(self, organization):
        return FleetFactory(organization=organization)

    @pytest.fixture
    def devices(self, fleet):
        return [
            DeviceFactory(fleet=fleet, device_id="dev001", app_user_name="user1"),
            DeviceFactory(fleet=fleet, device_id="dev002", app_user_name="user2"),
        ]

    @pytest.fixture
    def url(self, organization):
        return reverse(
            "publish_mdm:devices-import",
            kwargs={"organization_slug": organization.slug},
        )

    @pytest.fixture
    def dataset(self, devices):
        """Valid CSV import data updating both devices."""
        return Dataset(
            *((d.device_id, d.serial_number, f"new_user{n}") for n, d in enumerate(devices, 1)),
            headers=["device_id", "serial_number", "app_user_name"],
        )

    @pytest.mark.parametrize("format_name", ["csv", "xlsx"])
    def test_valid_upload(self, client, url, user, devices, dataset, format_name):
        """Ensure the review page is shown after a valid import file is uploaded."""
        _, io_class, form_format = self.FORMATS[format_name]
        import_file_data = dataset.export(format_name)
        data = {"format": form_format, "import_file": io_class(import_file_data)}
        response = client.post(url, data=data)

        assert response.status_code == 200
        assert isinstance(response.context["form"], ConfirmImportForm)
        assert (
            "Below is a preview of data to be imported. If you are satisfied "
            "with the results, click 'Confirm import'."
        ) in response.content.decode()
        assert len(response.context["result"].valid_rows()) == 2
        # Devices should not be updated yet
        for device in devices:
            device.refresh_from_db()
        assert devices[0].app_user_name == "user1"
        assert devices[1].app_user_name == "user2"

    @pytest.mark.parametrize("format_name", ["csv", "xlsx"])
    def test_import_confirmed(self, client, url, user, organization, devices, dataset, format_name):
        """Ensure confirming the import updates the devices' app_user_name."""
        import_format, _, form_format = self.FORMATS[format_name]
        import_file_data = dataset.export(format_name)
        tmp_storage = MediaStorage(
            encoding=import_format.encoding,
            read_mode=import_format.get_read_mode(),
        )
        tmp_storage.save(import_file_data)
        data = {
            "import_file_name": tmp_storage.name,
            "original_file_name": f"test.{format_name}",
            "format": form_format,
            "resource": "",
        }
        response = client.post(url, data=data, follow=True)

        assert response.status_code == 200
        assert response.redirect_chain == [
            (reverse("publish_mdm:devices-list", args=[organization.slug]), 302)
        ]
        assert (
            "Import finished successfully, with 0 new and 2 updated devices."
            in response.content.decode()
        )
        devices[0].refresh_from_db()
        devices[1].refresh_from_db()
        assert devices[0].app_user_name == "new_user1"
        assert devices[1].app_user_name == "new_user2"

    @pytest.mark.parametrize("format_name", ["csv", "xlsx"])
    def test_invalid_upload(self, client, url, user, devices, dataset, format_name):
        """Ensure a validation error is shown when an unknown device_id is uploaded."""
        dataset.append(("unknown_device", "some_serial_no", "some_user"))
        _, io_class, form_format = self.FORMATS[format_name]
        import_file_data = dataset.export(format_name)
        data = {"format": form_format, "import_file": io_class(import_file_data)}
        response = client.post(url, data=data)

        assert response.status_code == 200
        assert isinstance(response.context["form"], ImportForm)
        result = response.context["result"]
        assert result.has_validation_errors()
        assert len(result.invalid_rows) == 1
        assert result.invalid_rows[0].field_specific_errors["device_id"] == [
            "A device with ID 'unknown_device' does not exist in the current organization."
        ]
        # Devices should not be updated
        for device in devices:
            device.refresh_from_db()
        assert devices[0].app_user_name == "user1"
        assert devices[1].app_user_name == "user2"

    def test_push_device_config_called_after_confirm(
        self, client, url, user, organization, devices, dataset, mocker
    ):
        """Confirming a CSV import triggers Dagster mdm_job for updated devices and
        not the push_device_config method of the currently active MDM.
        """
        mock_trigger = mocker.patch("apps.publish_mdm.import_export.trigger_dagster_job")
        mock_push = mocker.patch.object(get_active_mdm_class(), "push_device_config")

        import_format_cls, _, form_format = self.FORMATS["csv"]
        import_file_data = dataset.export("csv")
        tmp_storage = MediaStorage(
            encoding=import_format_cls.encoding,
            read_mode=import_format_cls.get_read_mode(),
        )
        tmp_storage.save(import_file_data)
        data = {
            "import_file_name": tmp_storage.name,
            "original_file_name": "test.csv",
            "format": form_format,
            "resource": "",
        }
        client.post(url, data=data, follow=True)

        mock_trigger.assert_called_once()
        mock_push.assert_not_called()
        device_pks = mock_trigger.call_args.kwargs["run_config"]["ops"]["push_mdm_device_config"][
            "config"
        ]["device_pks"]
        assert set(device_pks) == {d.pk for d in devices}

    def test_push_device_config_not_called_on_dry_run(
        self, client, url, user, devices, dataset, mocker
    ):
        """During the dry-run preview stage, neither the Dagster mdm_job nor the
        push_device_config method of the currently active MDM is called.
        """
        mock_trigger = mocker.patch("apps.publish_mdm.import_export.trigger_dagster_job")
        mock_push = mocker.patch.object(get_active_mdm_class(), "push_device_config")

        _, io_class, form_format = self.FORMATS["csv"]
        import_file_data = dataset.export("csv")
        data = {"format": form_format, "import_file": io_class(import_file_data)}
        client.post(url, data=data)

        mock_trigger.assert_not_called()
        mock_push.assert_not_called()


class ExportTestBase(ImportExportTestBase):
    """Base class for testing the export views."""

    def check_export(
        self,
        response,
        export_format,
        expected_file_name_pattern,
        expected_col_headers,
        expected_rows,
    ):
        """Ensures an export response has the expected Content-Disposition header
        and the file has the expected content.
        """
        content_disposition = response.headers.get("Content-Disposition", "")
        assert re.match(
            rf'attachment; filename="{expected_file_name_pattern}"', content_disposition
        )
        dataset = Dataset()
        data = response.content
        if not export_format.is_binary():
            data = data.decode()
        dataset.load(data)
        assert dataset.headers == expected_col_headers
        assert set(dataset) == expected_rows

    def test_get(self, client, url, user):
        response = client.get(url)
        assert response.status_code == 200
        assert isinstance(response.context.get("form"), ExportForm)

    @pytest.mark.parametrize(
        "form_value,expected_error",
        (
            ("", "This field is required."),
            ("99", "Select a valid choice. 99 is not one of the available choices."),
        ),
    )
    def test_invalid_export_form(self, client, url, user, form_value, expected_error):
        """Ensure the export form raises a validation error if inputs are invalid."""
        response = client.post(url, data={"format": form_value})
        form = response.context.get("form")
        assert isinstance(form, ExportForm)
        assertFormError(form, "format", expected_error)
        assertContains(response, expected_error)


class TestAppUserExport(ExportTestBase):
    """Test the view for exporting AppUsers."""

    @pytest.fixture
    def project(self, organization):
        return ProjectFactory(organization=organization)

    @pytest.fixture
    def url(self, project):
        return reverse(
            "publish_mdm:app-users-export",
            kwargs={"organization_slug": project.organization.slug, "odk_project_pk": project.pk},
        )

    @pytest.mark.parametrize("format_index,format_class", enumerate(settings.IMPORT_EXPORT_FORMATS))
    def test_export(self, client, url, user, project, organization, format_index, format_class):
        """Ensure the exported file has the expected data and filename."""
        vars = [
            project.template_variables.create(name=f"var{i}", organization=organization)
            for i in range(2)
        ]
        templates = FormTemplateFactory.create_batch(4, project=project)
        app_users = AppUserFactory.create_batch(4, project=project)
        # The first 2 users have 2 form templates each and template variables
        app_user_templates = {}
        user_vars = {var: {} for var in vars}
        for _index, app_user in enumerate(app_users[:2], 1):
            template_ids = []
            for template in random.sample(templates, 2):
                app_user.app_user_forms.create(form_template=template)
                template_ids.append(template.form_id_base)
            app_user_templates[app_user] = ",".join(sorted(template_ids))
            for var in vars:
                user_vars[var][app_user] = AppUserTemplateVariableFactory(
                    app_user=app_user, template_variable=var
                ).value
        # Create some app users in a different project. These should not be included in the export
        AppUserFactory.create_batch(2, project=ProjectFactory(organization=organization))
        response = client.post(url, {"format": format_index})
        format = format_class()
        date_format = r"\d{4}-\d{2}-\d{2}"
        if format.is_binary():
            empty = None
        else:
            empty = ""
        self.check_export(
            response,
            format,
            f"app_users_{project.pk}_{date_format}.{format.get_extension()}",
            ["id", "name", "central_id", "form_templates", *(i.name for i in vars)],
            {
                (
                    str(i.pk),
                    i.name,
                    str(i.central_id),
                    app_user_templates.get(i, empty),
                    *(user_vars[var].get(i, empty) for var in vars),
                )
                for index, i in enumerate(app_users)
            },
        )


class TestDeviceExport(ExportTestBase):
    """Test the view for exporting Devices."""

    @pytest.fixture
    def url(self, organization):
        return reverse(
            "publish_mdm:devices-export",
            kwargs={"organization_slug": organization.slug},
        )

    @pytest.mark.parametrize("format_index,format_class", enumerate(settings.IMPORT_EXPORT_FORMATS))
    def test_export(self, client, url, user, organization, format_index, format_class):
        """Ensure the exported file has the expected data and filename."""
        devices = DeviceFactory.create_batch(10, fleet__organization=organization)
        # Create some devices in a different org. These should not be included in the export
        DeviceFactory.create_batch(2, fleet__organization=OrganizationFactory())
        response = client.post(url, {"format": format_index})
        format = format_class()
        date_format = r"\d{4}-\d{2}-\d{2}"
        # Brand and model may be None or empty strings depending on export format
        if format.is_binary():
            empty = None
        else:
            empty = ""
        expected_rows = {
            (
                i.device_id,
                i.serial_number,
                i.manufacturer or empty,
                i.model or empty,
                i.app_user_name,
            )
            for i in devices
        }
        self.check_export(
            response,
            format,
            f"devices_{organization.slug}_{date_format}.{format.get_extension()}",
            ["device_id", "serial_number", "manufacturer", "model", "app_user_name"],
            expected_rows,
        )
