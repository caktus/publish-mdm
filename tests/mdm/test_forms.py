import pytest

from apps.mdm.forms import (
    FirmwareSnapshotForm,
    PolicyApplicationAddForm,
    PolicyEditForm,
    PolicyVariableForm,
)
from apps.mdm.models import Policy, PolicyVariable
from tests.mdm.factories import DeviceFactory, PolicyApplicationFactory, PolicyFactory
from tests.publish_mdm.factories import OrganizationFactory


class TestFirmwareSnapshotForm:
    def test_post_request_initialization(self):
        json_data = {"version": "unknown", "deviceIdentifier": "12345"}
        form = FirmwareSnapshotForm(json_data=json_data)
        assert form.is_valid(), form.errors
        assert form.data["serial_number"] == "12345"

    @pytest.mark.django_db
    def test_save_with_existing_device(self):
        device = DeviceFactory(
            serial_number="12345", raw_mdm_device={"user_id": "123", "nickname": "test"}
        )
        json_data = {"serialNumber": "12345", "version": "1.0.0"}
        form = FirmwareSnapshotForm(json_data=json_data)
        form.is_valid()
        instance = form.save()
        assert instance.device == device

    @pytest.mark.django_db
    def test_save_without_existing_device(self):
        json_data = {"serialNumber": "12345", "version": "1.0.0"}
        form = FirmwareSnapshotForm(json_data=json_data)
        form.is_valid()
        instance = form.save()
        assert instance.device is None

    @pytest.mark.django_db
    def test_empty_post_doesnt_save(self):
        form = FirmwareSnapshotForm(json_data={})
        assert form.is_valid() is False


@pytest.mark.django_db
class TestFirmwareSnapshotFormVersionExtraction:
    def test_version_with_brackets_stripped(self):
        """clean() strips brackets from ro.product.version when present."""
        data = {
            "deviceIdentifier": "SN12345",
            "buildInfo": {"buildPropContent": {"[ro.product.version]": "[1.2.3]"}},
            "versionInfo": {},
        }
        form = FirmwareSnapshotForm(json_data=data)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["version"] == "1.2.3"

    def test_version_from_alternatives_when_build_info_empty(self):
        """clean() falls back to versionInfo.alternatives[0] when buildInfo has no version."""
        data = {
            "deviceIdentifier": "SN12345",
            "buildInfo": {"buildPropContent": {}},
            "versionInfo": {"alternatives": ["2.0.0", "1.9.9"]},
        }
        form = FirmwareSnapshotForm(json_data=data)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["version"] == "2.0.0"


@pytest.mark.django_db
class TestPolicyApplicationAddForm:
    def test_valid_new_application(self):
        policy = PolicyFactory()
        form = PolicyApplicationAddForm({"package_name": "com.example.app"}, policy=policy)
        assert form.is_valid(), form.errors

    def test_duplicate_package_name_raises_validation_error(self):
        policy = PolicyFactory()
        PolicyApplicationFactory(policy=policy, package_name="com.example.app")
        form = PolicyApplicationAddForm({"package_name": "com.example.app"}, policy=policy)
        assert not form.is_valid()
        assert "package_name" in form.errors
        assert "already exists" in form.errors["package_name"][0]

    def test_duplicate_allowed_for_different_policy(self):
        policy1 = PolicyFactory()
        policy2 = PolicyFactory()
        PolicyApplicationFactory(policy=policy1, package_name="com.example.app")
        form = PolicyApplicationAddForm({"package_name": "com.example.app"}, policy=policy2)
        assert form.is_valid(), form.errors

    def test_no_policy_skips_duplicate_check(self):
        """Without a policy, the duplicate check is skipped."""
        form = PolicyApplicationAddForm({"package_name": "com.example.app"})
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestPolicyEditForm:
    def _base_data(self):
        return {
            "name": "Test Policy",
            "odk_collect_package": "org.odk.collect.android",
            "device_password_quality": "PASSWORD_QUALITY_UNSPECIFIED",
            "device_password_min_length": "",
            "device_password_require_unlock": "REQUIRE_PASSWORD_UNLOCK_UNSPECIFIED",
            "work_password_quality": "PASSWORD_QUALITY_UNSPECIFIED",
            "work_password_min_length": "",
            "work_password_require_unlock": "REQUIRE_PASSWORD_UNLOCK_UNSPECIFIED",
            "vpn_package_name": "",
            "kiosk_power_button_actions": "POWER_BUTTON_ACTIONS_UNSPECIFIED",
            "kiosk_system_error_warnings": "SYSTEM_ERROR_WARNINGS_UNSPECIFIED",
            "kiosk_system_navigation": "SYSTEM_NAVIGATION_UNSPECIFIED",
            "kiosk_status_bar": "STATUS_BAR_UNSPECIFIED",
            "kiosk_device_settings": "DEVICE_SETTINGS_UNSPECIFIED",
            "developer_settings": "DEVELOPER_SETTINGS_DISABLED",
        }

    def test_valid_data_is_valid(self):
        policy = PolicyFactory()
        form = PolicyEditForm(self._base_data(), instance=policy)
        assert form.is_valid(), form.errors

    def test_kiosk_custom_launcher_blocked_when_kiosk_install_type_app_exists(self):
        policy = PolicyFactory()
        PolicyApplicationFactory(
            policy=policy, install_type="KIOSK", package_name="com.example.kiosk"
        )
        data = {**self._base_data(), "kiosk_custom_launcher_enabled": True}
        form = PolicyEditForm(data, instance=policy)
        assert not form.is_valid()
        assert form.non_field_errors()
        assert "com.example.kiosk" in str(form.non_field_errors())

    def test_kiosk_custom_launcher_allowed_when_no_kiosk_install_type_apps(self):
        policy = PolicyFactory()
        data = {**self._base_data(), "kiosk_custom_launcher_enabled": True}
        form = PolicyEditForm(data, instance=policy)
        assert form.is_valid(), form.errors

    def test_kiosk_custom_launcher_allowed_for_new_policy_without_pk(self):
        """New policies (no pk yet) skip the kiosk app check."""
        policy = PolicyFactory()
        PolicyApplicationFactory(policy=policy, install_type="KIOSK")
        # Simulate a new (unsaved) policy instance
        new_policy = Policy(name="New", mdm="Android Enterprise")
        data = {**self._base_data(), "kiosk_custom_launcher_enabled": True}
        form = PolicyEditForm(data, instance=new_policy)
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestPolicyVariableForm:
    """Tests for PolicyVariableForm.clean() duplicate-key validation."""

    def test_org_duplicate_key_caught_when_instance_org_is_none(self):
        """Duplicate org-scoped key should raise ValidationError even when the instance.org
        is None (e.g., when changing a fleet-scoped variable to org-scoped).

        Regression: previously used self.instance.org which can be None in this case,
        causing the duplicate check to be silently skipped.
        """
        org = OrganizationFactory()
        # Create an existing org-scoped variable
        PolicyVariable.objects.create(key="my_key", value="existing", scope="org", org=org)

        # Try to create another with the same key using the form
        # instance has org=None (simulating a fleet-scoped var being changed to org)
        instance = PolicyVariable(key="my_key", value="new", scope="fleet", fleet=None, org=None)
        form = PolicyVariableForm(
            data={"key": "my_key", "value": "new", "scope": "org", "fleet": ""},
            instance=instance,
            organization=org,
        )
        assert not form.is_valid()
        assert any("my_key" in str(e) for e in form.non_field_errors())
