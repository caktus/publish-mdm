import structlog
from django.contrib import admin, messages
from django.db import transaction, models
from django.db.models.functions import Collate
from django.utils.html import mark_safe
from import_export.admin import ImportExportMixin
from import_export.forms import ExportForm
from requests.exceptions import RequestException

from apps.publish_mdm.http import HttpRequest
from apps.mdm.forms import DeviceConfirmImportForm, DeviceImportForm

from .import_export import DeviceResource
from .models import Device, DeviceSnapshot, DeviceSnapshotApp, FirmwareSnapshot, Fleet, Policy
from .tasks import add_group_to_policy, get_tinymdm_session

logger = structlog.getLogger(__name__)


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "policy_id", "default_policy")
    search_fields = ("name", "policy_id")


@admin.register(Fleet)
class FleetAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "mdm_group_id", "policy", "project")
    search_fields = ("name", "organization__name", "policy__name", "project__name", "mdm_group_id")
    list_filter = ("organization", "policy", "project")

    def save_model(self, request, obj, form, change):
        # Always sync with MDM when saving a Fleet in the admin
        obj.save(sync_with_mdm=True)
        # If the policy has changed, add the group to the new policy
        if "policy" in form.changed_data and (session := get_tinymdm_session()):
            try:
                add_group_to_policy(session, obj)
            except RequestException as e:
                logger.debug(
                    "Unable to add the TinyMDM group to policy",
                    fleet=obj,
                    organization=obj.organization,
                    policy=obj.policy,
                    exc_info=True,
                )
                messages.warning(
                    request,
                    mark_safe(
                        "The fleet has been saved but it could not be added to the "
                        f"{obj.policy.name} policy in TinyMDM due to the following error:"
                        f"<br><code>{e}</code>"
                    ),
                )


@admin.register(Device)
class DeviceAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ("name", "serial_number", "app_user_name", "fleet")
    search_fields = (
        "id",
        "name",
        "device_id",
        "serial_number",
        "app_user_deterministic",
        "fleet__name",
    )
    readonly_fields = ("name", "device_id", "raw_mdm_device", "latest_snapshot")
    list_filter = ("fleet", "app_user_name")
    import_form_class = DeviceImportForm
    confirm_form_class = DeviceConfirmImportForm
    export_form_class = ExportForm
    resource_classes = [DeviceResource]

    def save_model(self, request, obj, form, change):
        """Always push to MDM when saving a Device in the admin."""
        obj.save(push_to_mdm=True)

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[Device]:
        return (
            super().get_queryset(request)
            # Create admin-searchable field for app_user_name that is deterministic
            .annotate(app_user_deterministic=Collate("app_user_name", "und-x-icu"))
        )

    def get_import_data_kwargs(self, request, *args, **kwargs):
        """Prepare kwargs for import_data."""
        form = kwargs.get("form", None)
        if form and hasattr(form, "cleaned_data"):
            kwargs.update({"push_method": form.cleaned_data.get("push_method", None)})
        print(form.cleaned_data)
        return kwargs

    def get_confirm_form_initial(self, request, dataset, **kwargs):
        """Pass the push method to the confirm form."""
        initial = super().get_confirm_form_initial(request, dataset, **kwargs)
        initial["push_method"] = request.POST.get("push_method", "")
        return initial

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
