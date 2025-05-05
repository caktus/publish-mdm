import structlog
from django import forms
from .models import FirmwareSnapshot
from apps.mdm.models import Device


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
