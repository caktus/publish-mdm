import structlog
from import_export.resources import ModelResource
from import_export.results import Result
import tablib

from .models import Device
from config.dagster import dagster_enabled, trigger_dagster_job

logger = structlog.get_logger(__name__)


class DeviceResource(ModelResource):
    """Custom ModelResource for importing/exporting Devices."""

    class Meta:
        model = Device
        fields = ("id", "fleet", "serial_number", "app_user_name", "device_id")
        clean_model_instances = True
        skip_unchanged = True

    def save_instance(self, instance, is_create, row, **kwargs):
        """Exact copy of the ModelResource.save_instance except it passes a
        is_dry_run arg to do_instance_save.
        """
        self.before_save_instance(instance, row, **kwargs)
        if self._meta.use_bulk:
            if is_create:
                self.create_instances.append(instance)
            else:
                self.update_instances.append(instance)
        else:
            if not self._is_using_transactions(kwargs) and self._is_dry_run(kwargs):
                # we don't have transactions and we want to do a dry_run
                pass
            else:
                self.do_instance_save(instance, is_create, self._is_dry_run(kwargs))
        self.after_save_instance(instance, row, **kwargs)

    def do_instance_save(self, instance: Device, is_create: bool, is_dry_run: bool = False):
        """Save the instance to the database, optionally pushing to MDM."""
        push_to_mdm = not is_dry_run and not dagster_enabled()
        instance.save(push_to_mdm=push_to_mdm)

    def after_import(self, dataset: tablib.Dataset, result: Result, dry_run: bool = True, **kwargs):
        super().after_import(dataset, result, **kwargs)
        if not dagster_enabled():
            return
        if dry_run:
            logger.debug("Dry run mode, skipping post-import actions")
            return
        # Trigger the Dagster job to push device configurations after import
        device_pks = [row.object_id for row in result if row.is_new() or row.is_update()]
        logger.info("Triggering Dagster job", device_pks=device_pks)
        try:
            run_config = {
                "ops": {"push_tinymdm_device_config": {"config": {"device_pks": device_pks}}}
            }
            trigger_dagster_job(job_name="tinymdm_job", run_config=run_config)
        except Exception as e:
            logger.error("Failed to trigger Dagster job after import", error=str(e))
            raise e
