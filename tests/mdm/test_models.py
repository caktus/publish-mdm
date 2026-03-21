import pytest
import datetime as dt

import faker
from apps.mdm.mdms import get_active_mdm_class
from apps.mdm.models import Policy
from tests.mdm import TestAllMDMs

from .factories import DeviceFactory, FleetFactory, PolicyFactory

fake = faker.Faker()


@pytest.mark.django_db
class TestModels(TestAllMDMs):
    @pytest.fixture
    def fleet(self):
        return FleetFactory()

    def test_fleet_save_without_mdm_env_vars(self, fleet, mocker):
        """On Fleet.save(), pull_devices() shouldn't be called if the
        active MDM's environment variables are not set.
        """
        mock_pull_devices = mocker.patch.object(get_active_mdm_class(), "pull_devices")
        fleet.save()
        mock_pull_devices.assert_not_called()

    def test_fleet_save_with_mdm_env_vars(self, fleet, mocker, set_mdm_env_vars):
        """On Fleet.save(), pull_devices() should be called if the active MDM's
        environment variables are set.
        """
        mock_pull_devices = mocker.patch.object(get_active_mdm_class(), "pull_devices")
        fleet.save(sync_with_mdm=True)
        mock_pull_devices.assert_called_once()

    def test_device_save_without_mdm_env_vars(self, fleet, mocker):
        """On Device.save(), push_device_config() shouldn't be called if the
        active MDM's environment variables are not set.
        """
        mock_push_device_config = mocker.patch.object(get_active_mdm_class(), "push_device_config")
        DeviceFactory(fleet=fleet)
        mock_push_device_config.assert_not_called()

    def test_device_save_with_mdm_env_vars(self, fleet, mocker, set_mdm_env_vars):
        """On Device.save(), push_device_config() should be called if the
        active MDM's environment variables are set.
        """
        mock_push_device_config = mocker.patch.object(get_active_mdm_class(), "push_device_config")
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
        settings.MDM_DEFAULT_POLICY = None
        # Cannot determine a default either from the database or using the setting
        assert not Policy.get_default()

        settings.MDM_DEFAULT_POLICY = "12345"
        # The default policy is created in the database and returned
        policy = Policy.get_default()
        assert policy
        assert policy.policy_id == settings.MDM_DEFAULT_POLICY
        assert policy.default_policy

        # get_default() gets whichever Policy has default_policy=True
        policy.default_policy = False
        policy.save()
        new_default = PolicyFactory(default_policy=True)
        assert Policy.get_default() == new_default

    def test_get_policy_data(self):
        """Tests the Policy.get_policy_data() method using the new serializer."""
        from apps.mdm.models import PolicyApplication

        # A policy with default fields should return a dict with the ODK Collect app
        policy = PolicyFactory()
        policy_data = policy.get_policy_data()
        assert policy_data is not None
        assert "applications" in policy_data
        # ODK Collect is always present
        odk_app = policy_data["applications"][0]
        assert odk_app["packageName"] == "org.odk.collect.android"
        assert odk_app["installType"] == "FORCE_INSTALLED"

        # Add password policy fields
        policy.device_password_quality = "NUMERIC"
        policy.device_password_min_length = 6
        policy.save()
        policy_data = policy.get_policy_data()
        assert "passwordPolicies" in policy_data
        device_pw = policy_data["passwordPolicies"][0]
        assert device_pw["passwordQuality"] == "NUMERIC"
        assert device_pw["passwordMinimumLength"] == 6

        # Add a VPN
        policy.vpn_package_name = "com.tailscale.ipn"
        policy.vpn_lockdown = True
        policy.save()
        policy_data = policy.get_policy_data()
        assert policy_data["alwaysOnVpnPackage"] == {
            "packageName": "com.tailscale.ipn",
            "lockdownEnabled": True,
        }

        # Add a non-ODK application
        PolicyApplication.objects.create(
            policy=policy,
            package_name="com.example.app",
            install_type="PREINSTALLED",
            order=1,
        )
        policy_data = policy.get_policy_data()
        assert len(policy_data["applications"]) == 2
        assert policy_data["applications"][1]["packageName"] == "com.example.app"
        assert policy_data["applications"][1]["installType"] == "PREINSTALLED"

        # get_policy_data() with device context should inject ODK managed config
        device = DeviceFactory()
        policy_data = policy.get_policy_data(device=device)
        odk_app = policy_data["applications"][0]
        assert "managedConfiguration" in odk_app or "packageName" in odk_app

    def test_fleet_enroll_token_expired(self):
        """Tests the Fleet.enroll_token_expired property."""
        fleet = FleetFactory(enroll_token_expires_at=None)
        assert not fleet.enroll_token_expired

        fleet = FleetFactory(enroll_token_expires_at=fake.past_datetime(tzinfo=dt.UTC))
        assert fleet.enroll_token_expired

        fleet = FleetFactory(enroll_token_expires_at=fake.future_datetime(tzinfo=dt.UTC))
        assert not fleet.enroll_token_expired

    def test_fleet_enrollment_url(self, settings):
        """Tests the Fleet.enrollment_url property."""
        fleet = FleetFactory(enroll_token_value=fake.pystr())
        if settings.ACTIVE_MDM["name"] == "Android Enterprise":
            assert (
                fleet.enrollment_url
                == f"https://enterprise.google.com/android/enroll?et={fleet.enroll_token_value}"
            )
        else:
            assert fleet.enrollment_url is None
