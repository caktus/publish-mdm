from django.urls import path

from . import consumers, screen_consumers

websocket_urlpatterns = [
    path(
        "ws/publish-template/",
        consumers.PublishTemplateConsumer.as_asgi(),
        name="publish_template",
    ),
    path(
        "ws/devices/<int:device_pk>/screen-view/",
        screen_consumers.DeviceScreenViewerConsumer.as_asgi(),
        name="device_screen_view",
    ),
    path(
        "ws/devices/screen-publish/<str:token>/",
        screen_consumers.DeviceScreenPublisherConsumer.as_asgi(),
        name="device_screen_publish",
    ),
]
