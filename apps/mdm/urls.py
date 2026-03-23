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
        "o/<slug:organization_slug>/policies/<int:policy_id>/applications/<int:app_id>/configure/",
        views.policy_save_managed_config,
        name="policy-save-managed-config",
    ),
]
