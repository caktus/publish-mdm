import pytest

from .factories import DeviceFactory, FleetFactory


@pytest.mark.django_db
class TestModels:
    TINYMDM_ENV_VARS = ("TINYMDM_APIKEY_PUBLIC", "TINYMDM_APIKEY_SECRET", "TINYMDM_ACCOUNT_ID")

    @pytest.fixture
    def fleet(self):
        return FleetFactory()

    @pytest.fixture
    def del_tinymdm_env_vars(self, monkeypatch):
        """Delete environment variables for TinyMDM API credentials, if they exist."""
        for var in self.TINYMDM_ENV_VARS:
            monkeypatch.delenv(var, raising=False)

    @pytest.fixture
    def set_tinymdm_env_vars(self, monkeypatch):
        """Set environment variables for TinyMDM API credentials to fake values."""
        for var in self.TINYMDM_ENV_VARS:
            monkeypatch.setenv(var, "test")

    def test_fleet_save_without_tinymdm_env_vars(self, fleet, mocker, del_tinymdm_env_vars):
        """On Fleet.save(), pull_devices() shouldn't be called if the
        TinyMDM environment variables are not set.
        """
        mock_pull_devices = mocker.patch("apps.mdm.tasks.pull_devices")
        fleet.save()
        mock_pull_devices.assert_not_called()

    def test_fleet_save_with_tinymdm_env_vars(self, fleet, mocker, set_tinymdm_env_vars):
        """On Fleet.save(), pull_devices() should be called if the TinyMDM
        environment variables are set.
        """
        mock_pull_devices = mocker.patch("apps.mdm.tasks.pull_devices")
        fleet.save()
        mock_pull_devices.assert_called_once()

    def test_device_save_without_tinymdm_env_vars(self, fleet, mocker, del_tinymdm_env_vars):
        """On Device.save(), push_device_config() shouldn't be called if the
        TinyMDM environment variables are not set.
        """
        mock_push_device_config = mocker.patch("apps.mdm.tasks.push_device_config")
        DeviceFactory(fleet=fleet)
        mock_push_device_config.assert_not_called()

    def test_device_save_with_tinymdm_env_vars(self, fleet, mocker, set_tinymdm_env_vars):
        """On Device.save(), push_device_config() should be called if the
        TinyMDM environment variables are set.
        """
        mock_push_device_config = mocker.patch("apps.mdm.tasks.push_device_config")
        DeviceFactory(fleet=fleet)
        mock_push_device_config.assert_called_once()
