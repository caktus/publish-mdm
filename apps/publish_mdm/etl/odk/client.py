from pathlib import Path

import structlog
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


class PublishMDMClient(Client):
    """Extended pyODK Client for interacting with ODK Central."""

    def __init__(self, central_server, project_id: int | None = None):
        """Create an ODK Central-configured client without a config file."""
        self.central_server = central_server
        # Create stub config file if it doesn't exist, so that pyodk doesn't complain
        config_path = Path(f"/tmp/.pyodk_config_{central_server.id}.toml")
        if not config_path.exists():
            config_path.write_text(CONFIG_TOML)
        # Create stub cache file if it doesn't exist, so that pyodk doesn't complain
        cache_path = Path(f"/tmp/.pyodk_cache_{central_server.id}.toml")
        new_cache_file = not cache_path.exists()
        if new_cache_file:
            cache_path.write_text('token = ""')
        # Create a session with the given authentication details and supply the
        # session to the super class, so it doesn't try and create one itself
        session = Session(
            base_url=central_server.base_url,
            api_version="v1",
            username=central_server.username,
            password=central_server.password,
            cache_path=str(cache_path),
        )
        super().__init__(config_path=str(config_path), session=session, project_id=project_id)
        # Update the stub config with the provided authentication details
        self.config: config.Config = config.objectify_config(
            {
                "central": {
                    "base_url": central_server.base_url,
                    "username": central_server.username,
                    "password": central_server.password,
                }
            }
        )
        # Create a Publish MDM service for this client, which provides
        # additional functionality for interacting with ODK Central
        self.publish_mdm: PublishService = PublishService(client=self)
        logger.debug(
            "Initialized Publish MDM client",
            project_id=project_id,
            base_url=central_server.base_url,
        )
        # If we created a stub cache file, set a valid token in the file to prevent
        # error messages later about the token being invalid
        if new_cache_file:
            logger.debug("Setting the token in the new cache file", cache_path=cache_path)
            try:
                token = session.auth.service.get_new_token(
                    session.auth.username, session.auth.password
                )
                config.write_cache(key="token", value=token, cache_path=cache_path)
            except Exception:
                # pyodk will create the new token anyway on the first API request,
                # just that it will log a message with ERROR level, which will end
                # up in Sentry if Sentry is configured
                logger.debug(
                    "Error setting the token in the new cache file",
                    cache_path=cache_path,
                    exc_info=True,
                )

    def __enter__(self) -> "PublishMDMClient":
        return super().__enter__()  # type: ignore
