import base64
import json

import pytest
from django.contrib.messages import SUCCESS, WARNING, Message
from django.urls import reverse, reverse_lazy
from django.utils.timezone import now
from pytest_django.asserts import assertContains, assertMessages, assertRedirects

from apps.mdm.mdms import AndroidEnterprise
from apps.mdm.models import Device, DeviceSnapshot, Policy, PolicyApplication, PolicyVariable
from tests.mdm import TestAllMDMs, TestAndroidEnterpriseOnly, TestTinyMDMOnly
from tests.mdm.factories import (
    DeviceFactory,
    FleetFactory,
    PolicyApplicationFactory,
    PolicyFactory,
)
from tests.publish_mdm.factories import OrganizationFactory, UserFactory


class PolicyViewBase:
    """Base class for policy editor view tests."""

    @pytest.fixture
    def user(self, client):
        user = UserFactory()
        user.save()
        client.force_login(user=user)
        return user

    @pytest.fixture
    def organization(self, user):
        org = OrganizationFactory()
        org.users.add(user)
        return org

    @pytest.fixture
    def policy(self, organization):
        return PolicyFactory(organization=organization)

    @pytest.fixture
    def other_org_policy(self):
        """A policy belonging to a different organization."""
        return PolicyFactory(organization=OrganizationFactory())


# ---------------------------------------------------------------------------
# policy_list
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicyList(PolicyViewBase, TestAllMDMs):
    @pytest.fixture
    def url(self, organization):
        return reverse("mdm:policy-list", args=[organization.slug])

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.get(url)
        assert response.status_code == 302

    def test_lists_org_policies(self, client, url, policy, other_org_policy):
        response = client.get(url)
        assert response.status_code == 200
        assert policy in response.context["policies"]
        assert other_org_policy not in response.context["policies"]


# ---------------------------------------------------------------------------
# policy_add
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicyAddAndroidEnterprise(PolicyViewBase, TestAndroidEnterpriseOnly):
    @pytest.fixture
    def url(self, organization):
        return reverse("mdm:policy-add", args=[organization.slug])

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.get(url)
        assert response.status_code == 302

    def test_get(self, client, url, user, set_mdm_env_vars):
        response = client.get(url)
        assert response.status_code == 200
        assert "form" in response.context

    def test_valid_post_creates_policy_and_redirects(
        self, client, url, user, organization, set_mdm_env_vars, mocker
    ):
        mocker.patch.object(AndroidEnterprise, "create_or_update_policy")
        response = client.post(url, {"name": "My Policy"})
        assert Policy.objects.filter(organization=organization, name="My Policy").exists()
        policy = Policy.objects.get(organization=organization, name="My Policy")
        # Creates the default ODK Collect application row
        assert policy.applications.filter(order=0).exists()
        assert response.status_code == 302
        assert (
            reverse("mdm:policy-edit", args=[organization.slug, policy.pk]) in response["Location"]
        )

    def test_invalid_post_returns_form(self, client, url, user, set_mdm_env_vars):
        response = client.post(url, {"name": ""})
        assert response.status_code == 200
        assert response.context["form"].errors

    def test_requires_configured_mdm(self, client, url, user, organization):
        response = client.get(url, follow=True)
        assertRedirects(response, reverse("mdm:policy-list", args=[organization.slug]))
        assertContains(
            response, "Sorry, cannot create a policy at this time. Please try again later."
        )


# ---------------------------------------------------------------------------
# policy_add (TinyMDM-specific)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicyAddTinyMDM(PolicyViewBase, TestTinyMDMOnly):
    @pytest.fixture
    def url(self, organization):
        return reverse("mdm:policy-add", args=[organization.slug])

    def test_get_includes_policy_id_field(self, client, url, set_mdm_env_vars):
        response = client.get(url)
        assert response.status_code == 200
        assert "policy_id" in response.context["form"].fields
        assert response.context["is_tinymdm"] is True

    def test_valid_post_uses_provided_policy_id(self, client, url, organization, set_mdm_env_vars):
        response = client.post(url, {"name": "My Policy", "policy_id": "tinymdm-123"})
        assert Policy.objects.filter(organization=organization, name="My Policy").exists()
        policy = Policy.objects.get(organization=organization, name="My Policy")
        assert policy.policy_id == "tinymdm-123"
        # No ODK Collect application row for TinyMDM
        assert not policy.applications.filter(order=0).exists()
        assert response.status_code == 302
        # Redirects to the policy list (no additional fields to edit)
        assert reverse("mdm:policy-list", args=[organization.slug]) in response["Location"]

    def test_invalid_post_missing_policy_id(self, client, url, set_mdm_env_vars):
        response = client.post(url, {"name": "My Policy"})
        assert response.status_code == 200
        assert response.context["form"].errors

    def test_requires_configured_mdm(self, client, url, user, organization):
        response = client.get(url, follow=True)
        assertRedirects(response, reverse("mdm:policy-list", args=[organization.slug]))
        assertContains(
            response, "Sorry, cannot create a policy at this time. Please try again later."
        )


