import pytest

from apps.infisical.api import InfisicalKMS


@pytest.fixture(autouse=True)
def disable_infisical_encryption(mocker):
    # Never attempt to encrypt/decrypt with Infisical
    def side_effect(key_name, value):
        # Return the value unchanged
        return value

    mocker.patch.object(InfisicalKMS, "encrypt", side_effect=side_effect)
    mocker.patch.object(InfisicalKMS, "decrypt", side_effect=side_effect)
