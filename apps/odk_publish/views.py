import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .etl.load import generate_and_save_app_user_collect_qrcodes
from .models import FormTemplateVersion, FormTemplate
from .nav import Breadcrumbs
from .tables import FormTemplateTable


logger = logging.getLogger(__name__)


@login_required
def app_user_list(request: HttpRequest, odk_project_pk):
    app_users = request.odk_project.app_users.prefetch_related("app_user_forms__form_template")
    context = {
        "app_users": app_users,
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[("App Users", "app-user-list")],
        ),
    }
    return render(request, "odk_publish/app_user_list.html", context)


@login_required
def app_user_generate_qr_codes(request: HttpRequest, odk_project_pk):
    generate_and_save_app_user_collect_qrcodes(project=request.odk_project)
    return redirect("odk_publish:app-user-list", odk_project_pk=odk_project_pk)


@login_required
def form_template_list(request: HttpRequest, odk_project_pk):
    form_templates = request.odk_project.form_templates.annotate(
        app_user_count=models.Count("app_user_forms"),
    ).prefetch_related(
        models.Prefetch(
            "versions",
            queryset=FormTemplateVersion.objects.order_by("-modified_at"),
            to_attr="latest_version",
        )
    )
    table = FormTemplateTable(data=form_templates, request=request, show_footer=False)
    context = {
        "form_templates": form_templates,
        "table": table,
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[("Form Templates", "form-template-list")],
        ),
    }
    return render(request, "odk_publish/form_template_list.html", context)


@login_required
def form_template_detail(request: HttpRequest, odk_project_pk: int, form_template_id: int):
    form_template: FormTemplate = get_object_or_404(
        request.odk_project.form_templates.annotate(
            app_user_count=models.Count("app_user_forms"),
        ).prefetch_related(
            models.Prefetch(
                "versions",
                queryset=FormTemplateVersion.objects.order_by("-modified_at"),
                to_attr="latest_version",
            )
        ),
        pk=form_template_id,
    )
    context = {
        "form_template": form_template,
        "form_template_app_users": form_template.app_user_forms.values_list(
            "app_user__name", flat=True
        ),
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[
                ("Form Templates", "form-template-list"),
                (form_template.title_base, "form-template-detail", [form_template.pk]),
            ],
        ),
    }
    return render(request, "odk_publish/form_template_detail.html", context)


@login_required
def form_template_publish(request: HttpRequest, odk_project_pk: int, form_template_id: int):
    form_template: FormTemplate = get_object_or_404(
        request.odk_project.form_templates, pk=form_template_id
    )
    context = {
        "form_template": form_template,
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[
                ("Form Templates", "form-template-list"),
                (form_template.title_base, "form-template-detail", [form_template.pk]),
                ("Publish", "form-template-publish", [form_template.pk]),
            ],
        ),
    }
    return render(request, "odk_publish/form_template_publish.html", context)


@login_required
@transaction.atomic
@require_http_methods(["POST"])
def form_template_publish_next_version(request: HttpRequest, odk_project_pk, form_template_id):
    form_template: FormTemplate = get_object_or_404(
        request.odk_project.form_templates, pk=form_template_id
    )
    version = form_template.create_next_version(user=request.user)
    messages.add_message(request, messages.SUCCESS, f"{version} published.")
    return HttpResponse(status=204)
