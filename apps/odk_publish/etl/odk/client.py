import contextlib
from pathlib import Path
from typing import Generator, Self

from django.conf import settings
from pyodk._utils import config
from pyodk.client import Client, Session

from .publish import PublishService

CONFIG_TOML = """
[central]
base_url = "http://localhost"
username = "username"
password = "password"
default_project_id = 999
"""


class ODKPublishClient(Client):
    """Extended pyODK Client for interacting with ODK Central."""

    @classmethod
    @contextlib.contextmanager
    def new_client(cls, base_url: str) -> Generator[Self, None, Self]:
        """Context manager to create an ODK Central-configured client without a config file."""
        # Create stub config file if it doesn't exist, so that pyodk doesn't complain
        config_path = Path("/tmp/.pyodk_config.toml")
        if not config_path.exists():
            config_path.write_text(CONFIG_TOML)
        # Pass in authentication details ourselves to configure the client
        with cls(
            base_url=base_url,
            username=settings.ODK_CENTRAL_USERNAME,
            password=settings.ODK_CENTRAL_PASSWORD,
            config_path=config_path,
        ) as client:
            yield client

    def __init__(self, base_url: str, username: str, password: str, config_path: Path):
        # Create a session with the given authentication details and supply the
        # session to the super class, so it doesn't try and create one itself
        session = Session(
            base_url=base_url,
            api_version="v1",
            username=username,
            password=password,
            cache_path=None,
        )
        super().__init__(config_path=config_path, session=session)
        # Update the stub config with the environment-provided authentication
        # details
        self.config: config.Config = config.objectify_config(
            {
                "central": {
                    "base_url": base_url,
                    "username": username,
                    "password": password,
                }
            }
        )
        # Create a ODK Publish service for this client, which provides
        # additional functionality for interacting with ODK Central
        self.odk_publish: PublishService = PublishService(client=self)
