import os

import pytest
from googleapiclient.errors import Error as GoogleAPIClientError
from requests.exceptions import HTTPError

ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE = os.path.join(
    os.path.dirname(__file__), "mdm", "android_enterprise_service_account.json"
)
TINYMDM_ENV_VARS = ("TINYMDM_APIKEY_PUBLIC", "TINYMDM_APIKEY_SECRET", "TINYMDM_ACCOUNT_ID")
ANDROID_ENTERPRISE_ENV_VARS = (
    "ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE",
    "ANDROID_ENTERPRISE_ID",
)


@pytest.fixture(autouse=True)
def del_mdm_env_vars(monkeypatch, settings):
    """Delete environment variables for MDM API credentials, if they exist."""
    for var in TINYMDM_ENV_VARS + ANDROID_ENTERPRISE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
        settings.SECRETS.pop(var, None)


@pytest.fixture
def set_mdm_env_vars(monkeypatch):
    """Set environment variables for TinyMDM API credentials to fake values."""
    for var in TINYMDM_ENV_VARS:
        monkeypatch.setenv(var, "test")


@pytest.fixture
def mdm_api_error_class(organization):
    if organization.mdm == "Android Enterprise":
        return GoogleAPIClientError
    return HTTPError


@pytest.fixture
def mdm_api_error(request, mdm_api_error_class):
    if getattr(request, "param", True):
        return mdm_api_error_class("error")
