import structlog

from django.http import HttpRequest
from django.urls import ResolverMatch
from django.shortcuts import get_object_or_404

from .models import Organization, Project
from .nav import Breadcrumbs

logger = structlog.getLogger(__name__)


class ODKProjectMiddleware:
    """Middleware to lookup the current ODK project based on the URL.

    The `odk_project`, `odk_project_tabs` and `odk_projects` attributes are
    added to the request object.

    This must come after OrganizationMiddleware in the MIDDLEWARE setting to ensure
    `request.organization` is set correctly if an organization slug is in the URL.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        return self.get_response(request)

    def process_view(self, request: HttpRequest, view_func, view_args, view_kwargs):
        # Set common context for all views
        request.odk_project = None
        request.odk_project_tabs = []
        request.odk_projects = Project.objects.select_related()
        if not getattr(request, "organization", None):
            request.organization = Organization.objects.order_by("created_at").first()
        if request.organization:
            request.odk_projects = request.organization.projects.select_related()
        # Automatically lookup the current project
        resolver_match: ResolverMatch = request.resolver_match
        if (
            "odk_publish" in resolver_match.namespaces
            and "odk_project_pk" in resolver_match.captured_kwargs
            and request.organization
        ):
            odk_project_pk = resolver_match.captured_kwargs["odk_project_pk"]
            project = get_object_or_404(request.odk_projects, pk=odk_project_pk)
            logger.debug(
                "odk_project_pk detected",
                odk_project_pk=odk_project_pk,
                project=project,
                organization=request.organization,
            )
            request.odk_project = project
            request.odk_project_tabs = Breadcrumbs.from_items(
                request=request,
                items=[
                    ("Form Templates", "form-template-list"),
                    ("App Users", "app-user-list"),
                ],
            )


class OrganizationMiddleware:
    """Middleware to look up the current organization based on the URL.

    The `organization` and `organizations` attributes are added to the request object.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        return self.get_response(request)

    def process_view(self, request: HttpRequest, view_func, view_args, view_kwargs):
        request.organizations = Organization.objects.order_by("created_at")
        request.organization = None
        # Automatically lookup the current project
        resolver_match: ResolverMatch = request.resolver_match
        if (
            "odk_publish" in resolver_match.namespaces
            and "organization_slug" in resolver_match.captured_kwargs
        ):
            organization_slug = resolver_match.captured_kwargs["organization_slug"]
            organization = get_object_or_404(request.organizations, slug=organization_slug)
            logger.debug(
                "organization_slug detected",
                organization_slug=organization_slug,
                organization=organization,
            )
            request.organization = organization
