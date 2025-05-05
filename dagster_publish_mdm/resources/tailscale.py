from urllib.parse import urljoin

import dagster as dg
import requests
import logging
import time

from oauthlib.oauth2 import BackendApplicationClient
from requests.adapters import HTTPAdapter, Retry
from requests_oauthlib import OAuth2Session


logger = logging.getLogger(__name__)


class ClientCredentialsAutoTokenSession(OAuth2Session):
    """
    OAuth2Session wrapper to manage requesting and re-requesting access tokens
    automatically using client credentials.

    Refresh tokens are excluded from a Client Credentials Grant [1], so the
    requests_oauthlib built-in refresh functionality [2] does not support our
    use case.

    1. https://datatracker.ietf.org/doc/html/rfc6749#section-4.4.3
    2. https://requests-oauthlib.readthedocs.io/en/latest/oauth2_workflow.html#refreshing-tokens
    """

    def __init__(self, client_secret: str, token_url: str, **kwargs) -> None:
        # The client secret is used to fetch a new token, so save it here
        # for fetch_token() to use
        self.client_secret = client_secret
        # While token_url is not technically an auto_refresh_url, setting it
        # here will trigger OAuth2Session's expired tokens functionality
        # to use this URL to refresh the token
        kwargs["auto_refresh_url"] = token_url
        # The client's token is automatically updated, so use a no-op to prevent
        # raising the TokenUpdated exception
        kwargs["token_updater"] = lambda _: None
        # Configure this session's client as a backend application client
        client = BackendApplicationClient(client_id=kwargs.get("client_id"))
        super().__init__(
            client=client,
            # Set a dummy token to trigger the auto-refresh logic on the first
            # session request
            token={"access_token": "dummy", "expires_in": -1, "token_type": "Bearer"},
            **kwargs,
        )
        # Automatically retry requests that fail
        retries = Retry(
            total=10,
            backoff_factor=0.1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=frozenset(["GET"]),
        )
        self.mount("https://", HTTPAdapter(max_retries=retries))

    def fetch_token(self, **kwargs) -> None:
        """Fetch a new token using saved client credentials"""
        logger.debug("Fetching a new access token")
        super().fetch_token(
            client_id=self.client_id,
            client_secret=self.client_secret,
            token_url=self.auto_refresh_url,
            **kwargs,
        )

    def refresh_token(self, *args, **kwargs) -> None:
        """Override the refresh_token method to simply invoke fetch_token"""
        logger.debug("Refreshing access token")
        self.is_token_expired()
        self.fetch_token()

    def is_token_expired(self) -> bool:
        """Returns True if the current access token has expired"""
        expired = (not self.token) or self._client._expires_at < time.time()
        logger.debug(f"Token expired? {expired}")
        return expired


class TailscaleResource(dg.ConfigurableResource):
    """A Dagster resource for interacting with the Tailscale API."""

    base_url: str = "https://api.tailscale.com/api/v2/"
    # OAuth2 client ID and secret for Tailscale API
    client_id: str
    client_secret: str
    tailnet: str

    def client(self) -> requests.Session:
        """Return a requests session configured with the Tailscale API key."""
        return ClientCredentialsAutoTokenSession(
            client_id=self.client_id,
            client_secret=self.client_secret,
            token_url=self.url("oauth/token"),
        )

    def url(self, path: str) -> str:
        """Return a full URL for the Tailscale API."""
        return urljoin(self.base_url, path.lstrip("/"))

    def get(self, path: str, *args, **kwargs) -> dict:
        """Make a GET request to the Tailscale API."""
        response = self.client().get(url=self.url(path), *args, **kwargs)
        response.raise_for_status()
        return response.json()
