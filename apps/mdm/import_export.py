from import_export.resources import ModelResource

from .models import Device


class DeviceResource(ModelResource):
    """Custom ModelResource for importing/exporting Devices."""

    class Meta:
        model = Device
        fields = ("id", "policy", "serial_number", "app_user_name", "device_id")
        clean_model_instances = True
        skip_unchanged = True
