import structlog
from django import forms
from .models import FirmwareSnapshot
from apps.mdm.models import Device


logger = structlog.get_logger()


class FirmwareSnapshotForm(forms.ModelForm):
    class Meta:
        model = FirmwareSnapshot
        fields = ["serial_number", "device_identifier", "version", "raw_data"]

    def __init__(self, request, *args, **kwargs):
        """
        Sample URL: GET /api/firmware/?version=unknown&alternatives=W6_V1.0_20241217,15,AP3A.240905.015.A2&device_id=CHANGEME&work_type=immediate&app_version=1.0.1%20(2)
        """  # noqa: E501
        data = None
        if request.method == "GET":
            data = request.GET.copy()
        elif request.method == "POST":
            data = request.POST.copy()
        if data:
            # include _all_ GET or POSTed data in the raw_data field
            data["raw_data"] = data.copy()
            if "serial_number" not in data:
                # Convert the device_id to serial_number
                # TODO: Remove this when the app posts serial_number and device_identifier
                data["serial_number"] = data["device_id"]
        super().__init__(data, *args, **kwargs)
        # serial_number is required to save and look up related devices
        self.fields["serial_number"].required = True

    def clean(self):
        cleaned_data = super().clean()
        version = cleaned_data.get("version")
        if version == "unknown":
            alternatives = cleaned_data["raw_data"].get("alternatives", "").split(",")
            if alternatives:
                # If alternatives are provided, set the version to the first alternative
                cleaned_data["version"] = alternatives[0]
            else:
                logger.error("Neither version nor alternatives provided.", data=cleaned_data)

    def save(self, *args, **kwargs):
        # Get the device identifier from the form data
        serial_number = self.cleaned_data.get("serial_number")
        # Get the device object
        device = Device.objects.filter(serial_number=serial_number).order_by("-pk").first()
        if device:
            self.instance.device = device
        return super().save(*args, **kwargs)
