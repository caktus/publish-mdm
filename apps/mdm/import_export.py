from import_export.resources import ModelResource

from .models import Device


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

    def do_instance_save(self, instance, is_create, is_dry_run=False):
        """Only push changes to MDM if not in dry run (Preview) mode."""
        instance.save(push_to_mdm=not is_dry_run)
