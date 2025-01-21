from django import forms
from django.http import QueryDict
from django.urls import reverse_lazy

from apps.patterns.forms import PlatformFormMixin
from apps.patterns.widgets import Select

from .etl.odk.client import ODKPublishClient
from .http import HttpRequest


class ProjectSyncForm(PlatformFormMixin, forms.Form):
    """Form for syncing projects from an ODK Central server.

    In addition to processing the form normally, this form also handles
    render logic for the project field during an HTMX request.
    """

    server = forms.ChoiceField(
        # When a server is selected, the project field below is populated with
        # the available projects for that server using HMTX.
        widget=Select(
            attrs={
                "hx-trigger": "change",
                "hx-get": reverse_lazy("odk_publish:server-sync-projects"),
                "hx-target": "#id_project_container",
                "hx-swap": "innerHTML",
                "hx-indicator": ".loading",
            }
        ),
    )
    project = forms.ChoiceField(widget=Select(attrs={"disabled": "disabled"}))

    def __init__(self, request: HttpRequest, data: QueryDict, *args, **kwargs):
        htmx_data = data.copy() if request.htmx else {}
        # Don't bind the form on an htmx request, otherwise we'll see "This
        # field is required" errors
        data = data if not request.htmx else None
        super().__init__(data, *args, **kwargs)
        # The server field is populated with the available ODK Central servers
        # (from an environment variable) when the form is rendered. Loaded here to
        # avoid fetching during the project initialization sequence.
        self.fields["server"].choices = [("", "Select an ODK Central server...")] + [
            (config.base_url, config.base_url) for config in ODKPublishClient.get_configs().values()
        ]
        # Set `project` field choices when a server is provided either via a
        # POST or HTMX request
        if server := htmx_data.get("server") or self.data.get("server"):
            self.set_project_choices(base_url=server)
            self.fields["project"].widget.attrs.pop("disabled", None)

    def set_project_choices(self, base_url: str):
        with ODKPublishClient(base_url=base_url) as client:
            self.fields["project"].choices = [
                (project.id, project.name) for project in client.projects.list()
            ]
