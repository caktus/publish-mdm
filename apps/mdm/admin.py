import structlog
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.admin.decorators import action
from django.contrib.admin.exceptions import DisallowedModelAdminToField
from django.contrib.admin.options import IS_POPUP_VAR, TO_FIELD_VAR
from django.contrib.admin.utils import model_ngettext, unquote
from django.core.exceptions import PermissionDenied
from django.db import transaction, models
from django.db.models.functions import Collate
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils.html import linebreaks, mark_safe
from django.utils.translation import gettext as _
from import_export.admin import ImportExportMixin
from import_export.forms import ExportForm
from requests.exceptions import RequestException

from apps.publish_mdm.http import HttpRequest
from apps.mdm.forms import DeviceConfirmImportForm, DeviceImportForm

from .import_export import DeviceResource
from .models import Device, DeviceSnapshot, DeviceSnapshotApp, FirmwareSnapshot, Fleet, Policy
from .tasks import add_group_to_policy, delete_group, get_tinymdm_session

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
    actions = ["delete_selected"]

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

    def _delete_view(self, request, object_id, extra_context):
        """This is an exact copy of the builtin _delete_view(), except it will
        not delete a Fleet if it has devices either in the database or in TinyMDM.
        We could not use the delete_model() method as it "isn't meant for veto
        purposes" (https://docs.djangoproject.com/en/5.2/ref/contrib/admin/#modeladmin-methods):
        a deletion would still be logged in LogEntry and a success message would
        still be shown.
        """
        app_label = self.opts.app_label

        to_field = request.POST.get(TO_FIELD_VAR, request.GET.get(TO_FIELD_VAR))
        if to_field and not self.to_field_allowed(request, to_field):
            raise DisallowedModelAdminToField("The field %s cannot be referenced." % to_field)

        obj = self.get_object(request, unquote(object_id), to_field)

        if not self.has_delete_permission(request, obj):
            raise PermissionDenied

        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, object_id)

        # Populate deleted_objects, a data structure of all related objects that
        # will also be deleted.
        (
            deleted_objects,
            model_count,
            perms_needed,
            protected,
        ) = self.get_deleted_objects([obj], request)

        if request.POST and not protected:  # The user has confirmed the deletion.
            if perms_needed:
                raise PermissionDenied

            # BEGIN ADDED CODE
            # Delete the TinyMDM group first. Won't delete anything if the fleet
            # is linked to devices either in the database or in TinyMDM.
            error = None
            if session := get_tinymdm_session():
                try:
                    if not delete_group(session, obj):
                        error = "Cannot delete the fleet because it has devices linked to it."
                except RequestException:
                    error = (
                        "Cannot delete the fleet due a TinyMDM API error. Please try again later."
                    )
            else:
                error = "Cannot delete the fleet. Please try again later."

            if error:
                messages.error(request, error)
                return redirect("admin:mdm_fleet_changelist")
            # END ADDED CODE

            obj_display = str(obj)
            attr = str(to_field) if to_field else self.opts.pk.attname
            obj_id = obj.serializable_value(attr)
            self.log_deletions(request, [obj])
            self.delete_model(request, obj)

            return self.response_delete(request, obj_display, obj_id)

        object_name = str(self.opts.verbose_name)

        if perms_needed or protected:
            title = _("Cannot delete %(name)s") % {"name": object_name}
        else:
            title = _("Delete")

        context = {
            **self.admin_site.each_context(request),
            "title": title,
            "subtitle": None,
            "object_name": object_name,
            "object": obj,
            "deleted_objects": deleted_objects,
            "model_count": dict(model_count).items(),
            "perms_lacking": perms_needed,
            "protected": protected,
            "opts": self.opts,
            "app_label": app_label,
            "preserved_filters": self.get_preserved_filters(request),
            "is_popup": IS_POPUP_VAR in request.POST or IS_POPUP_VAR in request.GET,
            "to_field": to_field,
            **(extra_context or {}),
        }

        return self.render_delete_form(request, context)

    @action(permissions=["delete"], description="Delete selected fleets")
    def delete_selected(self, request, queryset):
        """This is an exact copy of the builtin delete_selected action, except it
        won't delete a Fleet if it has devices either in the database or in TinyMDM.
        We could not use the delete_queryset() method because a deletion would still
        be logged in LogEntry even for fleets that are not deleted, and a success
        message would always be shown saying that the total number of fleets that
        was originally selected has been successfully deleted.
        """
        opts = self.model._meta
        app_label = opts.app_label

        # Populate deletable_objects, a data structure of all related objects that
        # will also be deleted.
        (
            deletable_objects,
            model_count,
            perms_needed,
            protected,
        ) = self.get_deleted_objects(queryset, request)

        # The user has already confirmed the deletion.
        # Do the deletion and return None to display the change list view again.
        if request.POST.get("post") and not protected:
            if perms_needed:
                raise PermissionDenied
            n = len(queryset)
            if n:
                # BEGIN ADDED CODE
                # Delete the TinyMDM groups first. Won't delete a fleet if it
                # is linked to devices either in the database or in TinyMDM.
                if not (session := get_tinymdm_session()):
                    messages.error(request, "Cannot delete fleets. Please try again later.")
                    return

                has_devices = []
                api_errors = []
                successful = []

                for fleet in queryset:
                    try:
                        if delete_group(session, fleet):
                            successful.append(fleet.pk)
                        else:
                            has_devices.append(fleet.name)
                    except RequestException:
                        api_errors.append(fleet.name)

                if has_devices:
                    messages.error(
                        request,
                        mark_safe(
                            "Cannot delete the following fleets because they have "
                            f"devices linked to them: {linebreaks('\n'.join(sorted(has_devices)))}"
                        ),
                    )

                if api_errors:
                    messages.error(
                        request,
                        mark_safe(
                            "Cannot delete the following fleets due a TinyMDM API error: "
                            f"{linebreaks('\n'.join(sorted(api_errors)))}Please try again later."
                        ),
                    )

                n = len(successful)

                if not n:
                    return

                queryset = queryset.filter(pk__in=successful)
                # END ADDED CODE

                self.log_deletions(request, queryset)
                self.delete_queryset(request, queryset)
                self.message_user(
                    request,
                    _("Successfully deleted %(count)d %(items)s.")
                    % {"count": n, "items": model_ngettext(self.opts, n)},
                    messages.SUCCESS,
                )
            # Return None to display the change list page again.
            return None

        objects_name = model_ngettext(queryset)

        if perms_needed or protected:
            title = _("Cannot delete %(name)s") % {"name": objects_name}
        else:
            title = _("Delete multiple objects")

        context = {
            **self.admin_site.each_context(request),
            "title": title,
            "subtitle": None,
            "objects_name": str(objects_name),
            "deletable_objects": [deletable_objects],
            "model_count": dict(model_count).items(),
            "queryset": queryset,
            "perms_lacking": perms_needed,
            "protected": protected,
            "opts": opts,
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            "media": self.media,
        }

        request.current_app = self.admin_site.name

        # Display the confirmation page
        return TemplateResponse(
            request,
            self.delete_selected_confirmation_template
            or [
                "admin/{}/{}/delete_selected_confirmation.html".format(app_label, opts.model_name),
                "admin/%s/delete_selected_confirmation.html" % app_label,
                "admin/delete_selected_confirmation.html",
            ],
            context,
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
            super()
            .get_queryset(request)
            # Create admin-searchable field for app_user_name that is deterministic
            .annotate(app_user_deterministic=Collate("app_user_name", "und-x-icu"))
        )

    def get_import_data_kwargs(self, request, *args, **kwargs):
        """Prepare kwargs for import_data."""
        form = kwargs.get("form", None)
        if form and hasattr(form, "cleaned_data"):
            kwargs.update({"push_method": form.cleaned_data.get("push_method", None)})
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
