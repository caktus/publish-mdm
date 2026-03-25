import pytest

from apps.mdm.models import (
    DeveloperSettings,
    PasswordQuality,
    PolicyApplication,
    PolicyVariable,
    RequirePasswordUnlock,
)
from apps.mdm.serializers import PolicySerializer
from apps.publish_mdm.etl.odk.constants import DEFAULT_COLLECT_SETTINGS
from tests.mdm import TestAllMDMs
from tests.mdm.factories import DeviceFactory, FleetFactory, PolicyFactory
from tests.publish_mdm.factories import AppUserFactory, OrganizationFactory


@pytest.mark.django_db
class TestPolicySerializer(TestAllMDMs):
    def test_basic_policy(self):
        """A policy with defaults should produce a dict with ODK Collect app."""
        policy = PolicyFactory()
        serializer = PolicySerializer(policy=policy)
        result = serializer.to_dict()
        assert "applications" in result
        assert result["applications"][0]["packageName"] == "org.odk.collect.android"
        assert result["applications"][0]["installType"] == "FORCE_INSTALLED"

    def test_password_policies(self):
        """Password policy fields should produce passwordPolicies entries."""
        policy = PolicyFactory(
            device_password_quality=PasswordQuality.NUMERIC,
            device_password_min_length=6,
            device_password_require_unlock=RequirePasswordUnlock.REQUIRE_EVERY_DAY,
            work_password_quality=PasswordQuality.ALPHANUMERIC,
            work_password_min_length=8,
        )
        serializer = PolicySerializer(policy=policy)
        result = serializer.to_dict()
        assert len(result["passwordPolicies"]) == 2
        device_pw = result["passwordPolicies"][0]
        assert device_pw["passwordScope"] == "SCOPE_DEVICE"
        assert device_pw["passwordQuality"] == "NUMERIC"
        assert device_pw["passwordMinimumLength"] == 6
        assert device_pw["requirePasswordUnlock"] == "REQUIRE_EVERY_DAY"
        work_pw = result["passwordPolicies"][1]
        assert work_pw["passwordScope"] == "SCOPE_PROFILE"
        assert work_pw["passwordQuality"] == "ALPHANUMERIC"
        assert work_pw["passwordMinimumLength"] == 8

    def test_no_password_policy_when_unspecified(self):
        """Unspecified password quality should not produce passwordPolicies."""
        policy = PolicyFactory(
            device_password_quality=PasswordQuality.PASSWORD_QUALITY_UNSPECIFIED,
            work_password_quality=PasswordQuality.PASSWORD_QUALITY_UNSPECIFIED,
        )
        serializer = PolicySerializer(policy=policy)
        result = serializer.to_dict()
        assert "passwordPolicies" not in result

    def test_vpn(self):
        """VPN fields should produce alwaysOnVpnPackage."""
        policy = PolicyFactory(vpn_package_name="com.tailscale.ipn", vpn_lockdown=True)
        serializer = PolicySerializer(policy=policy)
        result = serializer.to_dict()
        assert result["alwaysOnVpnPackage"] == {
            "packageName": "com.tailscale.ipn",
            "lockdownEnabled": True,
        }

    def test_no_vpn_when_empty(self):
        """Empty VPN package should not produce alwaysOnVpnPackage."""
        policy = PolicyFactory(vpn_package_name="")
        serializer = PolicySerializer(policy=policy)
        result = serializer.to_dict()
        assert "alwaysOnVpnPackage" not in result

    def test_developer_settings_allowed(self):
        """Allowed developer settings should produce advancedSecurityOverrides."""
        policy = PolicyFactory(
            developer_settings=DeveloperSettings.DEVELOPER_SETTINGS_ALLOWED,
        )
        serializer = PolicySerializer(policy=policy)
        result = serializer.to_dict()
        assert result["advancedSecurityOverrides"] == {
            "developerSettings": "DEVELOPER_SETTINGS_ALLOWED"
        }

    def test_developer_settings_disabled(self):
        """Disabled developer settings must be sent explicitly so a previous ALLOWED value is cleared."""
        policy = PolicyFactory(
            developer_settings=DeveloperSettings.DEVELOPER_SETTINGS_DISABLED,
        )
        serializer = PolicySerializer(policy=policy)
        result = serializer.to_dict()
        assert result["advancedSecurityOverrides"] == {
            "developerSettings": "DEVELOPER_SETTINGS_DISABLED"
        }

    def test_applications(self):
        """PolicyApplication rows should appear in the applications list."""
        policy = PolicyFactory()
        app1 = PolicyApplication.objects.create(
            policy=policy,
            package_name="com.example.app",
            install_type="PREINSTALLED",
            order=1,
        )
        app2 = PolicyApplication.objects.create(
            policy=policy,
            package_name="com.example.blocked",
            install_type="BLOCKED",
            disabled=True,
            order=2,
        )
        serializer = PolicySerializer(
            policy=policy,
            applications=[app1, app2],
        )
        result = serializer.to_dict()
        # ODK Collect + 2 apps
        assert len(result["applications"]) == 3
        assert result["applications"][1]["packageName"] == "com.example.app"
        assert result["applications"][1]["installType"] == "PREINSTALLED"
        assert result["applications"][2]["packageName"] == "com.example.blocked"
        assert result["applications"][2]["disabled"] is True

    def test_empty_managed_configuration_is_included(self):
        """An empty dict ({}) managed_configuration should appear in the output, not be omitted.

        Regression test: previously `if app.managed_configuration` was used, which
        silently dropped an explicitly-set empty dict.
        """
        policy = PolicyFactory()
        app = PolicyApplication.objects.create(
            policy=policy,
            package_name="com.example.app",
            install_type="FORCE_INSTALLED",
            managed_configuration={},
            order=1,
        )
        serializer = PolicySerializer(policy=policy, applications=[app])
        result = serializer.to_dict()
        app_entry = next(a for a in result["applications"] if a["packageName"] == "com.example.app")
        assert "managedConfiguration" in app_entry
        assert app_entry["managedConfiguration"] == {}

    def test_none_managed_configuration_is_omitted(self):
        """A None managed_configuration should not produce a managedConfiguration key."""
        policy = PolicyFactory()
        app = PolicyApplication.objects.create(
            policy=policy,
            package_name="com.example.app",
            install_type="FORCE_INSTALLED",
            managed_configuration=None,
            order=1,
        )
        serializer = PolicySerializer(policy=policy, applications=[app])
        result = serializer.to_dict()
        app_entry = next(a for a in result["applications"] if a["packageName"] == "com.example.app")
        assert "managedConfiguration" not in app_entry

    def test_variable_substitution(self):
        """Variables should be substituted in string values."""
        policy = PolicyFactory()
        org = OrganizationFactory()
        var = PolicyVariable.objects.create(key="auth_key", value="secret123", scope="org", org=org)
        app = PolicyApplication.objects.create(
            policy=policy,
            package_name="com.example.vpn",
            install_type="FORCE_INSTALLED",
            managed_configuration={"AuthKey": "$auth_key"},
            order=1,
        )
        serializer = PolicySerializer(
            policy=policy,
            applications=[app],
            variables=[var],
        )
        result = serializer.to_dict()
        vpn_app = result["applications"][1]
        assert vpn_app["managedConfiguration"]["AuthKey"] == "secret123"

    def test_fleet_variable_overrides_org(self):
        """Fleet-level variable should override org-level for the same key."""
        policy = PolicyFactory()
        org = OrganizationFactory()
        fleet = FleetFactory(policy=policy, organization=org)
        org_var = PolicyVariable.objects.create(
            key="auth_key", value="org_value", scope="org", org=org
        )
        fleet_var = PolicyVariable.objects.create(
            key="auth_key", value="fleet_value", scope="fleet", fleet=fleet
        )
        app = PolicyApplication.objects.create(
            policy=policy,
            package_name="com.example.app",
            install_type="FORCE_INSTALLED",
            managed_configuration={"key": "$auth_key"},
            order=1,
        )
        serializer = PolicySerializer(
            policy=policy,
            applications=[app],
            variables=[org_var, fleet_var],
        )
        result = serializer.to_dict()
        assert result["applications"][1]["managedConfiguration"]["key"] == "fleet_value"

    def test_device_system_variables(self):
        """Built-in device variables should be resolved."""
        policy = PolicyFactory()
        device = DeviceFactory(
            serial_number="ABC123",
            raw_mdm_device={"hardwareInfo": {"imei": "IMEI456"}},
        )
        app = PolicyApplication.objects.create(
            policy=policy,
            package_name="com.example.app",
            install_type="FORCE_INSTALLED",
            managed_configuration={
                "device_id": "$imei",
                "serial": "$serial_number",
            },
            order=1,
        )
        serializer = PolicySerializer(
            policy=policy,
            applications=[app],
            device=device,
        )
        result = serializer.to_dict()
        config = result["applications"][1]["managedConfiguration"]
        assert config["device_id"] == "IMEI456"
        assert config["serial"] == "ABC123"

    def test_odk_collect_always_first(self):
        """ODK Collect should always be the first application."""
        policy = PolicyFactory()
        app = PolicyApplication.objects.create(
            policy=policy,
            package_name="com.example.first",
            install_type="FORCE_INSTALLED",
            order=0,
        )
        serializer = PolicySerializer(policy=policy, applications=[app])
        result = serializer.to_dict()
        assert result["applications"][0]["packageName"] == "org.odk.collect.android"

    def test_unresolved_variable_preserved(self):
        """Unresolved variables should remain as-is in the output."""
        policy = PolicyFactory()
        app = PolicyApplication.objects.create(
            policy=policy,
            package_name="com.example.app",
            install_type="FORCE_INSTALLED",
            managed_configuration={"key": "$unknown_var"},
            order=1,
        )
        serializer = PolicySerializer(policy=policy, applications=[app])
        result = serializer.to_dict()
        assert result["applications"][1]["managedConfiguration"]["key"] == "$unknown_var"

    def test_kiosk_customization_settings(self):
        """All kiosk fields appear in kioskCustomization when non-default values are set."""
        policy = PolicyFactory(
            kiosk_power_button_actions="POWER_BUTTON_AVAILABLE",
            kiosk_system_error_warnings="ERROR_AND_WARNINGS_MUTED",
            kiosk_system_navigation="NAVIGATION_DISABLED",
            kiosk_status_bar="NOTIFICATIONS_AND_SYSTEM_INFO_DISABLED",
            kiosk_device_settings="SETTINGS_ACCESS_BLOCKED",
        )
        serializer = PolicySerializer(policy=policy)
        result = serializer.to_dict()
        kiosk = result["kioskCustomization"]
        assert kiosk["powerButtonActions"] == "POWER_BUTTON_AVAILABLE"
        assert kiosk["systemErrorWarnings"] == "ERROR_AND_WARNINGS_MUTED"
        assert kiosk["systemNavigation"] == "NAVIGATION_DISABLED"
        assert kiosk["statusBar"] == "NOTIFICATIONS_AND_SYSTEM_INFO_DISABLED"
        assert kiosk["deviceSettings"] == "SETTINGS_ACCESS_BLOCKED"

    def test_odk_managed_config_injected_when_device_has_app_user(self):
        """managedConfiguration is injected into the ODK Collect app entry when
        the device's app_user_name resolves to a project AppUser with qr_code_data."""
        fleet = FleetFactory()
        device = DeviceFactory(fleet=fleet, app_user_name="testuser")
        AppUserFactory(
            name="testuser",
            project=fleet.project,
            qr_code_data=DEFAULT_COLLECT_SETTINGS,
        )
        policy = fleet.policy
        serializer = PolicySerializer(policy=policy, device=device)
        result = serializer.to_dict()
        odk_app = result["applications"][0]
        assert "managedConfiguration" in odk_app
        assert "settings_json" in odk_app["managedConfiguration"]
        assert odk_app["managedConfiguration"]["device_id"] == (
            f"{device.app_user_name}-{device.device_id}"
        )

    def test_odk_collect_duplicate_in_applications_skipped(self):
        """An application row whose package_name matches odk_collect_package is
        not duplicated in the output; only the pinned ODK entry appears."""
        policy = PolicyFactory()
        PolicyApplication.objects.create(
            policy=policy,
            package_name=policy.odk_collect_package,
            install_type="FORCE_INSTALLED",
            order=5,
        )
        serializer = PolicySerializer(policy=policy, applications=list(policy.applications.all()))
        result = serializer.to_dict()
        odk_entries = [
            a for a in result["applications"] if a["packageName"] == policy.odk_collect_package
        ]
        assert len(odk_entries) == 1

    def test_merge_variables_exception_on_bad_raw_mdm_device(self):
        """AttributeError accessing hardwareInfo on a non-dict raw_mdm_device is swallowed
        and device.serial_number is still added to the variable map."""
        policy = PolicyFactory()
        device = DeviceFactory(fleet=FleetFactory(policy=policy))
        device.raw_mdm_device = "not-a-dict"  # truthy non-dict → .get() raises AttributeError
        device.save()
        serializer = PolicySerializer(policy=policy, device=device)
        merged = serializer._merge_variables()
        assert "serial_number" in merged
        assert merged["serial_number"] == device.serial_number

    def test_resolve_variables_substitutes_strings_in_list(self):
        """String items inside a list value in the policy dict have $var replaced."""
        policy = PolicyFactory()
        serializer = PolicySerializer(policy=policy)
        obj = {"items": ["hello $name", "world"]}
        serializer._resolve_variables(obj, {"name": "Alice"})
        assert obj["items"][0] == "hello Alice"
        assert obj["items"][1] == "world"

    def test_odk_device_id_template_used_when_set(self):
        """When odk_collect_device_id_template is set, it is used as the device_id
        in the ODK Collect managed configuration (with variable substitution)."""
        fleet = FleetFactory()
        device = DeviceFactory(
            fleet=fleet,
            app_user_name="testuser",
            serial_number="SN-999",
        )
        AppUserFactory(
            name="testuser",
            project=fleet.project,
            qr_code_data=DEFAULT_COLLECT_SETTINGS,
        )
        policy = fleet.policy
        policy.odk_collect_device_id_template = "$serial_number"
        policy.save()
        serializer = PolicySerializer(policy=policy, device=device)
        result = serializer.to_dict()
        odk_app = result["applications"][0]
        assert odk_app["managedConfiguration"]["device_id"] == "SN-999"

    def test_odk_device_id_omitted_when_template_empty(self):
        """When odk_collect_device_id_template is blank, device_id is omitted from managed config."""
        fleet = FleetFactory()
        device = DeviceFactory(fleet=fleet, app_user_name="testuser")
        AppUserFactory(
            name="testuser",
            project=fleet.project,
            qr_code_data=DEFAULT_COLLECT_SETTINGS,
        )
        policy = fleet.policy
        policy.odk_collect_device_id_template = ""
        policy.save()
        serializer = PolicySerializer(policy=policy, device=device)
        result = serializer.to_dict()
        odk_app = result["applications"][0]
        assert "device_id" not in odk_app["managedConfiguration"]
