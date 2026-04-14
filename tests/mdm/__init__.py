import json

import httplib2
import pytest
from googleapiclient.http import RequestMockBuilder

from tests.publish_mdm.factories import AndroidEnterpriseAccountFactory, OrganizationFactory


class TestAllMDMsNoAutouse:
    """Test methods in subclasses of this class will be run once for each MDM
    only if they use the all_mdms fixture.
    """

    @pytest.fixture
    def organization(self):
        return OrganizationFactory()

    @pytest.fixture(params=["TinyMDM", "Android Enterprise"])
    def all_mdms(self, request, settings, organization):
        if request.param == "TinyMDM":
            settings.ACTIVE_MDM = {"name": "TinyMDM", "class": "apps.mdm.mdms.TinyMDM"}
        elif request.param == "Android Enterprise":
            settings.ACTIVE_MDM = {
                "name": "Android Enterprise",
                "class": "apps.mdm.mdms.AndroidEnterprise",
            }
            AndroidEnterpriseAccountFactory(
                organization=organization, enterprise_name="enterprises/test"
            )


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

    @pytest.fixture
    def organization(self):
        return OrganizationFactory()

    @pytest.fixture(autouse=True)
    def force_android_enterprise(self, settings, organization):
        settings.ACTIVE_MDM = {
            "name": "Android Enterprise",
            "class": "apps.mdm.mdms.AndroidEnterprise",
        }
        AndroidEnterpriseAccountFactory(
            organization=organization, enterprise_name="enterprises/test"
        )

    def get_mock_request_builder(self, *responses, prefix="androidmanagement.enterprises."):
        """Creates a RequestMockBuilder that can be used to mock API responses
        in the Google API Client. Takes MockAPIResponse objects as args, where
        the `method_id` should be without the prefix.

        Args:
            *responses: MockAPIResponse objects describing each expected call.
            prefix: The method-ID prefix for the target API.  Defaults to
                ``'androidmanagement.enterprises.'`` for the Android Management
                API.  Use ``'pubsub.projects.'`` for the Cloud Pub/Sub API.
        """
        responses_dict = {}
        for response in responses:
            if response.content:
                response_content = json.dumps(response.content)
            else:
                response_content = ""
            if response.status_code:
                response_obj = httplib2.Response({"status": response.status_code})
            else:
                # None results in a 200 response
                response_obj = None
            value = [response_obj, response_content.encode()]
            if response.expected_request_body is not None:
                # Will raise an error if the actual request body does not match exactly
                value.append(response.expected_request_body)
            responses_dict[f"{prefix}{response.method_id}"] = value
        return RequestMockBuilder(responses_dict, check_unexpected=True)
