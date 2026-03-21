from django.urls import path

from . import views

app_name = "mdm"

urlpatterns = [
    path("mdm/api/firmware/", views.firmware_snapshot_view, name="firmware_snapshot"),
    # Policy editor
    path(
        "o/<slug:organization_slug>/policies/",
        views.policy_list,
        name="policy-list",
    ),
    path(
        "o/<slug:organization_slug>/policies/add/",
        views.policy_add,
        name="policy-add",
    ),
    path(
        "o/<slug:organization_slug>/policies/<int:policy_id>/",
        views.policy_edit,
        name="policy-edit",
    ),
    path(
        "o/<slug:organization_slug>/policies/<int:policy_id>/name/",
        views.policy_save_name,
        name="policy-save-name",
    ),
    path(
        "o/<slug:organization_slug>/policies/<int:policy_id>/odk-package/",
        views.policy_save_odk_package,
        name="policy-save-odk-package",
    ),
    path(
        "o/<slug:organization_slug>/policies/<int:policy_id>/applications/add/",
        views.policy_add_application,
        name="policy-add-application",
    ),
    path(
        "o/<slug:organization_slug>/policies/<int:policy_id>/applications/<int:app_id>/",
        views.policy_save_application,
        name="policy-save-application",
    ),
    path(
        "o/<slug:organization_slug>/policies/<int:policy_id>/applications/<int:app_id>/delete/",
        views.policy_delete_application,
        name="policy-delete-application",
    ),
    path(
        "o/<slug:organization_slug>/policies/<int:policy_id>/applications/<int:app_id>/configure/",
        views.policy_save_managed_config,
        name="policy-save-managed-config",
    ),
    path(
        "o/<slug:organization_slug>/policies/<int:policy_id>/password/",
        views.policy_save_password,
        name="policy-save-password",
    ),
    path(
        "o/<slug:organization_slug>/policies/<int:policy_id>/vpn/",
        views.policy_save_vpn,
        name="policy-save-vpn",
    ),
    path(
        "o/<slug:organization_slug>/policies/<int:policy_id>/developer/",
        views.policy_save_developer,
        name="policy-save-developer",
    ),
    path(
        "o/<slug:organization_slug>/policies/<int:policy_id>/save-kiosk/",
        views.policy_save_kiosk,
        name="policy-save-kiosk",
    ),
    path(
        "o/<slug:organization_slug>/policies/<int:policy_id>/variables/add/",
        views.policy_add_variable,
        name="policy-add-variable",
    ),
    path(
        "o/<slug:organization_slug>/policies/<int:policy_id>/variables/<int:var_id>/delete/",
        views.policy_delete_variable,
        name="policy-delete-variable",
    ),
]
