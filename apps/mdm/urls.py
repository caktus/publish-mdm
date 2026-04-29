from django.urls import path

from . import views

app_name = "mdm"

urlpatterns = [
    path("mdm/api/firmware/", views.firmware_snapshot_view, name="firmware_snapshot"),
    path(
        "mdm/api/amapi/notifications/", views.amapi_notifications_view, name="amapi_notifications"
    ),
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
        "o/<slug:organization_slug>/policies/<int:policy_id>/applications/<int:app_id>/configure/",
        views.policy_save_managed_config,
        name="policy-save-managed-config",
    ),
    path(
        "o/<slug:organization_slug>/enrollment-tokens/",
        views.enrollment_token_list,
        name="enrollment-token-list",
    ),
    path(
        "o/<slug:organization_slug>/enrollment-tokens/create/",
        views.enrollment_token_create,
        name="enrollment-token-create",
    ),
    path(
        "o/<slug:organization_slug>/enrollment-tokens/<int:token_pk>/",
        views.enrollment_token_detail,
        name="enrollment-token-detail",
    ),
    path(
        "o/<slug:organization_slug>/enrollment-tokens/<int:token_pk>/revoke/",
        views.enrollment_token_revoke,
        name="enrollment-token-revoke",
    ),
]
