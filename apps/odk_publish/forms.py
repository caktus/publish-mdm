from django import forms
from django.http import QueryDict
from django.urls import reverse_lazy

from apps.patterns.forms import PlatformFormMixin
from apps.patterns.widgets import Select, TextInput

from .etl.odk.client import ODKPublishClient
from .http import HttpRequest
from .models import FormTemplate


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


class PublishTemplateForm(PlatformFormMixin, forms.Form):
    """Form for publishing a form template to ODK Central."""

    form_template = forms.IntegerField(widget=forms.HiddenInput())
    app_users = forms.CharField(
        required=False,
        label="Limit App Users",
        help_text="Publish to a limited set of app users by entering a comma-separated list.",
        widget=TextInput(attrs={"placeholder": "e.g., 10001, 10002, 10003"}),
    )

    def __init__(self, request: HttpRequest, form_template: FormTemplate, *args, **kwargs):
        self.request = request
        kwargs["initial"] = {"form_template": form_template.id}
        super().__init__(*args, **kwargs)

    def clean_app_users(self):
        """Validate by checking if the entered app users are in this project."""
        if app_users := self.cleaned_data.get("app_users"):
            app_users_list = app_users.split(",")
            app_users_in_db = self.request.odk_project.app_users.filter(
                name__in=app_users_list
            ).order_by("name")
            if not len(app_users_in_db) == len(app_users_list):
                invalid_users = sorted(
                    set(app_users_list) - {user.name for user in app_users_in_db}
                )
                error_message = "Invalid App Users: " + ", ".join(invalid_users)
                raise forms.ValidationError(error_message)
            return app_users_in_db
        return []
