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


logger = structlog.getLogger(__name__)


@admin.register(CentralServer)
class CentralServerAdmin(admin.ModelAdmin):
    list_display = ("base_url", "created_at", "modified_at")
    search_fields = ("base_url",)
    ordering = ("base_url",)


@admin.register(TemplateVariable)
class TemplateVariableAdmin(admin.ModelAdmin):
    list_display = ("name", "transform")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "central_id", "central_server")
    search_fields = ("name", "central_id")
    list_filter = ("central_server",)
    filter_horizontal = ("template_variables",)


@admin.register(FormTemplate)
class FormTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "title_base", "form_id_base", "modified_at")
    search_fields = ("title_base", "form_id_base")
    list_filter = ("created_at", "modified_at")
    ordering = ("form_id_base",)


@admin.register(FormTemplateVersion)
class FormTemplateVersionAdmin(admin.ModelAdmin):
    list_display = ("id", "form_template", "user", "version", "created_at")
    search_fields = ("form_template", "user")
    list_filter = ("created_at", "modified_at")
    ordering = ("-created_at",)


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
