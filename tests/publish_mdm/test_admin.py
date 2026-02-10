import pytest
from django.urls import reverse
from django.conf import settings
from pytest_django.asserts import assertContains

from apps.publish_mdm.models import CentralServer, Organization, Project
from tests.mdm import TestAllMDMsNoAutouse
from tests.publish_mdm.factories import (
    CentralServerFactory,
    FormTemplateFactory,
    OrganizationFactory,
    ProjectFactory,
    UserFactory,
    TemplateVariableFactory,
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
        mock_odk_request = requests_mock.post(f'{data["base_url"]}/v1/sessions')
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
            f'{data["base_url"]}/v1/sessions',
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
    def test_new_organization(self, user, client, mocker, all_mdms, mdm_api_error):
        """Ensures the create_default_fleet() method is called when creating a
        new organization.
        """
        organization = OrganizationFactory.build()
        data = {
            "name": organization.name,
            "slug": organization.slug,
            "users": [user.id],
        }
        mock_create_default_fleet = mocker.patch.object(
            Organization, "create_default_fleet", side_effect=mdm_api_error
        )
        response = client.post(
            reverse("admin:publish_mdm_organization_add"), data=data, follow=True
        )

        assert response.status_code == 200
        mock_create_default_fleet.assert_called_once()
        assert Organization.objects.count() == 1
        if mdm_api_error:
            assertContains(
                response,
                (
                    f"The organization was created but the following {settings.ACTIVE_MDM['name']} "
                    f"API error occurred while setting up its default Fleet:<br><code>{mdm_api_error}</code>"
                ),
            )

    def test_edit_organization(self, user, client, mocker):
        """Ensures the create_default_fleet() method is not called when editing
        an organization.
        """
        organization = OrganizationFactory()
        data = {
            "name": organization.name + "edited",
            "slug": organization.slug + "edited",
            "users": [user.id],
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
