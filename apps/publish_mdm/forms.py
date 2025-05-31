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
    CheckboxInput,
    CheckboxSelectMultiple,
    FileInput,
    InputWithAddon,
    Select,
    TextInput,
)

from .etl.odk.client import PublishMDMClient
from .http import HttpRequest
from .models import (
    AppUser,
    AppUserTemplateVariable,
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

    server = forms.ChoiceField(
        # When a server is selected, the project field below is populated with
        # the available projects for that server using HMTX.
        widget=Select(
            attrs={
                "hx-trigger": "change",
                "hx-get": reverse_lazy("publish_mdm:server-sync-projects"),
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
            (config.base_url, config.base_url) for config in PublishMDMClient.get_configs().values()
        ]
        # Set `project` field choices when a server is provided either via a
        # POST or HTMX request
        if server := htmx_data.get("server") or self.data.get("server"):
            self.set_project_choices(base_url=server)
            self.fields["project"].widget.attrs.pop("disabled", None)

    def set_project_choices(self, base_url: str):
        with PublishMDMClient(base_url=base_url) as client:
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
        # Limit template variables to those linked to the project's organization
        self.fields[
            "template_variables"
        ].queryset = self.instance.organization.template_variables.all()


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


class FleetForm(PlatformFormMixin, forms.ModelForm):
    class Meta:
        model = Fleet
        fields = ["name", "project"]
        widgets = {
            "name": TextInput,
            "project": Select,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = self.instance.organization.projects.all()

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
