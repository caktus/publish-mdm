from typing import ClassVar

import structlog
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import mark_safe
from invitations.admin import InvitationAdmin
from requests.exceptions import RequestException

from apps.mdm.mdms import AndroidEnterprise

from .etl.load import generate_and_save_app_user_collect_qrcodes
from .forms import CentralServerForm
from .models import (
    AndroidEnterpriseAccount,
    AppUser,
    AppUserFormTemplate,
    AppUserFormVersion,
    CentralServer,
    FormTemplate,
    FormTemplateVersion,
    Organization,
    OrganizationInvitation,
    Project,
    ProjectAttachment,
    ProjectTemplateVariable,
    TemplateVariable,
)

logger = structlog.getLogger(__name__)


@admin.register(CentralServer)
class CentralServerAdmin(admin.ModelAdmin):
    list_display = ("base_url", "created_at", "modified_at", "organization")
    search_fields = ("base_url",)
    ordering = ("base_url",)
    form = CentralServerForm

    def save_model(self, request, obj, form, change):
        if change:
            # If the username or password is blank, keep the current value.
            # The other fields cannot be blank.
            obj.save(update_fields=[f for f, v in form.cleaned_data.items() if v])
        else:
            obj.save()


@admin.register(TemplateVariable)
class TemplateVariableAdmin(admin.ModelAdmin):
    list_display = ("name", "transform", "organization")
    search_fields = ("name",)
    ordering = ("name",)


class ProjectAttachmentInline(admin.TabularInline):
    model = ProjectAttachment
    extra = 0


class ProjectTemplateVariableInline(admin.TabularInline):
    """Allows editing project-level template variables directly in ProjectAdmin."""

    model = ProjectTemplateVariable
    extra = 1
    fields = ("template_variable", "value")
    autocomplete_fields = ("template_variable",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "central_id", "central_server", "organization", "app_language")
    search_fields = ("name", "central_id")
    list_filter = ("central_server",)
    filter_horizontal = ("template_variables",)
    inlines = (ProjectAttachmentInline, ProjectTemplateVariableInline)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Regenerate app user QR codes if any field that impacts them has changed
        qr_code_fields = ("app_language", "central_id", "name")
        if change and any(field in form.changed_data for field in qr_code_fields):
            generate_and_save_app_user_collect_qrcodes(obj)

    def save_formset(self, request, form, formset, change):
        """Overriden to regenerate app user QR codes if the project's admin_pw
        template variable has changed.
        """
        is_template_variables_formset = formset.model == ProjectTemplateVariable
        if change and is_template_variables_formset:
            admin_pw = form.instance.get_admin_pw()
        super().save_formset(request, form, formset, change)
        if (
            change
            and is_template_variables_formset
            and formset.has_changed()
            and admin_pw != form.instance.get_admin_pw()
        ):
            generate_and_save_app_user_collect_qrcodes(form.instance)


class FormTemplateForm(forms.ModelForm):
    class Meta:
        model = FormTemplate
        fields = (
            "project",
            "title_base",
            "form_id_base",
            "template_url",
            "template_url_user",
        )
        widgets: ClassVar = {
            "template_url_user": forms.HiddenInput,
        }


@admin.register(FormTemplate)
class FormTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title_base",
        "form_id_base",
        "template_url_user",
        "project",
        "modified_at",
    )
    search_fields = ("title_base", "form_id_base")
    list_filter = ("created_at", "project")
    ordering = ("form_id_base",)
    form = FormTemplateForm

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        # Add context variables needed for the Google Picker
        extra_context.update(
            {
                "google_client_id": settings.GOOGLE_CLIENT_ID,
                "google_scopes": " ".join(settings.SOCIALACCOUNT_PROVIDERS["google"]["SCOPE"]),
                "google_api_key": settings.GOOGLE_API_KEY,
                "google_app_id": settings.GOOGLE_APP_ID,
            }
        )
        response = super().changeform_view(
            request,
            object_id,
            form_url,
            extra_context=extra_context,
        )
        # Needed for the Google Picker popup to work
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        return response


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
    ordering = ("-form_template_version__version",)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at", "modified_at", "public_signup_enabled")
    search_fields = ("name", "slug")
    ordering = ("name",)
    filter_horizontal = ("users",)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Create the default fleet for new organizations, unless Android Enterprise is active —
        # it requires an enrolled enterprise first, so the fleet is created in enterprise_callback.
        if not change and settings.ACTIVE_MDM["name"] != "Android Enterprise":
            try:
                obj.create_default_fleet()
            except RequestException as e:
                logger.debug("Unable to create the default fleet", organization=obj, exc_info=True)
                messages.warning(
                    request,
                    mark_safe(
                        "The organization was created but the following "
                        f"{settings.ACTIVE_MDM['name']} API error occurred while "
                        f"setting up its default Fleet:<br><code>{getattr(e, 'api_error', e)}</code>"
                    ),
                )


admin.site.unregister(OrganizationInvitation)


@admin.register(OrganizationInvitation)
class OrganizationInvitationAdmin(InvitationAdmin):
    list_display = ("email", "organization", "sent", "accepted")


@admin.register(AndroidEnterpriseAccount)
class AndroidEnterpriseAccountAdmin(admin.ModelAdmin):
    list_display = ("organization", "enterprise_name", "is_enrolled", "created_at")
    readonly_fields = (
        "signup_url_name",
        "signup_url_link",
        "callback_token",
        "enterprise_name",
        "created_at",
        "modified_at",
    )
    fields = (
        "organization",
        "signup_url_name",
        "signup_url_link",
        "callback_token",
        "enterprise_name",
        "created_at",
        "modified_at",
    )

    @admin.display(description="Signup URL")
    def signup_url_link(self, obj):
        if obj.signup_url:
            return mark_safe(
                f'<a href="{obj.signup_url}" rel="nofollow noreferrer">{obj.signup_url}</a>'
            )
        return "—"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change and not obj.signup_url:
            try:
                callback_path = reverse(
                    "publish_mdm:enterprise-callback",
                    kwargs={"callback_token": obj.callback_token},
                )
                callback_domain = settings.ANDROID_ENTERPRISE_CALLBACK_DOMAIN
                callback_url = (
                    "https://" + callback_domain + callback_path
                    if callback_domain
                    else request.build_absolute_uri(callback_path)
                )
                signup = AndroidEnterprise.get_signup_url(callback_url=callback_url)
                obj.signup_url_name = signup["name"]
                obj.signup_url = signup["url"]
                obj.save(update_fields=["signup_url_name", "signup_url", "modified_at"])
            except Exception as e:
                messages.error(request, f"Failed to generate signup URL: {e}")
