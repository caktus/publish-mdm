import io
import os

import segno
from django.conf import settings


def get_secret(key):
    """Get a value either from the SECRETS setting (populated from a file) or
    from environment variables.
    """
    return settings.SECRETS.get(key, os.getenv(key))


def create_qr_code(data):
    code = segno.make(data, micro=False)
    code_buffer = io.BytesIO()
    code.save(code_buffer, scale=4, kind="png")
    return code_buffer
