import pytest

from apps.mdm.models import (
    DeveloperSettings,
    PasswordQuality,
    PolicyApplication,
    PolicyVariable,
    RequirePasswordUnlock,
)
from apps.mdm.serializers import PolicySerializer
from tests.mdm import TestAllMDMs
from tests.mdm.factories import DeviceFactory, FleetFactory, PolicyFactory
from tests.publish_mdm.factories import OrganizationFactory


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
        """Disabled developer settings should not produce advancedSecurityOverrides."""
        policy = PolicyFactory(
            developer_settings=DeveloperSettings.DEVELOPER_SETTINGS_DISABLED,
        )
        serializer = PolicySerializer(policy=policy)
        result = serializer.to_dict()
        assert "advancedSecurityOverrides" not in result

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

    def test_variable_substitution(self):
        """Variables should be substituted in string values."""
        policy = PolicyFactory()
        org = OrganizationFactory()
        var = PolicyVariable.objects.create(
            key="auth_key", value="secret123", scope="org", org=org
        )
        app = PolicyApplication.objects.create(
            policy=policy,
            package_name="com.example.vpn",
            install_type="FORCE_INSTALLED",
            managed_configuration={"AuthKey": "{{ auth_key }}"},
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
            managed_configuration={"key": "{{ auth_key }}"},
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
                "device_id": "{{ device.imei }}",
                "serial": "{{ device.serial_number }}",
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
            managed_configuration={"key": "{{ unknown_var }}"},
            order=1,
        )
        serializer = PolicySerializer(policy=policy, applications=[app])
        result = serializer.to_dict()
        assert result["applications"][1]["managedConfiguration"]["key"] == "{{ unknown_var }}"
