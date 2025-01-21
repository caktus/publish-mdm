from django.db.models import QuerySet
from django.http import HttpRequest as HttpRequestBase
from django_htmx.middleware import HtmxDetails

from .models import Project
from .nav import Breadcrumbs


class HttpRequest(HttpRequestBase):
    """Custom HttpRequest class for type-checking purposes."""

    htmx: HtmxDetails
    odk_project = Project | None
    odk_project_tabs = Breadcrumbs | None
    odk_projects = QuerySet[Project] | None
