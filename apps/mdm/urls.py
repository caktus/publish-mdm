from django.urls import path
from .views import firmware_snapshot_view

app_name = "mdm"
urlpatterns = [
    path("api/firmware/", firmware_snapshot_view, name="firmware_snapshot"),
]
