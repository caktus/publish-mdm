import os

import pytest

from apps.publish_mdm.models import AndroidEnterpriseAccount
from tests.publish_mdm.factories import AndroidEnterpriseAccountFactory, OrganizationFactory

ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE = os.path.join(
    os.path.dirname(__file__), "android_enterprise_service_account.json"
)


def _set_mdm_env_vars(mdm, organization):
    organization.mdm = mdm
    if mdm == "TinyMDM":
        organization.tinymdm_apikey_public = "test"
        organization.tinymdm_apikey_secret = "test"
        organization.tinymdm_account_id = "test"
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
    only if they use the all_mdms fixture.
    """

    @pytest.fixture(params=["TinyMDM", "Android Enterprise"])
    def all_mdms(self, request, organization, set_amapi_service_account_file):
        _set_mdm_env_vars(request.param, organization)
        self.mdm = request.param


class TestAllMDMs(TestAllMDMsNoAutouse):
    """Test methods in subclasses of this class will automatically be run once
    for each MDM.
    """

    @pytest.fixture(autouse=True)
    def _all_mdms(self, all_mdms):
        pass


class TestTinyMDMOnly(MDMTestBase):
    """Test methods in subclasses of this class will always use TinyMDM as the
    active MDM. The organization fixture will have mdm="TinyMDM".
    If you also want to set fake API credentials for the MDM, add the
    set_mdm_env_vars fixture to test methods.
    """

    @pytest.fixture(autouse=True)
    def force_tinymdm(self, force_tinymdm): ...


class TestAndroidEnterpriseOnly(MDMTestBase):
    """Test methods in subclasses of this class will always use Android Enterprise
    as the active MDM. The organization fixture will have mdm="Android Enterprise".
    If you also want to set fake API credentials for the MDM, add the
    set_mdm_env_vars fixture to test methods.
    """

    @pytest.fixture(autouse=True)
    def force_android_enterprise(self, force_android_enterprise): ...
