import pytest
import datetime as dt

import faker
from apps.mdm.mdms import get_active_mdm_class
from apps.mdm.models import Policy, PolicyApplication, PolicyVariable
from tests.mdm import TestAllMDMs
from tests.publish_mdm.factories import OrganizationFactory

from .factories import (
    DeviceFactory,
    FleetFactory,
    PolicyApplicationFactory,
    PolicyFactory,
    PolicyVariableFactory,
)

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
        # Cannot determine a default from the database or using the setting
        assert not Policy.get_default()

        settings.MDM_DEFAULT_POLICY = "12345"
        # The default policy is created in the database and returned
        policy = Policy.get_default()
        assert policy
        assert policy.policy_id == settings.MDM_DEFAULT_POLICY

        # Calling again returns the same policy (get_or_create)
        same_policy = Policy.get_default()
        assert same_policy == policy

    def test_get_policy_data(self):
        """Tests the Policy.get_policy_data() method using the new serializer."""
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

    def test_get_policy_data_includes_fleet_variables(self):
        """get_policy_data() must include fleet-scoped variables so fleet overrides work."""
        org = OrganizationFactory()
        policy = PolicyFactory(organization=org)
        fleet = FleetFactory(policy=policy, organization=org)

        PolicyApplication.objects.create(
            policy=policy,
            package_name="com.example.app",
            install_type="FORCE_INSTALLED",
            managed_configuration={"token": "{{ api_token }}"},
            order=1,
        )
        PolicyVariable.objects.create(key="api_token", value="org_value", scope="org", org=org)
        PolicyVariable.objects.create(
            key="api_token", value="fleet_value", scope="fleet", fleet=fleet
        )

        policy_data = policy.get_policy_data()
        app_entry = next(
            a for a in policy_data["applications"] if a["packageName"] == "com.example.app"
        )
        # Fleet-scoped variable must override org-scoped variable
        assert app_entry["managedConfiguration"]["token"] == "fleet_value"

    def test_get_policy_data_uses_org_variables_without_fleet(self):
        """get_policy_data() resolves org-scoped variables even when the policy has no fleet.

        Regression test: variables were only fetched via fleet→org, so a policy not yet
        attached to any fleet had no org in the query and {{ var }} produced nothing.
        """
        org = OrganizationFactory()
        policy = PolicyFactory(organization=org)
        # No fleet — policy.fleets.all() is empty

        PolicyApplication.objects.create(
            policy=policy,
            package_name="com.example.app",
            install_type="FORCE_INSTALLED",
            managed_configuration={"token": "{{ api_token }}"},
            order=1,
        )
        PolicyVariable.objects.create(key="api_token", value="org_value", scope="org", org=org)

        policy_data = policy.get_policy_data()
        app_entry = next(
            a for a in policy_data["applications"] if a["packageName"] == "com.example.app"
        )
        # Org-scoped variable must be substituted even with no fleet
        assert app_entry["managedConfiguration"]["token"] == "org_value"

    def test_managed_configuration_str_empty_dict_returns_json(self):
        """managed_configuration_str() returns '{}' for an empty dict, not ''.

        Regression test: previously used ``if self.managed_configuration:`` which
        treated ``{}`` as falsy and incorrectly returned an empty string.
        """
        app = PolicyApplicationFactory(managed_configuration={})
        assert app.managed_configuration_str() == "{}"

    def test_managed_configuration_str_none_returns_empty_string(self):
        """managed_configuration_str() returns '' when managed_configuration is None."""
        app = PolicyApplicationFactory(managed_configuration=None)
        assert app.managed_configuration_str() == ""

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

    def test_policy_application_str(self):
        """PolicyApplication.__str__ returns package name with install type display."""
        app = PolicyApplicationFactory(
            package_name="com.example.app",
            install_type="FORCE_INSTALLED",
        )
        assert str(app) == "com.example.app (Force installed)"

    def test_policy_variable_str(self):
        """PolicyVariable.__str__ returns key=value (scope) format."""

        variable = PolicyVariableFactory(key="server_url", value="https://example.com", scope="org")
        assert str(variable) == "server_url=https://example.com (Policy)"

    def test_policy_variable_clean_raises_when_org_scope_without_org(self):
        """PolicyVariable.clean() raises ValidationError when scope=org but org is None."""
        from django.core.exceptions import ValidationError
        from apps.mdm.models import PolicyVariable

        variable = PolicyVariable(key="k", value="v", scope="org", org=None)
        with pytest.raises(ValidationError, match="Organization is required"):
            variable.clean()

    def test_policy_variable_clean_raises_when_fleet_scope_without_fleet(self):
        """PolicyVariable.clean() raises ValidationError when scope=fleet but fleet is None."""
        from django.core.exceptions import ValidationError
        from apps.mdm.models import PolicyVariable

        variable = PolicyVariable(key="k", value="v", scope="fleet", fleet=None)
        with pytest.raises(ValidationError, match="Fleet is required"):
            variable.clean()

    def test_policy_variable_clean_clears_fleet_for_org_scope(self):
        """PolicyVariable.clean() sets fleet=None for org-scoped variables."""
        from apps.mdm.models import PolicyVariable

        fleet = FleetFactory()
        variable = PolicyVariable(
            key="k", value="v", scope="org", org=fleet.organization, fleet=fleet
        )
        variable.clean()
        assert variable.fleet is None

    def test_policy_variable_clean_clears_org_for_fleet_scope(self):
        """PolicyVariable.clean() sets org=None for fleet-scoped variables."""
        from apps.mdm.models import PolicyVariable

        fleet = FleetFactory()
        variable = PolicyVariable(
            key="k", value="v", scope="fleet", fleet=fleet, org=fleet.organization
        )
        variable.clean()
        assert variable.org is None

    def test_device_odk_collect_qr_code_property(self, fleet):
        """Device.odk_collect_qr_code returns a mark_safe JSON string."""
        device = DeviceFactory(fleet=fleet)
        result = device.odk_collect_qr_code
        assert isinstance(result, str)
        # It should be a JSON-escaped string (double-quoted empty string if no app user)
        import json

        inner = json.loads(result)
        assert inner == ""  # empty since no AppUser

    def test_device_snapshot_str(self):
        """DeviceSnapshot.__str__ returns name (device_id) format."""
        from tests.mdm.factories import DeviceSnapshotFactory

        snapshot = DeviceSnapshotFactory(name="My Device", device_id="abc123")
        assert str(snapshot) == "My Device (abc123)"

    def test_device_snapshot_app_str(self):
        """DeviceSnapshotApp.__str__ returns app_name (package_name) snapshot format."""
        from apps.mdm.models import DeviceSnapshotApp
        from tests.mdm.factories import DeviceSnapshotFactory

        snapshot = DeviceSnapshotFactory()
        app = DeviceSnapshotApp.objects.create(
            device_snapshot=snapshot,
            package_name="org.odk.collect.android",
            app_name="ODK Collect",
            version_code=1,
            version_name="2024.1",
        )
        assert str(app) == "ODK Collect (org.odk.collect.android) snapshot"

    def test_firmware_snapshot_str(self, fleet):
        """FirmwareSnapshot.__str__ shows device_identifier, not the FK integer."""
        from tests.mdm.factories import FirmwareSnapshotFactory

        snap = FirmwareSnapshotFactory(
            device=DeviceFactory(fleet=fleet),
            device_identifier="TMDM-DEVICE-99",
            version="2.3.1",
        )
        assert str(snap) == "TMDM-DEVICE-99 (2.3.1) firmware snapshot"
