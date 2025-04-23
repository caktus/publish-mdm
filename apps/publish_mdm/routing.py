from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path(
        "ws/publish-template/",
        consumers.PublishTemplateConsumer.as_asgi(),
        name="publish_template",
    ),
]
