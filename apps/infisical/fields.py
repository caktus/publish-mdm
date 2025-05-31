from django.db import models
from django.utils.functional import cached_property

from .api import kms_api


class EncryptedCol(models.expressions.Col):
    def get_db_converters(self, connection):
        """Don't call self.target.get_db_converters() if self.target != self.output_field.
        self.target.get_db_converters() would call EncryptedMixin.from_db_value()
        which decrypts the DB value, and we don't want to do that when we've set a
        different output_field.
        """
        return self.output_field.get_db_converters(connection)


class EncryptedMixin:
    # Based on https://gitlab.com/lansharkconsulting/django/django-encrypted-model-fields/-/blob/develop/encrypted_model_fields/fields.py#L64

    def from_db_value(self, value, *args, **kwargs):
        if value:
            return kms_api.decrypt(self.model.__name__.lower(), value)
        return self.to_python(value)

    def get_db_prep_save(self, value, connection):
        value = super().get_db_prep_save(value, connection)

        if value is None:
            return value

        return kms_api.encrypt(self.model.__name__.lower(), value)

    def get_internal_type(self):
        return "TextField"

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()

        if "max_length" in kwargs:
            del kwargs["max_length"]

        return name, path, args, kwargs

    @cached_property
    def cached_col(self):
        return EncryptedCol(self.model._meta.db_table, self, output_field=models.TextField())

    def get_col(self, alias, output_field=None):
        """Like Field.get_col(), but returns an EncryptedCol with a TextField as
        the default output_field so the value is not decrypted by default.
        """
        if alias == self.model._meta.db_table and (
            output_field is None or isinstance(output_field, models.TextField)
        ):
            return self.cached_col
        return EncryptedCol(alias, self, output_field)


class EncryptedCharField(EncryptedMixin, models.CharField):
    pass


class EncryptedEmailField(EncryptedMixin, models.EmailField):
    pass
