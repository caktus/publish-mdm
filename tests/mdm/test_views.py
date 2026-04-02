import json

import pytest
from django.urls import reverse

from apps.mdm.models import Policy, PolicyApplication, PolicyVariable
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
class TestPolicyList(PolicyViewBase):
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
class TestPolicyAdd(PolicyViewBase):
    @pytest.fixture
    def url(self, organization):
        return reverse("mdm:policy-add", args=[organization.slug])

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.get(url)
        assert response.status_code == 302

    def test_get(self, client, url, user):
        response = client.get(url)
        assert response.status_code == 200
        assert "form" in response.context

    def test_valid_post_creates_policy_and_redirects(self, client, url, organization):
        response = client.post(url, {"name": "My Policy"})
        assert Policy.objects.filter(organization=organization, name="My Policy").exists()
        policy = Policy.objects.get(organization=organization, name="My Policy")
        # Creates the default ODK Collect application row
        assert policy.applications.filter(order=0).exists()
        assert response.status_code == 302
        assert (
            reverse("mdm:policy-edit", args=[organization.slug, policy.pk]) in response["Location"]
        )

    def test_invalid_post_returns_form(self, client, url, user):
        response = client.post(url, {"name": ""})
        assert response.status_code == 200
        assert response.context["form"].errors


# ---------------------------------------------------------------------------
# policy_edit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicyEdit(PolicyViewBase):
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
class TestPolicyEditPost(PolicyViewBase):
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
# policy_save_managed_config
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicySaveManagedConfig(PolicyViewBase):
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
class TestPolicyEditFormsets(PolicyViewBase):
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


# ---------------------------------------------------------------------------
# _push_policy_to_mdm — Dagster integration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPushPolicyToMdmDagster(PolicyViewBase):
    """Tests that _push_policy_to_mdm() uses Dagster for child-device pushes
    when Dagster is enabled and falls back to synchronous behaviour when not.
    """

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
        settings,
    ):
        """When Dagster is enabled, _push_policy_to_mdm() queues child-device
        config pushes via mdm_job instead of calling push_device_config() synchronously.
        """
        settings.DAGSTER_URL = "http://dagster-host:3000"
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

    def test_sync_fallback_without_dagster(
        self,
        client,
        url,
        user,
        organization,
        policy_with_devices,
        mocker,
        set_mdm_env_vars,
        settings,
    ):
        """When Dagster is disabled, _push_policy_to_mdm() falls back to calling
        push_device_config() synchronously for each child device.
        """
        settings.DAGSTER_URL = ""
        _, devices = policy_with_devices
        mock_mdm = mocker.MagicMock()
        mocker.patch("apps.mdm.views.get_active_mdm_instance", return_value=mock_mdm)
        mock_trigger = mocker.patch("apps.mdm.views.trigger_dagster_job")

        response = client.post(url, self._valid_data())

        assert response.status_code == 302
        mock_trigger.assert_not_called()
        assert mock_mdm.push_device_config.call_count == len(devices)
