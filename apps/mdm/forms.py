import structlog
from django import forms
from import_export.forms import ConfirmImportForm, ImportForm

from apps.mdm.models import Device, PushMethodChoices
from apps.patterns.forms import PlatformFormMixin
from apps.patterns.widgets import CheckboxInput, Select, TextInput

from .models import FirmwareSnapshot, Policy, PolicyApplication, PolicyVariable

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


class PolicyApplicationAddForm(PlatformFormMixin, forms.ModelForm):
    """Form for adding a new app (just package name)."""

    class Meta:
        model = PolicyApplication
        fields = ["package_name"]
        widgets = {"package_name": TextInput(attrs={"placeholder": "com.example.app"})}


class OdkCollectPackageForm(PlatformFormMixin, forms.ModelForm):
    """Form for overriding the ODK Collect package name."""

    class Meta:
        model = Policy
        fields = ["odk_collect_package"]
        widgets = {
            "odk_collect_package": TextInput(attrs={"placeholder": "org.odk.collect.android"})
        }
        labels = {"odk_collect_package": "Package name override"}


class PasswordPolicyForm(PlatformFormMixin, forms.ModelForm):
    """Section 3: Password policy (device + work scopes)."""

    class Meta:
        model = Policy
        fields = [
            "device_password_quality",
            "device_password_min_length",
            "device_password_require_unlock",
            "work_password_quality",
            "work_password_min_length",
            "work_password_require_unlock",
        ]
        widgets = {
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
        }
        labels = {
            "device_password_quality": "Password quality",
            "device_password_min_length": "Minimum length",
            "device_password_require_unlock": "Require unlock",
            "work_password_quality": "Password quality",
            "work_password_min_length": "Minimum length",
            "work_password_require_unlock": "Require unlock",
        }


class VPNForm(PlatformFormMixin, forms.ModelForm):
    """Section 4: Always-on VPN."""

    class Meta:
        model = Policy
        fields = ["vpn_package_name", "vpn_lockdown"]
        widgets = {
            "vpn_package_name": TextInput(attrs={"placeholder": "com.tailscale.ipn"}),
            "vpn_lockdown": CheckboxInput,
        }
        labels = {
            "vpn_package_name": "VPN Package Name",
            "vpn_lockdown": "Lockdown Mode",
        }


class DeveloperSettingsForm(PlatformFormMixin, forms.ModelForm):
    """Section 5: Developer options."""

    class Meta:
        model = Policy
        fields = ["developer_settings"]
        widgets = {"developer_settings": Select}
        labels = {"developer_settings": "Developer Settings"}


class KioskModeForm(PlatformFormMixin, forms.ModelForm):
    """Section: Kiosk mode settings."""

    class Meta:
        model = Policy
        fields = [
            "kiosk_power_button_actions",
            "kiosk_system_error_warnings",
            "kiosk_system_navigation",
            "kiosk_status_bar",
            "kiosk_device_settings",
        ]
        widgets = {
            "kiosk_power_button_actions": Select,
            "kiosk_system_error_warnings": Select,
            "kiosk_system_navigation": Select,
            "kiosk_status_bar": Select,
            "kiosk_device_settings": Select,
        }
        labels = {
            "kiosk_power_button_actions": "Power Button Actions",
            "kiosk_system_error_warnings": "System Error Warnings",
            "kiosk_system_navigation": "System Navigation",
            "kiosk_status_bar": "Status Bar",
            "kiosk_device_settings": "Device Settings",
        }


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