# ---------------------------------------------------------------------------
# policy_edit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicyEditAndroidEnterprise(PolicyViewBase, TestAndroidEnterpriseOnly):
    @pytest.fixture
    def url(self, organization, policy):
        return reverse("mdm:policy-edit", args=[organization.slug, policy.pk])

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.get(url)
        assert response.status_code == 302

    def test_get(self, client, url, policy, user):
        response = client.get(url)
        assert response.status_code == 200
        assert response.context["policy"] == policy
        assert "form" in response.context
        assert "app_formset" in response.context
        assert "var_formset" in response.context

    def test_org_isolation(self, client, organization, other_org_policy, user):
        url = reverse("mdm:policy-edit", args=[organization.slug, other_org_policy.pk])
        response = client.get(url)
        assert response.status_code == 404

    def test_configured_badge_shown_for_empty_managed_configuration(self, client, url, policy):
        """The 'Configured' badge is shown even when managed_configuration is {}.

        Regression test: the template previously used
        ``{% if app.managed_configuration %}``, which treated ``{}`` as falsy
        and skipped the badge for an empty-but-present managed configuration.
        """
        PolicyApplicationFactory(policy=policy, order=1, managed_configuration={})
        response = client.get(url)
        assert response.status_code == 200
        assert b"Configured" in response.content


# ---------------------------------------------------------------------------
# policy_edit (POST)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicyEditPostAndroidEnterprise(PolicyViewBase, TestAndroidEnterpriseOnly):
    @pytest.fixture
    def url(self, organization, policy):
        return reverse("mdm:policy-edit", args=[organization.slug, policy.pk])

    def _valid_data(self, app_forms=None, var_forms=None):
        """Build valid POST data for PolicyEditForm + empty formsets."""
        data = {
            "name": "Updated Policy",
            "odk_collect_package": "org.odk.collect.android",
            "odk_collect_device_id_template": "",
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
            # App formset management form
            "apps-TOTAL_FORMS": "1",
            "apps-INITIAL_FORMS": "0",
            "apps-MIN_NUM_FORMS": "0",
            "apps-MAX_NUM_FORMS": "1000",
            # Var formset management form
            "vars-TOTAL_FORMS": "1",
            "vars-INITIAL_FORMS": "0",
            "vars-MIN_NUM_FORMS": "0",
            "vars-MAX_NUM_FORMS": "1000",
        }
        if app_forms:
            data.update(app_forms)
        if var_forms:
            data.update(var_forms)
        return data

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.post(url, self._valid_data())
        assert response.status_code == 302

    def test_valid_post_saves_and_redirects(self, client, url, policy):
        response = client.post(url, self._valid_data())
        assert response.status_code == 302
        policy.refresh_from_db()
        assert policy.name == "Updated Policy"

    def test_invalid_post_returns_form_with_errors(self, client, url, policy):
        data = {
            "name": "",
            "apps-TOTAL_FORMS": "1",
            "apps-INITIAL_FORMS": "0",
            "apps-MIN_NUM_FORMS": "0",
            "apps-MAX_NUM_FORMS": "1000",
            "vars-TOTAL_FORMS": "1",
            "vars-INITIAL_FORMS": "0",
            "vars-MIN_NUM_FORMS": "0",
            "vars-MAX_NUM_FORMS": "1000",
        }
        response = client.post(url, data)
        assert response.status_code == 200
        assert response.context["form"].errors

    def test_org_isolation(self, client, organization, other_org_policy, user):
        url = reverse("mdm:policy-edit", args=[organization.slug, other_org_policy.pk])
        response = client.post(url, self._valid_data())
        assert response.status_code == 404

    def test_kiosk_validation_error_when_app_has_kiosk_install_type(self, client, url, policy):
        """Enabling kiosk_custom_launcher while an app has KIOSK install type is rejected."""
        PolicyApplicationFactory(
            policy=policy, install_type="KIOSK", package_name="com.example.kiosk"
        )
        data = self._valid_data()
        data["kiosk_custom_launcher_enabled"] = "on"
        response = client.post(url, data)
        assert response.status_code == 200
        form = response.context["form"]
        assert form.non_field_errors()
        assert "com.example.kiosk" in str(form.non_field_errors())

    def test_kiosk_launcher_allowed_when_no_kiosk_install_type_apps(self, client, url, policy):
        """Enabling kiosk_custom_launcher is allowed when no apps use KIOSK install type."""
        data = self._valid_data()
        data["kiosk_custom_launcher_enabled"] = "on"
        response = client.post(url, data)
        assert response.status_code == 302
        policy.refresh_from_db()
        assert policy.kiosk_custom_launcher_enabled is True

    def test_odk_collect_app_updated_on_package_name_change(self, client, url, policy):
        """When odk_collect_package changes, the pinned order=0 app row is also updated."""
        pinned = PolicyApplicationFactory(
            policy=policy, order=0, package_name="org.odk.collect.android"
        )
        data = self._valid_data(
            app_forms={
                "apps-TOTAL_FORMS": "2",
                "apps-INITIAL_FORMS": "1",
                "apps-0-id": str(pinned.pk),
                "apps-0-package_name": "org.odk.collect.android",
                "apps-0-install_type": "FORCE_INSTALLED",
            }
        )
        data["odk_collect_package"] = "org.custom.collect"
        response = client.post(url, data)
        assert response.status_code == 302
        pinned.refresh_from_db()
        assert pinned.package_name == "org.custom.collect"


