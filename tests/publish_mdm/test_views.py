import json

import faker
import pytest
from django_tables2 import Table
from django.urls import reverse
from django.conf import settings
from django.db.models import Q
from django.utils.timezone import now, localtime
from django.utils.formats import date_format
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers.data import JsonLexer
from requests.exceptions import HTTPError

from tests.publish_mdm.factories import (
    AppUserFactory,
    AppUserFormTemplateFactory,
    FormTemplateFactory,
    FormTemplateVersionFactory,
    OrganizationFactory,
    OrganizationInvitationFactory,
    ProjectFactory,
    UserFactory,
    CentralServerFactory,
    TemplateVariableFactory,
)
from apps.publish_mdm.etl.odk.constants import DEFAULT_COLLECT_SETTINGS
from apps.publish_mdm.etl.odk.publish import ProjectAppUserAssignment
from apps.publish_mdm.etl.template import VariableTransform
from apps.publish_mdm.forms import (
    AppUserForm,
    AppUserTemplateVariableFormSet,
    OrganizationForm,
    OrganizationInviteForm,
    ProjectForm,
    ProjectTemplateVariableFormSet,
    TemplateVariableFormSet,
)
from apps.publish_mdm.models import (
    AppUser,
    FormTemplate,
    Organization,
    OrganizationInvitation,
    Project,
)
from tests.mdm.factories import (
    DeviceFactory,
    DeviceSnapshotFactory,
    FirmwareSnapshotFactory,
    PolicyFactory,
)
from tests.tailscale.factories import DeviceFactory as TailscaleDeviceFactory

fake = faker.Faker()


@pytest.mark.django_db
class ViewTestBase:
    @pytest.fixture
    def user(self, client):
        user = UserFactory()
        user.save()
        client.force_login(user=user)
        return user

    @pytest.fixture
    def organization(self, user):
        organization = OrganizationFactory()
        organization.users.add(user)
        return organization

    @pytest.fixture
    def project(self, organization):
        return ProjectFactory(central_server__base_url="https://central", organization=organization)

    def test_login_required(self, client, url):
        client.logout()
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
            "publish_mdm:form-template-publish",
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
            "publish_mdm:app-user-detail",
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
            "publish_mdm:app-users-generate-qr-codes",
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
            "apps.publish_mdm.etl.odk.publish.PublishService.get_app_users",
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
                reverse("publish_mdm:app-user-list", args=[project.organization.slug, project.id]),
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
        organization = OrganizationFactory()
        organization.users.add(user)
        url = reverse(f"publish_mdm:{url_name}", args=[organization.slug, 99])
        response = client.get(url)
        assert response.status_code == 404


