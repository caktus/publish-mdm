import json

import pytest
from django.urls import reverse
from django.conf import settings
from django.db.models import Q
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers.data import JsonLexer

from tests.odk_publish.factories import (
    AppUserFactory,
    AppUserFormTemplateFactory,
    FormTemplateFactory,
    OrganizationFactory,
    ProjectFactory,
    UserFactory,
)
from apps.odk_publish.etl.odk.constants import DEFAULT_COLLECT_SETTINGS
from apps.odk_publish.etl.odk.publish import ProjectAppUserAssignment
from apps.odk_publish.forms import AppUserForm, AppUserTemplateVariableFormSet, OrganizationForm
from apps.odk_publish.models import AppUser, FormTemplate, Organization


@pytest.mark.django_db
class ViewTestBase:
    @pytest.fixture
    def user(self, client):
        user = UserFactory()
        user.save()
        client.force_login(user=user)
        return user

    @pytest.fixture
    def project(self):
        return ProjectFactory(central_server__base_url="https://central")

    def test_login_required(self, client, url):
        response = client.get(url)
        assert response.status_code == 302

    def test_get(self, client, url, user):
        response = client.get(url)
        assert response.status_code == 200


class TestPublishTemplate(ViewTestBase):
    """Test the PublishTemplateForm form validation."""

    @pytest.fixture
    def form_template(self, project):
        return FormTemplateFactory(project=project)

    @pytest.fixture
    def url(self, project, form_template):
        return reverse(
            "odk_publish:form-template-publish",
            kwargs={
                "organization_slug": project.organization.slug,
                "odk_project_pk": project.pk,
                "form_template_id": form_template.pk,
            },
        )

    def test_post(self, client, url, user, project, form_template):
        app_user = AppUserFormTemplateFactory(
            form_template=form_template, app_user__project=project
        ).app_user
        data = {"app_users": app_user.name, "form_template": form_template.id}
        response = client.post(url, data=data)
        assert response.status_code == 200
        assert response.context["form"].is_valid()

    def test_htmx_post(self, client, url, user, project, form_template):
        app_user = AppUserFormTemplateFactory(
            form_template=form_template, app_user__project=project
        ).app_user
        data = {"app_users": app_user.name, "form_template": form_template.id}
        response = client.post(url, data=data, headers={"HX-Request": "true"})
        assert response.status_code == 200
        # Check that the response triggers the WebSocket connection
        assert 'hx-ws="send"' in str(response.content)


class TestAppUserDetail(ViewTestBase):
    @pytest.fixture
    def app_user(self, project):
        return AppUserFactory(project=project, qr_code_data=DEFAULT_COLLECT_SETTINGS)

    @pytest.fixture
    def url(self, app_user):
        return reverse(
            "odk_publish:app-user-detail",
            kwargs={
                "organization_slug": app_user.project.organization.slug,
                "odk_project_pk": app_user.project.pk,
                "app_user_pk": app_user.pk,
            },
        )

    def test_get(self, client, url, user, app_user):
        """Ensure the AppUser detail page contains the syntax-highlighed JSON
        for the QR code data and a button to copy the JSON without newlines and
        extra spaces.
        """
        response = client.get(url)
        assert response.status_code == 200

        app_user.refresh_from_db()
        expected_highlight_html = highlight(
            json.dumps(app_user.qr_code_data, indent=4), JsonLexer(), HtmlFormatter(linenos="table")
        )
        response_html = response.content.decode()

        assert response.context["qr_code_data"] == json.dumps(
            app_user.qr_code_data, separators=(",", ":")
        )
        assert response.context["qr_code_highlight_html"] == expected_highlight_html
        assert expected_highlight_html in response_html
        assert "Copy JSON" in response_html


