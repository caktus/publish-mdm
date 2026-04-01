import pytest

from apps.infisical.api import InfisicalKMS


@pytest.fixture(autouse=True)
def disable_client_auth(mocker):
    # Never attempt to authenticate with ODK Central
    mocker.patch("pyodk._utils.session.Auth.login")


@pytest.fixture(autouse=True)
def disable_infisical_encryption(mocker):
    # Never attempt to encrypt/decrypt with Infisical
    def side_effect(key_name, value):
        # Return the value unchanged
        return value

    mocker.patch.object(InfisicalKMS, "encrypt", side_effect=side_effect)
    mocker.patch.object(InfisicalKMS, "decrypt", side_effect=side_effect)


@pytest.fixture
def force_tinymdm(settings):
    settings.ACTIVE_MDM = {"name": "TinyMDM", "class": "apps.mdm.mdms.TinyMDM"}


@pytest.fixture
def force_android_enterprise(settings):
    settings.ACTIVE_MDM = {
        "name": "Android Enterprise",
        "class": "apps.mdm.mdms.AndroidEnterprise",
    }
