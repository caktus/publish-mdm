import pytest
from django.conf import settings
from django.contrib import admin
from django.urls import reverse
from pytest_django.asserts import assertContains

from apps.mdm.mdms import AndroidEnterprise
from apps.publish_mdm.admin import AndroidEnterpriseAccountAdmin
from apps.publish_mdm.models import AndroidEnterpriseAccount, CentralServer, Organization, Project
from tests.mdm import TestAllMDMsNoAutouse
from tests.publish_mdm.factories import (
    AndroidEnterpriseAccountFactory,
    CentralServerFactory,
    FormTemplateFactory,
    OrganizationFactory,
    ProjectFactory,
    TemplateVariableFactory,
    UserFactory,
)


@pytest.mark.django_db
class BaseTestAdmin(TestAllMDMsNoAutouse):
    @pytest.fixture
    def user(self, client):
        user = UserFactory(is_staff=True, is_superuser=True)
        user.save()
        client.force_login(user=user)
        return user


@pytest.mark.django_db
class TestChangeFormTemplate(BaseTestAdmin):
    @pytest.fixture
    def form_template(self):
        return FormTemplateFactory()

    @pytest.fixture
    def url(self, form_template):
        return reverse(
            "publish_mdm:edit-form-template",
            kwargs={
                "organization_slug": form_template.project.organization.slug,
                "odk_project_pk": form_template.project_id,
                "form_template_id": form_template.id,
            },
        )

    def test_get(self, client, url, user, form_template):
        urls = [
            reverse("admin:publish_mdm_formtemplate_add"),
            reverse("admin:publish_mdm_formtemplate_change", args=[form_template.id]),
        ]
        for url in urls:
            response = client.get(url)
            assert response.status_code == 200
            # Ensure the context includes the variables required for the Google Picker JS
            for var in ("google_client_id", "google_api_key", "google_app_id"):
                assert response.context[var] == getattr(settings, var.upper())
            assert response.context["google_scopes"] == " ".join(
                settings.SOCIALACCOUNT_PROVIDERS["google"]["SCOPE"]
            )
            # Ensure the 'Cross-Origin-Opener-Policy' header has the value required
            # for the Google Picker popup to work correctly
            assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin-allow-popups"


@pytest.mark.django_db
class TestOrganizationInvitationAdminAdd(BaseTestAdmin):
    @pytest.fixture
    def url(self):
        return reverse("admin:publish_mdm_organizationinvitation_add")

    def valid_form(self, client, url, organization, data, mailoutbox):
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # Ensure the expected OrganizationInvitation is created in the DB
        qs = organization.organizationinvitation_set.filter(email=data["email"])
        assert qs.count() == 1
        invitation = qs.get()
        if data.get("inviter"):
            assert invitation.inviter.id == data["inviter"]
        else:
            assert invitation.inviter is None
        assert not invitation.accepted
        assert invitation.sent is not None
        assert not invitation.key_expired()
        # Ensure an invitation email was sent
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == [data["email"]]

    def test_valid_form(self, client, url, user, mailoutbox):
        organization = OrganizationFactory()
        data = {
            "email": "test@test.com",
            "organization": organization.id,
        }
        self.valid_form(client, url, organization, data, mailoutbox)

    def test_valid_form_with_inviter(self, client, url, user, mailoutbox):
        organization = OrganizationFactory()
        data = {
            "email": "test@test.com",
            "organization": organization.id,
            "inviter": user.id,
        }
        self.valid_form(client, url, organization, data, mailoutbox)


class TestProjectAdmin(BaseTestAdmin):
    @pytest.mark.parametrize(
        "changed_field",
        (
            None,
            "name",
            "central_id",
            "central_server",
            "organization",
            "app_language",
            "template_variables",
            "admin_pw",
        ),
    )
    def test_regenerating_qr_codes(self, client, user, mocker, changed_field):
        """Ensures app user QR codes are regenerated when form fields that impact
        them are changed.
        """
        project = project = ProjectFactory(
            app_language="en", central_server__base_url="https://central"
        )
        url = reverse("admin:publish_mdm_project_change", args=[project.pk])
        mock_generate_qr_codes = mocker.patch(
            "apps.publish_mdm.admin.generate_and_save_app_user_collect_qrcodes"
        )
        data = {
            "name": project.name,
            "central_id": project.central_id,
            "central_server": project.central_server_id,
            "organization": project.organization_id,
            "app_language": project.app_language,
            "template_variables": [],
        }
        for inline_prefix in ("attachments", "project_template_variables"):
            data.update(
                {
                    f"{inline_prefix}-TOTAL_FORMS": 0,
                    f"{inline_prefix}-INITIAL_FORMS": 0,
                    f"{inline_prefix}-MIN_NUM_FORMS": 0,
                    f"{inline_prefix}-MAX_NUM_FORMS": 1000,
                }
            )

        new_values = {
            "app_language": "ar",
            "central_id": project.central_id + 1,
            "name": project.name + " edited",
            "central_server": CentralServerFactory(organization=project.organization).id,
            "organization": OrganizationFactory().id,
            "template_variables": [
                i.id
                for i in TemplateVariableFactory.create_batch(2, organization=project.organization)
            ],
        }
        # QR codes should be regenerated if any of these fields are changed
        should_regenerate = ("app_language", "central_id", "name", "admin_pw")

        if changed_field == "admin_pw":
            admin_pw_var = TemplateVariableFactory.create(
                name="admin_pw", organization=project.organization
            )
            data.update(
                {
                    "project_template_variables-TOTAL_FORMS": 1,
                    "project_template_variables-0-template_variable": admin_pw_var.id,
                    "project_template_variables-0-value": "password",
                }
            )
        elif changed_field:
            data[changed_field] = new_values[changed_field]

        client.post(url, data)

        if changed_field in should_regenerate:
            mock_generate_qr_codes.assert_called_once()
        else:
            mock_generate_qr_codes.assert_not_called()

        # Ensure the change was actually made in the database
        if changed_field == "admin_pw":
            assert project.get_admin_pw() == "password"
        elif changed_field:
            new_db_value = Project.objects.values_list(changed_field, flat=True).filter(
                pk=project.pk
            )
            if changed_field == "template_variables":
                assert set(new_db_value) == set(new_values[changed_field])
            else:
                assert new_db_value.get() == new_values[changed_field]


