import os
import shutil
from io import BytesIO, StringIO
from pathlib import Path

import pytest
from tablib import Dataset
from django.urls import reverse
from django.conf import settings
from import_export.tmp_storages import MediaStorage

from tests.mdm.factories import DeviceFactory, FleetFactory
from tests.publish_mdm.factories import (
    OrganizationFactory,
    ProjectFactory,
    UserFactory,
)
from apps.publish_mdm.forms import ConfirmImportForm, ImportForm
from apps.publish_mdm.models import AppUser


@pytest.mark.django_db
class ImportTestBase:
    """Base class for testing the import process."""

    # Map each format name to a tuple with:
    # - an instance of the class from `settings.IMPORT_EXPORT_FORMATS`
    # - an `io` class to use to create a file-like object for POST data
    # - the value for selecting the format in import forms
    FORMATS = {}
    for index, format_class in enumerate(settings.IMPORT_EXPORT_FORMATS):
        f = format_class()
        if f.is_binary():
            f.encoding = "utf-8-sig"
        FORMATS[f.get_title()] = (f, BytesIO if f.is_binary() else StringIO, index)

    def teardown_class(cls):
        shutil.rmtree(os.path.join(settings.MEDIA_ROOT, "django-import-export"), ignore_errors=True)

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

    def test_get(self, client, url, user):
        response = client.get(url)
        assert response.status_code == 200


class TestAppUserImport(ImportTestBase):
    """Test the AppUser import process."""

    @pytest.fixture
    def project(self, user, organization):
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
        import_format, io_class, form_format = self.FORMATS[format_name]
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


@pytest.mark.django_db
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
            (devices[0].device_id, "new_user1"),
            (devices[1].device_id, "new_user2"),
            headers=["device_id", "app_user_name"],
        )

    @pytest.mark.parametrize("format_name", ["csv", "xlsx"])
    def test_valid_upload(self, client, url, user, devices, dataset, format_name):
        """Ensure the review page is shown after a valid import file is uploaded."""
        import_format, io_class, form_format = self.FORMATS[format_name]
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
        dataset.append(("unknown_device", "some_user"))
        import_format, io_class, form_format = self.FORMATS[format_name]
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
