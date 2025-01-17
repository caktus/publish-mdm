import structlog

from django.contrib import admin
from .models import (
    CentralServer,
    Project,
    FormTemplate,
    FormTemplateVersion,
    AppUser,
    AppUserFormTemplate,
    AppUserFormVersion,
    TemplateVariable,
)
from django.contrib import messages
from django.db.models import QuerySet
from django.utils.translation import ngettext


logger = structlog.getLogger(__name__)


@admin.register(CentralServer)
class CentralServerAdmin(admin.ModelAdmin):
    list_display = ("base_url", "created_at", "modified_at")
    search_fields = ("base_url",)
    ordering = ("base_url",)


@admin.register(TemplateVariable)
class TemplateVariableAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "project_id", "central_server")
    search_fields = ("name", "project_id")
    list_filter = ("central_server",)
    filter_horizontal = ("template_variables",)


@admin.register(FormTemplate)
class FormTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "title_base", "form_id_base", "modified_at")
    search_fields = ("title_base", "form_id_base")
    list_filter = ("created_at", "modified_at")
    ordering = ("form_id_base",)

    actions = ("create_next_version",)

    @admin.action(description="Create next version")
    def create_next_version(self, request, queryset: QuerySet[FormTemplate]):
        """Attempt to create the next version of the selected form templates."""
        versions_created = 0
        for form_template in queryset:
            try:
                form_template.create_next_version(user=request.user)
                versions_created += 1
            except Exception as e:
                logger.exception("Error creating next version", form_template=form_template)
                self.message_user(
                    request,
                    f"Error creating next version for {form_template}: {e}",
                    messages.ERROR,
                )
        if versions_created:
            self.message_user(
                request,
                ngettext(
                    "%d form template version was created.",
                    "%d form template versions were created.",
                    queryset.count(),
                )
                % queryset.count(),
                messages.SUCCESS,
            )


@admin.register(FormTemplateVersion)
class FormTemplateVersionAdmin(admin.ModelAdmin):
    list_display = ("id", "form_template", "user", "version", "created_at")
    search_fields = ("form_template", "user")
    list_filter = ("created_at", "modified_at")
    ordering = ("created_at",)


class AppUserTemplateVariableInline(admin.TabularInline):
    model = AppUser.template_variables.through
    extra = 0


@admin.register(AppUser)
class AppUserAdmin(admin.ModelAdmin):
    date_hierarchy = "modified_at"
    list_display = ("id", "name", "project", "modified_at")
    list_filter = ("project",)
    search_fields = ("id", "name")
    ordering = ("name",)
    inlines = (AppUserTemplateVariableInline,)


@admin.register(AppUserFormTemplate)
class AppUserFormAdmin(admin.ModelAdmin):
    list_display = ("id", "app_user", "form_template", "modified_at")
    list_filter = ("modified_at",)
    ordering = ("app_user__name", "form_template__form_id_base")


@admin.register(AppUserFormVersion)
class AppUserFormVersionAdmin(admin.ModelAdmin):
    list_display = ("id", "app_user_form_template", "form_template_version", "modified_at")
    list_filter = ("modified_at",)
    ordering = ("app_user_form_template__app_user__name", "form_template_version__version")
