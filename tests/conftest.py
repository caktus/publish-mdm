import pytest
from googleapiclient.errors import Error as GoogleAPIClientError
from requests.exceptions import HTTPError

from apps.publish_mdm.models import AndroidEnterpriseAccount
from tests.mdm import ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE, _configure_mdm


@pytest.fixture
def del_amapi_service_account_file(monkeypatch):
    monkeypatch.delenv("ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE", raising=False)


@pytest.fixture
def set_amapi_service_account_file(monkeypatch):
    monkeypatch.setenv(
        "ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE", ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE
    )


@pytest.fixture
def unconfigure_mdm(request, organization):
    """Unconfigure MDM API credentials for an organization."""
    if organization.mdm == "TinyMDM":
        organization.tinymdm_apikey_public = None
        organization.tinymdm_apikey_secret = None
        organization.tinymdm_account_id = None
        organization.save()
    elif organization.mdm == "Android Enterprise":
        AndroidEnterpriseAccount.objects.filter(organization=organization).delete()
        request.getfixturevalue("del_amapi_service_account_file")


@pytest.fixture
def configure_mdm(request, organization):
    """Configure MDM API credentials for an organization."""
    _configure_mdm(organization.mdm, organization)
    if organization.mdm == "Android Enterprise":
        request.getfixturevalue("set_amapi_service_account_file")


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
    _configure_mdm("TinyMDM", organization)


@pytest.fixture
def force_android_enterprise(organization, set_amapi_service_account_file):
    _configure_mdm("Android Enterprise", organization)
