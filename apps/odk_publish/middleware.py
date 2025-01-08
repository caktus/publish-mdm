import structlog

from django.http import HttpRequest
from django.urls import ResolverMatch

from .models import Project

logger = structlog.getLogger(__name__)


class ODKProjectMiddleware:
    """Middleware to lookup the current ODK project based on the URL.

    The `odk_project` and `odk_projects` attributes are added to the request object.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        return self.get_response(request)

    def process_view(self, request: HttpRequest, view_func, view_args, view_kwargs):
        # Set common context for all views
        request.odk_project = None
        request.odk_projects = Project.objects.select_related()
        # Automatically lookup the current project
        resolver_match: ResolverMatch = request.resolver_match
        if (
            "odk_publish" in resolver_match.namespaces
            and "odk_project_pk" in resolver_match.captured_kwargs
        ):
            odk_project_pk = resolver_match.captured_kwargs["odk_project_pk"]
            project = Project.objects.select_related().filter(pk=odk_project_pk).first()
            logger.debug("odk_project_pk detected", odk_project_pk=odk_project_pk, project=project)
            request.odk_project = project
