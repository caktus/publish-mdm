import os
from pathlib import Path

import structlog
from pydantic import BaseModel, SecretStr, field_validator
from pyodk._utils import config
from pyodk.client import Client, Session

from .publish import PublishService

logger = structlog.getLogger(__name__)

CONFIG_TOML = """
[central]
base_url = "http://localhost"
username = "username"
password = "password"
default_project_id = 999
"""


class CentralConfig(BaseModel):
    """Model to validate ODK Central server configuration."""

    base_url: str
    username: str
    password: SecretStr

    @field_validator("base_url")
    @classmethod
    def always_strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")


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
        server_config = self.get_config(base_url=base_url)
        session = Session(
            base_url=server_config.base_url,
            api_version="v1",
            username=server_config.username,
            password=server_config.password.get_secret_value(),
            cache_path=None,
        )
        super().__init__(config_path=str(config_path), session=session, project_id=project_id)
        # Update the stub config with the environment-provided authentication
        # details
        self.config: config.Config = config.objectify_config(
            {
                "central": {
                    "base_url": base_url,
                    "username": server_config.username,
                    "password": server_config.password.get_secret_value(),
                }
            }
        )
        # Create a ODK Publish service for this client, which provides
        # additional functionality for interacting with ODK Central
        self.odk_publish: PublishService = PublishService(client=self)
        logger.debug("Initialized ODK Publish client", project_id=project_id, base_url=base_url)

    def __enter__(self) -> "ODKPublishClient":
        return super().__enter__()  # type: ignore

    @classmethod
    def get_config(cls, base_url: str) -> CentralConfig:
        """Return the CentralConfig for the matching base URL."""
        available_configs = cls.get_configs()
        config = available_configs[base_url.rstrip("/")]
        logger.debug("Retrieved ODK Central config", config=config)
        return config

    @staticmethod
    def get_configs() -> dict[str, CentralConfig]:
        """
        Parse the ODK_CENTRAL_CREDENTIALS environment variable and return a dictionary
        of available server configurations.

        Example environment variable:
            export ODK_CENTRAL_CREDENTIALS="base_url=https://myserver.com;username=user1;password=pass1,base_url=https://otherserver.com;username=user2;password=pass2"

            Returns:
                {
                    "https://myserver.com": CentralConfig(base_url="https://myserver.com", username="user1", password=SecretStr('**********')
                    "https://otherserver.com": CentralConfig(base_url="https://otherserver.com", username="user2", password=SecretStr('**********')
                }
        """  # noqa
        servers = {}
        for server in os.getenv("ODK_CENTRAL_CREDENTIALS", "").split(","):
            server = server.split(";")
            server = {
                key: value for key, value in [item.split("=") for item in server if "=" in item]
            }
            if server:
                config = CentralConfig.model_validate(server)
                servers[config.base_url] = config
        logger.debug("Parsed ODK Central credentials", servers=list(servers.keys()))
        return servers
