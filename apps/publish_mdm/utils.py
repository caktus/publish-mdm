import os

from django.conf import settings


def get_secret(key):
    """Get a value either from the SECRETS setting (populated from a file) or
    from environment variables.
    """
    return settings.SECRETS.get(key, os.getenv(key))
