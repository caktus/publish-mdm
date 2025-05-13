from django.db import models

from .infisical import kms_api


class EncryptedMixin(object):
    # Based on https://gitlab.com/lansharkconsulting/django/django-encrypted-model-fields/-/blob/develop/encrypted_model_fields/fields.py#L64

    def to_python(self, value):
        if value is None:
            return value

        if isinstance(value, (bytes, str)):
            if isinstance(value, bytes):
                value = value.decode("utf-8")

            value = kms_api.decrypt(self.model.__name__.lower(), value)

        return super(EncryptedMixin, self).to_python(value)

    def get_prep_value(self, value):
        """This method gets called when saving a value in the database, and it in
        turn calls to_python(). We need to avoid calling EncryptedMixin.to_python()
        here as it would try to decrypt a value that has not yet been encrypted,
        causing Infisical to raise an APIError.
        """
        # Recreate CharField.get_prep_value()
        # https://github.com/django/django/blob/3176904/django/db/models/fields/__init__.py#L1297
        value = models.Field.get_prep_value(self, value)
        return models.CharField.to_python(self, value)

    def from_db_value(self, value, *args, **kwargs):
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


class EncryptedEmailField(EncryptedMixin, models.EmailField):
    pass