class TestCentralServerAdmin(BaseTestAdmin):
    @pytest.fixture
    def server(self):
        return CentralServerFactory()

    def test_edit_with_no_username_and_password(self, client, user, server, requests_mock):
        """Ensure submitting a form without a username or password is valid if
        they are already set in the database. The saved values should not be changed.
        """
        username_before = server.username
        password_before = server.password
        data = {
            "base_url": server.base_url,
            "username": "",
            "password": "",
            "organization": OrganizationFactory().id,
        }
        # Mock the ODK Central API request for validating the base URL and credentials
        mock_odk_request = requests_mock.post(f"{data['base_url']}/v1/sessions")
        response = client.post(
            reverse("admin:publish_mdm_centralserver_change", args=[server.id]),
            data=data,
            follow=True,
        )
        assert response.status_code == 200
        assert not mock_odk_request.called
        server.refresh_from_db()
        assert server.base_url == data["base_url"]
        assert server.organization_id == data["organization"]
        assert server.username == username_before
        assert server.password == password_before

    def test_add(self, client, user, requests_mock):
        """Test creating a new CentralServer."""
        data = {
            "base_url": "https://central.example.com",
            "username": "test@email.com",
            "password": "password",
            "organization": OrganizationFactory().id,
        }
        # Mock the ODK Central API request for validating the base URL and credentials
        mock_odk_request = requests_mock.post(
            f"{data['base_url']}/v1/sessions",
            json={
                "createdAt": "2018-04-18T03:04:51.695Z",
                "expiresAt": "2018-04-19T03:04:51.695Z",
                "token": "token",
            },
        )
        response = client.post(
            reverse("admin:publish_mdm_centralserver_add"), data=data, follow=True
        )
        assert response.status_code == 200
        assert mock_odk_request.called_once
        assert CentralServer.objects.values(*data).get() == data


class TestOrganizationAdmin(BaseTestAdmin):
    @pytest.mark.parametrize("mdm_api_error", [False, True], indirect=True)
    def test_new_organization(
        self, user, client, mocker, all_mdms, set_mdm_env_vars, mdm_api_error
    ):
        """For TinyMDM, create_default_fleet() is called immediately when creating a new
        organization. For Android Enterprise, fleet creation is deferred until enterprise
        enrollment completes via enterprise_callback, so create_default_fleet() is not
        called here.
        """
        organization = OrganizationFactory.build()
        data = {
            "name": organization.name,
            "slug": organization.slug,
            "mdm": self.mdm,
            "users": [user.id],
        }
        mock_create_default_fleet = mocker.patch.object(
            Organization, "create_default_fleet", side_effect=mdm_api_error
        )
        response = client.post(
            reverse("admin:publish_mdm_organization_add"), data=data, follow=True
        )

        assert response.status_code == 200
        assert Organization.objects.filter(name=data["name"], slug=data["slug"]).exists()
        if self.mdm == "Android Enterprise":
            mock_create_default_fleet.assert_not_called()
        else:
            mock_create_default_fleet.assert_called_once()
            if mdm_api_error:
                assertContains(
                    response,
                    (
                        f"The organization was created but the following {self.mdm} "
                        f"API error occurred while setting up its default Fleet:<br><code>{mdm_api_error}</code>"
                    ),
                )

    def test_edit_organization(self, user, client, mocker, organization):
        """Ensures the create_default_fleet() method is not called when editing
        an organization.
        """
        data = {
            "name": organization.name + "edited",
            "slug": organization.slug + "edited",
            "users": [user.id],
            "mdm": organization.mdm,
        }
        mock_create_default_fleet = mocker.patch.object(Organization, "create_default_fleet")
        response = client.post(
            reverse("admin:publish_mdm_organization_change", args=[organization.id]),
            data=data,
            follow=True,
        )

        assert response.status_code == 200
        mock_create_default_fleet.assert_not_called()
        organization.refresh_from_db()
        assert organization.name == data["name"]
        assert organization.slug == data["slug"]


