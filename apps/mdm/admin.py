from django.contrib import admin
from .models import Policy, Device, DeviceSnapshot, DeviceSnapshotApp


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "policy_id", "project")
    search_fields = ("name", "policy_id", "project__name")
    list_filter = ("project",)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "serial_number", "app_user_name", "policy")
    search_fields = ("serial_number", "app_user_name", "policy__name", "serial_number")
    readonly_fields = ("name", "device_id", "raw_mdm_device", "latest_snapshot")
    list_filter = ("policy", "app_user_name")


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
