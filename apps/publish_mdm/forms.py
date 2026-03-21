from pathlib import Path

import requests
import structlog
from django import forms
from django.conf import settings
from django.http import QueryDict
from django.urls import reverse_lazy
from import_export import forms as import_export_forms
from import_export.tmp_storages import MediaStorage
from invitations.adapters import get_invitations_adapter
from invitations.exceptions import AlreadyAccepted, AlreadyInvited, UserRegisteredEmail

from apps.mdm.models import Fleet
from apps.patterns.forms import PlatformFormMixin
from apps.patterns.widgets import (
    BaseEmailInput,
    CheckboxInput,
    CheckboxSelectMultiple,
    EmailInput,
    FileInput,
    InputWithAddon,
    PasswordInput,
    Select,
    TextInput,
)

from .etl.odk.client import PublishMDMClient
from .http import HttpRequest
from .models import (
    AppUser,
    AppUserTemplateVariable,
    CentralServer,
    FormTemplate,
    Organization,
    OrganizationInvitation,
    Project,
    ProjectTemplateVariable,
    TemplateVariable,
)

logger = structlog.getLogger(__name__)


class ProjectSyncForm(PlatformFormMixin, forms.Form):
    """Form for syncing projects from an ODK Central server.

    In addition to processing the form normally, this form also handles
    render logic for the project field during an HTMX request.
    """

    server = forms.ModelChoiceField(
        # The queryset will be updated based on the current organization in __init__()
        queryset=None,
        # When a server is selected, the project field below is populated with
        # the available projects for that server using HMTX.
        widget=Select(
            attrs={
                "hx-trigger": "change",
                "hx-target": "#id_project_container",
                "hx-swap": "innerHTML",
                "hx-indicator": ".loading",
            }
        ),
        empty_label="Select an ODK Central server...",
    )
    project = forms.ChoiceField(widget=Select(attrs={"disabled": "disabled"}))

    def __init__(self, request: HttpRequest, data: QueryDict, *args, **kwargs):
        htmx_data = data.copy() if request.htmx else {}
        # Don't bind the form on an htmx request, otherwise we'll see "This
        # field is required" errors
        data = data if not request.htmx else None
        super().__init__(data, *args, **kwargs)
        # The server field is populated with the CentralServers linked to the current
        # Organization whose username and password fields are set
        self.fields["server"].queryset = central_servers = (
            request.organization.central_servers.filter(
                username__isnull=False, password__isnull=False
            )
        )
        self.fields["server"].widget.attrs["hx-get"] = reverse_lazy(
            "publish_mdm:server-sync-projects", args=[request.organization.slug]
        )
        # Set `project` field choices when a server is provided either via a
        # POST or HTMX request
        if (
            (server_id := htmx_data.get("server") or self.data.get("server"))
            and server_id.isdigit()
            and (central_server := central_servers.filter(id=server_id).first())
        ):
            self.set_project_choices(central_server)
            self.fields["project"].widget.attrs.pop("disabled", None)

    def set_project_choices(self, central_server: CentralServer):
        central_server.decrypt()
        with PublishMDMClient(central_server=central_server) as client:
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
        widget=TextInput(attrs={"placeholder": "e.g., 10001, 10002, 10003", "autofocus": True}),
    )

    def __init__(self, request: HttpRequest, form_template: FormTemplate, *args, **kwargs):
        self.request = request
        self.form_template = form_template
        kwargs["initial"] = {"form_template": form_template.id}
        super().__init__(*args, **kwargs)

    def clean_app_users(self):
        """Validate by checking if the entered app users are in this project."""
        if app_users := self.cleaned_data.get("app_users"):
            app_users_list = [name.strip() for name in app_users.split(",")]
            app_users_in_db = self.form_template.get_app_users(names=app_users_list).order_by(
                "name"
            )
            if len(app_users_in_db) != len(app_users_list):
                invalid_users = sorted(
                    set(app_users_list) - {user.name for user in app_users_in_db}
                )
                error_message = "Invalid App Users: " + ", ".join(invalid_users)
                raise forms.ValidationError(error_message)
            return app_users_in_db
        return []


