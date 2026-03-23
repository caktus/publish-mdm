import json
import structlog

from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from django.conf import settings

from .forms import FirmwareSnapshotForm

logger = structlog.get_logger()


@csrf_exempt
@require_POST
def firmware_snapshot_view(request):
    api_key = settings.MDM_FIRMWARE_API_KEY
    if api_key:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header != f"Bearer {api_key}":
            return HttpResponse(status=401)
    else:
        logger.warning(
            "firmware_snapshot_view: MDM_FIRMWARE_API_KEY not configured; endpoint is unauthenticated",
            remote_addr=request.META.get("REMOTE_ADDR"),
        )
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