class TestGenerateQRCodes(ViewTestBase):
    @pytest.fixture
    def app_users(self, project):
        return AppUserFactory.create_batch(3, project=project)

    @pytest.fixture
    def url(self, project):
        return reverse(
            "odk_publish:app-users-generate-qr-codes",
            kwargs={"organization_slug": project.organization.slug, "odk_project_pk": project.pk},
        )

    def test_get(self, client, url, user, project, app_users, mocker):
        """Ensure generating QR codes sets both the qr_code and qr_code_data fields
        for the project's users.
        """
        # Initially, qr_code and qr_code_data fields are not set for all app users
        assert project.app_users.count() == 3
        assert (
            project.app_users.filter(Q(qr_code__gt="") | Q(qr_code_data__isnull=False)).count() == 0
        )

        mocker.patch(
            "apps.odk_publish.etl.odk.publish.PublishService.get_app_users",
            return_value={
                app_user.name: ProjectAppUserAssignment(
                    projectId=project.central_id,
                    id=app_user.central_id,
                    type="field_key",
                    displayName="user1",
                    createdAt=app_user.created_at,
                    updatedAt=None,
                    deletedAt=None,
                    token="token1",
                )
                for app_user in app_users
            },
        )
        response = client.get(url, follow=True)
        assert response.status_code == 200
        assert response.redirect_chain == [
            (
                reverse("odk_publish:app-user-list", args=[project.organization.slug, project.id]),
                302,
            )
        ]
        # All app users should have their qr_code and qr_code_data fields set now
        assert project.app_users.filter(Q(qr_code="") | Q(qr_code_data__isnull=True)).count() == 0


@pytest.mark.django_db
class TestNonExistentProjectID:
    @pytest.fixture
    def user(self, client):
        user = UserFactory()
        user.save()
        client.force_login(user=user)
        return user

    @pytest.fixture
    def project(self):
        return ProjectFactory()

    @pytest.mark.parametrize(
        "url_name",
        [
            "app-user-list",
            "app-users-generate-qr-codes",
            "app-users-export",
            "app-users-import",
            "form-template-list",
        ],
    )
    def test_get_returns_404(self, client, user, url_name):
        """Ensure URLs that take a project ID as an argument return a 404 status code
        instead of a 500 for non-existent project IDs.
        """
        url = reverse(f"odk_publish:{url_name}", args=[OrganizationFactory().slug, 99])
        response = client.get(url)
        assert response.status_code == 404


class TestAddFormTemplate(ViewTestBase):
    """Test the adding a form template."""

    @pytest.fixture
    def url(self, project):
        return reverse(
            "odk_publish:add-form-template",
            kwargs={"organization_slug": project.organization.slug, "odk_project_pk": project.pk},
        )

    def test_get(self, client, url, user):
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

    def test_post(self, client, url, user, project):
        data = {
            "title_base": "Test template",
            "form_id_base": "testing",
            "template_url": "https://docs.google.com/spreadsheets/d/1/edit",
            "template_url_user": user.id,
        }
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # Ensure a new FormTemplate was created with the expected values
        assert FormTemplate.objects.count() == 1
        form_template_values = FormTemplate.objects.values("project", *data.keys()).get()
        assert form_template_values.pop("project") == project.id
        assert form_template_values == data
        # Ensure the view redirects to the form templates list page
        assert response.redirect_chain == [
            (
                reverse(
                    "odk_publish:form-template-list", args=[project.organization.slug, project.id]
                ),
                302,
            )
        ]
        # Ensure there is a success message
        assert (
            f"Successfully added {form_template_values['title_base']}." in response.content.decode()
        )


class TestEditFormTemplate(ViewTestBase):
    """Test the editing a form template."""

    @pytest.fixture
    def form_template(self, project):
        return FormTemplateFactory(project=project)

    @pytest.fixture
    def url(self, form_template):
        return reverse(
            "odk_publish:edit-form-template",
            kwargs={
                "organization_slug": form_template.project.organization.slug,
                "odk_project_pk": form_template.project_id,
                "form_template_id": form_template.id,
            },
        )

    def test_get(self, client, url, user):
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

    def test_post(self, client, url, user, form_template):
        data = {
            "title_base": "Test template",
            "form_id_base": "testing",
            "template_url": "https://docs.google.com/spreadsheets/d/1/edit",
            "template_url_user": user.id,
        }
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # Ensure the FormTemplate was edited with the expected values
        assert FormTemplate.objects.count() == 1
        form_template_values = FormTemplate.objects.values("id", "project", *data.keys()).get()
        assert form_template_values.pop("id") == form_template.id
        assert form_template_values.pop("project") == form_template.project_id
        assert form_template_values == data
        # Ensure the view redirects to the form templates list page
        assert response.redirect_chain == [
            (
                reverse(
                    "odk_publish:form-template-list",
                    args=[form_template.project.organization.slug, form_template.project_id],
                ),
                302,
            )
        ]
        # Ensure there is a success message
        assert (
            f"Successfully edited {form_template_values['title_base']}."
            in response.content.decode()
        )


