from decimal import InvalidOperation
from functools import partial

import structlog
from django.core.exceptions import ValidationError
from import_export import resources, fields, widgets

from .models import AppUser, AppUserTemplateVariable

logger = structlog.getLogger(__name__)


class AppUserTemplateVariableWidget(widgets.ForeignKeyWidget):
    """Widget for the AppUserTemplateVariable columns in the import/export files."""

    def __init__(self, template_variable, **kwargs):
        # The TemplateVariable instance for the column
        self.template_variable = template_variable
        super().__init__(AppUserTemplateVariable, field="value", **kwargs)

    def get_lookup_kwargs(self, value, row, **kwargs):
        # A dictionary used to query the AppUserTemplateVariable model to get
        # the variable for the current row
        return {"template_variable": self.template_variable, "app_user_id": row["id"] or None}

    def clean(self, value, row=None, **kwargs):
        """Validate the AppUserTemplateVariable during import."""
        try:
            template_variable = super().clean(value, row, **kwargs)
        except AppUserTemplateVariable.DoesNotExist:
            template_variable = AppUserTemplateVariable(
                value=value, **self.get_lookup_kwargs(value, row, **kwargs)
            )
        if template_variable is not None:
            template_variable.value = value
            try:
                template_variable.full_clean(exclude=["app_user"])
            except ValidationError as e:
                raise ValueError(e.messages[0])
        return template_variable


class AppUserTemplateVariableField(fields.Field):
    """Field for the AppUserTemplateVariable columns in the import/export files."""

    def save(self, instance, row, is_m2m=False, **kwargs):
        """Queue up saving or deleting the AppUserTemplateVariable during import.
        At this point the related AppUser may not exist yet (if "id" column is blank)
        and/or may not be fully validated so we'll save or delete the
        AppUserTemplateVariable later in `AppUserResource.do_instance_save()`.
        """
        # Get the validated AppUserTemplateVariable. It will be None if the value
        # is blank in the import file, in which case we need to delete the variable
        cleaned = self.clean(row, **kwargs)
        if cleaned is None:
            instance._template_variables_to_delete.append(self.column_name)
        else:
            instance._template_variables_to_save.append(cleaned)


class PositiveIntegerWidget(widgets.IntegerWidget):
    """Widget for the `central_id` column."""

    def clean(self, value, row=None, **kwargs):
        try:
            val = super().clean(value, row, **kwargs)
        except InvalidOperation:
            # The base class will raise a decimal.InvalidOperation if the value
            # is not a valid number
            raise ValueError("Value must be an integer.")
        if val and val < 0:
            raise ValueError("Value must be positive.")
        return val


class AppUserResource(resources.ModelResource):
    """Custom ModelResource for importing/exporting AppUsers."""

    central_id = fields.Field(
        attribute="central_id", column_name="central_id", widget=PositiveIntegerWidget()
    )

    class Meta:
        model = AppUser
        fields = ("id", "name", "central_id")
        clean_model_instances = True

    def __init__(self, project):
        # The project for which we are importing/exporting AppUsers
        self.project = project
        super().__init__()
        # Add columns for each TemplateVariable related to the project passed in
        for template_variable in project.template_variables.all():
            self.fields[template_variable.name] = AppUserTemplateVariableField(
                attribute=template_variable.name,
                column_name=template_variable.name,
                # The `dehydrate_method` will be called with an AppUser instance as
                # the only argument to get the value for the AppUserTemplateVariable
                # column during export
                dehydrate_method=partial(self.get_template_variable_value, template_variable.pk),
                widget=AppUserTemplateVariableWidget(template_variable),
            )

    def export_resource(self, instance, selected_fields=None, **kwargs):
        """Called for each AppUser instance during export."""
        # Create a dictionary that we can use to look up template variables
        # for the instance, instead of doing a DB query for each variable.
        # The template variables are prefetched in the queryset passed in to
        # the `AppUserResource.export()` call in the view
        instance.template_variables_dict = {
            i.template_variable_id: i.value for i in instance.app_user_template_variables.all()
        }
        return super().export_resource(instance, selected_fields, **kwargs)

    def get_queryset(self):
        # Queryset used to look up AppUsers during import
        return self.project.app_users.all()

    def get_instance(self, instance_loader, row):
        """Called during import to get the current AppUser, by querying the
        queryset from `get_queryset()` using the id from the current row.
        """
        # `instance` will be None if an AppUser with the ID could not be found
        # in the queryset from `get_queryset()`
        instance = super().get_instance(instance_loader, row)
        if row["id"] and not instance:
            raise ValidationError(
                {"id": f"An app user with ID {row['id']} does not exist in the current project."}
            )
        return instance

    @staticmethod
    def get_template_variable_value(variable_pk, app_user):
        """Used to set the `dehydrate_method` argument when instantiating a
        AppUserTemplateVariableField.
        """
        return app_user.template_variables_dict.get(variable_pk)

    def import_instance(self, instance, row, **kwargs):
        """Called for each AppUser during import."""
        instance.project = self.project
        # We'll use these lists to queue up AppUserTemplateVariables for saving
        # or deleting together in the do_instance_save() method below.
        instance._template_variables_to_save = []
        instance._template_variables_to_delete = []
        super().import_instance(instance, row, **kwargs)

    def do_instance_save(self, instance, is_create):
        """Save the AppUser and save/delete the AppUserTemplateVariables."""
        logger.info(
            "Updating AppUser via file import",
            new=is_create,
            id=instance.id,
            project_id=self.project.id,
        )
        instance.save()
        for template_variable in instance._template_variables_to_save:
            template_variable.app_user = instance
            logger.info(
                "Updating AppUserTemplateVariable via file import",
                new=not template_variable.pk,
                id=template_variable.id,
                variable_name=template_variable.template_variable.name,
                app_user_id=instance.id,
                project_id=self.project.id,
            )
            template_variable.save()
        if not is_create:
            for name in instance._template_variables_to_delete:
                logger.info(
                    "Deleting AppUserTemplateVariable via file import",
                    variable_name=name,
                    app_user_id=instance.id,
                    project_id=self.project.id,
                )
                instance.app_user_template_variables.filter(template_variable__name=name).delete()
