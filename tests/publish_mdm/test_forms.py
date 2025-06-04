from pathlib import Path

import pytest
from django.forms.widgets import PasswordInput
from django.urls import reverse
from pytest_django.asserts import assertQuerySetEqual, assertFormError
from requests.exceptions import ConnectionError

from apps.patterns.widgets import BaseEmailInput
from apps.publish_mdm.forms import (
    CentralServerForm,
    CentralServerFrontendForm,
    FleetAddForm,
    FleetEditForm,
    ProjectSyncForm,
    PublishTemplateForm,
)
from apps.publish_mdm.http import HttpRequest
from tests.mdm.factories import FleetFactory
from tests.publish_mdm.factories import (
    FormTemplateFactory,
    ProjectFactory,
    AppUserFormTemplateFactory,
    OrganizationFactory,
    CentralServerFactory,
)


@pytest.mark.django_db
class TestPublishTemplateForm:
    """Test the PublishTemplateForm form validation."""

    @pytest.fixture
    def req(self):
        request = HttpRequest()
        request.odk_project = ProjectFactory()
        return request

    def test_no_app_users(self, req: HttpRequest):
        form_template = FormTemplateFactory(project=req.odk_project)
        form = PublishTemplateForm(data={}, request=req, form_template=form_template)
        assert not form.is_valid()
        assert form.cleaned_data["app_users"] == []

    def test_app_users_do_not_exist(self, req: HttpRequest):
        form_template = FormTemplateFactory(project=req.odk_project)
        data = {"app_users": "user1,user2"}
        form = PublishTemplateForm(data=data, request=req, form_template=form_template)
        assert not form.is_valid()
        assert form.errors["app_users"] == ["Invalid App Users: user1, user2"]

    def test_app_users_one_does_not_exist(self, req: HttpRequest):
        form_template = FormTemplateFactory(project=req.odk_project)
        AppUserFormTemplateFactory(
            form_template=form_template, app_user__name="user1", app_user__project=req.odk_project
        )
        data = {"app_users": "user1,user2"}
        form = PublishTemplateForm(data=data, request=req, form_template=form_template)
        assert not form.is_valid()
        assert form.errors["app_users"] == ["Invalid App Users: user2"]

    def test_app_users(self, req: HttpRequest):
        form_template = FormTemplateFactory(project=req.odk_project)
        AppUserFormTemplateFactory(
            form_template=form_template, app_user__name="user1", app_user__project=req.odk_project
        )
        AppUserFormTemplateFactory(
            form_template=form_template, app_user__name="user2", app_user__project=req.odk_project
        )
        data = {"app_users": "user1,user2", "form_template": form_template.id}
        form = PublishTemplateForm(data=data, request=req, form_template=form_template)
        assert form.is_valid(), form.errors

    def test_app_users_with_spaces(self, req: HttpRequest):
        form_template = FormTemplateFactory(project=req.odk_project)
        AppUserFormTemplateFactory(
            form_template=form_template, app_user__name="user1", app_user__project=req.odk_project
        )
        AppUserFormTemplateFactory(
            form_template=form_template, app_user__name="user2", app_user__project=req.odk_project
        )
        data = {"app_users": " user1, user2 ", "form_template": form_template.id}
        form = PublishTemplateForm(data=data, request=req, form_template=form_template)
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestProjectSyncForm:
    """Test ProjectSyncForm, the form for syncing projects with ODK Central."""

    @pytest.fixture
    def organization(self):
        organization = OrganizationFactory()
        # Create some servers in the org that have a username and password
        CentralServerFactory.create_batch(3, organization=organization)
        # Create some servers in the org that don't have all credentials
        CentralServerFactory(organization=organization, username=None, password=None)
        CentralServerFactory(organization=organization, password=None)
        CentralServerFactory(organization=organization, password=None)
        # Create some servers in a different organization
        CentralServerFactory.create_batch(3, organization=OrganizationFactory())
        return organization

    @pytest.fixture
    def req(self, organization, rf):
        # Mock request
        url = reverse("publish_mdm:server-sync", args=[organization.slug])
        request = rf.get(url)
        request.organization = organization
        return request

    def test_non_htmx(self, organization, req):
        req.htmx = False
        expected_servers = organization.central_servers.filter(
            username__isnull=False, password__isnull=False
        )
        form = ProjectSyncForm(req, None)

        assert set(form.fields["server"].queryset) == set(expected_servers)
        assert not form.fields["project"].choices

    def test_htmx(self, organization, req, requests_mock):
        req.htmx = True
        expected_servers = organization.central_servers.filter(
            username__isnull=False, password__isnull=False
        )
        server = expected_servers[0]
        # Mock ODK Central API request to get projects
        json_response = [
            {
                "id": 1,
                "name": "Default Project",
                "description": "Description",
                "createdAt": "2025-04-18T23:19:14.802Z",
            },
            {
                "id": 2,
                "name": "Another Project",
                "description": "Description 2",
                "createdAt": "2025-04-18T23:19:14.802Z",
            },
        ]
        requests_mock.get(f"{server.base_url}/v1/projects", json=json_response)

        form = ProjectSyncForm(req, {"server": str(server.id)})

        assert set(form.fields["server"].queryset) == set(expected_servers)
        assert form.fields["project"].choices == [(i["id"], i["name"]) for i in json_response]


