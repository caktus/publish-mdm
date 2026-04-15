import json
import os

import httplib2
import pytest
from django.utils.crypto import get_random_string
from googleapiclient.http import RequestMockBuilder

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
        organization.tinymdm_default_policy_id = get_random_string(12)
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
