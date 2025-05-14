from django.db import models
from django.forms.widgets import PasswordInput

from .infisical import kms_api


class EncryptedMixin(object):
    # Based on https://gitlab.com/lansharkconsulting/django/django-encrypted-model-fields/-/blob/develop/encrypted_model_fields/fields.py#L64

    def from_db_value(self, value, *args, **kwargs):
        if value:
            return kms_api.decrypt(self.model.__name__.lower(), value)
        return self.to_python(value)

    def get_db_prep_save(self, value, connection):
        value = super(EncryptedMixin, self).get_db_prep_save(value, connection)

        if value is None:
            return value

        return kms_api.encrypt(self.model.__name__.lower(), value)

    def get_internal_type(self):
        return "TextField"

    def deconstruct(self):
        name, path, args, kwargs = super(EncryptedMixin, self).deconstruct()

        if "max_length" in kwargs:
            del kwargs["max_length"]

        return name, path, args, kwargs


class EncryptedCharField(EncryptedMixin, models.CharField):
    pass


class EncryptedPasswordField(EncryptedMixin, models.CharField):
    """Similar to EncryptedCharField but its default form widget is PasswordInput."""

    def formfield(self, **kwargs):
        kwargs["widget"] = PasswordInput
        return super().formfield(**kwargs)


class EncryptedEmailField(EncryptedMixin, models.EmailField):
    pass
