import logging
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localdate
from import_export.results import RowResult
from import_export.tmp_storages import MediaStorage
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers.data import JsonLexer

from .etl.load import generate_and_save_app_user_collect_qrcodes, sync_central_project

from .forms import (
    ProjectSyncForm,
    AppUserConfirmImportForm,
    AppUserExportForm,
    AppUserImportForm,
    PublishTemplateForm,
    FormTemplateForm,
)
from .import_export import AppUserResource
from .models import FormTemplateVersion, FormTemplate
from .nav import Breadcrumbs
from .tables import FormTemplateTable


logger = logging.getLogger(__name__)


@login_required
@transaction.atomic
def server_sync(request: HttpRequest):
    form = ProjectSyncForm(request=request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        project = sync_central_project(
            base_url=form.cleaned_data["server"], project_id=form.cleaned_data["project"]
        )
        messages.add_message(request, messages.SUCCESS, "Project synced.")
        return redirect("odk_publish:form-template-list", odk_project_pk=project.id)
    context = {
        "form": form,
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[("Sync Project", "sync-project")],
        ),
    }
    return render(request, "odk_publish/project_sync.html", context)


@login_required
def server_sync_projects(request: HttpRequest):
    form = ProjectSyncForm(request=request, data=request.GET or None)
    return render(request, "odk_publish/project_sync.html#project-select-partial", {"form": form})


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
    """Publish a FormTemplate to ODK Central."""
    form_template: FormTemplate = get_object_or_404(
        request.odk_project.form_templates, pk=form_template_id
    )
    form = PublishTemplateForm(
        request=request, form_template=form_template, data=request.POST or None
    )
    template = "odk_publish/form_template_publish.html"
    if request.htmx:
        # Only render the form container for htmx requests
        template = f"{template}#publish-partial"
    if request.method == "POST" and form.is_valid():
        # The publish process is initiated by the HTMX response, so we don't
        # need to do anything here.
        pass
    context = {
        "form": form,
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
    return render(request, template, context)


@login_required
def app_user_export(request, odk_project_pk):
    """Exports AppUsers to a CSV or Excel file.

    For each user in the current project, there will be "id", "name", and "central_id"
    columns. Additionally there will be a column for each TemplateVariable related to
    the current project.
    """
    resource = AppUserResource(request.odk_project)
    form = AppUserExportForm([resource], data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        export_format = form.cleaned_data["format"]
        dataset = resource.export()
        data = export_format.export_data(dataset)
        filename = f"app_users_{odk_project_pk}_{localdate()}.{export_format.get_extension()}"
        return HttpResponse(
            data,
            content_type=export_format.get_content_type(),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    context = {
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[("App Users", "app-user-list"), ("Export", "app-users-export")],
        ),
        "form": form,
    }
    return render(request, "odk_publish/app_user_export.html", context)


@login_required
def app_user_import(request, odk_project_pk):
    """Imports AppUsers from a CSV or Excel file.

    The file is expected to have the same columns as a file exported using the
    app_user_export view above. New AppUsers will be added if the "id" column is blank.
    If a AppUserTemplateVariable column is blank and it exists in the database,
    it will be deleted. The import is done in 2 stages: first the user uploads a
    file, then they will be shown a preview of the import and asked to confirm.
    Once the user confirms, the database will be updated.
    """
    resource = AppUserResource(request.odk_project)
    result = None
    confirm = "original_file_name" in request.POST
    if confirm:
        # Confirm stage
        form_class = AppUserConfirmImportForm
        args = ()
    else:
        # Initial import stage
        form_class = AppUserImportForm
        args = ([resource],)
    form = form_class(*args, data=request.POST or None, files=request.FILES or None)
    if request.POST and form.is_valid():
        result = resource.import_data(
            form.dataset,
            use_transactions=True,
            rollback_on_validation_errors=True,
            dry_run=not confirm,
        )
        if not (result.has_validation_errors() or result.has_errors()):
            if confirm:
                messages.success(
                    request,
                    f"Import finished successfully, with {result.totals[RowResult.IMPORT_TYPE_NEW]} "
                    f"new and {result.totals[RowResult.IMPORT_TYPE_UPDATE]} updated app users.",
                )
                return redirect("odk_publish:app-user-list", odk_project_pk=odk_project_pk)
            # Save the import file data in a temporary file and show the confirm page
            import_format = form.cleaned_data["format"]
            tmp_storage = MediaStorage(
                encoding=import_format.encoding,
                read_mode=import_format.get_read_mode(),
            )
            tmp_storage.save(form.file_data)
            form = AppUserConfirmImportForm(
                initial={
                    "import_file_name": tmp_storage.name,
                    "original_file_name": form.cleaned_data["import_file"].name,
                    "format": form.data["format"],
                    "resource": form.cleaned_data.get("resource", ""),
                }
            )
    if confirm:
        # An error has occurred during validation of the confirm form or during
        # the actual import. Since there are no fields the user can edit in the
        # confirm form, take them back to the initial import form so they can
        # begin the import process afresh.
        messages.error(request, "We could not complete your import. Please try importing again.")
        form = AppUserImportForm([resource])
    context = {
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[("App Users", "app-user-list"), ("Import", "app-users-import")],
        ),
        "form": form,
        "result": result,
        "confirm": isinstance(form, AppUserConfirmImportForm),
    }
    return render(request, "odk_publish/app_user_import.html", context)


def websockets_server_health(request):
    """When using separate ASGI and WSGI deployments, this can be used for health checks
    for the ASGI (Websockets) server.
    """
    return HttpResponse("OK")


@login_required
def app_user_detail(request: HttpRequest, odk_project_pk, app_user_pk):
    """Detail page for an AppUser."""
    app_user = get_object_or_404(request.odk_project.app_users, pk=app_user_pk)
    if app_user.qr_code_data:
        # Generate the HTML for the syntax-highligted JSON
        qr_code_data = json.dumps(app_user.qr_code_data, indent=4)
        qr_code_highlight_html = highlight(
            qr_code_data, JsonLexer(), HtmlFormatter(linenos="table")
        )
        # Get the JSON without newlines and extra spaces
        qr_code_data = json.dumps(app_user.qr_code_data, separators=(",", ":"))
    else:
        qr_code_highlight_html = qr_code_data = None
    context = {
        "app_user": app_user,
        "qr_code_highlight_html": qr_code_highlight_html,
        "qr_code_data": qr_code_data,
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[
                ("App Users", "app-user-list"),
                (app_user.name, "app-user-detail", [app_user.pk]),
            ],
        ),
    }
    return render(request, "odk_publish/app_user_detail.html", context)


