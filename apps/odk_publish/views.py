import logging

from django.db import models
from django.http import HttpRequest
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from .etl.load import generate_and_save_app_user_collect_qrcodes
from .models import FormTemplateVersion
from .tables import FormTemplateTable


logger = logging.getLogger(__name__)


@login_required
def app_users_list(request: HttpRequest, odk_project_pk):
    app_users = request.odk_project.app_users.prefetch_related("app_user_forms__form_template")
    return render(request, "odk_publish/app_users.html", {"app_users": app_users})


@login_required
def app_users_generate_qr_codes(request: HttpRequest, odk_project_pk):
    generate_and_save_app_user_collect_qrcodes(project=request.odk_project)
    return redirect("odk_publish:app-users-list", odk_project_pk=odk_project_pk)


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
    context = {"form_templates": form_templates, "table": table}
    return render(request, "odk_publish/form_template_list.html", context)
