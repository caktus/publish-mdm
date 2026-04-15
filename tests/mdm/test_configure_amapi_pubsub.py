import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.mdm.mdms import AndroidEnterprise
from tests.publish_mdm.factories import AndroidEnterpriseAccountFactory, OrganizationFactory


@pytest.mark.django_db
class TestConfigureAmapiPubsubCommand:
    def call_command(self, *args, **kwargs):
        stdout = io.StringIO()
        call_command("configure_amapi_pubsub", *args, stdout=stdout, **kwargs)
        return stdout.getvalue()

    def test_raises_when_service_account_not_configured(self, del_amapi_service_account_file):
        """Raises CommandError when ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE is not set."""
        with pytest.raises(CommandError, match="ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE"):
            self.call_command()

    def test_calls_configure_pubsub_when_token_is_set(
        self, set_amapi_service_account_file, mocker, settings
    ):
        """configure_pubsub() is called when ANDROID_ENTERPRISE_PUBSUB_TOKEN is set."""
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = "secret"
        mock_configure = mocker.patch.object(AndroidEnterprise, "configure_pubsub")
        mocker.patch.object(AndroidEnterprise, "patch_enterprise_pubsub")

        self.call_command()

        mock_configure.assert_called_once_with(push_endpoint_domain=None)

    def test_push_endpoint_domain_forwarded_to_configure_pubsub(
        self, set_amapi_service_account_file, mocker, settings
    ):
        """--push-endpoint-domain is forwarded to configure_pubsub() when the token is set."""
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = "secret"
        mock_configure = mocker.patch.object(AndroidEnterprise, "configure_pubsub")
        mocker.patch.object(AndroidEnterprise, "patch_enterprise_pubsub")

        self.call_command("--push-endpoint-domain", "example.com")

        mock_configure.assert_called_once_with(push_endpoint_domain="example.com")

    def test_skips_configure_pubsub_when_token_not_set(
        self, set_amapi_service_account_file, mocker, settings
    ):
        """configure_pubsub() is not called when ANDROID_ENTERPRISE_PUBSUB_TOKEN is unset."""
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = None
        mock_configure = mocker.patch.object(AndroidEnterprise, "configure_pubsub")
        mocker.patch.object(AndroidEnterprise, "patch_enterprise_pubsub")

        output = self.call_command()

        mock_configure.assert_not_called()
        assert "ANDROID_ENTERPRISE_PUBSUB_TOKEN is not set" in output

    def test_patches_all_enrolled_organizations(
        self, set_amapi_service_account_file, mocker, settings
    ):
        """patch_enterprise_pubsub() is called once per enrolled organization."""
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = None
        mocker.patch.object(AndroidEnterprise, "configure_pubsub")
        mock_patch = mocker.patch.object(AndroidEnterprise, "patch_enterprise_pubsub")

        org1 = OrganizationFactory(mdm="Android Enterprise")
        AndroidEnterpriseAccountFactory(organization=org1, enterprise_name="enterprises/test1")
        org2 = OrganizationFactory(mdm="Android Enterprise")
        AndroidEnterpriseAccountFactory(organization=org2, enterprise_name="enterprises/test2")

        self.call_command()

        assert mock_patch.call_count == 2

    def test_skips_unenrolled_organizations(self, set_amapi_service_account_file, mocker, settings):
        """Organizations with an empty enterprise_name are not patched."""
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = None
        mocker.patch.object(AndroidEnterprise, "configure_pubsub")
        mock_patch = mocker.patch.object(AndroidEnterprise, "patch_enterprise_pubsub")

        enrolled = OrganizationFactory(mdm="Android Enterprise")
        AndroidEnterpriseAccountFactory(organization=enrolled, enterprise_name="enterprises/test")
        unenrolled = OrganizationFactory(mdm="Android Enterprise")
        AndroidEnterpriseAccountFactory(organization=unenrolled, enterprise_name="")

        self.call_command()

        mock_patch.assert_called_once()

    def test_no_enrolled_organizations(self, set_amapi_service_account_file, mocker, settings):
        """Outputs an informational message and skips patching when no enrolled orgs exist."""
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = None
        mocker.patch.object(AndroidEnterprise, "configure_pubsub")
        mock_patch = mocker.patch.object(AndroidEnterprise, "patch_enterprise_pubsub")

        output = self.call_command()

        mock_patch.assert_not_called()
        assert "No enrolled Android Enterprise organizations found" in output

    def test_output_lists_patched_organizations(
        self, set_amapi_service_account_file, mocker, settings
    ):
        """Output names the organizations that were patched and prints a final count."""
        settings.ANDROID_ENTERPRISE_PUBSUB_TOKEN = None
        mocker.patch.object(AndroidEnterprise, "configure_pubsub")
        mocker.patch.object(AndroidEnterprise, "patch_enterprise_pubsub")

        org = OrganizationFactory(mdm="Android Enterprise", name="Acme Corp")
        AndroidEnterpriseAccountFactory(organization=org, enterprise_name="enterprises/test")

        output = self.call_command()

        assert "Acme Corp" in output
        assert "1 organization(s) patched" in output
