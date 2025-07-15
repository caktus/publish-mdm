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
        """Tests the Policy.get_policy_data() method."""
        # Policy.json_template is an empty string. get_policy_data() should return None
        policy = PolicyFactory(json_template="")
        assert policy.get_policy_data() is None

        # Policy.json_template is invalid JSON. get_policy_data() should return None
        policy.json_template = "invalid"
        policy.save()

        assert policy.get_policy_data() is None

        # Policy.json_template is valid JSON
        policy.json_template = """
        {
            "passwordPolicies": {
                "passwordQuality": "SOMETHING"
            },
            "applications": [
                {
                    {% if device %}
                    "managedConfiguration": {
                        "device_id": "{{ device.username }}",
                        "settings_json": {{ device.odk_collect_qr_code }}
                    },
                    {% endif %}
                    "packageName": "org.odk.collect.android",
                    "installType": "FORCE_INSTALLED"
                }
            ]
        }
        """
        policy.save()
        expected_policy_data = {
            "passwordPolicies": {"passwordQuality": "SOMETHING"},
            "applications": [
                {"packageName": "org.odk.collect.android", "installType": "FORCE_INSTALLED"}
            ],
        }

        assert policy.get_policy_data() == expected_policy_data

        # get_policy_data() is passed a Device object in the `device` kwarg.
        # It should be passed to the template as a context variable
        device = DeviceFactory()
        expected_policy_data["applications"][0].update(
            {
                "managedConfiguration": {"device_id": device.username, "settings_json": ""},
            }
        )
        assert policy.get_policy_data(device=device) == expected_policy_data

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
