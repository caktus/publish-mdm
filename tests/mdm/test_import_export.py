from enum import auto
import pytest
from tablib import Dataset

from apps.mdm import import_export, models

from .factories import DeviceFactory, FleetFactory


@pytest.mark.django_db
class TestDeviceResource:
    HEADERS = ["id", "fleet", "serial_number", "app_user_name", "device_id"]

    @pytest.fixture(autouse=True)
    def disable_dagster(self, settings):
        """Disable Dagster queuing for these tests."""
        settings.DAGSTER_URL = None

    @pytest.fixture
    def fleet(self):
        return FleetFactory()

    @pytest.fixture
    def devices(self, fleet):
        return DeviceFactory.create_batch(5, fleet=fleet)

    @pytest.fixture
    def dataset(self):
        """A Dataset with no rows."""
        return Dataset(headers=self.HEADERS)

    def test_export(self, devices):
        """Ensure an export has the expected columns and rows."""
        resource = import_export.DeviceResource()
        dataset = resource.export()
        expected_headers = self.HEADERS
        expected_export_values = {
            tuple(str(i) for i in device)
            for device in models.Device.objects.values_list(*expected_headers)
        }

        assert len(dataset) == models.Device.objects.count()
        assert dataset.headers == expected_headers
        for row in dataset:
            assert tuple(str(i) for i in row) in expected_export_values

    def test_valid_import(self, fleet, devices, dataset):
        """Ensure a valid import updates the database as expected."""
        # Add all current devices to the dataset
        dataset.extend(models.Device.objects.values_list(*dataset.headers))
        new_fleet = FleetFactory()
        # Leave the first row unchanged, then change a different column in each row
        expected_rows = []
        for index, row in enumerate(dataset):
            if index:
                row = list(row)
                if index == 1:
                    # Change the fleet
                    row[index] = new_fleet.id
                else:
                    # Prepend 'edited-' to the value
                    row[index] = f"edited-{row[index]}"
                row = tuple(row)
                dataset[index] = row
            expected_rows.append(row)
        # Add new Devices
        new_devices = [
            # one with only the required fields set (fleet and serial number)
            (None, fleet.id, "111111", "", ""),
            # one with all fields set
            (None, new_fleet.id, "222222", "appuser", "99999"),
        ]
        dataset.extend(new_devices)
        expected_rows.extend(new_devices)

        # Import the data
        resource = import_export.DeviceResource()
        result = resource.import_data(dataset)

        # Get the Devices from the DB
        existing_ids = [i.id for i in devices]
        existing_in_db = set(
            models.Device.objects.filter(id__in=existing_ids).values_list(*dataset.headers)
        )
        new_in_db = set(
            models.Device.objects.exclude(id__in=existing_ids).values_list(*dataset.headers[1:])
        )

        # Ensure all rows are valid
        assert len(result.valid_rows()) == len(dataset)
        # Ensure new Devices have been added
        assert models.Device.objects.count() == len(devices) + len(new_devices)
        # Ensure the values in the DB are what we expect
        for row in expected_rows:
            if row[0]:
                assert row in existing_in_db
            else:
                assert row[1:] in new_in_db
        # Check import_type on each row
        for index, row in enumerate(result.valid_rows()):
            if not index:
                # Unchanged row should be skipped (Device.save() not called)
                assert row.import_type == "skip"
            elif dataset[index][0]:
                # Edited row
                assert row.import_type == "update"
            else:
                # New row
                assert row.import_type == "new"

    def test_invalid_import(self, fleet, devices, dataset):
        """Ensure errors are caught properly for an invalid import."""
        expected_validation_errors = []
        for index, row in enumerate(models.Device.objects.values_list(*dataset.headers)[:3], 1):
            row = list(row)
            if index == 1:
                # Value not provided for a required field (fleet)
                new_value = ""
                col = "fleet"
                error = "This field cannot be null."
            elif index == 2:
                # Invalid AppUser name (contains spaces)
                new_value = "an invalid name"
                col = "app_user_name"
                error = (
                    "Name can only contain alphanumeric characters, underscores, "
                    "hyphens, and not more than one colon."
                )
            else:
                # Same device_id as the previous device
                new_value = dataset[-1][-1]
                col = "device_id"
                error = "Device with this Device ID already exists."
            errors = {col: [error]}
            col_index = dataset.headers.index(col)
            row[col_index] = new_value
            dataset.append(row)
            expected_validation_errors.append((index, errors))
        # A new row with a non-existent fleet
        dataset.append(["", fleet.id + 1, "12345", "", ""])

        # Import the data
        resource = import_export.DeviceResource()
        result = resource.import_data(dataset)

        # Ensure all the expected validation errors are raised
        assert result.has_validation_errors()
        assert len(result.invalid_rows) == len(expected_validation_errors)
        for index, (row_number, row_errors) in enumerate(expected_validation_errors):
            assert result.invalid_rows[index].number == row_number
            assert result.invalid_rows[index].error_dict == row_errors

        # Ensure an error is raised for the new row with a non-existent fleet
        assert result.has_errors()
        row_errors = result.row_errors()
        assert len(row_errors) == 1
        row_number, error_list = row_errors[0]
        assert row_number == 4
        assert isinstance(error_list[0].error, models.Fleet.DoesNotExist)

    @pytest.mark.parametrize("dry_run", [True, False])
    def test_valid_import_dry_run(self, fleet, devices, dataset, mocker, dry_run):
        """Ensure we only push to the MDM when an import is confirmed and not
        during the dry run (preview).
        """
        # Add one edited device to the import data
        device = devices[0]
        row = list(models.Device.objects.values_list(*dataset.headers).get(id=device.id))
        row[-1] = device.device_id = f"edited-{row[-1]}"
        dataset.append(row)

        resource = import_export.DeviceResource()
        mock_device_save = mocker.patch.object(models.Device, "save", wraps=device.save)
        mock_get_tinymdm_session = mocker.patch("apps.mdm.tasks.get_tinymdm_session")
        mock_push_device_config = mocker.patch("apps.mdm.tasks.push_device_config")

        # Do the import
        result = resource.import_data(dataset, dry_run=dry_run)
        # Ensure there are no validation errors
        assert len(result.valid_rows()) == 1
        # Ensure Device.save is called and push_device_config() is only called
        # if the import is not a dry run
        mock_device_save.assert_called()
        if dry_run:
            mock_get_tinymdm_session.assert_not_called()
            mock_push_device_config.assert_not_called()
        else:
            mock_get_tinymdm_session.assert_called()
            mock_push_device_config.assert_called()
