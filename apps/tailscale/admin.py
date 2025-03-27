from django.contrib import admin

from .models import Device, DeviceSnapshot


@admin.register(DeviceSnapshot)
class DeviceSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "os",
        "client_version",
        "update_available",
        "tags",
        "last_seen",
        "synced_at",
    )
    list_filter = ("os", "user", "client_version", "synced_at", "tailnet")
    search_fields = (
        "name",
        "hostname",
        "user",
        "os",
        "client_version",
        "tags",
        "tailnet",
    )
    date_hierarchy = "synced_at"
    ordering = ("-synced_at",)
    readonly_fields = (
        "addresses",
        "client_version",
        "created",
        "expires",
        "hostname",
        "last_seen",
        "name",
        "node_id",
        "os",
        "tags",
        "update_available",
        "user",
        # Non-API fields
        "device",
        "tailnet",
        "synced_at",
        "raw_data",
    )


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    date_hierarchy = "last_seen"
    list_display = (
        "id",
        "name",
        "node_id",
        "last_seen",
        "latest_snapshot__tags",
        "latest_snapshot__synced_at",
    )
    list_filter = (
        "last_seen",
        "latest_snapshot__created",
        "latest_snapshot__client_version",
        "tailnet",
    )
    list_select_related = ("latest_snapshot",)
    search_fields = (
        "id",
        "name",
        "node_id",
        "latest_snapshot__client_version",
        "latest_snapshot__tags",
        "latest_snapshot__os",
    )
    ordering = ("name",)
    readonly_fields = (
        "name",
        "node_id",
        "tailnet",
        "last_seen",
        "latest_snapshot",
    )
