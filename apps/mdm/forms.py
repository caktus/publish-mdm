import structlog
from django import forms
from django.forms import (
    BaseInlineFormSet,
    BaseModelFormSet,
    inlineformset_factory,
    modelformset_factory,
)
from import_export.forms import ConfirmImportForm, ImportForm

from apps.mdm.models import Device, PushMethodChoices
from apps.patterns.forms import PlatformFormMixin
from apps.patterns.widgets import CheckboxInput, Select, TextInput

from .models import (
    FirmwareSnapshot,
    InstallType,
    Policy,
    PolicyApplication,
    PolicyVariable,
    PolicyVariableScope,
)

logger = structlog.get_logger()


class FirmwareSnapshotForm(forms.ModelForm):
    """Form to parse the firmware snapshot JSON data."""

    class Meta:
        model = FirmwareSnapshot
        fields = ["serial_number", "device_identifier", "version", "raw_data"]

    def __init__(self, json_data, *args, **kwargs):
        form_data = {"raw_data": json_data}
        if "serialNumber" in json_data:
            form_data["serial_number"] = json_data["serialNumber"]
        elif "deviceIdentifier" in json_data:
            form_data["serial_number"] = json_data["deviceIdentifier"]
        super().__init__(form_data, *args, **kwargs)
        # serial_number is required to save and look up related devices
        self.fields["serial_number"].required = True
        self.fields["raw_data"].required = True

    def clean(self):
        """Clean the form data and extract the version information."""
        cleaned_data = super().clean()
        raw_data = cleaned_data.get("raw_data", {})
        build_info = raw_data.get("buildInfo", {}).get("buildPropContent", {})
        version_info = raw_data.get("versionInfo", {})
        if version := build_info.get("[ro.product.version]"):
            # Remove brackets from the version string if present
            if "[" in version:
                version = version.strip("[]")
            cleaned_data["version"] = version
        elif versions := version_info.get("alternatives", []):
            # If no version is found in build_info, check alternatives
            cleaned_data["version"] = versions[0]

    def save(self, *args, **kwargs):
        # Get the device identifier from the form datpya
        serial_number = self.cleaned_data.get("serial_number")
        # Get the device object
        device = Device.objects.filter(serial_number=serial_number).order_by("-pk").first()
        if device:
            self.instance.device = device
        return super().save(*args, **kwargs)


class DeviceImportForm(ImportForm):
    """Form for importing devices with a choice of push method."""

    push_method = forms.ChoiceField(
        choices=PushMethodChoices.choices,
        initial=PushMethodChoices.NEW_AND_UPDATED,
        label="MDM Device Push Method",
        help_text="Choose how to handle devices after import.",
    )


class DeviceConfirmImportForm(ConfirmImportForm):
    # Pull the push_method from the import form and make it hidden in the confirm form
    push_method = forms.ChoiceField(choices=PushMethodChoices.choices, widget=forms.HiddenInput)


class PolicyNameForm(PlatformFormMixin, forms.ModelForm):
    """Section 1: Policy name."""

    class Meta:
        model = Policy
        fields = ["name"]
        widgets = {"name": TextInput(attrs={"placeholder": "Policy name"})}


class PolicyApplicationForm(PlatformFormMixin, forms.ModelForm):
    """Form for a single PolicyApplication row."""

    class Meta:
        model = PolicyApplication
        fields = ["package_name", "install_type", "disabled"]
        widgets = {
            "package_name": TextInput,
            "install_type": Select,
            "disabled": CheckboxInput,
        }
        labels = {
            "install_type": "Install type",
            "disabled": "Disabled",
        }

    def has_changed(self):
        # An unsaved (extra) row with no package_name is an empty placeholder row;
        # treat it as unchanged so empty_permitted=True skips validation.
        if not self.instance.pk and not self.data.get(self.add_prefix("package_name")):
            return False
        return super().has_changed()


