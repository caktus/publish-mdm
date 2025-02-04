from decimal import InvalidOperation
from functools import partial

from django.core.exceptions import ValidationError
from import_export import resources, fields, widgets

from .models import AppUser, AppUserTemplateVariable


class AppUserTemplateVariableWidget(widgets.ForeignKeyWidget):
    def __init__(self, template_variable, **kwargs):
        self.template_variable = template_variable
        super().__init__(AppUserTemplateVariable, field="value", **kwargs)

    def get_lookup_kwargs(self, value, row, **kwargs):
        return {"template_variable": self.template_variable, "app_user_id": row["id"] or None}

    def clean(self, value, row=None, **kwargs):
        if value and len(str(value)) > 1024:
            raise ValueError("Value cannot be more than 1024 characters long.")
        try:
            template_variable = super().clean(value, row, **kwargs)
        except AppUserTemplateVariable.DoesNotExist:
            template_variable = AppUserTemplateVariable(
                value=value, **self.get_lookup_kwargs(value, row, **kwargs)
            )
        else:
            if template_variable is not None:
                template_variable.value = value
        return template_variable


class AppUserTemplateVariableField(fields.Field):
    def save(self, instance, row, is_m2m=False, **kwargs):
        cleaned = self.clean(row, **kwargs)
        if cleaned is None:
            instance._template_variables_to_delete.append(self.column_name)
        else:
            instance._template_variables_to_save.append(cleaned)


class PositiveIntegerWidget(widgets.IntegerWidget):
    def clean(self, value, row=None, **kwargs):
        try:
            val = super().clean(value, row, **kwargs)
        except InvalidOperation:
            raise ValueError("Value must be an integer.")
        if val < 0:
            raise ValueError("Value must be positive.")
        return val


class AppUserResource(resources.ModelResource):
    central_id = fields.Field(
        attribute="central_id", column_name="central_id", widget=PositiveIntegerWidget()
    )

    class Meta:
        model = AppUser
        fields = ("id", "name", "central_id")
        clean_model_instances = True

    def __init__(self, project):
        self.project = project
        super().__init__()
        for template_variable in project.template_variables.all():
            self.fields[template_variable.name] = AppUserTemplateVariableField(
                attribute=template_variable.name,
                column_name=template_variable.name,
                dehydrate_method=partial(self.get_template_variable_value, template_variable.pk),
                widget=AppUserTemplateVariableWidget(template_variable),
            )

    def export_resource(self, instance, selected_fields=None, **kwargs):
        instance.template_variables_dict = {
            i.template_variable_id: i.value for i in instance.app_user_template_variables.all()
        }
        return super().export_resource(instance, selected_fields, **kwargs)

    def get_queryset(self):
        return self.project.app_users.all()

    def get_instance(self, instance_loader, row):
        instance = super().get_instance(instance_loader, row)
        if row["id"] and not instance:
            raise ValidationError(
                {"id": f"An app user with ID {row['id']} does not exist in the current project."}
            )
        return instance

    @staticmethod
    def get_template_variable_value(variable_pk, app_user):
        return app_user.template_variables_dict.get(variable_pk)

    def import_instance(self, instance, row, **kwargs):
        instance.project = self.project
        instance._template_variables_to_save = []
        instance._template_variables_to_delete = []
        super().import_instance(instance, row, **kwargs)

    def do_instance_save(self, instance, is_create):
        instance.save()
        for template_variable in instance._template_variables_to_save:
            template_variable.app_user = instance
            template_variable.save()
        for name in instance._template_variables_to_delete:
            instance.app_user_template_variables.filter(template_variable__name=name).delete()