# ---------------------------------------------------------------------------
# policy_edit (TinyMDM-specific)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicyEditTinyMDM(PolicyViewBase, TestTinyMDMOnly):
    @pytest.fixture
    def policy(self, organization):
        return PolicyFactory(organization=organization, policy_id="original-id")

    @pytest.fixture
    def url(self, organization, policy):
        return reverse("mdm:policy-edit", args=[organization.slug, policy.pk])

    def test_get_shows_is_tinymdm_context(self, client, url, policy):
        response = client.get(url)
        assert response.status_code == 200
        assert response.context["is_tinymdm"] is True

    def test_get_form_has_policy_id_field(self, client, url, policy):
        response = client.get(url)
        assert response.status_code == 200
        assert "policy_id" in response.context["form"].fields

    def test_get_no_app_or_var_formsets(self, client, url, policy):
        response = client.get(url)
        assert response.status_code == 200
        assert response.context["app_formset"] is None
        assert response.context["var_formset"] is None

    def test_valid_post_saves_name_and_policy_id(self, client, url, policy):
        response = client.post(url, {"name": "Updated Name", "policy_id": "new-id"})
        assert response.status_code == 302
        policy.refresh_from_db()
        assert policy.name == "Updated Name"
        assert policy.policy_id == "new-id"

    def test_invalid_post_missing_policy_id(self, client, url, policy):
        response = client.post(url, {"name": "Updated Name"})
        assert response.status_code == 200
        assert response.context["form"].errors


# ---------------------------------------------------------------------------
# policy_save_managed_config
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicySaveManagedConfig(PolicyViewBase, TestAndroidEnterpriseOnly):
    @pytest.fixture
    def app(self, policy):
        return PolicyApplicationFactory(policy=policy, order=1)

    @pytest.fixture
    def url(self, organization, policy, app):
        return reverse(
            "mdm:policy-save-managed-config", args=[organization.slug, policy.pk, app.pk]
        )

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.post(url, {"managed_configuration": "{}"})
        assert response.status_code == 302

    def test_valid_json_saves(self, client, url, app):
        response = client.post(url, {"managed_configuration": '{"key": "value"}'})
        assert response.status_code == 200
        app.refresh_from_db()
        assert app.managed_configuration == {"key": "value"}
        assert response.context["saved"] is True
        assert response.context["error"] is None

    def test_invalid_json_returns_error(self, client, url, app):
        response = client.post(url, {"managed_configuration": "not json"})
        assert response.status_code == 200
        assert response.context["error"] is not None
        assert response.context["saved"] is False

    def test_empty_config_clears_field(self, client, url, app):
        app.managed_configuration = {"existing": "data"}
        app.save()
        response = client.post(url, {"managed_configuration": ""})
        assert response.status_code == 200
        app.refresh_from_db()
        assert app.managed_configuration is None
        assert response.context["saved"] is True


# ---------------------------------------------------------------------------
# firmware_snapshot_view
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFirmwareSnapshotView:
    @pytest.fixture
    def url(self):
        return reverse("mdm:firmware_snapshot")

    def test_empty_body_returns_400(self, client, url):
        response = client.post(url, data="", content_type="application/json")
        assert response.status_code == 400

    def test_invalid_json_returns_400(self, client, url):
        response = client.post(url, data="not-json", content_type="application/json")
        assert response.status_code == 400

    def test_invalid_form_data_returns_400(self, client, url):
        response = client.post(url, data="{}", content_type="application/json")
        assert response.status_code == 400

    @pytest.mark.django_db
    def test_valid_data_saves_and_returns_201(self, client, url):
        data = json.dumps({"deviceIdentifier": "SN-VIEW-TEST", "version": "1.0"})
        response = client.post(url, data=data, content_type="application/json")
        assert response.status_code == 201


