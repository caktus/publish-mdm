import pytest
import datetime as dt

import faker
from django.core.exceptions import ValidationError
from apps.mdm.mdms import get_active_mdm_class
from apps.mdm.models import Policy
from tests.mdm import TestAllMDMs
from tests.publish_mdm.factories import AppUserFactory, ProjectFactory

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

    def test_device_save_auto_assigns_default_app_user(self, fleet):
        """When a device has no app_user_name and the fleet has a default_app_user,
        the device's app_user_name should be auto-assigned on save.
        """
        app_user = AppUserFactory(project=fleet.project)
        fleet.default_app_user = app_user
        fleet.save()
        device = DeviceFactory(fleet=fleet, app_user_name="")
        device.refresh_from_db()
        assert device.app_user_name == app_user.name

    def test_device_save_auto_assigns_default_app_user_when_update_fields_is_set(self, fleet):
        """When a device has no app_user_name and the fleet has a default_app_user,
        the device's app_user_name should be auto-assigned on save even if update_fields
        was set and did not include app_user_name.
        """
        device = DeviceFactory(fleet=fleet, app_user_name="")
        assert device.app_user_name == ""
        app_user = AppUserFactory(project=fleet.project)
        fleet.default_app_user = app_user
        fleet.save()
        device.serial_number += "_edited"
        device.save(update_fields=["serial_number"])
        device.refresh_from_db()
        # Both app_user_name and serial_number should be updated
        assert device.app_user_name == app_user.name
        assert device.serial_number.endswith("_edited")

    def test_device_save_auto_assigns_and_pushes_to_mdm(self, fleet, mocker, set_mdm_env_vars):
        """When auto-assigning the default_app_user, push_device_config should
        still fire if push_to_mdm=True.
        """
        app_user = AppUserFactory(project=fleet.project)
        fleet.default_app_user = app_user
        fleet.save()
        mock_push_device_config = mocker.patch.object(get_active_mdm_class(), "push_device_config")
        device = DeviceFactory(fleet=fleet, app_user_name="")
        device.app_user_name = ""
        device.save(push_to_mdm=True)
        mock_push_device_config.assert_called_once()
        device.refresh_from_db()
        assert device.app_user_name == app_user.name

    def test_device_save_does_not_overwrite_existing_app_user_name(self, fleet):
        """When a device already has an app_user_name, the default_app_user
        should not overwrite it.
        """
        app_user = AppUserFactory(project=fleet.project)
        fleet.default_app_user = app_user
        fleet.save()
        original_name = "existing-user"
        device = DeviceFactory(fleet=fleet, app_user_name=original_name)
        device.refresh_from_db()
        assert device.app_user_name == original_name

    def test_device_save_no_default_app_user_leaves_name_empty(self, fleet):
        """When the fleet has no default_app_user and a device is saved
        without an app_user_name, the name should remain empty.
        """
        assert fleet.default_app_user_id is None
        device = DeviceFactory(fleet=fleet, app_user_name="")
        device.refresh_from_db()
        assert device.app_user_name == ""

    def test_fleet_clean_valid_default_app_user(self, fleet):
        """Fleet.clean() should not raise when default_app_user belongs to fleet.project.
        The fleet should also be saveable after passing validation.
        """
        app_user = AppUserFactory(project=fleet.project)
        fleet.default_app_user = app_user
        fleet.full_clean()  # Should not raise
        fleet.save()
        fleet.refresh_from_db()
        assert fleet.default_app_user == app_user

    def test_fleet_clean_default_app_user_wrong_project(self, fleet):
        """Fleet.clean() should raise ValidationError when default_app_user belongs
        to a different project than fleet.project.
        """
        other_project = ProjectFactory(organization=fleet.organization)
        app_user = AppUserFactory(project=other_project)
        fleet.default_app_user = app_user
        with pytest.raises(ValidationError) as exc_info:
            fleet.clean()
        assert "default_app_user" in exc_info.value.message_dict

    def test_fleet_clean_default_app_user_without_project(self, fleet):
        """Fleet.clean() should raise ValidationError when default_app_user is set
        but fleet.project is None.
        """
        app_user = AppUserFactory(project=fleet.project)
        fleet.default_app_user = app_user
        fleet.project = None
        with pytest.raises(ValidationError) as exc_info:
            fleet.clean()
        assert "default_app_user" in exc_info.value.message_dict

    def test_fleet_clean_no_default_app_user(self, fleet):
        """Fleet.clean() should not raise when default_app_user is None,
        regardless of whether project is set.
        """
        fleet.default_app_user = None
        fleet.clean()  # Should not raise
        fleet.project = None
        fleet.clean()  # Should also not raise

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
