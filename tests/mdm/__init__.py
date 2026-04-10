import pytest

from tests.publish_mdm.factories import OrganizationFactory


class TestAllMDMsNoAutouse:
    """Test methods in subclasses of this class will be run once for each MDM
    only if they use the all_mdms fixture.
    """

    @pytest.fixture
    def organization(self):
        return OrganizationFactory()

    @pytest.fixture(params=["TinyMDM", "Android Enterprise"])
    def all_mdms(self, request, settings, organization):
        organization.mdm = request.param
        if request.param == "TinyMDM":
            organization.tinymdm_apikey_public = "test"
            organization.tinymdm_apikey_secret = "test"
            organization.tinymdm_account_id = "test"
        organization.save()


class TestAllMDMs(TestAllMDMsNoAutouse):
    """Test methods in subclasses of this class will automatically be run once
    for each MDM.
    """

    @pytest.fixture(autouse=True)
    def _all_mdms(self, all_mdms):
        pass


class TestTinyMDMOnly:
    """Test methods in subclasses of this class will always use TinyMDM as the
    active MDM. The organization fixture will have mdm="TinyMDM" (the default).
    If you also want to set fake API credentials for the MDM, add the
    set_mdm_env_vars fixture to test methods.
    """


class TestAndroidEnterpriseOnly:
    """Test methods in subclasses of this class will always use Android Enterprise
    as the active MDM. The organization fixture will have mdm="Android Enterprise".
    If you also want to set fake API credentials for the MDM, add the
    set_mdm_env_vars fixture to test methods.
    """

    @pytest.fixture(autouse=True)
    def force_android_enterprise(self, organization):
        organization.mdm = "Android Enterprise"
        organization.save()
