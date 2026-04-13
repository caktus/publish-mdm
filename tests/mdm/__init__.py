import os

import pytest
from django.utils.crypto import get_random_string

from apps.publish_mdm.models import AndroidEnterpriseAccount
from tests.publish_mdm.factories import AndroidEnterpriseAccountFactory, OrganizationFactory

ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE = os.path.join(
    os.path.dirname(__file__), "android_enterprise_service_account.json"
)


def _configure_mdm(mdm, organization):
    """Set the mdm field for an organization and set its MDM API credentials to fake values.
    For TinyMDM, the credentials are saved in tinymdm_* field.
    For Android Enterprise, an enrolled enterprise is created (a AndroidEnterpriseAccount
    with an enterprise_name). If needed, use the set_amapi_service_account_file fixture to set
    the ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE env var with a fake service account file.
    """
    organization.mdm = mdm
    if mdm == "TinyMDM":
        organization.tinymdm_apikey_public = "test"
        organization.tinymdm_apikey_secret = "test"
        organization.tinymdm_account_id = "test"
        organization.tinymdm_policy_id = get_random_string(12)
    elif mdm == "Android Enterprise":
        if not AndroidEnterpriseAccount.objects.filter(organization=organization).exists():
            AndroidEnterpriseAccountFactory(
                organization=organization, enterprise_name="enterprises/test"
            )
    organization.save()


class MDMTestBase:
    @pytest.fixture
    def organization(self):
        return OrganizationFactory()


class TestAllMDMsNoAutouse(MDMTestBase):
    """Test methods in subclasses of this class will be run once for each MDM
    only if they use the all_mdms fixture, with the MDM fully configured.
    """

    @pytest.fixture(params=["TinyMDM", "Android Enterprise"])
    def all_mdms(self, request, organization, set_amapi_service_account_file):
        _configure_mdm(request.param, organization)
        self.mdm = request.param


class TestAllMDMs(TestAllMDMsNoAutouse):
    """Test methods in subclasses of this class will automatically be run once
    for each MDM, and the MDM will be fully configured.
    """

    @pytest.fixture(autouse=True)
    def _all_mdms(self, all_mdms):
        pass


class TestTinyMDMOnly(MDMTestBase):
    """Test methods in subclasses of this class will always use TinyMDM as the
    active MDM and it will be fully configured (the organization fixture will
    have mdm="TinyMDM" and its tinymdm_* fields will be set with fake values).
    """

    @pytest.fixture(autouse=True)
    def force_tinymdm(self, force_tinymdm): ...


class TestAndroidEnterpriseOnly(MDMTestBase):
    """Test methods in subclasses of this class will always use Android Enterprise
    as the active MDM and it will be fully configured (the organization fixture
    will have mdm="Android Enterprise", an enrolled enterprise will be created,
    and the ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE env var will be set).
    """

    @pytest.fixture(autouse=True)
    def force_android_enterprise(self, force_android_enterprise): ...
