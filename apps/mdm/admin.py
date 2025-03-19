from django.contrib import admin
from .models import Policy, Device


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "policy_id", "project")
    search_fields = ("name", "policy_id", "project__name")
    list_filter = ("project",)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "serial_number", "policy", "app_user_name")
    search_fields = ("serial_number", "app_user_name", "policy__name")
    readonly_fields = ("name", "device_id", "raw_mdm_device")
    list_filter = ("policy",)