# ---------------------------------------------------------------------------
# policy_edit — formset tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicyEditFormsets(PolicyViewBase, TestAndroidEnterpriseOnly):
    @pytest.fixture
    def url(self, organization, policy):
        return reverse("mdm:policy-edit", args=[organization.slug, policy.pk])

    @pytest.fixture
    def pinned_app(self, policy):
        return PolicyApplicationFactory(
            policy=policy,
            order=0,
            package_name="org.odk.collect.android",
            install_type="FORCE_INSTALLED",
        )

    @pytest.fixture
    def extra_app(self, policy, pinned_app):
        return PolicyApplicationFactory(
            policy=policy, order=1, package_name="com.example.app", install_type="AVAILABLE"
        )

    def _policy_base_data(self):
        return {
            "name": "My Policy",
            "odk_collect_package": "org.odk.collect.android",
            "odk_collect_device_id_template": "",
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

    def test_edit_app_install_type_via_formset(self, client, url, policy, pinned_app, extra_app):
        data = self._policy_base_data()
        data.update(
            {
                "apps-TOTAL_FORMS": "3",
                "apps-INITIAL_FORMS": "2",
                "apps-0-id": str(pinned_app.pk),
                "apps-0-package_name": "org.odk.collect.android",
                "apps-0-install_type": "FORCE_INSTALLED",
                "apps-1-id": str(extra_app.pk),
                "apps-1-package_name": "com.example.app",
                "apps-1-install_type": "KIOSK",
                "vars-TOTAL_FORMS": "1",
                "vars-INITIAL_FORMS": "0",
                "vars-MIN_NUM_FORMS": "0",
                "vars-MAX_NUM_FORMS": "1000",
            }
        )
        response = client.post(url, data)
        assert response.status_code == 302
        extra_app.refresh_from_db()
        assert extra_app.install_type == "KIOSK"

    def test_add_app_via_formset_extra_row(self, client, url, policy, pinned_app):
        data = self._policy_base_data()
        data.update(
            {
                "apps-TOTAL_FORMS": "2",
                "apps-INITIAL_FORMS": "1",
                "apps-0-id": str(pinned_app.pk),
                "apps-0-package_name": "org.odk.collect.android",
                "apps-0-install_type": "FORCE_INSTALLED",
                "apps-1-id": "",
                "apps-1-package_name": "com.newapp.example",
                "apps-1-install_type": "AVAILABLE",
                "vars-TOTAL_FORMS": "1",
                "vars-INITIAL_FORMS": "0",
                "vars-MIN_NUM_FORMS": "0",
                "vars-MAX_NUM_FORMS": "1000",
            }
        )
        response = client.post(url, data)
        assert response.status_code == 302
        assert policy.applications.filter(package_name="com.newapp.example").exists()

    def test_delete_app_via_formset(self, client, url, policy, pinned_app, extra_app):
        data = self._policy_base_data()
        data.update(
            {
                "apps-TOTAL_FORMS": "3",
                "apps-INITIAL_FORMS": "2",
                "apps-0-id": str(pinned_app.pk),
                "apps-0-package_name": "org.odk.collect.android",
                "apps-0-install_type": "FORCE_INSTALLED",
                "apps-1-id": str(extra_app.pk),
                "apps-1-package_name": "com.example.app",
                "apps-1-install_type": "AVAILABLE",
                "apps-1-DELETE": "on",
                "vars-TOTAL_FORMS": "1",
                "vars-INITIAL_FORMS": "0",
                "vars-MIN_NUM_FORMS": "0",
                "vars-MAX_NUM_FORMS": "1000",
            }
        )
        response = client.post(url, data)
        assert response.status_code == 302
        assert not PolicyApplication.objects.filter(pk=extra_app.pk).exists()

    def test_cannot_delete_pinned_app_via_formset(self, client, url, policy, pinned_app):
        data = self._policy_base_data()
        data.update(
            {
                "apps-TOTAL_FORMS": "2",
                "apps-INITIAL_FORMS": "1",
                "apps-0-id": str(pinned_app.pk),
                "apps-0-package_name": "org.odk.collect.android",
                "apps-0-install_type": "FORCE_INSTALLED",
                "apps-0-DELETE": "on",
                "vars-TOTAL_FORMS": "1",
                "vars-INITIAL_FORMS": "0",
                "vars-MIN_NUM_FORMS": "0",
                "vars-MAX_NUM_FORMS": "1000",
            }
        )
        response = client.post(url, data)
        assert response.status_code == 200
        assert PolicyApplication.objects.filter(pk=pinned_app.pk).exists()
        assert response.context["app_formset"].non_form_errors()

    def test_delete_app_with_order_zero_but_not_pinned_is_allowed(
        self, client, url, policy, pinned_app
    ):
        """Regression: an app whose order happens to be 0 but is not the ODK
        collect app must be deletable (the old code only checked order==0)."""
        non_pinned = PolicyApplicationFactory(
            policy=policy,
            order=0,
            package_name="com.other.app",
            install_type="AVAILABLE",
        )
        data = self._policy_base_data()
        data.update(
            {
                "apps-TOTAL_FORMS": "3",
                "apps-INITIAL_FORMS": "2",
                "apps-0-id": str(pinned_app.pk),
                "apps-0-package_name": "org.odk.collect.android",
                "apps-0-install_type": "FORCE_INSTALLED",
                "apps-1-id": str(non_pinned.pk),
                "apps-1-package_name": "com.other.app",
                "apps-1-install_type": "AVAILABLE",
                "apps-1-DELETE": "on",
                "vars-TOTAL_FORMS": "1",
                "vars-INITIAL_FORMS": "0",
                "vars-MIN_NUM_FORMS": "0",
                "vars-MAX_NUM_FORMS": "1000",
            }
        )
        response = client.post(url, data)
        assert response.status_code == 302
        assert not PolicyApplication.objects.filter(pk=non_pinned.pk).exists()

    def test_new_app_added_via_formset_gets_positive_order(self, client, url, policy, pinned_app):
        """Apps added through the formset extra row should get order > 0."""
        data = self._policy_base_data()
        data.update(
            {
                "apps-TOTAL_FORMS": "2",
                "apps-INITIAL_FORMS": "1",
                "apps-0-id": str(pinned_app.pk),
                "apps-0-package_name": "org.odk.collect.android",
                "apps-0-install_type": "FORCE_INSTALLED",
                "apps-1-id": "",
                "apps-1-package_name": "com.brand.new",
                "apps-1-install_type": "AVAILABLE",
                "vars-TOTAL_FORMS": "1",
                "vars-INITIAL_FORMS": "0",
                "vars-MIN_NUM_FORMS": "0",
                "vars-MAX_NUM_FORMS": "1000",
            }
        )
        response = client.post(url, data)
        assert response.status_code == 302
        new_app = policy.applications.get(package_name="com.brand.new")
        assert new_app.order > 0

    def test_variable_scope_change_clears_stale_policy_or_fleet(
        self, client, url, organization, policy, pinned_app
    ):
        """A new fleet-scoped variable saves with policy=None (not a stale policy reference).

        Regression test: the old code set stale FKs on variables with the wrong scope.
        """
        fleet = FleetFactory(policy=policy, organization=organization)
        data = self._policy_base_data()
        data.update(
            {
                "apps-TOTAL_FORMS": "2",
                "apps-INITIAL_FORMS": "1",
                "apps-0-id": str(pinned_app.pk),
                "apps-0-package_name": "org.odk.collect.android",
                "apps-0-install_type": "FORCE_INSTALLED",
                # New fleet-scoped variable (no id → new instance)
                "vars-TOTAL_FORMS": "1",
                "vars-INITIAL_FORMS": "0",
                "vars-MIN_NUM_FORMS": "0",
                "vars-MAX_NUM_FORMS": "1000",
                "vars-0-id": "",
                "vars-0-key": "api_token",
                "vars-0-value": "secret",
                "vars-0-scope": "fleet",
                "vars-0-fleet": str(fleet.pk),
            }
        )
        response = client.post(url, data)
        assert response.status_code == 302
        var = PolicyVariable.objects.get(key="api_token", fleet=fleet)
        assert var.scope == "fleet"
        # policy must NOT be set on fleet-scoped variables
        assert var.policy is None


@pytest.mark.django_db
class TestAmapiNotificationsView(TestAndroidEnterpriseOnly):
    """Tests for the AMAPI Pub/Sub push notification endpoint."""

    TOKEN = "test-pubsub-token-secret"
    URL = reverse_lazy("mdm:amapi_notifications")

    @staticmethod
    def build_pubsub_body(device_data: dict, notification_type: str = "ENROLLMENT") -> dict:
        """Build a minimal Pub/Sub push notification body."""
        encoded = base64.b64encode(json.dumps(device_data).encode()).decode()
        return {
            "message": {
                "attributes": {"notificationType": notification_type},
                "data": encoded,
                "messageId": "1234567890",
                "publishTime": "2024-01-01T00:00:00Z",
            },
            "subscription": "projects/test/subscriptions/amapi-sub",
        }

    @pytest.fixture(autouse=True)
    def set_pubsub_token(self, settings):
        """Set ANDROID_ENTERPRISE_PUBSUB_TOKEN for all tests in this class."""
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = self.TOKEN

    @pytest.fixture(autouse=True)
    def set_enterprise_env(self, set_mdm_env_vars):
        """Ensure ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE env var is set."""

    def post(self, client, body, token=TOKEN):
        url = self.URL
        if token:
            url = f"{url}?token={token}"
        return client.post(
            url,
            data=json.dumps(body),
            content_type="application/json",
        )

    @pytest.fixture
    def mock_notification_handler(self, mocker):
        return mocker.patch.object(AndroidEnterprise, "handle_device_notification")

    def test_missing_token_setting_rejects_all_requests(
        self, client, settings, mock_notification_handler
    ):
        """When ANDROID_ENTERPRISE_PUBSUB_TOKEN is not set, all requests are rejected."""
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = None
        body = self.build_pubsub_body({"name": "enterprises/test/devices/abc"})
        response = self.post(client, body)
        assert response.status_code == 403
        mock_notification_handler.assert_not_called()

    def test_valid_token_accepted(self, client, mock_notification_handler):
        """A request with the correct token is accepted."""
        body = self.build_pubsub_body({"name": "enterprises/test/devices/abc"})
        response = self.post(client, body, token=self.TOKEN)
        assert response.status_code == 204
        mock_notification_handler.assert_called_once()

    def test_valid_request_with_different_enterprise_name(self, client, mock_notification_handler):
        """A valid enrollment notification is not handled if it's for a different
        enterprise from the currently configured one.
        """
        body = self.build_pubsub_body({"name": "enterprises/different/devices/abc"})
        response = self.post(client, body, token=self.TOKEN)
        assert response.status_code == 204
        mock_notification_handler.assert_not_called()

    def test_valid_request_with_different_mdm(self, client, settings, mock_notification_handler):
        """A valid enrollment notification is not handled if Android Enterprise is
        not the currently configured MDM.
        """
        settings.ACTIVE_MDM = {"name": "TinyMDM", "class": "apps.mdm.mdms.TinyMDM"}
        body = self.build_pubsub_body({"name": "enterprises/test/devices/abc"})
        response = self.post(client, body, token=self.TOKEN)
        assert response.status_code == 204
        mock_notification_handler.assert_not_called()

    def test_invalid_token_rejected(self, client, mock_notification_handler):
        """A request with an incorrect token is rejected with 403."""
        body = self.build_pubsub_body({"name": "enterprises/test/devices/abc"})
        response = self.post(client, body, token="wrong")
        assert response.status_code == 403
        mock_notification_handler.assert_not_called()

    def test_missing_token_rejected(self, client, mock_notification_handler):
        """A request without a token is rejected with 403."""
        body = self.build_pubsub_body({"name": "enterprises/test/devices/abc"})
        response = self.post(client, body, token=None)
        assert response.status_code == 403
        mock_notification_handler.assert_not_called()

    def test_empty_body_returns_400(self, client, mock_notification_handler):
        response = client.post(
            f"{self.URL}?token={self.TOKEN}", data="", content_type="application/json"
        )
        assert response.status_code == 400
        mock_notification_handler.assert_not_called()

    def test_invalid_json_returns_400(self, client, mock_notification_handler):
        response = client.post(
            f"{self.URL}?token={self.TOKEN}", data="not-json", content_type="application/json"
        )
        assert response.status_code == 400
        mock_notification_handler.assert_not_called()

    def test_missing_data_field_returns_204(self, client, mock_notification_handler):
        """A message without a data payload is accepted (acknowledged) silently."""
        body = {
            "message": {
                "attributes": {"notificationType": "ENROLLMENT"},
                "messageId": "1",
            },
            "subscription": "projects/test/subscriptions/sub",
        }
        response = self.post(client, body)
        assert response.status_code == 204
        mock_notification_handler.assert_not_called()

    def test_invalid_base64_data_returns_400(self, client, mock_notification_handler):
        body = {
            "message": {
                "attributes": {"notificationType": "ENROLLMENT"},
                "data": "!!!not-valid-base64!!!",
                "messageId": "1",
            },
            "subscription": "projects/test/subscriptions/sub",
        }
        response = self.post(client, body)
        assert response.status_code == 400
        mock_notification_handler.assert_not_called()

    def test_unknown_notification_type_returns_204(self, client, mock_notification_handler):
        """An unknown notification type is acknowledged without processing."""
        body = self.build_pubsub_body(
            {"name": "enterprises/test/devices/abc"}, notification_type="COMMAND"
        )
        response = self.post(client, body)
        assert response.status_code == 204
        mock_notification_handler.assert_not_called()

    def test_enrollment_creates_new_device(self, client):
        """An ENROLLMENT notification for a new device creates a Device record."""
        fleet = FleetFactory()
        device_data = {
            "name": "enterprises/test/devices/newdevice1",
            "state": "ACTIVE",
            "enrollmentTokenData": json.dumps({"fleet": fleet.pk}),
            "hardwareInfo": {"serialNumber": "SN-NEW-001", "manufacturer": "Acme"},
        }
        body = self.build_pubsub_body(device_data, "ENROLLMENT")
        response = self.post(client, body)
        assert response.status_code == 204
        device = Device.objects.get(device_id="newdevice1")
        assert device.fleet == fleet
        assert device.serial_number == "SN-NEW-001"
        assert device.name == device_data["name"]

    def test_enrollment_updates_existing_device(self, client):
        """An ENROLLMENT notification for an existing device updates it."""
        fleet = FleetFactory()
        device = DeviceFactory(fleet=fleet, device_id="existingdev1", serial_number="OLD-SN")
        device_data = {
            "name": "enterprises/test/devices/existingdev1",
            "state": "ACTIVE",
            "enrollmentTokenData": json.dumps({"fleet": fleet.pk}),
            "hardwareInfo": {"serialNumber": "NEW-SN", "manufacturer": "Acme"},
        }
        body = self.build_pubsub_body(device_data, "ENROLLMENT")
        response = self.post(client, body)
        assert response.status_code == 204
        device.refresh_from_db()
        assert device.serial_number == "NEW-SN"

    def test_enrollment_without_fleet_data_skips_creation(self, client):
        """An ENROLLMENT notification without fleet info does not create a device."""
        initial_count = Device.objects.count()
        device_data = {
            "name": "enterprises/test/devices/orphandevice",
            "state": "ACTIVE",
            # No enrollmentTokenData
        }
        body = self.build_pubsub_body(device_data, "ENROLLMENT")
        response = self.post(client, body)
        assert response.status_code == 204
        assert Device.objects.count() == initial_count

    def test_status_report_updates_existing_device(self, client):
        """A STATUS_REPORT notification updates the device and creates a snapshot."""
        fleet = FleetFactory()
        device = DeviceFactory(fleet=fleet, device_id="statusdev1", serial_number="OLD-SN")
        policy_sync_time = now()
        device_data = {
            "name": "enterprises/test/devices/statusdev1",
            "state": "ACTIVE",
            "managementMode": "DEVICE_OWNER",
            "lastPolicySyncTime": policy_sync_time.isoformat(),
            "hardwareInfo": {"serialNumber": "STATUS-SN", "manufacturer": "Acme"},
        }
        body = self.build_pubsub_body(device_data, "STATUS_REPORT")
        snapshot_count_before = DeviceSnapshot.objects.count()
        response = self.post(client, body)
        assert response.status_code == 204
        device.refresh_from_db()
        assert device.serial_number == "STATUS-SN"
        assert device.raw_mdm_device == device_data
        assert DeviceSnapshot.objects.count() == snapshot_count_before + 1
        latest_snapshot = DeviceSnapshot.objects.latest("synced_at")
        assert latest_snapshot.last_sync == policy_sync_time

    def test_status_report_for_unknown_device_returns_204(self, client):
        """A STATUS_REPORT for a device not in our DB is acknowledged silently."""
        device_data = {
            "name": "enterprises/test/devices/unknowndev",
            "state": "ACTIVE",
            "managementMode": "DEVICE_OWNER",
            "lastPolicySyncTime": "2024-01-01T12:00:00Z",
            "hardwareInfo": {"serialNumber": "UNK-SN", "manufacturer": "Acme"},
        }
        body = self.build_pubsub_body(device_data, "STATUS_REPORT")
        response = self.post(client, body)
        assert response.status_code == 204

    def test_status_report_pushes_config_on_provisioning_to_active(self, client, mocker):
        """STATUS_REPORT PROVISIONING→ACTIVE calls push_device_config for a device
        with an app_user_name that doesn't yet have a device-specific policy."""
        mock_push = mocker.patch.object(AndroidEnterprise, "push_device_config")
        fleet = FleetFactory()
        device = DeviceFactory(
            fleet=fleet,
            device_id="provdev",
            app_user_name="user1",
            raw_mdm_device={
                "name": "enterprises/test/devices/provdev",
                "state": "PROVISIONING",
                "policyName": "enterprises/test/policies/default",
            },
        )
        device_data = {
            "name": "enterprises/test/devices/provdev",
            "state": "ACTIVE",
            "policyName": "enterprises/test/policies/default",
            "hardwareInfo": {"serialNumber": "PROV-SN"},
        }
        body = self.build_pubsub_body(device_data, "STATUS_REPORT")
        response = self.post(client, body)
        assert response.status_code == 204
        mock_push.assert_called_once_with(device)

    def test_status_report_no_snapshot_without_sufficient_data(self, client):
        """A STATUS_REPORT lacking lastPolicySyncTime does not create a DeviceSnapshot."""
        fleet = FleetFactory()
        DeviceFactory(fleet=fleet, device_id="nosnapdev")
        device_data = {
            "name": "enterprises/test/devices/nosnapdev",
            "state": "ACTIVE",
            "hardwareInfo": {"serialNumber": "NOSNAP-SN"},
        }
        body = self.build_pubsub_body(device_data, "STATUS_REPORT")
        before = DeviceSnapshot.objects.count()
        response = self.post(client, body)
        assert response.status_code == 204
        assert DeviceSnapshot.objects.count() == before


# ---------------------------------------------------------------------------
# _push_policy_to_mdm — Dagster integration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPushPolicyToMdmDagster(PolicyViewBase, TestAndroidEnterpriseOnly):
    """Tests that _push_policy_to_mdm() uses Dagster for child-device pushes."""

    @pytest.fixture
    def policy_with_devices(self, organization):
        policy = PolicyFactory(organization=organization)
        fleet = FleetFactory(policy=policy)
        devices = []
        for device in DeviceFactory.build_batch(2, fleet=fleet):
            device.raw_mdm_device = {
                "policyName": f"enterprises/test/policies/fleet{fleet.id}_{device.device_id}"
            }
            device.save()
            devices.append(device)
        return policy, devices

    @pytest.fixture
    def url(self, organization, policy_with_devices):
        policy, _ = policy_with_devices
        return reverse("mdm:policy-edit", args=[organization.slug, policy.pk])

    def _valid_data(self):
        return {
            "name": "Test Policy",
            "odk_collect_package": "org.odk.collect.android",
            "odk_collect_device_id_template": "",
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
            "apps-TOTAL_FORMS": "0",
            "apps-INITIAL_FORMS": "0",
            "vars-TOTAL_FORMS": "1",
            "vars-INITIAL_FORMS": "0",
            "vars-MIN_NUM_FORMS": "0",
            "vars-MAX_NUM_FORMS": "1000",
        }

    def test_dagster_triggered_for_child_devices(
        self,
        client,
        url,
        user,
        organization,
        policy_with_devices,
        mocker,
        set_mdm_env_vars,
    ):
        """_push_policy_to_mdm() queues child-device config pushes via Dagster mdm_job."""
        _, devices = policy_with_devices
        mock_push = mocker.patch("apps.mdm.views.get_active_mdm_instance")
        mock_trigger = mocker.patch("apps.mdm.views.trigger_dagster_job")

        response = client.post(url, self._valid_data())

        assert response.status_code == 302
        mock_trigger.assert_called_once()
        call_kwargs = mock_trigger.call_args
        assert call_kwargs.kwargs["job_name"] == "mdm_job"
        device_pks = call_kwargs.kwargs["run_config"]["ops"]["push_mdm_device_config"]["config"][
            "device_pks"
        ]
        assert set(device_pks) == {d.pk for d in devices}
        mock_push.return_value.push_device_config.assert_not_called()

    def test_dagster_exception_is_swallowed(
        self,
        client,
        url,
        user,
        organization,
        policy_with_devices,
        mocker,
        set_mdm_env_vars,
        caplog,
    ):
        """_push_policy_to_mdm() logs and swallows a trigger_dagster_job exception without
        interrupting the view response.
        """
        mocker.patch("apps.mdm.views.get_active_mdm_instance")
        mock_trigger = mocker.patch(
            "apps.mdm.views.trigger_dagster_job",
            side_effect=Exception("Dagster unavailable"),
        )

        response = client.post(url, self._valid_data())

        assert response.status_code == 302
        mock_trigger.assert_called_once()
        assert any(
            "Failed to trigger Dagster mdm_job for child policies" in r.message
            for r in caplog.records
            if r.name == "apps.mdm.views" and r.levelname == "ERROR"
        )
        assertMessages(
            response,
            [
                Message(SUCCESS, "Policy saved."),
                Message(
                    WARNING,
                    "Your policy has been saved, but we encountered an issue syncing it to your devices. "
                    "Please try saving again, or contact support if the problem continues.",
                ),
            ],
        )
