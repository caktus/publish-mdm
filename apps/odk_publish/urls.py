from django.urls import path

from . import views

app_name = "odk_publish"
urlpatterns = [
    path(
        "servers/sync/",
        views.server_sync,
        name="server-sync",
    ),
    path(
        "servers/sync/projects/",
        views.server_sync_projects,
        name="server-sync-projects",
    ),
    path(
        "<int:odk_project_pk>/app-users/",
        views.app_user_list,
        name="app-user-list",
    ),
    path(
        "<int:odk_project_pk>/app-users/generate-qr-codes/",
        views.app_user_generate_qr_codes,
        name="app-users-generate-qr-codes",
    ),
    path(
        "<int:odk_project_pk>/form-templates/",
        views.form_template_list,
        name="form-template-list",
    ),
    path(
        "<int:odk_project_pk>/form-templates/<int:form_template_id>/",
        views.form_template_detail,
        name="form-template-detail",
    ),
    path(
        "<int:odk_project_pk>/form-templates/<int:form_template_id>/publish/",
        views.form_template_publish,
        name="form-template-publish",
    ),
    path(
        "<int:odk_project_pk>/form-templates/<int:form_template_id>/publish-next-version/",
        views.form_template_publish_next_version,
        name="form-template-publish-next-version",
    ),
]
