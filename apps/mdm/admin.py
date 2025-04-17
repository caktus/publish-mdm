from django.contrib import admin
from django.contrib import messages
from django.db import transaction
from django.utils.html import mark_safe
from import_export.admin import ImportExportMixin
from import_export.forms import ExportForm

from .import_export import DeviceResource
from .models import Policy, Device


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "policy_id", "project")
    search_fields = ("name", "policy_id", "project__name")
    list_filter = ("project",)


@admin.register(Device)
class DeviceAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ("name", "serial_number", "app_user_name", "policy")
    search_fields = ("serial_number", "app_user_name", "policy__name", "serial_number")
    readonly_fields = ("name", "device_id", "raw_mdm_device")
    list_filter = ("policy", "app_user_name")
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