class PolicyApplicationAddForm(PlatformFormMixin, forms.ModelForm):
    """Form for adding a new app (just package name)."""

    class Meta:
        model = PolicyApplication
        fields = ["package_name"]
        widgets = {"package_name": TextInput(attrs={"placeholder": "com.example.app"})}

    def __init__(self, *args, policy=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy = policy

    def clean_package_name(self):
        package_name = self.cleaned_data.get("package_name")
        if (
            self.policy
            and PolicyApplication.objects.filter(
                policy=self.policy, package_name=package_name
            ).exists()
        ):
            raise forms.ValidationError(
                f'An application with package name "{package_name}" already exists in this policy.'
            )
        return package_name


class PolicyEditForm(PlatformFormMixin, forms.ModelForm):
    """Combined form for all editable Policy fields."""

    class Meta:
        model = Policy
        fields = [
            "name",
            "odk_collect_package",
            "odk_collect_device_id_template",
            "device_password_quality",
            "device_password_min_length",
            "device_password_require_unlock",
            "work_password_quality",
            "work_password_min_length",
            "work_password_require_unlock",
            "vpn_package_name",
            "vpn_lockdown",
            "kiosk_custom_launcher_enabled",
            "kiosk_power_button_actions",
            "kiosk_system_error_warnings",
            "kiosk_system_navigation",
            "kiosk_status_bar",
            "kiosk_device_settings",
            "developer_settings",
        ]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Policy name"}),
            "odk_collect_package": TextInput(attrs={"placeholder": "org.odk.collect.android"}),
            "odk_collect_device_id_template": TextInput(
                attrs={"placeholder": "e.g. {{ serial_number }} or {{ imei }}"}
            ),
            "device_password_quality": Select,
            "device_password_min_length": TextInput(
                attrs={"type": "number", "min": "0", "max": "16"}
            ),
            "device_password_require_unlock": Select,
            "work_password_quality": Select,
            "work_password_min_length": TextInput(
                attrs={"type": "number", "min": "0", "max": "16"}
            ),
            "work_password_require_unlock": Select,
            "vpn_package_name": TextInput(attrs={"placeholder": "com.tailscale.ipn"}),
            "vpn_lockdown": CheckboxInput,
            "kiosk_custom_launcher_enabled": CheckboxInput,
            "kiosk_power_button_actions": Select,
            "kiosk_system_error_warnings": Select,
            "kiosk_system_navigation": Select,
            "kiosk_status_bar": Select,
            "kiosk_device_settings": Select,
            "developer_settings": Select,
        }
        labels = {
            "odk_collect_package": "Package name override",
            "odk_collect_device_id_template": "Device ID template",
            "device_password_quality": "Quality",
            "device_password_min_length": "Minimum length",
            "device_password_require_unlock": "Require unlock after",
            "work_password_quality": "Quality",
            "work_password_min_length": "Minimum length",
            "work_password_require_unlock": "Require unlock after",
            "vpn_package_name": "VPN app package name",
            "vpn_lockdown": "Lockdown mode",
            "kiosk_custom_launcher_enabled": "Custom launcher",
            "kiosk_power_button_actions": "Power button actions",
            "kiosk_system_error_warnings": "System error warnings",
            "kiosk_system_navigation": "System navigation",
            "kiosk_status_bar": "Status bar",
            "kiosk_device_settings": "Device settings",
            "developer_settings": "Developer options",
        }

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("kiosk_custom_launcher_enabled") and self.instance.pk:
            kiosk_apps = self.instance.applications.filter(install_type=InstallType.KIOSK)
            if kiosk_apps.exists():
                pkg_list = ", ".join(kiosk_apps.values_list("package_name", flat=True))
                raise forms.ValidationError(
                    "Kiosk Custom Launcher cannot be enabled while apps are set to KIOSK "
                    f"install type ({pkg_list}). Change those apps' install type first."
                )
        return cleaned_data


class PolicyVariableForm(PlatformFormMixin, forms.ModelForm):
    """Form for a single PolicyVariable row."""

    class Meta:
        model = PolicyVariable
        fields = ["key", "value", "scope", "fleet"]
        widgets = {
            "key": TextInput(attrs={"placeholder": "variable_name"}),
            "value": TextInput(attrs={"placeholder": "value"}),
            "scope": Select,
            "fleet": Select,
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            self.fields["fleet"].queryset = organization.fleets.all()
        self.fields["fleet"].required = False

    def clean(self):
        cleaned_data = super().clean()
        scope = cleaned_data.get("scope")
        key = cleaned_data.get("key")
        if not key or not scope:
            return cleaned_data
        qs = PolicyVariable.objects.exclude(pk=self.instance.pk if self.instance.pk else None)
        if scope == PolicyVariableScope.ORG:
            org = self.instance.org
            if org and qs.filter(key=key, org=org, scope=scope).exists():
                raise forms.ValidationError(
                    f'A policy-level variable with key "{key}" already exists.'
                )
        elif scope == PolicyVariableScope.FLEET:
            fleet = cleaned_data.get("fleet")
            if fleet and qs.filter(key=key, fleet=fleet, scope=scope).exists():
                raise forms.ValidationError(
                    f'A fleet-level variable with key "{key}" for this fleet already exists.'
                )
        return cleaned_data


class PolicyApplicationBaseFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        for form in self.deleted_forms:
            instance = form.instance
            if (
                instance.pk
                and instance.order == 0
                and instance.package_name == self.instance.odk_collect_package
            ):
                raise forms.ValidationError("The pinned ODK Collect application cannot be removed.")
        seen = set()
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            pkg = form.cleaned_data.get("package_name", "")
            if pkg:
                if pkg in seen:
                    raise forms.ValidationError(f'Duplicate package name "{pkg}".')
                seen.add(pkg)


PolicyApplicationFormSet = inlineformset_factory(
    Policy,
    PolicyApplication,
    form=PolicyApplicationForm,
    formset=PolicyApplicationBaseFormSet,
    extra=0,
    can_delete=True,
)


class PolicyVariableBaseFormSet(BaseModelFormSet):
    def __init__(self, *args, organization=None, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["organization"] = self.organization
        return kwargs

    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        if not form.instance.pk and self.organization:
            form.instance.org = self.organization
        return form


PolicyVariableFormSet = modelformset_factory(
    PolicyVariable,
    form=PolicyVariableForm,
    formset=PolicyVariableBaseFormSet,
    extra=0,
    can_delete=True,
)
