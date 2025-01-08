from django.urls import path

from . import views

app_name = "odk_publish"
urlpatterns = [
    path(
        "<int:odk_project_pk>/app-users/",
        views.app_users_list,
        name="app-users-list",
    ),
    path(
        "<int:odk_project_pk>/app-users/generate-qr-codes/",
        views.app_users_generate_qr_codes,
        name="app-users-generate-qr-codes",
    ),
]