@pytest.mark.django_db
class TestCentralServerForm:
    """Test CentralServerForm, the form for adding/editing Central servers."""

    @pytest.fixture
    def organization(self):
        return OrganizationFactory()

    def test_invalid_form(self, organization):
        """Test form validation."""
        data = {
            "base_url": "invalid_url",
            "username": "invalid_email",
            "password": "",
            "organization": organization.id,
        }
        form = CentralServerForm(data)
        assert not form.is_valid()
        assert form.errors == {
            "base_url": ["Enter a valid URL."],
            "username": ["Enter a valid email address."],
            "password": ["This field is required."],
        }

    @pytest.mark.parametrize("username", ["", "new@test.com"])
    def test_username_and_password_validation(self, organization, requests_mock, username):
        """Ensure the username and password can be blank for an existing server
        if there is already a value saved. If any of them is not blank, the
        credentials should be validated using the ODK API.
        """
        server = CentralServerFactory(organization=organization)
        data = {
            "base_url": server.base_url,
            "username": username,
            "password": "",
            "organization": organization.id,
        }
        mock_odk_request = requests_mock.post(
            f'{data["base_url"]}/v1/sessions',
            json={
                "createdAt": "2018-04-18T03:04:51.695Z",
                "expiresAt": "2018-04-19T03:04:51.695Z",
                "token": "token",
            },
        )
        form = CentralServerForm(data, instance=server)
        assert form.is_valid()
        if username:
            assert mock_odk_request.called_once
        else:
            assert not mock_odk_request.called

    def test_credentials_validation_via_api_successful(self, organization, requests_mock):
        """Test successful validation of the base_url and credentials using an ODK Central
        API request.
        """
        data = {
            "base_url": "https://central.example.com",
            "username": "test@email.com",
            "password": "password",
            "organization": organization.id,
        }
        form = CentralServerForm(data)
        mock_odk_request = requests_mock.post(
            f'{data["base_url"]}/v1/sessions',
            json={
                "createdAt": "2018-04-18T03:04:51.695Z",
                "expiresAt": "2018-04-19T03:04:51.695Z",
                "token": "token",
            },
        )
        assert form.is_valid()
        assert mock_odk_request.called_once

    def test_credentials_validation_via_api_failed(self, organization, requests_mock):
        """Test failed validation of the base_url and credentials using an ODK Central
        API request.
        """
        data = {
            "base_url": "https://central.example.com",
            "username": "test@email.com",
            "password": "password",
            "organization": organization.id,
        }
        form = CentralServerForm(data)
        mock_odk_request = requests_mock.post(
            f'{data["base_url"]}/v1/sessions',
            status_code=401,
            json={
                "code": 401.2,
                "message": "Could not authenticate with the provided credentials.",
            },
        )
        assert not form.is_valid()
        assert mock_odk_request.called_once
        assert form.errors == {
            "__all__": [
                "The base URL and/or login credentials appear to be incorrect. Please try again."
            ],
        }

    def test_credentials_validation_api_request_error(self, organization, requests_mock):
        """Ensure an error message is raised in case of a request error during the
        API request for validating of the base_url and credentials.
        """
        data = {
            "base_url": "https://central.example.com",
            "username": "test@email.com",
            "password": "password",
            "organization": organization.id,
        }
        form = CentralServerForm(data)
        mock_odk_request = requests_mock.post(
            f'{data["base_url"]}/v1/sessions', exc=ConnectionError()
        )
        assert not form.is_valid()
        assert mock_odk_request.called_once
        assert form.errors == {
            "__all__": [
                "The base URL and/or login credentials appear to be incorrect. Please try again."
            ],
        }

    def test_deleting_pyodk_cache_file(self, organization, requests_mock):
        """Ensure an existing PyODK cache file is deleted after updating a CentralServer."""
        server = CentralServerFactory(organization=organization)
        cache_file = Path(f"/tmp/.pyodk_cache_{server.id}.toml")
        cache_file.touch()
        assert cache_file.exists()

        data = {
            "base_url": "https://central.example.com",
            "username": "test@email.com",
            "password": "password",
            "organization": organization.id,
        }
        form = CentralServerForm(data, instance=server)
        requests_mock.post(
            f'{data["base_url"]}/v1/sessions',
            json={
                "createdAt": "2018-04-18T03:04:51.695Z",
                "expiresAt": "2018-04-19T03:04:51.695Z",
                "token": "token",
            },
        )

        assert form.is_valid()
        assert form.save()
        assert not cache_file.exists()

    @pytest.mark.parametrize("form_class", [CentralServerForm, CentralServerFrontendForm])
    @pytest.mark.parametrize("field_name", ["username", "password"])
    def test_password_and_username_input(self, organization, form_class, field_name):
        """Ensure the correct widget is used for username and password fields."""
        # Creating a new CentralServer
        form = form_class()
        field = form.fields[field_name]
        assert isinstance(field.widget, (PasswordInput, BaseEmailInput))
        assert not field.widget.render_value
        assert not field.help_text
        # The field should be required when creating a server
        assert field.required

        # Editing a CentralServer and the field doesn't have a value
        server = CentralServerFactory(organization=organization, **{field_name: None})
        form = form_class(instance=server)
        field = form.fields[field_name]
        assert isinstance(field.widget, (PasswordInput, BaseEmailInput))
        assert not field.widget.render_value
        assert not field.help_text
        # The field should be required if there is currently no value in the DB
        assert field.required

        # Editing a CentralServer and the field has a value
        server = CentralServerFactory(organization=organization)
        form = form_class(instance=server)
        field = form.fields[field_name]
        assert isinstance(field.widget, (PasswordInput, BaseEmailInput))
        assert not field.widget.render_value
        # Help text when editing a server
        assert field.help_text == (
            f"A {field_name} exists. You can leave it blank to keep the current value."
        )
        # The field should not be required if there is already a value in the DB
        assert not field.required


