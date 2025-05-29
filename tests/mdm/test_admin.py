import pytest
from django.conf import settings
from django.urls import reverse
from import_export.tmp_storages import TempFolderStorage

from apps.mdm.import_export import DeviceResource
from apps.mdm.models import Device
from tests.users.factories import UserFactory

from .factories import DeviceFactory, FleetFactory


@pytest.mark.django_db
class TestDeviceAdmin:
    @pytest.fixture
    def user(self, client):
        user = UserFactory(is_staff=True, is_superuser=True)
        user.save()
        client.force_login(user=user)
        return user

    @pytest.fixture
    def dataset(self):
        # Create 3 Devices with the same Fleet
        fleet = FleetFactory()
        DeviceFactory.create_batch(3, fleet=fleet)
        # Create a Dataset in the format expected by the import functionality
        return DeviceResource().export()

    def check_import(self, client, dataset, expected_app_user_names):
        # Create a temp file as expected for the import confirmation step
        import_format = settings.IMPORT_EXPORT_FORMATS[0]()
        format_name = import_format.get_title()
        import_file_data = dataset.export(format_name)
        tmp_storage = TempFolderStorage(
            encoding="utf-8-sig",
            read_mode=import_format.get_read_mode(),
        )
        tmp_storage.save(import_file_data.encode())
        # Submit a form for confirming the import
        data = {
            "import_file_name": tmp_storage.name,
            "original_file_name": f"test.{format_name}",
            "format": 0,
            "resource": "",
        }
        response = client.post(reverse("admin:mdm_device_process_import"), data=data, follow=True)
        assert response.status_code == 200
        assert response.redirect_chain == [(reverse("admin:mdm_device_changelist"), 302)]
        for id, app_user_name in expected_app_user_names.items():
            assert Device.objects.get(id=id).app_user_name == app_user_name
        return response

    def test_confirm_import_with_no_errors(self, client, user, dataset):
        """Happy path: confirming an import and no errors occur when saving changes."""
        # Change the app_user_name on the first 2 devices
        expected_app_user_names = {}
        for index, row in enumerate(dataset[:2]):
            row = list(row)
            row[3] += "_edited"
            dataset[index] = row
            expected_app_user_names[row[0]] = row[3]
        # Add one new device
        new_device = DeviceFactory.build()
        dataset.append(
            [
                None,
                dataset[0][1],
                new_device.serial_number,
                new_device.app_user_name,
                new_device.device_id,
            ]
        )
        response = self.check_import(client, dataset, expected_app_user_names)
        # We should now have 4 Devices: 3 existing devices + 1 new device
        assert Device.objects.count() == 4
        assert (
            "Import finished: 1 new, 2 updated, 0 deleted and 1 skipped devices."
            in response.content.decode()
        )

    def test_confirm_import_with_errors(self, client, user, dataset, mocker):
        """Ensure error messages are shown for errors that occur during the
        confirmation step of an import, and any devices that were added/updated
        and did not have errors are saved in the database.
        """
        # Change the app_user_name on the first 2 devices
        expected_app_user_names = {}
        for index, row in enumerate(dataset[:2]):
            row = list(row)
            before = row[3]
            row[3] += "_edited"
            dataset[index] = row
            if index:
                expected_app_user_names[row[0]] = row[3]
            else:
                # We will fake an exception within the save() for the first row, so it
                # won't actually get updated in the database
                expected_app_user_names[row[0]] = before
        # Add two new rows, but one will have a validation error (a duplicate device_id)
        for index, new_device in enumerate(DeviceFactory.build_batch(2)):
            row = [
                None,
                dataset[0][1],
                new_device.serial_number,
                new_device.app_user_name,
                new_device.device_id if index else dataset[0][-1],
            ]
            dataset.append(row)
        mocker.patch(
            "apps.mdm.tasks.get_tinymdm_session",
            side_effect=[Exception("MDM API error")] + [None] * 4,
        )
        response = self.check_import(client, dataset, expected_app_user_names)
        # We should now have 4 Devices: 3 existing devices + 1 new device
        assert Device.objects.count() == 4
        response_content = response.content.decode()
        assert (
            "Import finished: 1 new, 1 updated, 0 deleted and 1 skipped devices."
            in response_content
        )
        # An error message for the exception within save()
        assert "Row 1: Exception('MDM API error')" in response_content
        # An error message for the validation error on one of the new Devices
        assert (
            "Row 4, Column 'device_id': Device with this Device ID already exists."
            in response_content
        )
