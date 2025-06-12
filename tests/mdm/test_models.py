import pytest

from apps.mdm.models import Policy
from .factories import DeviceFactory, FleetFactory, PolicyFactory


@pytest.mark.django_db
class TestModels:
    @pytest.fixture
    def fleet(self):
        return FleetFactory()

    def test_fleet_save_without_tinymdm_env_vars(self, fleet, mocker):
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
        fleet.save(sync_with_mdm=True)
        mock_pull_devices.assert_called_once()

    def test_device_save_without_tinymdm_env_vars(self, fleet, mocker):
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
        device = DeviceFactory(fleet=fleet)
        device.save(push_to_mdm=True)
        mock_push_device_config.assert_called_once()

    def test_fleet_group_name(self, fleet):
        """Ensure the Fleet.group_name property returns a string in the format
        '<org name>: <fleet name>'.
        """
        assert fleet.group_name == f"{fleet.organization.name}: {fleet.name}"

    def test_policy_get_default(self, settings):
        """Tests the Policy.get_default() method."""
        settings.TINYMDM_DEFAULT_POLICY = None
        # Cannot determine a default either from the database or using the setting
        assert not Policy.get_default()

        settings.TINYMDM_DEFAULT_POLICY = "12345"
        # The default policy is created in the database and returned
        policy = Policy.get_default()
        assert policy
        assert policy.policy_id == settings.TINYMDM_DEFAULT_POLICY
        assert policy.default_policy

        # get_default() gets whichever Policy has default_policy=True
        policy.default_policy = False
        policy.save()
        new_default = PolicyFactory(default_policy=True)
        assert Policy.get_default() == new_default
