from decimal import InvalidOperation
from functools import partial

import structlog
from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from import_export import resources, fields, widgets

from .models import AppUser, AppUserFormTemplate, AppUserTemplateVariable

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

    def render(self, value, obj=None, **kwargs):
        """Return the string value of the variable, or an empty string if the user
        does not have the variable (value is None).
        """
        return value or ""


class AppUserTemplateVariableField(fields.Field):
    """Field for the AppUserTemplateVariable columns in the import/export files."""

    def save(self, instance, row, is_m2m=False, **kwargs):
        """Queue up saving or deleting the AppUserTemplateVariable during import.
        At this point the related AppUser may not exist yet (if "id" column is blank)
        and/or may not be fully validated so we'll save or delete the
        AppUserTemplateVariable later in `AppUserResource.do_instance_save()`.
        """
        # Get the validated AppUserTemplateVariable. It will be None if the value
        # is blank in the import file, in which case we need to delete the variable.
        # We'll also update template_variables_dict so that the preview page can show
        # the changes made to template variables, and unchanged rows can be skipped
        # when saving changes in the DB
        cleaned = self.clean(row, **kwargs)
        if cleaned is None:
            if self.column_name in instance.template_variables_dict:
                instance._template_variables_to_delete.append(self.column_name)
                del instance.template_variables_dict[self.column_name]
        else:
            instance._template_variables_to_save.append(cleaned)
            instance.template_variables_dict[self.column_name] = cleaned.value

    def get_value(self, instance):
        # Get the value of the template variable using the dehydrate method
        return self.dehydrate_method(instance)


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


class FormTemplatesWidget(widgets.Widget):
    """Widget for the `form_templates` column."""

    def clean(self, value, row=None, **kwargs):
        """Validates the form_templates column during import and returns a set
        of the form_id_base strings. A ValueError will be raised if any of the
        values in the comma-separated list does not match a FormTemplate related
        to the project.
        """
        if not value:
            return set()
        template_ids = {t for i in value.split(",") if (t := i.strip())}
        invalid = template_ids - set(kwargs["project_form_templates"])
        if invalid:
            raise ValueError(
                f"The following form templates do not exist on the project: {', '.join(invalid)}"
            )
        return template_ids

    def render(self, value, obj=None, **kwargs):
        """Renders a user's AppUserFormTemplates as a comma-separated list of
        their form_template.form_id_base values.
        """
        return ",".join(sorted(value)) if value else ""


class FormTemplatesField(fields.Field):
    """Field for the `form_templates` column."""

    def save(self, instance, row, is_m2m=False, **kwargs):
        """Updates the `_new_form_templates` variable with a set of validated
        FormTemplate.form_id_base values during import. We'll create and/or delete
        the AppUserFormTemplates later in `AppUserResource.do_instance_save()`.
        """
        instance._new_form_templates = self.clean(row, **kwargs)

    def get_value(self, instance):
        # `instance._new_form_templates` will be set in save() above during import.
        # `instance.form_templates` will be the original templates before import.
        return getattr(instance, "_new_form_templates", instance.form_templates)


class AppUserResource(resources.ModelResource):
    """Custom ModelResource for importing/exporting AppUsers."""

    central_id = fields.Field(
        attribute="central_id", column_name="central_id", widget=PositiveIntegerWidget()
    )
    form_templates = FormTemplatesField(
        attribute="form_templates", column_name="form_templates", widget=FormTemplatesWidget()
    )

    class Meta:
        model = AppUser
        fields = ("id", "name", "central_id", "form_templates")
        clean_model_instances = True
        skip_unchanged = True

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
                dehydrate_method=partial(self.get_template_variable_value, template_variable.name),
                widget=AppUserTemplateVariableWidget(template_variable),
            )

    def get_queryset(self):
        # Queryset used to look up AppUsers during import and export
        return self.project.app_users.prefetch_related(
            Prefetch(
                "app_user_template_variables",
                AppUserTemplateVariable.objects.select_related("template_variable"),
            ),
            Prefetch(
                "app_user_forms",
                AppUserFormTemplate.objects.select_related("form_template").order_by(
                    "form_template__form_id_base"
                ),
            ),
        )

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
    def get_template_variable_value(variable_name, app_user):
        """Used to set the `dehydrate_method` argument when instantiating a
        AppUserTemplateVariableField.
        """
        return app_user.template_variables_dict.get(variable_name)

    def import_instance(self, instance, row, **kwargs):
        """Called for each AppUser during import."""
        instance.project = self.project
        # We'll use these lists to queue up AppUserTemplateVariables for saving
        # or deleting together in the do_instance_save() method below.
        instance._template_variables_to_save = []
        instance._template_variables_to_delete = []
        # Dict of the project's FormTemplates to be used for validation in
        # FormTemplatesWidget.clean()
        kwargs["project_form_templates"] = self.form_templates
        super().import_instance(instance, row, **kwargs)

    def do_instance_save(self, instance, is_create):
        """Save the AppUser and save/delete AppUserTemplateVariables and AppUserFormTemplates."""
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
        if is_create:
            existing_form_templates = set()
        else:
            existing_form_templates = instance.form_templates
        # If the current instance has no `_new_form_templates` variable it means
        # the import file did not have a "form_templates" column, so the user's
        # form templates should be left unchanged
        new_form_templates = getattr(instance, "_new_form_templates", existing_form_templates)
        for form_id_base in new_form_templates - existing_form_templates:
            logger.info(
                "Adding a AppUserFormTemplate via file import",
                app_user_id=instance.id,
                project_id=self.project.id,
                form_id_base=form_id_base,
                template_id=self.form_templates[form_id_base],
            )
            instance.app_user_forms.create(form_template_id=self.form_templates[form_id_base])
        to_delete = existing_form_templates - new_form_templates
        if to_delete:
            logger.info(
                "Deleting AppUserFormTemplates via file import",
                app_user_id=instance.id,
                project_id=self.project.id,
                form_id_base_set=to_delete,
            )
            instance.app_user_forms.filter(form_template__form_id_base__in=to_delete).delete()

    def before_import(self, dataset, **kwargs):
        # A dict of the project's form templates that will be used for validation
        # of the "form_templates" column during import and for getting a FormTemplate ID
        # when creating a new AppUserFormTemplate
        self.form_templates = dict(self.project.form_templates.values_list("form_id_base", "id"))
