import structlog

from django.http import HttpResponse
from django.views.decorators.http import require_http_methods

from .forms import FirmwareSnapshotForm

logger = structlog.get_logger()


@require_http_methods(["GET", "POST"])
def firmware_snapshot_view(request):
    form = FirmwareSnapshotForm(request=request)

    if form.is_valid():
        form.save()
        return HttpResponse(status=201)
    else:
        logger.error("Firmware snapshot validation failed", errors=form.errors)
        return HttpResponse(status=400)