@login_required
def change_form_template(request: HttpRequest, odk_project_pk, form_template_id=None):
    """Add or edit a FormTemplate."""
    if form_template_id:
        # Editing a FormTemplate
        form_template = get_object_or_404(request.odk_project.form_templates, pk=form_template_id)
    else:
        # Adding a new FormTemplate
        form_template = FormTemplate(project=request.odk_project)
    form = FormTemplateForm(request.POST or None, instance=form_template)
    if request.method == "POST" and form.is_valid():
        form_template = form.save()
        messages.success(
            request,
            f"Successfully {'edit' if form_template_id else 'add'}ed {form_template.title_base}.",
        )
        return redirect("odk_publish:form-template-list", odk_project_pk)
    context = {
        "form": form,
        "breadcrumbs": Breadcrumbs.from_items(
            request=request,
            items=[
                ("Form Templates", "form-template-list"),
                (f"Edit {form_template.title_base}", "edit-form-template", [form_template_id])
                if form_template_id
                else ("Add", "add-form-template"),
            ],
        ),
        # Variables needed for selecting a spreadsheet for the `template_url` using Google Picker
        "google_client_id": settings.GOOGLE_CLIENT_ID,
        "google_scopes": " ".join(settings.SOCIALACCOUNT_PROVIDERS["google"]["SCOPE"]),
        "google_api_key": settings.GOOGLE_API_KEY,
        "google_app_id": settings.GOOGLE_APP_ID,
    }
    response = render(request, "odk_publish/change_form_template.html", context)
    # Needed for the Google Picker popup to work
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    return response