class TestAddFormTemplate(ViewTestBase):
    """Test the adding a form template."""

    @pytest.fixture
    def url(self, project):
        return reverse(
            "publish_mdm:add-form-template",
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
                    "publish_mdm:form-template-list", args=[project.organization.slug, project.id]
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
            "publish_mdm:edit-form-template",
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
                    "publish_mdm:form-template-list",
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


class TestFormTemplateDetail(ViewTestBase):
    """Test the form template detail page."""

    @pytest.fixture
    def form_template(self, project):
        form_template = FormTemplateFactory(project=project)
        # Create 5 versions for the template
        FormTemplateVersionFactory.create_batch(5, form_template=form_template)
        return form_template

    @pytest.fixture
    def url(self, form_template):
        return reverse(
            "publish_mdm:form-template-detail",
            kwargs={
                "organization_slug": form_template.project.organization.slug,
                "odk_project_pk": form_template.project_id,
                "form_template_id": form_template.id,
            },
        )

    def test_get(self, client, url, user, form_template):
        response = client.get(url)
        assert response.status_code == 200
        # Ensure the versions table is included in the context and it has the
        # expected data
        versions_table = response.context.get("versions_table")
        assert isinstance(versions_table, Table)
        rows = response.context["versions_table"].as_values()
        assert next(rows) == ["Version number", "Date published", "Published by"]
        assert list(rows) == [
            [
                i.version,
                date_format(localtime(i.modified_at), settings.SHORT_DATE_FORMAT),
                i.user.get_full_name(),
            ]
            for i in form_template.versions.order_by("-modified_at")
        ]
        # Ensure the table is rendered in the page
        assert versions_table.as_html(response.wsgi_request) in response.content.decode()


class TestAddAppUser(ViewTestBase):
    @pytest.fixture
    def url(self, project):
        return reverse(
            "publish_mdm:add-app-user",
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
                reverse("publish_mdm:app-user-list", args=[project.organization.slug, project.id]),
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
                reverse("publish_mdm:app-user-list", args=[project.organization.slug, project.id]),
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
            "publish_mdm:edit-app-user",
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
                    "publish_mdm:app-user-list",
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
                    "publish_mdm:app-user-list",
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


class TestAddProject(ViewTestBase):
    @pytest.fixture
    def url(self, organization):
        return reverse(
            "publish_mdm:add-project",
            kwargs={"organization_slug": organization.slug},
        )

    def test_get(self, client, url, user):
        response = client.get(url)
        assert response.status_code == 200
        assert isinstance(response.context["form"], ProjectForm)
        assert response.context["form"].instance.pk is None
        assert isinstance(response.context["variables_formset"], ProjectTemplateVariableFormSet)
        assert response.context["variables_formset"].instance.pk is None

    @pytest.fixture
    def central_server(self, organization):
        return CentralServerFactory(organization=organization)

    @pytest.fixture
    def template_variables(self, organization):
        return TemplateVariableFactory.create_batch(2, organization=organization)

    @pytest.fixture
    def data(self, central_server, template_variables):
        """Valid POST data for creating a Project with ProjectTemplateVariables."""
        data = {
            "name": "New name",
            "central_server": central_server.pk,
            "template_variables": [i.id for i in template_variables],
            "app_language": "ar",
            "project_template_variables-TOTAL_FORMS": 2,
            "project_template_variables-INITIAL_FORMS": 0,
            "project_template_variables-MIN_NUM_FORMS": 0,
            "project_template_variables-MAX_NUM_FORMS": 1000,
        }
        for index, var in enumerate(template_variables):
            data.update(
                {
                    f"project_template_variables-{index}-template_variable": var.id,
                    f"project_template_variables-{index}-value": f"{var.name} value",
                }
            )
        return data

    def test_valid_form_and_valid_formset(
        self, client, url, user, data, organization, template_variables, central_server, mocker
    ):
        """Ensures the Project is created when a valid form and valid variables formset are submitted."""
        mocker.patch("apps.publish_mdm.views.create_project", return_value=10)
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # Ensure the Project is created with the expected values
        project = Project.objects.get()
        assert project.name == "New name"
        assert project.central_id == 10
        assert project.organization == organization
        assert project.central_server == central_server
        assert project.app_language == "ar"
        assert set(project.template_variables.all()) == set(template_variables)
        # Ensure ProjectTemplateVariables are created
        assert set(
            project.project_template_variables.values_list("template_variable", "value")
        ) == {(var.id, f"{var.name} value") for var in template_variables}
        # Ensure the view redirects to the form templates list page
        assert response.redirect_chain == [
            (
                reverse(
                    "publish_mdm:form-template-list", args=[project.organization.slug, project.id]
                ),
                302,
            )
        ]
        # Ensure there is a success message
        assert f"Successfully added {project}." in response.content.decode()

    def test_valid_form_and_formset_but_odk_create_project_error(
        self, client, url, user, data, mocker
    ):
        """Ensures a Project is not created in the database if there is an error
        creating the project in ODK Central, and an error message is displayed to
        the user.
        """
        exception = HTTPError("ODK API request error")
        mocker.patch("apps.publish_mdm.views.create_project", side_effect=exception)
        response = client.post(url, data=data)
        assert not Project.objects.exists()
        # Ensure the expected error message is displayed on the page
        expected_error = (
            "The following error occurred when creating the project in "
            "ODK Central. The project has not been saved."
            f'<code class="block text-xs mt-2">{exception}</code>'
        )
        assert expected_error in response.content.decode()

    def test_invalid_form(self, client, url, user, data):
        """Ensures form errors are displayed to the user."""
        data.update(
            {
                "name": "",
                "central_server": "",
            }
        )
        response = client.post(url, data=data)
        assert not Project.objects.exists()
        assert response.context["form"].errors == {
            "name": ["This field is required."],
            "central_server": ["This field is required."],
        }

    def test_valid_form_and_invalid_formset(self, client, url, user, data):
        """Test a form with a valid name and invalid template variables formset."""
        data["project_template_variables-0-template_variable"] = ""
        response = client.post(url, data=data)
        assert not Project.objects.exists()
        # Ensure the expected error message is displayed on the page
        expected_error = "This field is required."
        assert (
            response.context["variables_formset"].errors[0]["template_variable"][0]
            == expected_error
        )
        assert expected_error in response.content.decode()

    def test_invalid_template_variable_choice(self, client, url, user, data):
        """Ensure cannot select a template variable that is not linked to the project's
        organization, both in the form and in the variables formset.
        """
        template_variable = TemplateVariableFactory()
        data.update(
            {
                "template_variables": [template_variable.id],
                "project_template_variables-0-template_variable": template_variable.id,
            }
        )
        response = client.post(url, data=data)
        assert not Project.objects.exists()
        # Ensure the expected form error message is displayed on the page
        response_content = response.content.decode()
        expected_error = (
            f"Select a valid choice. {template_variable.id} is not one of the available choices."
        )
        assert response.context["form"].errors["template_variables"][0] == expected_error
        assert expected_error in response_content
        # Ensure the expected formset error message is displayed on the page
        expected_error = "Select a valid choice. That choice is not one of the available choices."
        assert (
            response.context["variables_formset"].errors[0]["template_variable"][0]
            == expected_error
        )
        assert expected_error in response_content


class TestEditProject(ViewTestBase):
    @pytest.fixture
    def url(self, project):
        return reverse(
            "publish_mdm:edit-project",
            kwargs={"organization_slug": project.organization.slug, "odk_project_pk": project.pk},
        )

    def test_get(self, client, url, user, project):
        response = client.get(url)
        assert response.status_code == 200
        assert response.context["form"].instance == project

    @pytest.fixture
    def other_central_server(self):
        return CentralServerFactory()

    @pytest.fixture
    def template_variables(self, project):
        return TemplateVariableFactory.create_batch(2, organization=project.organization)

    @pytest.fixture
    def data(self, project, template_variables):
        """POST data with a different valid name and valid formset data that changes
        an existing ProjectTemplateVariable and adds a new one.
        """
        var = template_variables[0]
        project_template_var = project.project_template_variables.create(
            template_variable=var, value=f"{var.name} value"
        )
        new_var = template_variables[1]
        return {
            "name": "New name",
            "central_server": project.central_server_id,
            "project_template_variables-TOTAL_FORMS": 2,
            "project_template_variables-INITIAL_FORMS": 1,
            "project_template_variables-MIN_NUM_FORMS": 0,
            "project_template_variables-MAX_NUM_FORMS": 1000,
            "project_template_variables-0-project": project.id,
            "project_template_variables-0-id": project_template_var.id,
            "project_template_variables-0-template_variable": project_template_var.template_variable_id,
            "project_template_variables-0-value": f"edited {project_template_var.value}",
            "project_template_variables-1-template_variable": new_var.id,
            "project_template_variables-1-value": f"edited {new_var.name} value",
        }

    def test_valid_form_and_valid_formset(
        self, client, url, user, project, data, template_variables, other_central_server, mocker
    ):
        """Ensures the Project is updated when a valid form and valid variables formset are submitted."""
        data.update(
            {
                "central_server": other_central_server.id,
                "template_variables": [i.id for i in template_variables],
                "app_language": "ar",
            }
        )
        mocker.patch("apps.publish_mdm.views.generate_and_save_app_user_collect_qrcodes")
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        project.refresh_from_db()
        assert project.name == "New name"
        assert project.central_server == other_central_server
        assert project.app_language == "ar"
        assert set(project.template_variables.all()) == set(template_variables)
        # Ensure the existing ProjectTemplateVariable was changed and a new one was added
        assert project.project_template_variables.count() == 2
        for var in project.project_template_variables.all():
            assert var.value == f"edited {var.template_variable.name} value"
        # Ensure the view redirects to the form templates list page
        assert response.redirect_chain == [
            (
                reverse(
                    "publish_mdm:form-template-list", args=[project.organization.slug, project.id]
                ),
                302,
            )
        ]
        # Ensure there is a success message
        assert f"Successfully edited {project}." in response.content.decode()

    @pytest.mark.parametrize("changed_field", [None, "admin_pw"] + ProjectForm._meta.fields)
    def test_regenerating_qr_codes(
        self,
        client,
        url,
        user,
        project,
        template_variables,
        other_central_server,
        mocker,
        changed_field,
    ):
        """Ensures app user QR codes are regenerated when form fields that impact
        them are changed.
        """
        mock_generate_qr_codes = mocker.patch(
            "apps.publish_mdm.views.generate_and_save_app_user_collect_qrcodes"
        )
        data = {
            "name": project.name,
            "central_server": project.central_server_id,
            "app_language": project.app_language,
            "template_variables": [],
            "project_template_variables-TOTAL_FORMS": 0,
            "project_template_variables-INITIAL_FORMS": 0,
            "project_template_variables-MIN_NUM_FORMS": 0,
            "project_template_variables-MAX_NUM_FORMS": 1000,
        }
        new_values = {
            "app_language": "ar",
            "name": project.name + " edited",
            "central_server": other_central_server.id,
            "template_variables": [i.id for i in template_variables],
        }
        # QR codes should be regenerated if any of these fields are changed
        should_regenerate = ("app_language", "name", "admin_pw")

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

    def test_valid_form_and_valid_formset_deleting_variable(
        self, client, url, user, project, data, template_variables, other_central_server, mocker
    ):
        """Test a valid form and valid template variables formset that deletes
        the existing ProjectTemplateVariable.
        """
        data.update(
            {
                "central_server": other_central_server.id,
                "template_variables": [i.id for i in template_variables],
                "project_template_variables-0-DELETE": "on",
            }
        )
        mocker.patch("apps.publish_mdm.views.generate_and_save_app_user_collect_qrcodes")
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        project.refresh_from_db()
        assert project.name == "New name"
        assert project.central_server == other_central_server
        assert set(project.template_variables.all()) == set(template_variables)
        # Ensure the existing ProjectTemplateVariable was changed and a new one was added
        assert project.project_template_variables.count() == 1
        project_template_var = project.project_template_variables.get()
        assert project_template_var.template_variable == template_variables[1]
        # Ensure the view redirects to the form templates list page
        assert response.redirect_chain == [
            (
                reverse(
                    "publish_mdm:form-template-list", args=[project.organization.slug, project.id]
                ),
                302,
            )
        ]
        # Ensure there is a success message
        assert f"Successfully edited {project}." in response.content.decode()

    def check_invalid_form_or_formset(self, project, data, response):
        assert response.status_code == 200
        # The Project was not changed
        project.refresh_from_db()
        assert project.name != data["name"]
        # Ensure the existing ProjectTemplateVariable was not changed and a new one was not added
        assert project.project_template_variables.count() == 1
        for var in project.project_template_variables.all():
            assert var.value != f"edited {var.template_variable.name} value"
        # The form and template variables formset are included in the context
        assert isinstance(response.context.get("form"), ProjectForm)
        assert isinstance(response.context.get("variables_formset"), ProjectTemplateVariableFormSet)

    def test_invalid_form(self, client, url, user, project, data):
        data.update(
            {
                "name": "",
                "central_server": "",
            }
        )
        response = client.post(url, data=data)
        self.check_invalid_form_or_formset(project, data, response)
        assert response.context["form"].errors == {
            "name": ["This field is required."],
            "central_server": ["This field is required."],
        }

    def test_valid_form_and_invalid_formset(self, client, url, user, project, data):
        """Test a form with a valid name and invalid template variables formset."""
        data["project_template_variables-0-template_variable"] = ""
        response = client.post(url, data=data)
        self.check_invalid_form_or_formset(project, data, response)
        # Ensure the expected error message is displayed on the page
        expected_error = "This field is required."
        assert (
            response.context["variables_formset"].errors[0]["template_variable"][0]
            == expected_error
        )
        assert expected_error in response.content.decode()

    def test_invalid_template_variable_choice(self, client, url, user, project, data):
        """Ensure cannot select a template variable that is not linked to the project's
        organization, both in the form and in the variables formset.
        """
        template_variable = TemplateVariableFactory()
        data.update(
            {
                "template_variables": [template_variable.id],
                "project_template_variables-0-template_variable": template_variable.id,
            }
        )
        response = client.post(url, data=data)
        self.check_invalid_form_or_formset(project, data, response)
        # Ensure the expected form error message is displayed on the page
        response_content = response.content.decode()
        expected_error = (
            f"Select a valid choice. {template_variable.id} is not one of the available choices."
        )
        assert response.context["form"].errors["template_variables"][0] == expected_error
        assert expected_error in response_content
        # Ensure the expected formset error message is displayed on the page
        expected_error = "Select a valid choice. That choice is not one of the available choices."
        assert (
            response.context["variables_formset"].errors[0]["template_variable"][0]
            == expected_error
        )
        assert expected_error in response_content


class TestOrganizationHome(ViewTestBase):
    @pytest.fixture
    def organization(self, user):
        organization = OrganizationFactory()
        organization.users.add(user)
        return organization

    @pytest.fixture
    def url(self, organization):
        return reverse(
            "publish_mdm:organization-home",
            kwargs={
                "organization_slug": organization.slug,
            },
        )


class TestCreateOrganization(ViewTestBase):
    @pytest.fixture
    def url(self):
        return reverse("publish_mdm:create-organization")

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
                    "publish_mdm:organization-home",
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


class TestOrganizationUsersList(ViewTestBase):
    @pytest.fixture
    def organization(self, user):
        organization = OrganizationFactory()
        organization.users.add(user)
        return organization

    @pytest.fixture
    def url(self, organization):
        return reverse(
            "publish_mdm:organization-users-list",
            kwargs={
                "organization_slug": organization.slug,
            },
        )

    def test_remove_self_from_organization(self, client, url, user, organization):
        """Test a user removing themself from the organization."""
        data = {
            "remove": user.id,
        }
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # Ensure the user is removed from the organization
        assert organization.users.count() == 0
        # Ensure the view redirects to the home page
        assert response.redirect_chain == [(reverse("home"), 302)]
        # Ensure there is a success message
        assert f"You have left {organization}." in response.content.decode()

    def test_remove_another_user_from_organization(self, client, url, user, organization):
        """Test removing another user from the organization."""
        other_user = UserFactory()
        organization.users.add(other_user)
        # Create an accepted invitation with the user's email to the organization
        OrganizationInvitationFactory(
            email=other_user.email.upper(), accepted=True, organization=organization
        )
        # Create invitations to other organizations
        other_orgs_invitations = OrganizationInvitationFactory.create_batch(
            2, email=other_user.email
        )
        data = {
            "remove": other_user.id,
        }
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # Ensure the user is removed from the organization
        assert organization.users.count() == 1
        # Ensure any accepted invitation for the user's email to the organization is deleted
        assert not organization.organizationinvitation_set.filter(
            email__iexact=other_user.email
        ).exists()
        # Invitations to other organizations should still exist
        assert set(OrganizationInvitation.objects.filter(email__iexact=other_user.email)) == set(
            other_orgs_invitations
        )
        # Ensure the view redirects back to the users list page
        assert response.redirect_chain == [
            (
                reverse("publish_mdm:organization-users-list", args=[organization.slug]),
                302,
            )
        ]
        # Ensure there is a success message
        assert (
            f"You have removed {other_user.get_full_name()} ({other_user.email}) from {organization}."
            in response.content.decode()
        )

    def test_invalid_user_id(self, client, url, user, organization):
        """Test attempting to remove a user that is not part of the organization.
        Should be ignored without an error.
        """
        other_user = UserFactory()
        data = {
            "remove": other_user.id,
        }
        response = client.post(url, data=data)
        assert response.status_code == 200
        # Organization users should be unchanged
        assert organization.users.count() == 1


class TestSendOrganizationInvite(ViewTestBase):
    @pytest.fixture
    def organization(self, user):
        organization = OrganizationFactory()
        organization.users.add(user)
        return organization

    @pytest.fixture
    def url(self, organization):
        return reverse(
            "publish_mdm:send-invite",
            kwargs={
                "organization_slug": organization.slug,
            },
        )

    def test_get(self, client, url, user):
        response = client.get(url)
        assert response.status_code == 200
        assert isinstance(response.context.get("form"), OrganizationInviteForm)

    def valid_form(self, client, url, user, organization, data, mailoutbox):
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # Ensure the expected OrganizationInvitation is created in the DB
        qs = organization.organizationinvitation_set.filter(email=data["email"])
        assert qs.count() == 1
        invitation = qs.get()
        assert invitation.inviter == user
        assert not invitation.accepted
        assert invitation.sent is not None
        assert not invitation.key_expired()
        # Ensure an invitation email was sent
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == [data["email"]]
        # Ensure the user is redirected to the organization home page
        assert response.redirect_chain == [
            (
                reverse("publish_mdm:organization-home", args=[organization.slug]),
                302,
            )
        ]

    def invalid_form(self, client, url, user, organization, data, expected_error, mailoutbox):
        response = client.post(url, data=data)
        assert response.status_code == 200
        assert isinstance(response.context.get("form"), OrganizationInviteForm)
        # Ensure the expected error message is displayed on the page
        assert response.context["form"].errors["email"][0] == expected_error
        assert expected_error in response.content.decode()
        assert len(mailoutbox) == 0

    def test_valid_form(self, client, url, user, organization, mailoutbox):
        """Test sending a valid organization invite."""
        data = {
            "email": "test@test.com",
        }
        self.valid_form(client, url, user, organization, data, mailoutbox)

    def test_same_email_different_organization(self, client, url, user, organization, mailoutbox):
        """Test sending an invitation to an email that has already been
        invited to another organization. This should be allowed.
        """
        invitation = OrganizationInvitationFactory()
        data = {
            "email": invitation.email,
        }
        self.valid_form(client, url, user, organization, data, mailoutbox)
        assert OrganizationInvitation.objects.count() == 2

    def test_same_email_same_organization(self, client, url, user, organization, mailoutbox):
        """Test attempting to send an invitation to an email that has already been
        invited to the organization. This should not be allowed.
        """
        invitation = OrganizationInvitationFactory(organization=organization)
        data = {
            "email": invitation.email,
        }
        self.invalid_form(
            client,
            url,
            user,
            organization,
            data,
            f"This e-mail address has already been invited to {organization}.",
            mailoutbox,
        )
        assert OrganizationInvitation.objects.count() == 1

    def test_same_email_same_organization_already_accepted(
        self, client, url, user, organization, mailoutbox
    ):
        """Test attempting to send an invitation to an email that has already accepted
        an invitation to the organization. This should not be allowed.
        """
        invitation = OrganizationInvitationFactory(organization=organization, accepted=True)
        data = {
            "email": invitation.email,
        }
        self.invalid_form(
            client,
            url,
            user,
            organization,
            data,
            f"This e-mail address has already accepted an invite to {organization}.",
            mailoutbox,
        )
        assert OrganizationInvitation.objects.count() == 1

    def test_user_already_in_organization(self, client, url, user, organization, mailoutbox):
        """Test attempting to send an invitation to a user that is already in
        the organization.
        """
        organization_user = UserFactory()
        organization.users.add(organization_user)
        data = {
            "email": organization_user.email,
        }
        self.invalid_form(
            client,
            url,
            user,
            organization,
            data,
            f"A user with this e-mail address has already joined {organization}.",
            mailoutbox,
        )
        assert not OrganizationInvitation.objects.exists()


@pytest.mark.django_db
class TestAcceptOrganizationInvite:
    @pytest.fixture
    def invitation(self):
        return OrganizationInvitationFactory(sent=now())

    @pytest.fixture
    def url(self, invitation):
        return reverse("accept-invite", kwargs={"key": invitation.key})

    @pytest.fixture
    def logged_in_user(self, request, client):
        if getattr(request, "param", True):
            user = UserFactory()
            user.save()
            client.force_login(user=user)
            return user

    def test_get(self, client, url, invitation):
        """Ensure visiting a valid invite URL redirects to the login page if a user
        is not logged in. The invitation should not be accepted at this stage, it
        should be accepted after the user signs up / logs in (in
        InvitationsAdapter.post_login()).
        """
        response = client.get(url, follow=True)
        assert response.status_code == 200
        assert response.redirect_chain == [(reverse("account_login"), 302)]
        invitation.refresh_from_db()
        # Invitation not yet accepted
        assert not invitation.accepted
        # Invitation ID stored in session for marking accepted later
        assert client.session.get("invitation_id") == invitation.id

    def test_logged_in_user(self, client, logged_in_user, url, invitation):
        """Ensure visiting a valid invite URL when already logged in immediately
        accepts the invitation and adds the user to the organization.
        """
        response = client.get(url, follow=True)
        assert response.status_code == 200
        invitation.refresh_from_db()
        # Invitation accepted
        assert invitation.accepted
        # User added to the organization
        assert invitation.organization.users.filter(id=logged_in_user.id).exists()
        # Redirected to the organization homepage
        assert response.redirect_chain == [
            (
                reverse("publish_mdm:organization-home", args=[invitation.organization.slug]),
                302,
            )
        ]
        assert "invitation_id" not in client.session
        assert (
            f"Invitation to - {invitation.email} - has been accepted" in response.content.decode()
        )

    def check_invalid_invitation(self, client, url, logged_in_user, expected_error_message):
        response = client.get(url, follow=True)
        assert response.status_code == 200
        expected_redirect_chain = [(reverse("account_login"), 302)]
        if logged_in_user:
            expected_redirect_chain.append((reverse("home"), 302))
        assert response.redirect_chain == expected_redirect_chain
        assert "invitation_id" not in client.session
        assert expected_error_message in response.content.decode()

    @pytest.mark.parametrize("logged_in_user", [False, True], indirect=True)
    def test_already_accepted(self, client, logged_in_user, url, invitation):
        """If the invitation has already been accepted, redirect with an error message."""
        invitation.accepted = True
        invitation.save()
        self.check_invalid_invitation(
            client,
            url,
            logged_in_user,
            f"The invitation for {invitation.email} was already accepted.",
        )

    @pytest.mark.parametrize("logged_in_user", [False, True], indirect=True)
    def test_expired_invitation(self, client, logged_in_user, url, invitation, mocker):
        """If the invitation has expired, redirect with an error message."""
        mocker.patch.object(OrganizationInvitation, "key_expired", return_value=True)
        self.check_invalid_invitation(
            client, url, logged_in_user, f"The invitation for {invitation.email} has expired."
        )

    @pytest.mark.parametrize("logged_in_user", [False, True], indirect=True)
    def test_invalid_key(self, client, logged_in_user):
        """If the invitation key is invalid, redirect with an error message."""
        url = reverse("accept-invite", kwargs={"key": "invalidkey"})
        self.check_invalid_invitation(
            client, url, logged_in_user, "An invalid invitation key was submitted."
        )


class TestOrganizationTemplateVariables(ViewTestBase):
    """Tests the page for editing an organization's template variables."""

    @pytest.fixture
    def url(self, organization):
        return reverse(
            "publish_mdm:organization-template-variables",
            kwargs={"organization_slug": organization.slug},
        )

    @pytest.fixture
    def template_variables(self, organization):
        return [
            organization.template_variables.create(
                name="var1", transform=VariableTransform.SHA256_DIGEST
            ),
            organization.template_variables.create(name="var2"),
        ]

    def test_get(self, client, url, user, organization, template_variables):
        response = client.get(url)
        assert response.status_code == 200
        assert isinstance(response.context.get("formset"), TemplateVariableFormSet)
        assert response.context["formset"].instance == organization
        assert len(response.context["formset"].forms) == len(template_variables)

    @pytest.fixture
    def data(self, template_variables):
        """Form data that would edit the first template variable, delete the other
        template variable, and add one new template variable.
        """
        template_variables_count = len(template_variables)
        data = {
            "template_variables-TOTAL_FORMS": template_variables_count + 1,
            "template_variables-INITIAL_FORMS": template_variables_count,
            "template_variables-MIN_NUM_FORMS": 0,
            "template_variables-MAX_NUM_FORMS": 1000,
            # The new template variable
            f"template_variables-{template_variables_count}-name": "new_var",
            f"template_variables-{template_variables_count}-transform": VariableTransform.SHA256_DIGEST.value,
        }
        for index, var in enumerate(template_variables):
            data.update(
                {
                    f"template_variables-{index}-id": var.id,
                    f"template_variables-{index}-organization": var.organization_id,
                    f"template_variables-{index}-name": var.name,
                    f"template_variables-{index}-transform": var.transform,
                }
            )
            if index:
                # Delete the template variable
                data[f"template_variables-{index}-DELETE"] = "on"
            else:
                # Edit the template variable
                data.update(
                    {
                        f"template_variables-{index}-name": "var1_edited",
                        f"template_variables-{index}-transform": "",
                    }
                )
        return data

    def test_valid_formset(self, client, url, user, organization, data, template_variables):
        """Test submitting valid data for the formset."""
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # Ensure one template variable has been edited, one deleted, and a new one added
        assert organization.template_variables.count() == 2
        updated_var = organization.template_variables.get(pk=template_variables[0].pk)
        assert updated_var.name == "var1_edited"
        assert updated_var.transform == ""
        new_var = organization.template_variables.exclude(pk=template_variables[0].pk).get()
        assert new_var.name == "new_var"
        assert new_var.transform == VariableTransform.SHA256_DIGEST.value
        # Ensure the view redirects back to the template variables page
        assert response.redirect_chain == [(url, 302)]
        # Ensure there is a success message
        assert (
            f"Successfully edited template variables for {organization}."
            in response.content.decode()
        )

    def test_invalid_formset(self, client, url, user, organization, data, template_variables):
        """Test submitting invalid data for the formset."""
        template_variables_count = len(template_variables)
        # Invalid name for the new template variable
        data[f"template_variables-{template_variables_count}-name"] = "12345"
        response = client.post(url, data=data, follow=True)
        assert response.status_code == 200
        # The template variables should be unchanged
        assert organization.template_variables.count() == template_variables_count
        for var in template_variables:
            assert (var.name, var.transform) == organization.template_variables.values_list(
                "name", "transform"
            ).get(pk=var.pk)
        # Ensure the expected error message is displayed on the page
        expected_error = "Name must start with a letter or underscore and contain no spaces."
        assert response.context["formset"].forms[-1].errors["name"][0] == expected_error
        assert expected_error in response.content.decode()


class TestDevicesList(ViewTestBase):
    """Tests the page that lists the MDM devices linked to a Project."""

    @pytest.fixture
    def url(self, project, organization):
        return reverse("publish_mdm:devices-list", args=[organization.slug, project.id])

    @staticmethod
    def format_datetime(datetime):
        """Format a datetime object the same way the django-tables2 DateTimeColumn does."""
        return date_format(localtime(datetime), settings.SHORT_DATETIME_FORMAT)

    def test_get(self, client, url, user, project, organization):
        # Set up some devices in 2 policies linked to the current project
        project_devices = []
        for policy in PolicyFactory.create_batch(2, project=project):
            # Some devices with values for serial_number and app_user_name
            for device in DeviceFactory.build_batch(5, policy=policy):
                # serial_number and device_id with mixed cases to test matching
                # to Tailscale devices
                device.serial_number = fake.pystr()
                device.device_id = fake.unique.pystr()
                device.save()
                project_devices.append(device)
            # Some devices with blank serial_number
            project_devices += DeviceFactory.create_batch(3, serial_number="", policy=policy)
            # Some devices with blank app_user_name
            project_devices += DeviceFactory.create_batch(2, app_user_name="", policy=policy)

        # Create matching Tailscale devices for some MDM devices
        ts_devices = []
        for device in fake.random_sample(project_devices, 10):
            if fake.boolean() and device.serial_number:
                # matches by serial number
                matcher = device.serial_number.lower()
            else:
                # matches by device id
                matcher = device.device_id.lower()
            ts_devices += TailscaleDeviceFactory.create_batch(
                3, name=f"{fake.word()}-{matcher}.tail123.ts.net"
            )

        # Create a device snapshot for some devices
        for device in fake.random_sample(project_devices, 10):
            device.latest_snapshot = DeviceSnapshotFactory(mdm_device=device)
            device.save()

        # Create firmware snapshots for some devices. firmware_versions will hold
        # the version from the latest snapshot by synced_at
        firmware_versions = {}
        for device in fake.random_sample(project_devices, 10):
            versions = {
                i.synced_at: i.version
                for i in FirmwareSnapshotFactory.create_batch(3, device=device)
            }
            firmware_versions[device.id] = versions[sorted(versions)[-1]]

        # Some devices in another project. Should not be included in the list
        DeviceFactory.create_batch(3, policy__project=ProjectFactory(organization=organization))

        def get_last_seen_vpn(device):
            # The last_seen from the most recent Tailscale Device (by last_seen)
            # whose name contains either:
            # (a) the lowercase serial number of the MDM device, or
            # (b) the lowercase device id of the MDM device
            matching = [
                ts_device.last_seen
                for ts_device in ts_devices
                if (
                    (device.serial_number and device.serial_number.lower() in ts_device.name)
                    or (device.device_id and device.device_id.lower() in ts_device.name)
                )
            ]
            if matching:
                last_seen = sorted(matching)[-1]
                return self.format_datetime(last_seen)
            return table.default

        response = client.get(url)

        assert response.status_code == 200
        # Ensure the devices table is included in the context and it has the
        # expected data
        table = response.context.get("table")
        assert isinstance(table, Table)
        rows = response.context["table"].as_values()
        assert next(rows) == [
            "Serial number",
            "App user name",
            "Firmware version",
            "Last seen (MDM)",
            "Last seen (VPN)",
        ]
        rows = {tuple(i) for i in rows}
        assert rows == {
            (
                i.serial_number or None,
                i.app_user_name or None,
                firmware_versions.get(i.id),
                (
                    self.format_datetime(i.latest_snapshot.last_sync)
                    if i.latest_snapshot
                    else table.default
                ),
                get_last_seen_vpn(i),
            )
            for i in project_devices
        }
        # All columns are sortable
        assert table.orderable
        # Not paginated
        assert not hasattr(table, "paginator")
        # Ensure the table is rendered in the page
        assert table.as_html(response.wsgi_request) in response.content.decode()
