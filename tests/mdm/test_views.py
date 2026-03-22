import pytest
from django.urls import reverse

from apps.mdm.models import Policy, PolicyApplication, PolicyVariable
from tests.mdm.factories import (
    FleetFactory,
    PolicyApplicationFactory,
    PolicyFactory,
    PolicyVariableFactory,
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

    def test_get(self, client, url, user):
        response = client.get(url)
        assert response.status_code == 200

    def test_org_isolation(self, client, organization, other_org_policy, user):
        url = reverse("mdm:policy-edit", args=[organization.slug, other_org_policy.pk])
        response = client.get(url)
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# policy_save_name
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicySaveName(PolicyViewBase):
    @pytest.fixture
    def url(self, organization, policy):
        return reverse("mdm:policy-save-name", args=[organization.slug, policy.pk])

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.post(url, {"name": "New Name"})
        assert response.status_code == 302

    def test_valid_post_saves_and_returns_partial(self, client, url, policy):
        response = client.post(url, {"name": "New Name"})
        assert response.status_code == 200
        policy.refresh_from_db()
        assert policy.name == "New Name"
        assert response.context["saved"] is True

    def test_invalid_post_returns_form_errors(self, client, url, policy):
        response = client.post(url, {"name": ""})
        assert response.status_code == 200
        assert response.context["name_form"].errors

    def test_org_isolation(self, client, organization, other_org_policy, user):
        url = reverse("mdm:policy-save-name", args=[organization.slug, other_org_policy.pk])
        response = client.post(url, {"name": "Hack"})
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# policy_save_odk_package
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicySaveOdkPackage(PolicyViewBase):
    @pytest.fixture
    def url(self, organization, policy):
        return reverse("mdm:policy-save-odk-package", args=[organization.slug, policy.pk])

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.post(url, {"odk_collect_package": "org.odk.collect.android"})
        assert response.status_code == 302

    def test_valid_post_saves_and_updates_pinned_app(self, client, url, policy):
        pinned = PolicyApplicationFactory(policy=policy, order=0)
        response = client.post(url, {"odk_collect_package": "org.custom.collect"})
        assert response.status_code == 200
        policy.refresh_from_db()
        pinned.refresh_from_db()
        assert policy.odk_collect_package == "org.custom.collect"
        assert pinned.package_name == "org.custom.collect"
        assert response.context["odk_package_saved"] is True


# ---------------------------------------------------------------------------
# policy_add_application
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicyAddApplication(PolicyViewBase):
    @pytest.fixture
    def url(self, organization, policy):
        return reverse("mdm:policy-add-application", args=[organization.slug, policy.pk])

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.post(url, {"package_name": "com.example.app"})
        assert response.status_code == 302

    def test_valid_post_adds_app(self, client, url, policy):
        count_before = policy.applications.count()
        response = client.post(url, {"package_name": "com.new.app"})
        assert response.status_code == 200
        assert policy.applications.count() == count_before + 1
        assert response.context["saved"] is True

    def test_invalid_post_returns_form_errors(self, client, url, policy):
        response = client.post(url, {"package_name": ""})
        assert response.status_code == 200
        assert response.context["add_app_form"].errors


# ---------------------------------------------------------------------------
# policy_save_application
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicySaveApplication(PolicyViewBase):
    @pytest.fixture
    def app(self, policy):
        return PolicyApplicationFactory(policy=policy, order=1)

    @pytest.fixture
    def url(self, organization, policy, app):
        return reverse("mdm:policy-save-application", args=[organization.slug, policy.pk, app.pk])

    def test_login_required(self, client, url, user, app):
        client.logout()
        response = client.post(url, {f"app_{app.pk}-package_name": app.package_name})
        assert response.status_code == 302

    def test_valid_post_saves_app(self, client, url, policy, app):
        data = {
            f"app_{app.pk}-package_name": app.package_name,
            f"app_{app.pk}-install_type": "AVAILABLE",
            f"app_{app.pk}-disabled": False,
        }
        response = client.post(url, data)
        assert response.status_code == 200
        app.refresh_from_db()
        assert app.install_type == "AVAILABLE"
        assert response.context["saved"] is True

    def test_org_isolation(self, client, organization, other_org_policy, user):
        other_app = PolicyApplicationFactory(policy=other_org_policy)
        url = reverse(
            "mdm:policy-save-application",
            args=[organization.slug, other_org_policy.pk, other_app.pk],
        )
        response = client.post(url, {f"app_{other_app.pk}-package_name": "x"})
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# policy_delete_application
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicyDeleteApplication(PolicyViewBase):
    @pytest.fixture
    def app(self, policy):
        return PolicyApplicationFactory(policy=policy, order=1)

    @pytest.fixture
    def url(self, organization, policy, app):
        return reverse("mdm:policy-delete-application", args=[organization.slug, policy.pk, app.pk])

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.post(url)
        assert response.status_code == 302

    def test_deletes_app(self, client, url, policy, app):
        response = client.post(url)
        assert response.status_code == 200
        assert not PolicyApplication.objects.filter(pk=app.pk).exists()

    def test_cannot_delete_pinned_odk_collect_row(self, client, organization, policy):
        pinned = PolicyApplicationFactory(
            policy=policy, package_name=policy.odk_collect_package, order=0
        )
        url = reverse(
            "mdm:policy-delete-application",
            args=[organization.slug, policy.pk, pinned.pk],
        )
        response = client.post(url)
        assert response.status_code == 403
        assert PolicyApplication.objects.filter(pk=pinned.pk).exists()


# ---------------------------------------------------------------------------
# policy_save_password
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicySavePassword(PolicyViewBase):
    @pytest.fixture
    def url(self, organization, policy):
        return reverse("mdm:policy-save-password", args=[organization.slug, policy.pk])

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.post(url, {})
        assert response.status_code == 302

    def test_valid_post_saves(self, client, url, policy):
        data = {
            "device_password_quality": "NUMERIC",
            "device_password_min_length": "6",
            "device_password_require_unlock": "REQUIRE_PASSWORD_UNLOCK_UNSPECIFIED",
            "work_password_quality": "PASSWORD_QUALITY_UNSPECIFIED",
            "work_password_min_length": "",
            "work_password_require_unlock": "REQUIRE_PASSWORD_UNLOCK_UNSPECIFIED",
        }
        response = client.post(url, data)
        assert response.status_code == 200
        policy.refresh_from_db()
        assert policy.device_password_quality == "NUMERIC"
        assert response.context["saved"] is True


# ---------------------------------------------------------------------------
# policy_save_vpn
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicySaveVPN(PolicyViewBase):
    @pytest.fixture
    def url(self, organization, policy):
        return reverse("mdm:policy-save-vpn", args=[organization.slug, policy.pk])

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.post(url, {})
        assert response.status_code == 302

    def test_valid_post_saves(self, client, url, policy):
        data = {"vpn_package_name": "com.tailscale.ipn", "vpn_lockdown": False}
        response = client.post(url, data)
        assert response.status_code == 200
        policy.refresh_from_db()
        assert policy.vpn_package_name == "com.tailscale.ipn"
        assert response.context["saved"] is True


# ---------------------------------------------------------------------------
# policy_save_developer
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicySaveDeveloper(PolicyViewBase):
    @pytest.fixture
    def url(self, organization, policy):
        return reverse("mdm:policy-save-developer", args=[organization.slug, policy.pk])

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.post(url, {})
        assert response.status_code == 302

    def test_valid_post_saves(self, client, url, policy):
        data = {"developer_settings": "DEVELOPER_SETTINGS_ALLOWED"}
        response = client.post(url, data)
        assert response.status_code == 200
        policy.refresh_from_db()
        assert policy.developer_settings == "DEVELOPER_SETTINGS_ALLOWED"
        assert response.context["saved"] is True


# ---------------------------------------------------------------------------
# policy_save_kiosk
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicySaveKiosk(PolicyViewBase):
    @pytest.fixture
    def url(self, organization, policy):
        return reverse("mdm:policy-save-kiosk", args=[organization.slug, policy.pk])

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.post(url, {})
        assert response.status_code == 302

    def test_valid_post_saves(self, client, url, policy):
        data = {
            "kiosk_power_button_actions": "POWER_BUTTON_AVAILABLE",
            "kiosk_system_error_warnings": "ERROR_AND_WARNINGS_MUTED",
            "kiosk_system_navigation": "NAVIGATION_DISABLED",
            "kiosk_status_bar": "NOTIFICATIONS_AND_SYSTEM_INFO_DISABLED",
            "kiosk_device_settings": "SETTINGS_ACCESS_BLOCKED",
        }
        response = client.post(url, data)
        assert response.status_code == 200
        policy.refresh_from_db()
        assert policy.kiosk_system_navigation == "NAVIGATION_DISABLED"
        assert response.context["saved"] is True


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
# policy_add_variable
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicyAddVariable(PolicyViewBase):
    @pytest.fixture
    def url(self, organization, policy):
        return reverse("mdm:policy-add-variable", args=[organization.slug, policy.pk])

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.post(url, {})
        assert response.status_code == 302

    def test_valid_post_creates_variable(self, client, url, policy, organization):
        data = {"key": "my_var", "value": "my_value", "scope": "org"}
        response = client.post(url, data)
        assert response.status_code == 200
        assert PolicyVariable.objects.filter(key="my_var", org=organization).exists()
        assert response.context["saved"] is True

    def test_invalid_post_returns_form_errors(self, client, url, policy):
        response = client.post(url, {"key": "", "value": "", "scope": "org"})
        assert response.status_code == 200
        assert response.context["variable_form"].errors

    def test_org_is_pre_set_on_form_instance(self, client, url, policy, organization):
        """org is pre-set before is_valid() so model.clean() finds the org."""
        data = {"key": "scoped_var", "value": "val", "scope": "org"}
        response = client.post(url, data)
        assert response.status_code == 200
        var = PolicyVariable.objects.get(key="scoped_var")
        assert var.org == organization

    def test_duplicate_policy_variable_raises_form_error(self, client, url, policy, organization):
        """Submitting a duplicate policy-level variable key shows a friendly form error."""
        PolicyVariableFactory(key="dup_key", org=organization, scope="org")
        data = {"key": "dup_key", "value": "other_val", "scope": "org"}
        response = client.post(url, data)
        assert response.status_code == 200
        form = response.context["variable_form"]
        assert form.errors
        assert "dup_key" in str(form.errors)
        assert PolicyVariable.objects.filter(key="dup_key", org=organization).count() == 1

    def test_duplicate_fleet_variable_raises_form_error(self, client, url, policy, organization):
        """Submitting a duplicate fleet-level variable key for the same fleet shows a friendly form error."""
        fleet = FleetFactory(organization=organization, policy=policy)
        PolicyVariableFactory(key="fleet_dup", fleet=fleet, org=None, scope="fleet")
        data = {"key": "fleet_dup", "value": "other_val", "scope": "fleet", "fleet": fleet.pk}
        response = client.post(url, data)
        assert response.status_code == 200
        form = response.context["variable_form"]
        assert form.errors
        assert "fleet_dup" in str(form.errors)
        assert PolicyVariable.objects.filter(key="fleet_dup", fleet=fleet).count() == 1

    def test_same_key_different_scope_is_allowed(self, client, url, policy, organization):
        """A key can exist as both policy-level and fleet-level — they are independent scopes."""
        PolicyVariableFactory(key="shared_key", org=organization, scope="org")
        fleet = FleetFactory(organization=organization, policy=policy)
        data = {"key": "shared_key", "value": "fleet_val", "scope": "fleet", "fleet": fleet.pk}
        response = client.post(url, data)
        assert response.status_code == 200
        assert not response.context["variable_form"].errors
        assert PolicyVariable.objects.filter(key="shared_key").count() == 2


# ---------------------------------------------------------------------------
# policy_delete_variable
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPolicyDeleteVariable(PolicyViewBase):
    @pytest.fixture
    def variable(self, organization):
        return PolicyVariableFactory(org=organization)

    @pytest.fixture
    def url(self, organization, policy, variable):
        return reverse(
            "mdm:policy-delete-variable", args=[organization.slug, policy.pk, variable.pk]
        )

    def test_login_required(self, client, url, user):
        client.logout()
        response = client.post(url)
        assert response.status_code == 302

    def test_deletes_variable(self, client, url, variable):
        response = client.post(url)
        assert response.status_code == 200
        assert not PolicyVariable.objects.filter(pk=variable.pk).exists()

    def test_org_isolation(self, client, organization, other_org_policy, user):
        other_var = PolicyVariableFactory(org=OrganizationFactory())
        url = reverse(
            "mdm:policy-delete-variable",
            args=[organization.slug, other_org_policy.pk, other_var.pk],
        )
        # Policy is cross-org → 404 before variable lookup
        response = client.post(url)
        assert response.status_code == 404
