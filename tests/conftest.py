import pytest
from googleapiclient.errors import Error as GoogleAPIClientError
from requests.exceptions import HTTPError

from apps.publish_mdm.models import AndroidEnterpriseAccount
from tests.mdm import ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE, _set_mdm_env_vars


@pytest.fixture
def del_amapi_service_account_file(monkeypatch):
    monkeypatch.delenv("ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE", raising=False)


@pytest.fixture
def set_amapi_service_account_file(monkeypatch):
    monkeypatch.setenv(
        "ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE", ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE
    )


@pytest.fixture
def del_mdm_env_vars(organization, del_amapi_service_account_file):
    """Delete environment variables for MDM API credentials, if they exist."""
    if organization.mdm == "TinyMDM":
        organization.tinymdm_apikey_public = None
        organization.tinymdm_apikey_secret = None
        organization.tinymdm_account_id = None
        organization.save()
    elif organization.mdm == "Android Enterprise":
        AndroidEnterpriseAccount.objects.filter(organization=organization).delete()


@pytest.fixture
def set_mdm_env_vars(organization, set_amapi_service_account_file):
    """Set environment variables for the currently active MDM's API credentials to fake values."""
    _set_mdm_env_vars(organization.mdm, organization)


@pytest.fixture
def mdm_api_error_class(organization):
    if organization.mdm == "Android Enterprise":
        return GoogleAPIClientError
    return HTTPError


@pytest.fixture
def mdm_api_error(request, mdm_api_error_class):
    if getattr(request, "param", True):
        return mdm_api_error_class("error")


@pytest.fixture
def force_tinymdm(organization):
    _set_mdm_env_vars("TinyMDM", organization)


@pytest.fixture
def force_android_enterprise(organization, set_amapi_service_account_file):
    _set_mdm_env_vars("Android Enterprise", organization)