@pytest.mark.django_db
class TestAndroidEnterpriseAccountAdmin(BaseTestAdmin):
    """Tests for the custom methods on AndroidEnterpriseAccountAdmin."""

    def test_signup_url_link_with_url(self):
        """Returns an HTML anchor tag containing the signup URL when signup_url is set."""
        admin_instance = AndroidEnterpriseAccountAdmin(AndroidEnterpriseAccount, admin.site)
        account = AndroidEnterpriseAccountFactory.build(
            signup_url="https://enterprise.google.com/signup?token=abc"
        )
        result = admin_instance.signup_url_link(account)
        assert 'href="https://enterprise.google.com/signup?token=abc"' in result
        assert 'rel="nofollow noreferrer"' in result

    def test_signup_url_link_without_url(self):
        """Returns an em-dash placeholder when signup_url is empty."""
        admin_instance = AndroidEnterpriseAccountAdmin(AndroidEnterpriseAccount, admin.site)
        account = AndroidEnterpriseAccountFactory.build(signup_url="")
        result = admin_instance.signup_url_link(account)
        assert result == "—"

    def test_add_calls_get_signup_url_and_saves_result(self, client, user, mocker):
        """Creating a new AndroidEnterpriseAccount calls get_signup_url and persists the URL fields."""
        org = OrganizationFactory()
        signup_result = {
            "name": "signupUrls/C455570ef9b12bfc",
            "url": "https://enterprise.google.com/signup?token=abc",
        }
        mock_get_signup_url = mocker.patch.object(
            AndroidEnterprise, "get_signup_url", return_value=signup_result
        )
        response = client.post(
            reverse("admin:publish_mdm_androidenterpriseaccount_add"),
            data={"organization": org.id},
            follow=True,
        )
        assert response.status_code == 200
        mock_get_signup_url.assert_called_once()
        account = AndroidEnterpriseAccount.objects.get(organization=org)
        assert account.signup_url_name == signup_result["name"]
        assert account.signup_url == signup_result["url"]

    def test_add_uses_callback_domain_when_configured(self, client, user, settings, mocker):
        """Uses ANDROID_ENTERPRISE_CALLBACK_DOMAIN to build the callback URL when configured."""
        settings.ANDROID_ENTERPRISE_CALLBACK_DOMAIN = "myapp.example.com"
        org = OrganizationFactory()
        mock_get_signup_url = mocker.patch.object(
            AndroidEnterprise,
            "get_signup_url",
            return_value={"name": "signupUrls/X", "url": "https://enterprise.google.com/signup"},
        )
        client.post(
            reverse("admin:publish_mdm_androidenterpriseaccount_add"),
            data={"organization": org.id},
            follow=True,
        )
        mock_get_signup_url.assert_called_once()
        callback_url = mock_get_signup_url.call_args.kwargs["callback_url"]
        assert callback_url.startswith("https://myapp.example.com/")

    def test_add_uses_request_host_without_callback_domain(self, client, user, settings, mocker):
        """Falls back to request.build_absolute_uri when ANDROID_ENTERPRISE_CALLBACK_DOMAIN is empty."""
        settings.ANDROID_ENTERPRISE_CALLBACK_DOMAIN = ""
        org = OrganizationFactory()
        mock_get_signup_url = mocker.patch.object(
            AndroidEnterprise,
            "get_signup_url",
            return_value={"name": "signupUrls/X", "url": "https://enterprise.google.com/signup"},
        )
        client.post(
            reverse("admin:publish_mdm_androidenterpriseaccount_add"),
            data={"organization": org.id},
            follow=True,
        )
        mock_get_signup_url.assert_called_once()
        callback_url = mock_get_signup_url.call_args.kwargs["callback_url"]
        # Django test client sends requests from "testserver"
        assert "testserver" in callback_url

    def test_add_shows_error_on_get_signup_url_exception(self, client, user, mocker):
        """Shows an error message and still creates the account when get_signup_url raises."""
        org = OrganizationFactory()
        mocker.patch.object(
            AndroidEnterprise, "get_signup_url", side_effect=Exception("API unavailable")
        )
        response = client.post(
            reverse("admin:publish_mdm_androidenterpriseaccount_add"),
            data={"organization": org.id},
            follow=True,
        )
        assert response.status_code == 200
        assertContains(response, "Failed to generate signup URL: API unavailable")
        # The account record is still created, but signup_url remains empty
        account = AndroidEnterpriseAccount.objects.get(organization=org)
        assert account.signup_url == ""

    def test_edit_does_not_call_get_signup_url(self, client, user, mocker):
        """Editing an existing AndroidEnterpriseAccount never calls get_signup_url."""
        account = AndroidEnterpriseAccountFactory()
        mock_get_signup_url = mocker.patch.object(AndroidEnterprise, "get_signup_url")
        response = client.post(
            reverse(
                "admin:publish_mdm_androidenterpriseaccount_change",
                args=[account.id],
            ),
            data={"organization": account.organization_id},
            follow=True,
        )
        assert response.status_code == 200
        mock_get_signup_url.assert_not_called()
