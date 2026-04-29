import datetime as dt
import json

import faker
import pytest
from django.core.exceptions import ValidationError
from django.utils.timezone import now

from apps.mdm.forms import (
    ENROLLMENT_TOKEN_DURATION_CHOICES,
)
from apps.mdm.mdms import get_active_mdm_class
from apps.mdm.models import (
    EMM_DPC_PACKAGE,
    AllowPersonalUsage,
    DeviceSnapshotApp,
    EnrollmentToken,
    PolicyApplication,
    PolicyVariable,
)
from tests.mdm import TestAllMDMs
from tests.publish_mdm.factories import (
    AppUserFactory,
    OrganizationFactory,
    ProjectFactory,
)

from .factories import (
    DeviceFactory,
    DeviceSnapshotFactory,
    EnrollmentTokenFactory,
    FirmwareSnapshotFactory,
    FleetFactory,
    PolicyApplicationFactory,
    PolicyFactory,
    PolicyVariableFactory,
)

fake = faker.Faker()


@pytest.mark.django_db
class TestModels(TestAllMDMs):
    @pytest.fixture
    def fleet(self, organization):
        return FleetFactory(organization=organization)

    def test_fleet_save_without_configured_mdm(self, fleet, mocker, unconfigure_mdm):
        """On Fleet.save(sync_with_mdm=True), pull_devices() shouldn't be called
        if an MDM is not configured for the organization.
        """
        mock_pull_devices = mocker.patch.object(
            get_active_mdm_class(fleet.organization), "pull_devices"
        )
        fleet.save(sync_with_mdm=True)
        mock_pull_devices.assert_not_called()

    def test_fleet_save_with_configured_mdm(self, fleet, mocker):
        """On Fleet.save(sync_with_mdm=True), pull_devices() should be called if
        an MDM is configured for the organization.
        """
        mock_pull_devices = mocker.patch.object(
            get_active_mdm_class(fleet.organization), "pull_devices"
        )
        fleet.save(sync_with_mdm=True)
        mock_pull_devices.assert_called_once()

    def test_device_save_without_configured_mdm(self, fleet, mocker, unconfigure_mdm):
        """On Device.save(push_to_mdm=True), push_device_config() shouldn't be called if
        an MDM is not configured for the organization.
        """
        mock_push_device_config = mocker.patch.object(
            get_active_mdm_class(fleet.organization), "push_device_config"
        )
        device = DeviceFactory.build(fleet=fleet)
        device.save(push_to_mdm=True)
        mock_push_device_config.assert_not_called()

    def test_device_save_with_configured_mdm(self, fleet, mocker):
        """On Device.save(push_to_mdm=True), push_device_config() should be called if
        an MDM is configured for the organization.
        """
        mock_push_device_config = mocker.patch.object(
            get_active_mdm_class(fleet.organization), "push_device_config"
        )
        device = DeviceFactory.build(fleet=fleet)
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

    def test_device_save_auto_assigns_and_pushes_to_mdm(self, fleet, mocker):
        """When auto-assigning the default_app_user, push_device_config should
        still fire if push_to_mdm=True.
        """
        app_user = AppUserFactory(project=fleet.project)
        fleet.default_app_user = app_user
        fleet.save()
        mock_push_device_config = mocker.patch.object(
            get_active_mdm_class(fleet.organization), "push_device_config"
        )
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
            managed_configuration={"token": "$api_token"},
            order=1,
        )
        PolicyVariable.objects.create(
            key="api_token", value="policy_value", scope="policy", policy=policy
        )
        PolicyVariable.objects.create(
            key="api_token", value="fleet_value", scope="fleet", fleet=fleet
        )

        policy_data = policy.get_policy_data()
        app_entry = next(
            a for a in policy_data["applications"] if a["packageName"] == "com.example.app"
        )
        # Fleet-scoped variable must override org-scoped variable
        assert app_entry["managedConfiguration"]["token"] == "fleet_value"

    def test_get_policy_data_uses_policy_variables_without_fleet(self):
        """get_policy_data() resolves policy-scoped variables even when the policy has no fleet."""
        org = OrganizationFactory()
        policy = PolicyFactory(organization=org)
        # No fleet — policy.fleets.all() is empty

        PolicyApplication.objects.create(
            policy=policy,
            package_name="com.example.app",
            install_type="FORCE_INSTALLED",
            managed_configuration={"token": "$api_token"},
            order=1,
        )
        PolicyVariable.objects.create(
            key="api_token", value="policy_value", scope="policy", policy=policy
        )

        policy_data = policy.get_policy_data()
        app_entry = next(
            a for a in policy_data["applications"] if a["packageName"] == "com.example.app"
        )
        # Policy-scoped variable must be substituted even with no fleet
        assert app_entry["managedConfiguration"]["token"] == "policy_value"

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

    def test_fleet_enrollment_url(self, organization):
        """Tests the Fleet.enrollment_url property."""
        fleet = FleetFactory(enroll_token_value=fake.pystr(), organization=organization)
        if fleet.organization.mdm == "Android Enterprise":
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

        variable = PolicyVariableFactory(
            key="server_url", value="https://example.com", scope="policy"
        )
        assert str(variable) == "server_url (Policy)"

    def test_policy_variable_clean_raises_when_policy_scope_without_policy(self):
        """PolicyVariable.clean() raises ValidationError when scope=policy but policy is None."""
        variable = PolicyVariable(key="k", value="v", scope="policy", policy=None)
        with pytest.raises(ValidationError, match="Policy is required"):
            variable.clean()

    def test_policy_variable_clean_raises_when_fleet_scope_without_fleet(self):
        """PolicyVariable.clean() raises ValidationError when scope=fleet but fleet is None."""
        variable = PolicyVariable(key="k", value="v", scope="fleet", fleet=None)
        with pytest.raises(ValidationError, match="Fleet is required"):
            variable.clean()

    def test_policy_variable_clean_clears_fleet_for_policy_scope(self):
        """PolicyVariable.clean() sets fleet=None for policy-scoped variables."""
        fleet = FleetFactory()
        variable = PolicyVariable(
            key="k", value="v", scope="policy", policy=fleet.policy, fleet=fleet
        )
        variable.clean()
        assert variable.fleet is None

    def test_policy_variable_clean_clears_policy_for_fleet_scope(self):
        """PolicyVariable.clean() sets policy=None for fleet-scoped variables."""
        fleet = FleetFactory()
        variable = PolicyVariable(key="k", value="v", scope="fleet", fleet=fleet)
        variable.clean()
        assert variable.policy is None

    def test_device_odk_collect_qr_code_property(self, fleet):
        """Device.odk_collect_qr_code returns a mark_safe JSON string."""
        device = DeviceFactory(fleet=fleet)
        result = device.odk_collect_qr_code
        assert isinstance(result, str)
        # It should be a JSON-escaped string (double-quoted empty string if no app user)
        inner = json.loads(result)
        assert inner == ""  # empty since no AppUser

    def test_device_snapshot_str(self):
        """DeviceSnapshot.__str__ returns name (device_id) format."""
        snapshot = DeviceSnapshotFactory(name="My Device", device_id="abc123")
        assert str(snapshot) == "My Device (abc123)"

    def test_device_snapshot_app_str(self):
        """DeviceSnapshotApp.__str__ returns app_name (package_name) snapshot format."""
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
        snap = FirmwareSnapshotFactory(
            device=DeviceFactory(fleet=fleet),
            device_identifier="TMDM-DEVICE-99",
            version="2.3.1",
        )
        assert str(snap) == "TMDM-DEVICE-99 (2.3.1) firmware snapshot"

    @pytest.mark.parametrize(
        "enrollment_type, expected",
        [
            ("DEVICE_OWNER", True),
            ("fully_managed", True),
            ("work_profile", False),
            ("PROFILE_OWNER", False),
        ],
    )
    def test_is_fully_managed_with_snapshot(self, enrollment_type, expected):
        """is_fully_managed returns True only for DEVICE_OWNER / fully_managed enrollment types."""
        snapshot = DeviceSnapshotFactory(enrollment_type=enrollment_type)
        device = snapshot.mdm_device
        device.latest_snapshot = snapshot
        device.save()
        assert device.is_fully_managed is expected

    def test_is_fully_managed_no_snapshot(self):
        """is_fully_managed returns False when the device has no latest snapshot."""
        device = DeviceFactory(latest_snapshot=None)
        assert device.is_fully_managed is False

    def test_wipe_and_soft_delete_success(self, organization, mocker):
        """wipe_and_soft_delete calls MDM delete_device, soft-deletes the device,
        and returns True.
        """
        device = DeviceFactory(fleet__organization=organization)
        MDM = get_active_mdm_class(organization)
        mock_delete = mocker.patch.object(MDM, "delete_device")
        result = device.wipe_and_soft_delete()
        assert result is True
        mock_delete.assert_called_once_with(device)
        device.refresh_from_db()
        assert device.is_deleted is True

    def test_wipe_and_soft_delete_no_mdm(self, organization, mocker, unconfigure_mdm):
        """wipe_and_soft_delete returns False and does not soft-delete if MDM is not configured."""
        device = DeviceFactory(fleet__organization=organization)
        MDM = get_active_mdm_class(organization)
        mock_delete = mocker.patch.object(MDM, "delete_device")
        result = device.wipe_and_soft_delete()
        assert result is False
        mock_delete.assert_not_called()
        device.refresh_from_db()
        assert device.is_deleted is False

    def test_wipe_and_soft_delete_mdm_error(self, organization, mocker, mdm_api_error):
        """wipe_and_soft_delete returns False and does not soft-delete if delete_device raises."""
        device = DeviceFactory(fleet__organization=organization)
        MDM = get_active_mdm_class(organization)
        mocker.patch.object(MDM, "delete_device", side_effect=mdm_api_error)
        result = device.wipe_and_soft_delete()
        assert result is False
        device.refresh_from_db()
        assert device.is_deleted is False


