"""Celery tasks for the MDM app."""

import structlog
from celery import shared_task

logger = structlog.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30, ignore_result=True)
def push_device_config_task(self, device_pk: int) -> None:
    """Push the device-specific AMAPI policy config to a single device.

    Queued asynchronously from the Pub/Sub notification handler so the
    ``amapi_notifications_view`` can return 204 quickly without waiting for
    the outbound AMAPI call to complete.
    """
    from apps.mdm.mdms import get_active_mdm_instance  # noqa: PLC0415
    from apps.mdm.models import Device  # noqa: PLC0415

    try:
        device = Device.objects.select_related("fleet__organization").get(pk=device_pk)
    except Device.DoesNotExist:
        logger.warning("push_device_config_task: device not found", device_pk=device_pk)
        return

    mdm = get_active_mdm_instance(organization=device.fleet.organization)
    if mdm is None:
        logger.warning("push_device_config_task: no active MDM", device_pk=device_pk)
        return

    try:
        mdm.push_device_config(device)
        logger.info("push_device_config_task: success", device_pk=device_pk)
    except Exception as exc:
        logger.exception("push_device_config_task: failed", device_pk=device_pk)
        raise self.retry(exc=exc)
