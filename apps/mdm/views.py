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
    if not api_key:
        # No API key configured — reject all requests rather than silently
        # accepting unauthenticated writes (VULN-002).
        logger.error(
            "firmware_snapshot_view: MDM_FIRMWARE_API_KEY not configured; rejecting request",
            remote_addr=request.META.get("REMOTE_ADDR"),
        )
        return HttpResponse(status=401)
    auth_header = request.headers.get("authorization", "")
    if auth_header != f"Bearer {api_key}":
        return HttpResponse(status=401)
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