class TestAddAppUser(ViewTestBase):
    @pytest.fixture
    def url(self, project):
        return reverse(
            "odk_publish:add-app-user",
            kwargs={"organization_slug": project.organization.slug, "odk_project_pk": project.pk},
        )

    @pytest.fixture
    def template_variables(self, project):
        return [
            project.template_variables.create(name="var1", organization=project.organization),
            project.template_variables.create(name="var2", organization=project.organization),
        ]

    def test_get(self, client, url, user):
        response = client.get(url)
        assert response.status_code == 200
        assert isinstance(response.context.get("form"), AppUserForm)
        assert isinstance(response.context.get("variables_formset"), AppUserTemplateVariableFormSet)
        assert response.context["form"].instance.pk is None
        assert response.context["variables_formset"].instance.pk is None
        assert len(response.context["variables_formset"].forms) == 0

    @pytest.fixture
    def data(self):
        return {
            "name": "testuser",
            "app_user_template_variables-TOTAL_FORMS": 0,
            "app_user_template_variables-INITIAL_FORMS": 0,
            "app_user_template_variables-MIN_NUM_FORMS": 0,
            "app_user_template_variables-MAX_NUM_FORMS": 1000,
        }

    def test_valid_form(self, client, url, user, project, data):
        """Test a form with a valid name and no template variables."""
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # Ensure a new AppUser was created with the expected name
        assert AppUser.objects.count() == 1
        app_user = AppUser.objects.get()
        assert app_user.name == data["name"]
        # No app user template variables were created
        assert app_user.template_variables.count() == 0
        # Ensure the view redirects to the app users list page
        assert response.redirect_chain == [
            (
                reverse("odk_publish:app-user-list", args=[project.organization.slug, project.id]),
                302,
            )
        ]
        # Ensure there is a success message
        assert f"Successfully added {app_user}." in response.content.decode()

    def test_valid_form_and_valid_formset(
        self, client, url, user, project, data, template_variables
    ):
        """Test a form with a valid name and valid template variables formset."""
        data["app_user_template_variables-TOTAL_FORMS"] = 2
        for index, var in enumerate(template_variables):
            data[f"app_user_template_variables-{index}-template_variable"] = var.id
            data[f"app_user_template_variables-{index}-value"] = f"{var.name} value"
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # Ensure a new AppUser was created with the expected name
        assert AppUser.objects.count() == 1
        app_user = AppUser.objects.get()
        assert app_user.name == data["name"]
        # Ensure 2 AppUserTemplateVariables were created with the expected values
        assert app_user.app_user_template_variables.count() == 2
        for var in app_user.app_user_template_variables.all():
            assert var.value == f"{var.template_variable.name} value"
        # Ensure the view redirects to the app users list page
        assert response.redirect_chain == [
            (
                reverse("odk_publish:app-user-list", args=[project.organization.slug, project.id]),
                302,
            )
        ]
        # Ensure there is a success message
        assert f"Successfully added {app_user}." in response.content.decode()

    def test_invalid_name(self, client, url, user, data):
        """Test a form with an invalid name and no template variables."""
        data["name"] = "test user"
        response = client.post(url, data=data)
        assert response.status_code == 200
        # No AppUser created
        assert AppUser.objects.count() == 0
        # The form and template variables formset are included in the context
        assert isinstance(response.context.get("form"), AppUserForm)
        assert isinstance(response.context.get("variables_formset"), AppUserTemplateVariableFormSet)
        # Ensure the expected error message is displayed on the page
        expected_error = "Name can only contain alphanumeric characters, underscores, hyphens, and not more than one colon."
        assert response.context["form"].errors["name"][0] == expected_error
        assert expected_error in response.content.decode()

    def test_duplicate_name(self, client, url, user, project, data):
        """Test a form with a name already used for another user and no template variables."""
        other_user = AppUserFactory(project=project, name="appuser")
        data["name"] = other_user.name
        response = client.post(url, data=data)
        assert response.status_code == 200
        # No new AppUser created
        assert AppUser.objects.count() == 1
        # The form and template variables formset are included in the context
        assert isinstance(response.context.get("form"), AppUserForm)
        assert isinstance(response.context.get("variables_formset"), AppUserTemplateVariableFormSet)
        # Ensure the expected error message is displayed on the page
        expected_error = "An app user with the same name already exists in the current project."
        assert response.context["form"].errors["name"][0] == expected_error
        assert expected_error in response.content.decode()

    def test_valid_form_and_invalid_formset(self, client, url, user, data, template_variables):
        """Test a form with a valid name and invalid template variables formset."""
        data.update(
            {
                "app_user_template_variables-TOTAL_FORMS": 1,
                "app_user_template_variables-0-template_variable": template_variables[0].id,
                "app_user_template_variables-0-value": "",
            }
        )
        response = client.post(url, data=data)
        assert response.status_code == 200
        # No AppUser created
        assert AppUser.objects.count() == 0
        # The form and template variables formset are included in the context
        assert isinstance(response.context.get("form"), AppUserForm)
        assert isinstance(response.context.get("variables_formset"), AppUserTemplateVariableFormSet)
        # Ensure the expected error message is displayed on the page
        expected_error = "This field is required."
        assert response.context["variables_formset"].errors[0]["value"][0] == expected_error
        assert expected_error in response.content.decode()


