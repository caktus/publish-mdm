import contextlib
from pathlib import Path
from pyodk.client import Client

from django.conf import settings

CONFIG_TOML = """
[central]
base_url = "{base_url}"
username = "{username}"
password = "{password}"
default_project_id = 999
"""


@contextlib.contextmanager
def odk_central_client(base_url: str):
    """Context manager for an ODK Central-configured client"""
    config_path = Path(".pyodk_config.toml")
    if not config_path.exists():
        config_toml = CONFIG_TOML.format(
            base_url=base_url,
            username=settings.ODK_CENTRAL_USERNAME,
            password=settings.ODK_CENTRAL_PASSWORD,
        )
        config_path.write_text(config_toml)
    with Client(config_path=config_path) as client:
        yield client