@pytest.mark.django_db
class TestFleetForm:
    @pytest.fixture
    def organization(self):
        return OrganizationFactory()

    @pytest.fixture
    def projects(self, organization):
        return ProjectFactory.create_batch(3, organization=organization)

    @pytest.mark.parametrize("FleetForm", [FleetAddForm, FleetEditForm])
    def test_project_choices(self, organization, projects, FleetForm):
        """Ensures the choices for the project field are the current organization's
        projects only.
        """
        # Create some projects in another organization
        ProjectFactory.create_batch(2, organization=OrganizationFactory())
        form = FleetForm(instance=FleetFactory.build(organization=organization))
        assertQuerySetEqual(form.fields["project"].queryset, projects, ordered=False)

    def test_name_validation(self, organization, projects):
        """Ensures a name cannot be duplicated within the same organization."""
        fleet = FleetFactory(organization=organization)
        # Try to create a Fleet with the same name
        data = {
            "name": fleet.name,
            "project": projects[0].id,
        }
        form = FleetAddForm(data=data, instance=FleetFactory.build(organization=organization))
        assert not form.is_valid()
        assertFormError(
            form, "name", "A fleet with the same name already exists in the current organization."
        )

        # If the existing fleet is in a different organization the form should be valid
        fleet.organization = OrganizationFactory()
        fleet.save()
        form = FleetAddForm(data=data, instance=FleetFactory.build(organization=organization))
        assert form.is_valid()