class FileFormatChoiceField(forms.ChoiceField):
    """Field for selecting a file format for importing and exporting."""

    widget = Select

    def __init__(self, *args, **kwargs):
        # Load the available file formats from Django settings
        self.formats = settings.IMPORT_EXPORT_FORMATS
        choices = [("", "---")] + [
            (i, format().get_title()) for i, format in enumerate(self.formats)
        ]
        super().__init__(choices=choices, *args, **kwargs)

    def clean(self, value):
        """Return the selected file format instance."""
        Format = self.formats[int(value)]
        return Format()


class AppUserImportExportFormMixin(PlatformFormMixin, forms.Form):
    """Base form for importing and exporting AppUsers."""

    format = FileFormatChoiceField()

    def __init__(self, resources, **kwargs):
        # Formats are handled by the FileFormatChoiceField, so we pass an empty list
        # to the parent class
        super().__init__(formats=[], resources=resources, **kwargs)

    def _init_formats(self, formats):
        # Again, formats are handled by the FileFormatChoiceField, so nothing to do here
        pass


class AppUserExportForm(AppUserImportExportFormMixin, import_export_forms.ImportExportFormBase):
    """Form for exporting AppUsers to a file."""

    pass


class AppUserImportForm(AppUserImportExportFormMixin, import_export_forms.ImportForm):
    """Form for importing AppUsers from a file."""

    import_file = forms.FileField(label="File to import", widget=FileInput)

    def __init__(self, resources, **kwargs):
        super().__init__(resources, **kwargs)
        # Add CSS classes to the import file and format fields so JS can detect them
        self.fields["import_file"].widget.attrs["class"] = "guess_format"
        self.fields["format"].widget.attrs["class"] = "guess_format"

    def clean(self):
        import_format = self.cleaned_data.get("format")
        import_file = self.cleaned_data.get("import_file")
        if import_format and import_file:
            data = import_file.read()
            if not import_format.is_binary():
                import_format.encoding = "utf-8-sig"
            try:
                self.dataset = import_format.create_dataset(data)
            except Exception:
                # Using debug() instead of exception() or error() so that it's not
                # logged in Sentry
                logger.debug(
                    "An error occurred when reading AppUser import file",
                    selected_format=import_format.get_title(),
                    filename=import_file.name,
                    exc_info=True,
                )
                raise forms.ValidationError(
                    {
                        "format": (
                            "An error was encountered while trying to read the file. "
                            "Ensure you have chosen the correct format for the file."
                        )
                    }
                )
            self.file_data = data
        return self.cleaned_data


class AppUserConfirmImportForm(import_export_forms.ConfirmImportForm):
    format = FileFormatChoiceField(widget=forms.HiddenInput)

    def clean(self):
        import_format = self.cleaned_data.get("format")
        import_file_name = self.cleaned_data.get("import_file_name")
        if import_format and import_file_name:
            # Read the temp file and create a tablib.Dataset that we'll use for importing
            if not import_format.is_binary():
                import_format.encoding = "utf-8-sig"
            tmp_storage = MediaStorage(
                name=import_file_name,
                encoding=import_format.encoding,
                read_mode=import_format.get_read_mode(),
            )
            data = None
            try:
                data = tmp_storage.read()
                self.dataset = import_format.create_dataset(data)
            except Exception:
                # Either the temp file could not be read, or there was an error
                # parsing the file using the selected format
                logger.exception(
                    "An error occurred when reading AppUser import temp file in confirm stage",
                    selected_format=import_format.get_title(),
                    filename=import_file_name,
                )
                raise forms.ValidationError(
                    "An error was encountered while trying to read the file."
                )
            finally:
                if data is not None:
                    # Delete the temp file
                    tmp_storage.remove()
        return self.cleaned_data


