from django.contrib import admin
from .models import CentralServer, Project, FormTemplate, FormTemplateVersion


@admin.register(CentralServer)
class CentralServerAdmin(admin.ModelAdmin):
    list_display = ("base_url", "created_at", "modified_at")
    search_fields = ("base_url",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "project_id", "central_server")
    search_fields = ("name", "project_id")
    list_filter = ("central_server",)


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
    ordering = ("created_at",)
