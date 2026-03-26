import base64
import json

import structlog
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import FirmwareSnapshotForm
from .mdms import get_active_mdm_instance

logger = structlog.get_logger()


@csrf_exempt
@require_POST
def firmware_snapshot_view(request):
    if not request.body:
        return HttpResponse(status=400)
    try:
        json_data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)
    form = FirmwareSnapshotForm(json_data=json_data)

    if form.is_valid():
        form.save()
        return HttpResponse(status=201)
    else:
        logger.error("Firmware snapshot validation failed", errors=form.errors)
        return HttpResponse(status=400)


@csrf_exempt
@require_POST
def amapi_notifications_view(request):
    """Handle push notifications from AMAPI via Google Cloud Pub/Sub.

    Google Cloud Pub/Sub delivers messages as HTTP POST requests to this endpoint.
    Each message contains a base64-encoded Device resource in the ``data`` field
    and a ``notificationType`` attribute.

    Authentication is performed by comparing the ``token`` query parameter
    against the ``ANDROID_ENTERPRISE_PUBSUB_TOKEN`` Django setting.  All
    requests are rejected if the setting is not configured.

    Returns HTTP 204 on success so that Pub/Sub acknowledges the message and
    does not retry.
    """
    secret_token = settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN
    if not secret_token:
        logger.warning("AMAPI notification rejected: ANDROID_ENTERPRISE_PUBSUB_TOKEN is not set")
        return HttpResponse(status=403)
    # The push subscription URL should include ?token=<secret>
    request_token = request.GET.get("token", "")
    if not (request_token and request_token == secret_token):
        logger.warning("AMAPI notification received with invalid or missing token")
        return HttpResponse(status=403)

    if not request.body:
        return HttpResponse(status=400)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("AMAPI notification body is not valid JSON")
        return HttpResponse(status=400)

    message = body.get("message", {})
    notification_type = message.get("attributes", {}).get("notificationType", "")
    data_b64 = message.get("data", "")

    if not data_b64:
        logger.warning(
            "AMAPI notification received without data payload",
            notification_type=notification_type,
        )
        return HttpResponse(status=204)

    try:
        device_data = json.loads(base64.b64decode(data_b64).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        logger.error("Failed to decode AMAPI notification data payload")
        return HttpResponse(status=400)

    logger.info(
        "AMAPI notification received",
        notification_type=notification_type,
        device_name=device_data.get("name"),
    )
    mdm = get_active_mdm_instance()

    if mdm.name != "Android Enterprise":
        logger.warning(
            "Active MDM is not Android Enterprise. Ignoring",
            mdm=mdm,
            notification_type=notification_type,
        )
    else:
        mdm.handle_device_notification(device_data, notification_type)

    return HttpResponse(status=204)