# ---------------------------------------------------------------------------
# EnrollmentToken model tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEnrollmentTokenModel:
    """Tests for the EnrollmentToken model properties and manager."""

    def test_is_expired_no_expiry(self):
        """is_expired returns False when expires_at is None."""
        token = EnrollmentTokenFactory(expires_at=None)
        assert token.is_expired is False

    def test_is_expired_future(self):
        """is_expired returns False when expires_at is in the future."""
        token = EnrollmentTokenFactory(expires_at=now() + dt.timedelta(days=30))
        assert token.is_expired is False

    def test_is_expired_past(self):
        """is_expired returns True when expires_at is in the past."""
        token = EnrollmentTokenFactory(expires_at=now() - dt.timedelta(seconds=1))
        assert token.is_expired is True

    def test_is_active_when_not_revoked_and_not_expired(self):
        """is_active returns True when the token is not revoked and not expired."""
        token = EnrollmentTokenFactory(revoked_at=None, expires_at=now() + dt.timedelta(days=30))
        assert token.is_active is True

    def test_is_active_false_when_revoked(self):
        """is_active returns False when the token is revoked."""
        token = EnrollmentTokenFactory(revoked_at=now())
        assert token.is_active is False

    def test_is_active_false_when_expired(self):
        """is_active returns False when the token is expired."""
        token = EnrollmentTokenFactory(revoked_at=None, expires_at=now() - dt.timedelta(seconds=1))
        assert token.is_active is False

    def test_is_active_false_when_both_revoked_and_expired(self):
        """is_active returns False when the token is both revoked and expired."""
        token = EnrollmentTokenFactory(
            revoked_at=now() - dt.timedelta(days=5),
            expires_at=now() - dt.timedelta(days=1),
        )
        assert token.is_active is False

    def test_enrollment_url_with_token_value(self):
        """enrollment_url returns the AMAPI enrollment URL when token_value is set."""
        token = EnrollmentTokenFactory(token_value="abc123")
        assert token.enrollment_url == "https://enterprise.google.com/android/enroll?et=abc123"

    def test_enrollment_url_without_token_value(self):
        """enrollment_url returns None when token_value is empty."""
        token = EnrollmentTokenFactory(token_value="")
        assert token.enrollment_url is None

    def test_dpc_extras_json_with_token_value(self):
        """dpc_extras_json returns valid JSON with the correct structure for ZTE."""
        token = EnrollmentTokenFactory(token_value="mytoken")
        result = token.dpc_extras_json
        assert result is not None
        data = json.loads(result)
        bundle = data["android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE"]
        assert bundle[f"{EMM_DPC_PACKAGE}.EXTRA_ENROLLMENT_TOKEN"] == "mytoken"

    def test_dpc_extras_json_without_token_value(self):
        """dpc_extras_json returns None when token_value is empty."""
        token = EnrollmentTokenFactory(token_value="")
        assert token.dpc_extras_json is None

    def test_str_uses_label_when_set(self):
        """__str__ returns the label when it is set."""
        token = EnrollmentTokenFactory(label="My Token")
        assert str(token) == "My Token"

    def test_str_uses_token_resource_name_when_no_label(self):
        """__str__ returns the last segment of token_resource_name (name property) when label is empty."""
        token = EnrollmentTokenFactory(
            label="", token_resource_name="enterprises/test/enrollmentTokens/abc"
        )
        assert str(token) == "abc"

    def test_name_property_extracts_last_segment(self):
        """name property returns the last path segment of token_resource_name."""
        token = EnrollmentTokenFactory(token_resource_name="enterprises/test/enrollmentTokens/abc")
        assert token.name == "abc"

    def test_name_property_empty_when_no_resource_name(self):
        """name property returns empty string when token_resource_name is empty."""
        token = EnrollmentTokenFactory(token_resource_name="")
        assert token.name == ""

    def test_str_uses_pk_when_no_label_or_resource_name(self):
        """__str__ returns 'Enrollment token <pk>' when both label and resource_name are empty."""
        token = EnrollmentTokenFactory(label="", token_resource_name="")
        assert str(token) == f"Enrollment token {token.pk}"

    def test_manager_excludes_deleted_org_tokens(self):
        """EnrollmentTokenManager excludes tokens for soft-deleted organizations."""
        token = EnrollmentTokenFactory()
        assert EnrollmentToken.objects.filter(pk=token.pk).exists()

        # Soft-delete the organization
        token.organization.soft_delete()
        assert not EnrollmentToken.objects.filter(pk=token.pk).exists()

    def test_all_orgs_manager_includes_deleted_org_tokens(self):
        """all_orgs manager includes tokens for soft-deleted organizations."""
        token = EnrollmentTokenFactory()
        token.organization.soft_delete()
        assert EnrollmentToken.all_orgs.filter(pk=token.pk).exists()

    def test_ordering_newest_first(self):
        """EnrollmentToken default ordering is newest-first by created_at."""

        fleet = FleetFactory()
        older = EnrollmentTokenFactory(fleet=fleet, organization=fleet.organization)
        newer = EnrollmentTokenFactory(fleet=fleet, organization=fleet.organization)
        tokens = list(EnrollmentToken.objects.filter(fleet=fleet))
        assert tokens[0].pk == newer.pk
        assert tokens[1].pk == older.pk

    def test_duration_choices_values(self):
        """ENROLLMENT_TOKEN_DURATION_CHOICES contains all five expected entries."""
        assert len(ENROLLMENT_TOKEN_DURATION_CHOICES) == 5
        keys = [k for k, _ in ENROLLMENT_TOKEN_DURATION_CHOICES]
        assert "1_week" in keys
        assert "1_month" in keys
        assert "3_months" in keys
        assert "6_months" in keys
        assert "12_months" in keys

    def test_allow_personal_usage_choices(self):
        """AllowPersonalUsage has the four expected choices."""
        values = [v for v, _ in AllowPersonalUsage.choices]
        assert "ALLOW_PERSONAL_USAGE_UNSPECIFIED" in values
        assert "PERSONAL_USAGE_ALLOWED" in values
        assert "PERSONAL_USAGE_DISALLOWED" in values
        assert "PERSONAL_USAGE_DISALLOWED_USERLESS" in values
