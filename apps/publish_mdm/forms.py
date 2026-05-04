import ipaddress
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse

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

from apps.mdm.models import Device, Fleet, Policy
from apps.patterns.forms import PlatformFormMixin
from apps.patterns.widgets import (
    BaseEmailInput,
    CheckboxInput,
    CheckboxSelectMultiple,
    ClearableFileInput,
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
    ProjectAttachment,
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
        super().__init__(*args, choices=choices, **kwargs)

    def clean(self, value):
        """Return the selected file format instance."""
        value = super().clean(value)
        Format = self.formats[int(value)]
        return Format()


class ImportExportFormMixin(PlatformFormMixin, forms.Form):
    """Base form for importing and exporting model instances."""

    format = FileFormatChoiceField()

    def __init__(self, resources, **kwargs):
        # Formats are handled by the FileFormatChoiceField, so we pass an empty list
        # to the parent class
        super().__init__(formats=[], resources=resources, **kwargs)

    def _init_formats(self, formats):
        # Again, formats are handled by the FileFormatChoiceField, so nothing to do here
        pass


class ExportForm(ImportExportFormMixin, import_export_forms.ImportExportFormBase):
    """Form for exporting model instances to a file."""

    pass


class ImportForm(ImportExportFormMixin, import_export_forms.ImportForm):
    """Form for importing model instances from a file."""

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
                    "An error occurred when reading import file",
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
                ) from None
            self.file_data = data
        return self.cleaned_data