class TestEditAppUser(ViewTestBase):
    @pytest.fixture
    def template_variables(self, project):
        return [
            project.template_variables.create(name="var1", organization=project.organization),
            project.template_variables.create(name="var2", organization=project.organization),
        ]

    @pytest.fixture
    def app_user(self, project, template_variables):
        app_user = AppUserFactory(project=project, name="testuser")
        var = template_variables[0]
        app_user.app_user_template_variables.create(
            template_variable=var, value=f"{var.name} value"
        )
        return app_user

    @pytest.fixture
    def url(self, app_user):
        return reverse(
            "odk_publish:edit-app-user",
            kwargs={
                "organization_slug": app_user.project.organization.slug,
                "odk_project_pk": app_user.project_id,
                "app_user_id": app_user.id,
            },
        )

    def test_get(self, client, url, user, app_user):
        response = client.get(url)
        assert response.status_code == 200
        assert isinstance(response.context.get("form"), AppUserForm)
        assert isinstance(response.context.get("variables_formset"), AppUserTemplateVariableFormSet)
        assert response.context["form"].instance == app_user
        assert response.context["variables_formset"].instance == app_user
        assert len(response.context["variables_formset"].forms) == 1

    @pytest.fixture
    def data(self, app_user, template_variables):
        """POST data with a different valid name and valid formset data that changes the
        user's current template variable and adds a new one.
        """
        app_user_template_var = app_user.app_user_template_variables.get()
        new_var = template_variables[1]
        return {
            "name": "newname",
            "app_user_template_variables-TOTAL_FORMS": 2,
            "app_user_template_variables-INITIAL_FORMS": 1,
            "app_user_template_variables-MIN_NUM_FORMS": 0,
            "app_user_template_variables-MAX_NUM_FORMS": 1000,
            "app_user_template_variables-0-app_user": app_user.id,
            "app_user_template_variables-0-id": app_user_template_var.id,
            "app_user_template_variables-0-template_variable": app_user_template_var.template_variable_id,
            "app_user_template_variables-0-value": f"edited {app_user_template_var.value}",
            "app_user_template_variables-1-template_variable": new_var.id,
            "app_user_template_variables-1-value": f"edited {new_var.name} value",
        }

    def test_valid_form_and_valid_formset(self, client, url, user, app_user, data):
        """Test a form with a valid name and valid template variables formset."""
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # Ensure the app user's name was changed
        assert AppUser.objects.count() == 1
        app_user.refresh_from_db()
        assert app_user.name == data["name"]
        # Ensure the existing AppUserTemplateVariable was changed and a new one was added
        assert app_user.app_user_template_variables.count() == 2
        for var in app_user.app_user_template_variables.all():
            assert var.value == f"edited {var.template_variable.name} value"
        # Ensure the view redirects to the app users list page
        assert response.redirect_chain == [
            (
                reverse(
                    "odk_publish:app-user-list",
                    args=[app_user.project.organization.slug, app_user.project_id],
                ),
                302,
            )
        ]
        # Ensure there is a success message
        assert f"Successfully edited {app_user}." in response.content.decode()

    def test_valid_form_and_valid_formset_deleting_variable(
        self, client, url, user, app_user, data, template_variables
    ):
        """Test a form with a valid name and valid template variables formset that deletes
        the user's existing template variable.
        """
        data["app_user_template_variables-0-DELETE"] = "on"
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # Ensure the app user's name was changed
        assert AppUser.objects.count() == 1
        app_user.refresh_from_db()
        assert app_user.name == data["name"]
        # Ensure the existing AppUserTemplateVariable was deleted and a new one was added
        assert app_user.app_user_template_variables.count() == 1
        app_user_template_var = app_user.app_user_template_variables.get()
        assert app_user_template_var.template_variable == template_variables[1]
        # Ensure the view redirects to the app users list page
        assert response.redirect_chain == [
            (
                reverse(
                    "odk_publish:app-user-list",
                    args=[app_user.project.organization.slug, app_user.project_id],
                ),
                302,
            )
        ]
        # Ensure there is a success message
        assert f"Successfully edited {app_user}." in response.content.decode()

    def check_invalid_form_or_formset(self, app_user, data, response):
        assert response.status_code == 200
        # The AppUser's name was not changed
        app_user.refresh_from_db()
        assert app_user.name != data["name"]
        # Ensure the existing AppUserTemplateVariable was not changed and a new one was not added
        assert app_user.app_user_template_variables.count() == 1
        for var in app_user.app_user_template_variables.all():
            assert var.value != f"edited {var.template_variable.name} value"
        # The form and template variables formset are included in the context
        assert isinstance(response.context.get("form"), AppUserForm)
        assert isinstance(response.context.get("variables_formset"), AppUserTemplateVariableFormSet)

    def test_invalid_name(self, client, url, user, app_user, data):
        """Test a form with an invalid name and no template variables."""
        data["name"] = "invalid name"
        response = client.post(url, data=data)
        self.check_invalid_form_or_formset(app_user, data, response)
        # Ensure the expected error message is displayed on the page
        expected_error = "Name can only contain alphanumeric characters, underscores, hyphens, and not more than one colon."
        assert response.context["form"].errors["name"][0] == expected_error
        assert expected_error in response.content.decode()

    def test_duplicate_name(self, client, url, user, app_user, data):
        """Test a form with a name already used for another user and no template variables."""
        other_user = AppUserFactory(project=app_user.project, name="newname")
        data["name"] = other_user.name
        response = client.post(url, data=data)
        self.check_invalid_form_or_formset(app_user, data, response)
        # Ensure the expected error message is displayed on the page
        expected_error = "An app user with the same name already exists in the current project."
        assert response.context["form"].errors["name"][0] == expected_error
        assert expected_error in response.content.decode()

    def test_valid_form_and_invalid_formset(self, client, url, user, app_user, data):
        """Test a form with a valid name and invalid template variables formset."""
        data["app_user_template_variables-0-value"] = ""
        response = client.post(url, data=data)
        self.check_invalid_form_or_formset(app_user, data, response)
        # Ensure the expected error message is displayed on the page
        expected_error = "This field is required."
        assert response.context["variables_formset"].errors[0]["value"][0] == expected_error
        assert expected_error in response.content.decode()


