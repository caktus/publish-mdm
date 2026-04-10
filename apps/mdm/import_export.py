import structlog
import tablib
from import_export.resources import ModelResource
from import_export.results import Result

from config.dagster import trigger_dagster_job

from .models import Device, PushMethodChoices

logger = structlog.get_logger(__name__)


class DeviceResource(ModelResource):
    """Custom ModelResource for importing/exporting Devices."""

    class Meta:
        model = Device
        fields = ("id", "fleet", "serial_number", "app_user_name", "device_id")
        clean_model_instances = True
        skip_unchanged = True

    def after_import(self, dataset: tablib.Dataset, result: Result, dry_run: bool = True, **kwargs):
        super().after_import(dataset, result, **kwargs)
        if dry_run:
            logger.debug("Dry run mode, skipping post-import actions")
            return
        push_method = kwargs.get("push_method")
        if push_method == PushMethodChoices.ALL:
            device_pks = [row.object_id for row in result]
            logger.info("Post-import actions triggered for all devices", device_pks=device_pks)
        else:
            device_pks = [row.object_id for row in result if row.is_new() or row.is_update()]
            logger.info(
                "Post-import actions triggered for new/updated devices only", device_pks=device_pks
            )
        # Trigger the Dagster job to push device configurations after import
        logger.info("Triggering Dagster job", device_pks=device_pks)
        try:
            run_config = {"ops": {"push_mdm_device_config": {"config": {"device_pks": device_pks}}}}
            trigger_dagster_job(job_name="mdm_job", run_config=run_config)
        except Exception as e:
            logger.error("Failed to trigger Dagster job after import", error=str(e))
            raise e
