import logging

from django.http import HttpRequest
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from .etl.load import generate_and_save_app_user_collect_qrcodes


logger = logging.getLogger(__name__)


@login_required
def app_users_list(request: HttpRequest, odk_project_pk):
    app_users = request.odk_project.app_users.prefetch_related("app_user_forms__form_template")
    return render(request, "odk_publish/app_users.html", {"app_users": app_users})


@login_required
def app_users_generate_qr_codes(request: HttpRequest, odk_project_pk):
    generate_and_save_app_user_collect_qrcodes(project=request.odk_project)
    return redirect("odk_publish:app-users-list", odk_project_pk=odk_project_pk)