class TestOrganizationHome(ViewTestBase):
    @pytest.fixture
    def organization(self):
        return OrganizationFactory()

    @pytest.fixture
    def url(self, organization):
        return reverse(
            "odk_publish:organization-home",
            kwargs={
                "organization_slug": organization.slug,
            },
        )


class TestCreateOrganization(ViewTestBase):
    @pytest.fixture
    def url(self):
        return reverse("odk_publish:create-organization")

    def test_get(self, client, url, user):
        response = client.get(url)
        assert response.status_code == 200
        assert isinstance(response.context.get("form"), OrganizationForm)

    def test_valid_form(self, client, url, user):
        """Test a valid form."""
        data = {"name": "New organization", "slug": "new-org"}
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # Ensure the Organization has been created with the expected values
        assert Organization.objects.count() == 1
        organization = Organization.objects.get()
        assert organization.name == data["name"]
        assert organization.slug == data["slug"]
        # Ensure the view redirects to Organization home page
        assert response.redirect_chain == [
            (
                reverse(
                    "odk_publish:organization-home",
                    args=[organization.slug],
                ),
                302,
            )
        ]
        # Ensure there is a success message
        assert f"Successfully created {organization}." in response.content.decode()

    def test_invalid_form(self, client, url, user):
        """Test a valid form."""
        data = {"name": "New organization", "slug": ""}
        response = client.post(url, data=data)
        assert response.status_code == 200
        # No Organization created
        assert Organization.objects.count() == 0
        # The form is included in the context
        assert isinstance(response.context.get("form"), OrganizationForm)
        # Ensure the expected error message is displayed on the page
        expected_error = "This field is required."
        assert response.context["form"].errors["slug"][0] == expected_error
        assert expected_error in response.content.decode()
