from pathlib import Path

import structlog
from pyodk._endpoints.auth import AuthService
from pyodk._utils import config
from pyodk.client import Client, Session
from pyodk.errors import PyODKError

from .publish import PublishService

logger = structlog.getLogger(__name__)

CONFIG_TOML = """
[central]
base_url = "http://localhost"
username = "username"
password = "password"
default_project_id = 999
"""


class PublishMDMAuthService(AuthService):
    def verify_token(self, token: str) -> str:
        """
        Check with Central that a token is valid.

        We are overriding this method only to change the logging level of the
        'token verification request failed' message from ERROR to DEBUG, so that
        the message does not get logged in Sentry when Sentry is configured.

        :param token: The token to check.
        :return:
        """
        response = self.session.get(
            url="users/current",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        if response.status_code == 200:
            return token
        else:
            msg = (
                f"The token verification request failed."
                f" Status: {response.status_code}, content: {response.content}"
            )
            err = PyODKError(msg)
            logger.debug(err, exc_info=True)
            raise err


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
        # No retries for POST requests
        for prefix, adapter in session.adapters.items():
            if (
                adapter.max_retries.allowed_methods
                and "POST" in adapter.max_retries.allowed_methods
            ):
                # pyodk is still retrying POSTs; revert to default value for allowed_methods
                # https://github.com/getodk/pyodk/issues/101
                # https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html#urllib3.util.Retry
                adapter.max_retries.allowed_methods = frozenset(
                    {"DELETE", "GET", "HEAD", "OPTIONS", "PUT", "TRACE"}
                )
                logger.debug(
                    f"Updated the {prefix} adapter to disable retries for POST requests",
                    allowed_methods=adapter.max_retries.allowed_methods,
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
        # Set the auth service to a PublishMDMAuthService, which uses DEBUG level
        # instead of ERROR level for "token verification request failed" log messages
        self.session.auth.service = PublishMDMAuthService(session=session, cache_path=cache_path)
        logger.debug(
            "Initialized Publish MDM client",
            project_id=project_id,
            base_url=central_server.base_url,
        )

    def __enter__(self) -> "PublishMDMClient":
        return super().__enter__()  # type: ignore
