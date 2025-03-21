from django.contrib import admin
from import_export.admin import ImportExportMixin
from import_export.forms import ExportForm
from import_export.resources import ModelResource

from .models import Policy, Device


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "policy_id", "project")
    search_fields = ("name", "policy_id", "project__name")
    list_filter = ("project",)


class DeviceResource(ModelResource):
    """Custom ModelResource for importing/exporting Devices."""

    class Meta:
        model = Device
        fields = ("id", "policy", "serial_number", "app_user_name", "device_id")
        clean_model_instances = True
        skip_unchanged = True


@admin.register(Device)
class DeviceAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ("name", "serial_number", "app_user_name", "policy")
    search_fields = ("serial_number", "app_user_name", "policy__name", "serial_number")
    readonly_fields = ("name", "device_id", "raw_mdm_device")
    list_filter = ("policy", "app_user_name")
    export_form_class = ExportForm
    resource_classes = [DeviceResource]