class FormTemplateForm(PlatformFormMixin, forms.ModelForm):
    app_users = forms.ModelMultipleChoiceField(
        # The queryset will be set to the current project's app users in __init__()
        queryset=None,
        required=False,
        widget=CheckboxSelectMultiple,
        help_text="The App Users this form template will be assigned to.",
    )

    class Meta:
        model = FormTemplate
        exclude = ["project"]
        widgets = {
            "title_base": TextInput,
            "form_id_base": TextInput,
            "template_url": InputWithAddon(
                addon_content="Select with Google Picker", addon_attrs={"onclick": "createPicker()"}
            ),
            "template_url_user": forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["app_users"].queryset = self.instance.project.app_users.all()
        if self.instance.pk:
            self.fields["app_users"].initial = AppUser.objects.filter(
                app_user_forms__form_template=self.instance
            )


class AppUserForm(PlatformFormMixin, forms.ModelForm):
    """A form for adding or editing an AppUser."""

    class Meta:
        model = AppUser
        fields = ["name"]
        widgets = {
            "name": TextInput,
        }

    def clean_name(self):
        """Check if another AppUser has the same name within the same project."""
        name = self.cleaned_data.get("name")
        if name and (
            self.instance.project.app_users.exclude(id=self.instance.id)
            .filter(name__iexact=name)
            .exists()
        ):
            raise forms.ValidationError(
                "An app user with the same name already exists in the current project."
            )
        return name


class AppUserTemplateVariableForm(PlatformFormMixin, forms.ModelForm):
    """A form for adding or editing an AppUserTemplateVariable."""

    class Meta:
        model = AppUserTemplateVariable
        fields = ["template_variable", "value"]
        widgets = {
            "template_variable": Select,
            "value": TextInput,
        }


AppUserTemplateVariableFormSet = forms.models.inlineformset_factory(
    AppUser, AppUserTemplateVariable, form=AppUserTemplateVariableForm, extra=0
)
AppUserTemplateVariableFormSet.deletion_widget = CheckboxInput


class ProjectForm(PlatformFormMixin, forms.ModelForm):
    """A form for editing a Project."""

    class Meta:
        model = Project
        fields = ["name", "central_server", "template_variables", "app_language"]
        widgets = {
            "name": TextInput,
            "central_server": Select,
            "template_variables": CheckboxSelectMultiple,
            "app_language": Select(attrs={"class": "!w-30"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit template variables and central servers to those linked to the project's organization
        self.fields[
            "template_variables"
        ].queryset = self.instance.organization.template_variables.all()
        self.fields["central_server"].queryset = self.instance.organization.central_servers.all()


class ProjectTemplateVariableForm(PlatformFormMixin, forms.ModelForm):
    """A form for adding or editing a ProjectTemplateVariable."""

    class Meta:
        model = ProjectTemplateVariable
        fields = ["template_variable", "value"]
        widgets = {
            "template_variable": Select,
            "value": TextInput,
        }

    def __init__(self, *args, **kwargs):
        valid_template_variables = kwargs.pop("valid_template_variables", None)
        super().__init__(*args, **kwargs)
        if valid_template_variables is not None:
            self.fields["template_variable"].queryset = valid_template_variables


ProjectTemplateVariableFormSet = forms.models.inlineformset_factory(
    Project, ProjectTemplateVariable, form=ProjectTemplateVariableForm, extra=0
)
ProjectTemplateVariableFormSet.deletion_widget = CheckboxInput


class OrganizationForm(PlatformFormMixin, forms.ModelForm):
    class Meta:
        model = Organization
        fields = ["name", "slug"]
        widgets = {
            "name": TextInput,
            "slug": TextInput,
        }


class CleanOrganizationInvitationMixin:
    """Similar to django-invitation's CleanEmailMixin, but checks for invitations
    to the same organization.
    """

    def validate_invitation(self, email, organization):
        if OrganizationInvitation.objects.all_valid().filter(
            email__iexact=email, organization=organization, accepted=False
        ):
            raise AlreadyInvited
        elif OrganizationInvitation.objects.filter(
            email__iexact=email, organization=organization, accepted=True
        ):
            raise AlreadyAccepted
        elif organization.users.filter(email__iexact=email):
            raise UserRegisteredEmail
        else:
            return True

    def clean(self):
        email = self.cleaned_data["email"]
        email = get_invitations_adapter().clean_email(email)
        if hasattr(self, "organization"):
            organization = self.organization
        else:
            organization = self.cleaned_data["organization"]

        errors = {
            "already_invited": f"This e-mail address has already been invited to {organization}.",
            "already_accepted": f"This e-mail address has already accepted an invite to {organization}.",
            "email_in_use": f"A user with this e-mail address has already joined {organization}.",
        }
        try:
            self.validate_invitation(email, organization)
        except AlreadyInvited:
            raise forms.ValidationError({"email": errors["already_invited"]})
        except AlreadyAccepted:
            raise forms.ValidationError({"email": errors["already_accepted"]})
        except UserRegisteredEmail:
            raise forms.ValidationError({"email": errors["email_in_use"]})
        return self.cleaned_data


class OrganizationInviteForm(PlatformFormMixin, CleanOrganizationInvitationMixin, forms.Form):
    email = forms.EmailField(widget=TextInput)

    def __init__(self, *args, **kwargs):
        self.organization = kwargs.pop("organization")
        super().__init__(*args, **kwargs)


class OrganizationInvitationAdminAddForm(CleanOrganizationInvitationMixin, forms.ModelForm):
    """Similar to django-invitation's InvitationAdminAddForm but includes the organization field."""

    class Meta:
        model = OrganizationInvitation
        fields = ("email", "organization", "inviter")

    def save(self, *args, **kwargs):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        organization = cleaned_data.get("organization")
        params = {"email": email, "organization": organization}
        if cleaned_data.get("inviter"):
            params["inviter"] = cleaned_data.get("inviter")
        instance = OrganizationInvitation.create(**params)
        instance.send_invitation(self.request)
        super().save(*args, **kwargs)
        return instance


class TemplateVariableForm(PlatformFormMixin, forms.ModelForm):
    """A form for adding or editing a TemplateVariable."""

    class Meta:
        model = TemplateVariable
        fields = ["name", "transform"]
        widgets = {
            "name": TextInput,
            "transform": Select,
        }


TemplateVariableFormSet = forms.models.inlineformset_factory(
    Organization, TemplateVariable, form=TemplateVariableForm, extra=0
)
TemplateVariableFormSet.deletion_widget = CheckboxInput


class CentralServerForm(forms.ModelForm):
    """A form for adding or editing a CentralServer."""

    class Meta:
        model = CentralServer
        fields = "__all__"
        widgets = {
            "username": BaseEmailInput(render_value=False),
            "password": forms.widgets.PasswordInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.id:
            # PasswordInput and BaseEmailInput with render_value=False do not
            # render the current value for security purposes (default is False
            # for PasswordInput). Add some help text to indicate that a value
            # exists even if the input is empty, and the user can leave it blank
            # to keep the current value.
            for field_name in ("username", "password"):
                field = self.fields[field_name]
                if not field.widget.render_value and getattr(self.instance, field_name):
                    field.help_text = (
                        f"A {field_name} exists. You can leave it blank to keep the current value."
                    )
                    field.required = False

    def clean(self):
        if not self.errors and (
            self.cleaned_data["username"]
            or self.cleaned_data["password"]
            or "base_url" in self.changed_data
        ):
            # Strip trailing "/" from base_url
            self.cleaned_data["base_url"] = self.cleaned_data["base_url"].rstrip("/")
            # Validate the base URL and credentials by checking if we can log in
            # https://docs.getodk.org/central-api-authentication/#logging-in
            if not (self.cleaned_data["username"] and self.cleaned_data["password"]):
                # We'll need to get at least one of the credentials from the database
                self.instance.decrypt()
            try:
                response = requests.post(
                    self.cleaned_data["base_url"] + "/v1/sessions",
                    json={
                        "email": self.cleaned_data["username"] or self.instance.username,
                        "password": self.cleaned_data["password"] or self.instance.password,
                    },
                    timeout=10,
                )
            except requests.RequestException:
                # Probably an invalid base_url
                success = False
            else:
                success = response.status_code == 200
            if not success:
                raise forms.ValidationError(
                    "The base URL and/or login credentials appear to be incorrect. Please try again."
                )
        return self.cleaned_data

    def save(self, commit=True):
        if self.instance.id:
            # Delete the pyodk cache file if it exists, else pyodk will continue
            # using the cached auth token until it expires (24h after it was created)
            Path(f"/tmp/.pyodk_cache_{self.instance.id}.toml").unlink(missing_ok=True)
        return super().save(commit)


class CentralServerFrontendForm(PlatformFormMixin, CentralServerForm):
    """A form for adding or editing a CentralServer on the frontend."""

    class Meta(CentralServerForm.Meta):
        fields = ["base_url", "username", "password"]
        widgets = {
            "base_url": TextInput,
            "username": EmailInput(render_value=False),
            "password": PasswordInput,
        }


class FleetEditForm(PlatformFormMixin, forms.ModelForm):
    class Meta:
        model = Fleet
        fields = ["project"]
        widgets = {
            "project": Select,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = self.instance.organization.projects.all()


class FleetAddForm(FleetEditForm):
    class Meta:
        model = Fleet
        fields = ["name", "project"]
        widgets = {
            "name": TextInput,
            "project": Select,
        }

    def clean_name(self):
        """Check if another Fleet has the same name within the same organization."""
        name = self.cleaned_data.get("name")
        if name and (
            self.instance.organization.fleets.exclude(id=self.instance.id)
            .filter(name__iexact=name)
            .exists()
        ):
            raise forms.ValidationError(
                "A fleet with the same name already exists in the current organization."
            )
        return name


class DeviceEnrollmentQRCodeForm(PlatformFormMixin, forms.Form):
    fleet = forms.ModelChoiceField(
        # The queryset will be updated based on the current organization in __init__()
        queryset=None,
        # When a fleet is selected, its QR code is fetched and displayed using HMTX.
        widget=Select(
            attrs={
                "hx-trigger": "change",
                "hx-target": "#qr-code",
                "hx-swap": "innerHTML",
                "hx-indicator": ".loading",
            }
        ),
        empty_label="Select a Fleet to view its QR code",
        required=False,
    )

    def __init__(self, organization, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fleet"].queryset = organization.fleets.all()
        self.fields["fleet"].widget.attrs["hx-post"] = reverse_lazy(
            "publish_mdm:fleet-qr-code", args=[organization.slug]
        )


class BYODDeviceEnrollmentForm(PlatformFormMixin, forms.Form):
    """A form for enrolling a BYOD device in the Device list page."""

    fleet = forms.ModelChoiceField(
        # The queryset will be updated based on the current organization in __init__()
        queryset=None,
        widget=Select,
        empty_label="Select a Fleet to join",
    )
    name = forms.CharField(widget=TextInput, label="Your name")
    email = forms.EmailField(widget=EmailInput, label="Your email")

    def __init__(self, organization, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fleet"].queryset = organization.fleets.all()


class SearchForm(PlatformFormMixin, forms.Form):
    search = forms.CharField(
        widget=TextInput(attrs={"placeholder": "Search", "x-model.fill": "search"}), required=False
    )
