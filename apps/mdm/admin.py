from django.contrib import admin
from django.contrib import messages
from django.db import transaction
from django.utils.html import mark_safe
from import_export.admin import ImportExportMixin
from import_export.forms import ExportForm

from .import_export import DeviceResource
from .models import Policy, Device, DeviceSnapshot, DeviceSnapshotApp, FirmwareSnapshot, Fleet


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "policy_id")
    search_fields = ("name", "policy_id")


@admin.register(Fleet)
class FleetAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "policy", "project")
    search_fields = ("name", "organization__name", "policy__name", "project__name")
    list_filter = ("organization", "policy", "project")


@admin.register(Device)
class DeviceAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ("name", "serial_number", "app_user_name", "fleet")
    search_fields = ("serial_number", "app_user_name", "fleet__name", "serial_number")
    readonly_fields = ("name", "device_id", "raw_mdm_device", "latest_snapshot")
    list_filter = ("fleet", "app_user_name")
    export_form_class = ExportForm
    resource_classes = [DeviceResource]

    def process_result(self, result, request):
        if request.path.endswith("/process_import/"):
            # If some errors occur during the confirm import step, show error messages
            for row in result.error_rows:
                for error in row.errors:
                    messages.error(
                        request,
                        mark_safe(
                            f"Row {row.number}: {error.error!r}<br><pre>{error.traceback}</pre>"
                        ),
                    )
            for row in result.invalid_rows:
                for field, errors in row.error_dict.items():
                    for error in errors:
                        messages.error(
                            request, mark_safe(f"Row {row.number}, Column '{field}': {error}")
                        )
            if result.has_errors():
                # Save successful rows, since all DB changes will have been rolled back
                # by DeviceResource.import_data()
                with transaction.atomic():
                    for row in result.valid_rows():
                        # We already successfully pushed to MDM
                        row.instance.save(push_to_mdm=False)
        return super().process_result(result, request)


class DeviceSnapshotAppInline(admin.TabularInline):
    model = DeviceSnapshotApp
    extra = 0
    readonly_fields = ("package_name", "app_name", "version_code", "version_name")


@admin.register(DeviceSnapshot)
class DeviceSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "device_id",
        "name",
        "manufacturer",
        "os_version",
        "battery_level",
        "last_sync",
        "synced_at",
    )
    search_fields = (
        "device_id",
        "name",
        "serial_number",
        "manufacturer",
        "os_version",
        "enrollment_type",
    )
    date_hierarchy = "synced_at"
    list_filter = ("manufacturer", "os_version", "enrollment_type")
    ordering = ("-synced_at",)
    inlines = [DeviceSnapshotAppInline]
    raw_id_fields = ("mdm_device",)
    readonly_fields = (
        "device_id",
        "name",
        "serial_number",
        "manufacturer",
        "os_version",
        "battery_level",
        "enrollment_type",
        "last_sync",
        "latitude",
        "longitude",
        "raw_mdm_device",
        "synced_at",
    )


@admin.register(FirmwareSnapshot)
class FirmwareSnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "device", "serial_number", "version", "synced_at")
    search_fields = ("serial_number", "version", "device__serial_number", "device__name")
    list_filter = ("synced_at", "version")
    list_select_related = ("device",)
    date_hierarchy = "synced_at"
    ordering = ("-synced_at",)
    readonly_fields = (
        "device",
        "version",
        "device_identifier",
        "serial_number",
        "synced_at",
        "raw_data",
    )
