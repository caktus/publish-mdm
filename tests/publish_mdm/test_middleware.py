import pytest
from django.http.response import Http404
from django.urls import reverse, resolve

from apps.publish_mdm.middleware import OrganizationMiddleware, ODKProjectMiddleware
from apps.publish_mdm.models import Organization

from .factories import CentralServerFactory, OrganizationFactory, ProjectFactory
from tests.users.factories import UserFactory


@pytest.mark.django_db
class TestCustomMiddleware:
    """Tests that OrganizationMiddleware and ODKProjectMiddleware set the expected
    attributes on the HttpRequest objects.
    """

    @pytest.fixture
    def user(self):
        return UserFactory()

    @pytest.fixture
    def organizations(self, user):
        organizations = OrganizationFactory.create_batch(3)
        for org in organizations:
            org.users.add(user)
        return organizations

    @pytest.fixture
    def projects(self, organizations):
        """Create projects in each of the organizations."""
        projects = []
        for organization in organizations:
            central_server = CentralServerFactory(organization=organization)
            projects += ProjectFactory.create_batch(
                3, central_server=central_server, organization=organization
            )
        return projects

    @pytest.fixture
    def middleware(self, mocker):
        """Create instances of the middleware classes that we'll be testing."""
        # Mock get_response function needed to create a middleware instance
        get_response = mocker.MagicMock()
        organization_middleware = OrganizationMiddleware(get_response)
        odk_project_middleware = ODKProjectMiddleware(get_response)
        return [organization_middleware, odk_project_middleware]

    def get_request(self, rf, url, user):
        """Create a HttpRequest object using a RequestFactory."""
        # Create a request object using the RequestFactory
        request = rf.get(url)
        # Set the user attribute
        request.user = user
        # We use the resolver_match object in the middleware but it's not set
        # for requests generated using a RequestFactory, so we'll set it manually
        request.resolver_match = resolve(url)
        return request

    def test_valid_organization_slug_and_project_id(
        self, organizations, projects, rf, middleware, user
    ):
        """Tests the middleware with a valid URL that includes an organization slug and a project ID."""
        project = projects[0]
        url_args = [project.organization.slug, project.pk]
        url = reverse("publish_mdm:app-user-list", args=url_args)
        request = self.get_request(rf, url, user)
        view_func, view_args, view_kwargs = request.resolver_match

        for m in middleware:
            response = m.process_view(request, view_func, view_args, view_kwargs)
            assert response is None

        assert request.organization == project.organization
        assert set(request.organizations) == set(organizations)
        assert request.odk_project == project
        assert set(request.odk_projects) == set(request.organization.projects.all())
        assert [(i.label, i.path) for i in request.odk_project_tabs] == [
            ("Form Templates", reverse("publish_mdm:form-template-list", args=url_args)),
            ("App Users", url),
        ]

    def test_valid_organization_slug(self, organizations, rf, middleware, user):
        """Tests the middleware with a valid URL that includes an organization slug but no project ID."""
        organization = organizations[0]
        url = reverse("publish_mdm:server-sync", args=[organization.slug])
        request = self.get_request(rf, url, user)
        view_func, view_args, view_kwargs = request.resolver_match

        for m in middleware:
            response = m.process_view(request, view_func, view_args, view_kwargs)
            assert response is None

        assert request.organization == organization
        assert set(request.organizations) == set(organizations)
        assert request.odk_project is None
        assert set(request.odk_projects) == set(request.organization.projects.all())
        assert request.odk_project_tabs == []

    def test_homepage(self, organizations, rf, middleware, user):
        """Test the middleware on the homepage."""
        url = "/"
        request = self.get_request(rf, url, user)
        view_func, view_args, view_kwargs = request.resolver_match

        for m in middleware:
            response = m.process_view(request, view_func, view_args, view_kwargs)
            assert response is None

        # Should get the first Organization
        assert request.organization == organizations[0]
        assert set(request.organizations) == set(organizations)
        assert request.odk_project is None
        assert set(request.odk_projects) == set(request.organization.projects.all())
        assert request.odk_project_tabs == []

    def test_homepage_no_organizations(self, rf, middleware, user):
        """Test the middleware on the homepage with no Organizations in the DB."""
        Organization.objects.all().delete()
        url = "/"
        request = self.get_request(rf, url, user)
        view_func, view_args, view_kwargs = request.resolver_match

        for m in middleware:
            response = m.process_view(request, view_func, view_args, view_kwargs)
            assert response is None

        assert request.organization is None
        assert request.organizations.count() == 0
        assert request.odk_project is None
        assert request.odk_projects is None
        assert request.odk_project_tabs == []

    def test_nonexistent_organization(self, rf, middleware, user):
        """Test the middleware with a URL with an organization slug that does not exist."""
        url = reverse("publish_mdm:app-user-list", args=["does-not-exist", 999])
        request = self.get_request(rf, url, user)
        view_func, view_args, view_kwargs = request.resolver_match

        with pytest.raises(Http404):
            middleware[0].process_view(request, view_func, view_args, view_kwargs)

    def test_project_in_different_organization(self, organizations, projects, rf, middleware, user):
        """Test the middleware with a URL with a valid organization slug and valid project ID
        but the project is not linked to that organization.
        """
        url = reverse("publish_mdm:app-user-list", args=[organizations[0].slug, projects[-1].pk])
        request = self.get_request(rf, url, user)
        view_func, view_args, view_kwargs = request.resolver_match

        # OrganizationMiddleware should not raise a 404 error
        response = middleware[0].process_view(request, view_func, view_args, view_kwargs)
        assert response is None

        # ODKProjectMiddleware should raise a 404 error
        with pytest.raises(Http404):
            middleware[1].process_view(request, view_func, view_args, view_kwargs)

    def test_user_not_added_to_organization(self, organizations, projects, rf, middleware, user):
        """Ensure a 404 error is raised for valid URLs if the user does not have access."""
        organization = organizations[0]
        project = projects[0]
        organization.users.remove(user)

        for url in [
            reverse("publish_mdm:server-sync", args=[organization.slug]),
            reverse("publish_mdm:app-user-list", args=[organization.slug, project.pk]),
        ]:
            request = self.get_request(rf, url, user)
            view_func, view_args, view_kwargs = request.resolver_match

            with pytest.raises(Http404):
                middleware[0].process_view(request, view_func, view_args, view_kwargs)
