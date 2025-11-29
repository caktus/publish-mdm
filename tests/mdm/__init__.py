import pytest


class TestAllMDMsNoAutouse:
    """Test methods in subclasses of this class will be run once for each MDM
    only if they use the all_mdms fixture.
    """

    @pytest.fixture(params=["TinyMDM", "Android Enterprise"])
    def all_mdms(self, request, settings):
        if request.param == "TinyMDM":
            settings.ACTIVE_MDM = {"name": "TinyMDM", "class": "apps.mdm.mdms.TinyMDM"}
        elif request.param == "Android Enterprise":
            settings.ACTIVE_MDM = {
                "name": "Android Enterprise",
                "class": "apps.mdm.mdms.AndroidEnterprise",
            }


class TestAllMDMs(TestAllMDMsNoAutouse):
    """Test methods in subclasses of this class will automatically be run once
    for each MDM.
    """

    @pytest.fixture(autouse=True)
    def _all_mdms(self, all_mdms):
        pass


class TestTinyMDMOnly:
    """Test methods in subclasses of this class will always use TinyMDM as the
    active MDM, regardless of the ACTIVE_MDM_* vars in the current environment.
    If you also want to set fake API credentials for the MDM, add the set_mdm_env_vars
    fixture to test methods.
    """

    @pytest.fixture(autouse=True)
    def force_tinymdm(self, settings):
        settings.ACTIVE_MDM = {"name": "TinyMDM", "class": "apps.mdm.mdms.TinyMDM"}


class TestAndroidEnterpriseOnly:
    """Test methods in subclasses of this class will always use Android Enterprise
    as the active MDM, regardless of the ACTIVE_MDM_* vars in the current environment.
    If you also want to set fake API credentials for the MDM, add the set_mdm_env_vars
    fixture to test methods.
    """

    @pytest.fixture(autouse=True)
    def force_android_enterprise(self, settings):
        settings.ACTIVE_MDM = {
            "name": "Android Enterprise",
            "class": "apps.mdm.mdms.AndroidEnterprise",
        }