class ConfirmImportForm(import_export_forms.ConfirmImportForm):
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
                    "An error occurred when reading import temp file in confirm stage",
                    selected_format=import_format.get_title(),
                    filename=import_file_name,
                )
                raise forms.ValidationError(
                    "An error was encountered while trying to read the file."
                ) from None
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
        fields = (
            "title_base",
            "form_id_base",
            "template_url",
            "template_url_user",
        )
        widgets: ClassVar = {
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
        fields = ("name",)
        widgets: ClassVar = {
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
        fields = (
            "template_variable",
            "value",
        )
        widgets: ClassVar = {
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
        fields = (
            "name",
            "central_server",
            "template_variables",
            # ODK Collect settings
            "collect_general_app_language",
            "collect_project_color",
            "collect_project_icon",
            "collect_general_font_size",
            "collect_general_form_update_mode",
            "collect_general_periodic_form_updates_check",
            "collect_general_autosend",
            "collect_general_delete_send",
            "collect_general_default_completed",
            "collect_general_analytics",
            "collect_general_app_theme",
            "collect_general_navigation",
            "collect_general_constraint_behavior",
            "collect_general_high_resolution",
            "collect_general_image_size",
            "collect_general_external_app_recording",
            "collect_general_guidance_hint",
            "collect_general_instance_sync",
            "collect_general_metadata_username",
            "collect_general_metadata_phonenumber",
            "collect_general_metadata_email",
            "collect_admin_edit_saved",
            "collect_admin_send_finalized",
            "collect_admin_view_sent",
            "collect_admin_get_blank",
            "collect_admin_delete_saved",
            "collect_admin_qr_code_scanner",
            "collect_admin_change_server",
            "collect_admin_change_project_display",
            "collect_admin_change_app_theme",
            "collect_admin_change_navigation",
            "collect_admin_maps",
            "collect_admin_form_update_mode",
            "collect_admin_periodic_form_updates_check",
            "collect_admin_automatic_update",
            "collect_admin_hide_old_form_versions",
            "collect_admin_change_autosend",
            "collect_admin_delete_after_send",
            "collect_admin_default_to_finalized",
            "collect_admin_change_constraint_behavior",
            "collect_admin_high_resolution",
            "collect_admin_image_size",
            "collect_admin_guidance_hint",
            "collect_admin_external_app_recording",
            "collect_admin_instance_form_sync",
            "collect_admin_change_form_metadata",
            "collect_admin_analytics",
            "collect_admin_change_app_language",
            "collect_admin_change_font_size",
            "collect_admin_moving_backwards",
            "collect_admin_access_settings",
            "collect_admin_change_language",
            "collect_admin_jump_to",
            "collect_admin_save_mid",
            "collect_admin_save_as",
            "collect_admin_mark_as_finalized",
            # Additional general fields
            "collect_general_protocol",
            "collect_general_password",
            "collect_general_formlist_url",
            "collect_general_submission_url",
            "collect_general_google_sheets_url",
            "collect_general_automatic_update",
            "collect_general_hide_old_form_versions",
            "collect_general_basemap_source",
            "collect_general_google_map_style",
            "collect_general_mapbox_map_style",
            "collect_general_usgs_map_style",
            "collect_general_carto_map_style",
            "collect_general_reference_layer",
        )
        widgets: ClassVar = {
            "name": TextInput,
            "central_server": Select,
            "template_variables": CheckboxSelectMultiple,
            "collect_general_app_language": Select(attrs={"class": "!w-30"}),
            "collect_project_color": TextInput,
            "collect_project_icon": TextInput,
            "collect_general_font_size": Select,
            "collect_general_form_update_mode": Select,
            "collect_general_periodic_form_updates_check": Select,
            "collect_general_autosend": Select,
            "collect_general_app_theme": Select,
            "collect_general_navigation": Select,
            "collect_general_constraint_behavior": Select,
            "collect_general_image_size": Select,
            "collect_general_guidance_hint": Select,
            "collect_general_metadata_username": TextInput,
            "collect_general_metadata_phonenumber": TextInput,
            "collect_general_metadata_email": TextInput,
            "collect_general_protocol": Select,
            "collect_general_password": TextInput(
                attrs={"type": "password", "autocomplete": "off"}
            ),
            "collect_general_formlist_url": TextInput,
            "collect_general_submission_url": TextInput,
            "collect_general_google_sheets_url": TextInput,
            "collect_general_basemap_source": Select,
            "collect_general_google_map_style": Select,
            "collect_general_mapbox_map_style": Select,
            "collect_general_usgs_map_style": Select,
            "collect_general_carto_map_style": Select,
            "collect_general_reference_layer": TextInput,
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
        fields = (
            "template_variable",
            "value",
        )
        widgets: ClassVar = {
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


class ProjectAttachmentForm(PlatformFormMixin, forms.ModelForm):
    """A form for adding or editing a ProjectAttachment."""

    class Meta:
        model = ProjectAttachment
        fields = (
            "name",
            "file",
        )
        widgets: ClassVar = {
            "name": TextInput,
            "file": ClearableFileInput,
        }

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get("name")
        # In an inline formset, project is set on the instance by _construct_form
        project = getattr(self.instance, "project", None)
        if name and project is not None:
            qs = ProjectAttachment.objects.filter(project=project, name=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    "name", "An attachment with this name already exists in this project."
                )
        return cleaned_data


class ProjectAttachmentBaseFormSet(forms.models.BaseInlineFormSet):
    """Inline formset for ProjectAttachment that deletes files for removed rows."""

    def delete_files_for_deleted_forms(self):
        for form in self.deleted_forms:
            if form.instance.pk and form.instance.file:
                form.instance.file.delete(save=False)

    def save(self, commit=True):
        if commit:
            self.delete_files_for_deleted_forms()
        return super().save(commit=commit)


ProjectAttachmentFormSet = forms.models.inlineformset_factory(
    Project,
    ProjectAttachment,
    form=ProjectAttachmentForm,
    formset=ProjectAttachmentBaseFormSet,
    extra=0,
)
ProjectAttachmentFormSet.deletion_widget = CheckboxInput


class OrganizationForm(PlatformFormMixin, forms.ModelForm):
    class Meta:
        model = Organization
        fields = (
            "name",
            "slug",
            "mdm",
            "tinymdm_apikey_public",
            "tinymdm_apikey_secret",
            "tinymdm_account_id",
            "tinymdm_default_policy_id",
        )
        widgets: ClassVar = {
            "name": TextInput,
            "slug": TextInput,
            "mdm": Select(attrs={"x-model": "mdm"}),
            "tinymdm_apikey_public": PasswordInput(render_value=True),
            "tinymdm_apikey_secret": PasswordInput(render_value=True),
            "tinymdm_account_id": TextInput,
            "tinymdm_default_policy_id": TextInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # TinyMDM credential fields are only relevant when mdm == "TinyMDM"
        self.tinymdm_fields = [
            "tinymdm_apikey_public",
            "tinymdm_apikey_secret",
            "tinymdm_account_id",
            "tinymdm_default_policy_id",
        ]

    def clean(self):
        cleaned_data = super().clean()
        mdm = cleaned_data.get("mdm")
        if mdm == "TinyMDM":
            for field in self.tinymdm_fields:
                if not cleaned_data.get(field):
                    self.add_error(field, "This field is required when TinyMDM is selected.")
        else:
            for field in self.tinymdm_fields:
                if field == "tinymdm_default_policy_id":
                    cleaned_data[field] = ""
                else:
                    cleaned_data[field] = None
        return cleaned_data


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
            raise forms.ValidationError({"email": errors["already_invited"]}) from None
        except AlreadyAccepted:
            raise forms.ValidationError({"email": errors["already_accepted"]}) from None
        except UserRegisteredEmail:
            raise forms.ValidationError({"email": errors["email_in_use"]}) from None
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
        fields = (
            "name",
            "transform",
        )
        widgets: ClassVar = {
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
        fields = (
            "base_url",
            "organization",
            "username",
            "password",
        )
        widgets: ClassVar = {
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

    # Private / reserved address blocks that must never be used as an ODK Central host.
    _BLOCKED_NETWORKS = (
        ipaddress.ip_network(cidr)
        for cidr in (
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "127.0.0.0/8",
            "169.254.0.0/16",  # link-local / AWS metadata
            "::1/128",
            "fc00::/7",
            "fe80::/10",
        )
    )

    def _validate_base_url(self, url: str) -> None:
        """Reject non-HTTPS URLs and URLs that target private / reserved hosts.

        When DEBUG is True (local development), all checks are skipped so that
        developers can use http:// or private-IP Central instances.
        """
        if settings.DEBUG:
            return
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise forms.ValidationError("The base URL must use the https:// scheme.")
        host = parsed.hostname or ""
        try:
            addr = ipaddress.ip_address(host)
            for network in self._BLOCKED_NETWORKS:
                if addr in network:
                    raise forms.ValidationError(
                        "The base URL must not point to a private or reserved IP address."
                    )
        except ValueError:
            # host is a hostname, not a bare IP address — allow it
            pass

    def clean(self):
        if not self.errors and (
            self.cleaned_data["username"]
            or self.cleaned_data["password"]
            or "base_url" in self.changed_data
        ):
            # Strip trailing "/" from base_url
            self.cleaned_data["base_url"] = self.cleaned_data["base_url"].rstrip("/")
            # VULN-002: validate scheme and host before making any outbound request
            try:
                self._validate_base_url(self.cleaned_data["base_url"])
            except forms.ValidationError as exc:
                self.add_error("base_url", exc)
                return self.cleaned_data
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
        fields = (
            "base_url",
            "username",
            "password",
        )
        widgets: ClassVar = {
            "base_url": TextInput,
            "username": EmailInput(render_value=False),
            "password": PasswordInput,
        }


class FleetEditForm(PlatformFormMixin, forms.ModelForm):
    class Meta:
        model = Fleet
        fields = ("policy", "project", "default_app_user")
        widgets: ClassVar = {
            "policy": Select,
            "project": Select,
            "default_app_user": Select,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = self.instance.organization.projects.all()
        self.fields["policy"].queryset = Policy.objects.filter(
            organization=self.instance.organization
        )
        self.fields["project"].widget.attrs.update(
            {
                "hx-trigger": "change",
                "hx-target": "#id_default_app_user_container",
                "hx-swap": "innerHTML",
                "hx-indicator": ".loading",
                "hx-get": reverse_lazy(
                    "publish_mdm:fleet-app-users", args=[self.instance.organization.slug]
                ),
            }
        )
        project = self.instance.project
        # When the form is bound, always derive the project from the submitted
        # data — not the saved instance — so that the default_app_user queryset
        # is always correct. On GET requests self.is_bound is False so the saved
        # project is used.
        if self.is_bound:
            project_id = self.data.get("project")
            if not project_id:
                project = None
            elif str(project_id) != str(self.instance.project_id):
                # Project changed — fetch from DB
                try:
                    project = self.instance.organization.projects.get(pk=project_id)
                except (Project.DoesNotExist, ValueError):
                    project = None
        if project and project.pk:
            self.fields["default_app_user"].queryset = AppUser.objects.filter(project=project)
        else:
            self.fields["default_app_user"].queryset = AppUser.objects.none()


class FleetAddForm(FleetEditForm):
    class Meta:
        model = Fleet
        fields = (
            "name",
            "policy",
            "project",
            "default_app_user",
        )
        widgets: ClassVar = {
            "name": TextInput,
            "policy": Select,
            "project": Select,
            "default_app_user": Select,
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


class DeviceAppUserForm(forms.ModelForm):
    """Form for updating a Device's app_user_name via HTMX."""

    app_user_name = forms.ChoiceField(
        required=False,
        choices=[("", "---")],
        widget=Select(
            attrs={
                "hx-target": "closest form",
                "hx-swap": "outerHTML",
            }
        ),
    )

    class Meta:
        model = Device
        fields = ("app_user_name",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.fleet.project:
            self.fields["app_user_name"].choices = [
                ("", "---"),
                *((i.name, i.name) for i in self.instance.fleet.project.app_users.order_by("name")),
            ]
        self.fields["app_user_name"].widget.attrs["hx-post"] = reverse_lazy(
            "publish_mdm:device-update-app-user",
            args=[self.instance.fleet.organization.slug, self.instance.pk],
        )


class SearchForm(PlatformFormMixin, forms.Form):
    search = forms.CharField(
        widget=TextInput(attrs={"placeholder": "Search", "x-model.fill": "search"}), required=False
    )
