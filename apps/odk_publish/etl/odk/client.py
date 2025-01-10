from pathlib import Path

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

    def __init__(self, base_url: str, project_id: int | None = None):
        """Create an ODK Central-configured client without a config file."""
        # Create stub config file if it doesn't exist, so that pyodk doesn't complain
        config_path = Path("/tmp/.pyodk_config.toml")
        if not config_path.exists():
            config_path.write_text(CONFIG_TOML)
        # Create a session with the given authentication details and supply the
        # session to the super class, so it doesn't try and create one itself
        session = Session(
            base_url=base_url,
            api_version="v1",
            username=settings.ODK_CENTRAL_USERNAME,
            password=settings.ODK_CENTRAL_PASSWORD,
            cache_path=None,
        )
        super().__init__(config_path=config_path, session=session, project_id=project_id)
        # Update the stub config with the environment-provided authentication
        # details
        self.config: config.Config = config.objectify_config(
            {
                "central": {
                    "base_url": base_url,
                    "username": settings.ODK_CENTRAL_USERNAME,
                    "password": settings.ODK_CENTRAL_PASSWORD,
                }
            }
        )
        # Create a ODK Publish service for this client, which provides
        # additional functionality for interacting with ODK Central
        self.odk_publish: PublishService = PublishService(client=self)

    def __enter__(self) -> "ODKPublishClient":
        return self.open()
