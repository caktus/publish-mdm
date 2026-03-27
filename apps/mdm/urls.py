from django.urls import path

from .views import amapi_notifications_view, firmware_snapshot_view

app_name = "mdm"
urlpatterns = [
    path("api/firmware/", firmware_snapshot_view, name="firmware_snapshot"),
    path("api/amapi/notifications/", amapi_notifications_view, name="amapi_notifications"),
]
