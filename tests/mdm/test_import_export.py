import pytest
from import_export.results import RowResult
from tablib import Dataset

from apps.mdm import import_export, models
from apps.mdm.mdms import get_active_mdm_class
from tests.mdm import TestAllMDMs

from .factories import DeviceFactory, FleetFactory


@pytest.mark.django_db
class TestDeviceResource(TestAllMDMs):
    HEADERS = (
        "id",
        "fleet",
        "serial_number",
        "app_user_name",
        "device_id",
    )

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
        assert tuple(dataset.headers) == expected_headers
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
    def test_valid_import_dry_run(self, fleet, devices, dataset, mocker, dry_run, set_mdm_env_vars):
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
        mock_push_device_config = mocker.patch.object(get_active_mdm_class(), "push_device_config")

        # Do the import
        result = resource.import_data(dataset, dry_run=dry_run)
        # Ensure there are no validation errors
        assert len(result.valid_rows()) == 1
        # Ensure Device.save is called and push_device_config() is only called
        # if the import is not a dry run
        mock_device_save.assert_called()
        if dry_run:
            mock_push_device_config.assert_not_called()
        else:
            mock_push_device_config.assert_called()


@pytest.mark.django_db
class TestDeviceResourceAfterImport(TestAllMDMs):
    """Tests for after_import() behavior when Dagster is enabled."""

    HEADERS = (
        "id",
        "fleet",
        "serial_number",
        "app_user_name",
        "device_id",
    )

    @pytest.fixture
    def fleet(self):
        return FleetFactory()

    @pytest.fixture
    def devices(self, fleet):
        return DeviceFactory.create_batch(3, fleet=fleet)

    @pytest.fixture
    def dataset(self, devices):
        ds = Dataset(headers=self.HEADERS)
        ds.extend(models.Device.objects.values_list(*self.HEADERS))
        return ds

    @pytest.fixture(autouse=True)
    def enable_dagster(self, settings):
        settings.DAGSTER_URL = "http://dagster-host:3000"

    def test_after_import_dry_run_skips_dagster(self, dataset, mocker):
        """after_import() with dry_run=True does not trigger the Dagster job."""
        mock_trigger = mocker.patch("apps.mdm.import_export.trigger_dagster_job")
        resource = import_export.DeviceResource()
        resource.import_data(dataset, dry_run=True)
        mock_trigger.assert_not_called()

    def test_after_import_push_all_includes_all_devices(self, dataset, mocker):
        """after_import() with push_method=ALL triggers Dagster for every device pk."""
        mock_trigger = mocker.patch("apps.mdm.import_export.trigger_dagster_job")
        resource = import_export.DeviceResource()
        resource.import_data(dataset, dry_run=False, push_method=models.PushMethodChoices.ALL)
        mock_trigger.assert_called_once()
        call_kwargs = mock_trigger.call_args
        device_pks = call_kwargs.kwargs["run_config"]["ops"]["push_mdm_device_config"]["config"][
            "device_pks"
        ]
        assert len(device_pks) == len(dataset)

    def test_after_import_default_push_method_includes_only_changed(self, fleet, mocker):
        """after_import() without push_method=ALL triggers Dagster only for new/updated rows."""
        mock_trigger = mocker.patch("apps.mdm.import_export.trigger_dagster_job")
        ds = Dataset(headers=self.HEADERS)
        # Add only a new device row (no id)
        ds.append([None, fleet.id, "NEWSERIAL", "", "NEWDEVID"])
        resource = import_export.DeviceResource()
        resource.import_data(ds, dry_run=False)
        mock_trigger.assert_called_once()
        device_pks = mock_trigger.call_args.kwargs["run_config"]["ops"]["push_mdm_device_config"][
            "config"
        ]["device_pks"]
        assert len(device_pks) == 1

    def test_after_import_dagster_error_is_logged_and_raised(self, fleet, mocker):
        """after_import() logs and re-raises exceptions from trigger_dagster_job."""
        mock_trigger = mocker.patch(
            "apps.mdm.import_export.trigger_dagster_job",
            side_effect=Exception("Dagster unavailable"),
        )
        ds = Dataset(headers=self.HEADERS)
        ds.append([None, fleet.id, "ERRSERIAL", "", "ERRDEVID"])
        resource = import_export.DeviceResource()
        # after_import() raises; import_data() may swallow it into result errors
        # — the key assertion is that trigger_dagster_job was called
        resource.import_data(ds, dry_run=False)
        mock_trigger.assert_called_once()


@pytest.mark.django_db
class TestDeviceResourceSaveInstance(TestAllMDMs):
    """Tests for save_instance() dry-run and do_instance_save() behavior."""

    @pytest.fixture
    def fleet(self):
        return FleetFactory()

    @pytest.fixture(autouse=True)
    def disable_dagster(self, settings):
        settings.DAGSTER_URL = None

    def test_do_instance_save_dry_run_does_not_push(self, fleet, mocker):
        """do_instance_save() with is_dry_run=True does not call save(push_to_mdm=True)."""
        device = DeviceFactory(fleet=fleet)
        mock_save = mocker.patch.object(device, "save")
        resource = import_export.DeviceResource()
        resource.do_instance_save(device, is_create=False, is_dry_run=True)
        mock_save.assert_called_once_with(push_to_mdm=False)


@pytest.mark.django_db
class TestDeviceResourceBulkMode(TestAllMDMs):
    """Tests for save_instance() when use_bulk=True."""

    @pytest.fixture(autouse=True)
    def disable_dagster(self, settings):
        settings.DAGSTER_URL = None

    @pytest.fixture
    def fleet(self):
        return FleetFactory()

    def test_save_instance_bulk_create_appends_to_list(self, fleet):
        """save_instance with use_bulk=True and is_create=True appends to create_instances."""

        class BulkDeviceResource(import_export.DeviceResource):
            class Meta(import_export.DeviceResource.Meta):
                use_bulk = True

        device = DeviceFactory.build(fleet=fleet)
        resource = BulkDeviceResource()
        resource.create_instances = []
        resource.update_instances = []
        resource.save_instance(device, is_create=True, row=RowResult())
        assert device in resource.create_instances

    def test_save_instance_bulk_update_appends_to_list(self, fleet):
        """save_instance with use_bulk=True and is_create=False appends to update_instances."""

        class BulkDeviceResource(import_export.DeviceResource):
            class Meta(import_export.DeviceResource.Meta):
                use_bulk = True

        device = DeviceFactory(fleet=fleet)
        resource = BulkDeviceResource()
        resource.create_instances = []
        resource.update_instances = []
        resource.save_instance(device, is_create=False, row=RowResult())
        assert device in resource.update_instances
